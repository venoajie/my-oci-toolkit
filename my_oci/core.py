# myoci/core.py
import os
import subprocess
import typer
import re
import json
import yaml
from pathlib import Path
from rich.console import Console
from rapidfuzz import process, fuzz
from jsonschema import validate, ValidationError

from . import constants

console = Console()

# --- KNOWLEDGE BASE: Best Practice Argument Suggestions ---
BEST_PRACTICE_ARGS = {
    "oci compute instance list": [
        {"arg": "--output", "description": "Specify output format (e.g., table, json)."},
        {"arg": "--all", "description": "Fetch all records."},
    ]
}

# --- KNOWLEDGE BASE: Intelligent Broadening Suggestions ---
BROADENING_SUGGESTIONS = {
    "oci compute instance list": {
        "narrow_arg": "--compartment-id",
        "broad_env_var": "OCI_TENANCY_ID",
        "narrow_resource_name": "instances in this compartment",
        "broad_resource_name": "the entire tenancy"
    }
}

# --- SCHEMA & VALIDATION LOGIC ---
def load_common_schemas(common_schemas_path: Path) -> dict:
    if common_schemas_path.is_file():
        with open(common_schemas_path, 'r') as f:
            schemas = yaml.safe_load(f)
            console.print(f"✅ Loaded common schemas from [cyan]{common_schemas_path.name}[/cyan]")
            return schemas
    return {}

def resolve_schema_ref(ref_path: str, common_schemas: dict) -> dict | None:
    keys = ref_path.split('.')
    current_level = common_schemas
    for key in keys:
        if isinstance(current_level, dict) and key in current_level:
            current_level = current_level[key]
        else: return None
    return current_level

def find_schema_for_command(command_parts: list[str], templates_dir: Path) -> dict | None:
    command_base = [p for p in command_parts if not p.startswith('--')][:4]
    if not command_base: return None
    command_key = "_".join(command_base).replace(" ", "_")
    schema_path = templates_dir / f"{command_key}.yaml"
    if schema_path.is_file():
        with open(schema_path, 'r') as f: return yaml.safe_load(f)
    return None

def parse_cli_args(command_parts: list[str]) -> dict:
    args = {}
    i = 0
    while i < len(command_parts):
        part = command_parts[i]
        if part.startswith('--'):
            if i + 1 < len(command_parts) and not command_parts[i+1].startswith('--'):
                args[part] = command_parts[i+1]
                i += 2
            else:
                args[part] = None
                i += 1
        else: i += 1
    return args

def load_json_from_value(value: str) -> any:
    if value.startswith('file://'):
        file_path = Path(value[7:]).expanduser()
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        with open(file_path, 'r') as f: return json.load(f)
    return json.loads(value)

def validate_command_with_schema(command_parts: list[str], templates_dir: Path, common_schemas: dict) -> tuple[bool | None, list[str]]:
    command_base = [p for p in command_parts if not p.startswith('--')][:4]
    schema = find_schema_for_command(command_base, templates_dir)
    if not schema: return None, command_parts
    console.print(f"✅ Found validation schema: [cyan]{schema['command']}[/cyan]")
    parsed_args = parse_cli_args(command_parts)
    modified_command_parts = list(command_parts)
    for required in schema.get('required_args', []):
        if required not in parsed_args:
            console.print(f"[yellow]Warning:[/] Missing required argument: [bold]{required}[/bold]")
            search_key = required.strip('-').replace('-', '_').upper()
            candidates = [v for v in os.environ if search_key in v]
            if candidates and typer.confirm(f"  I found [cyan]{', '.join(candidates)}[/cyan] in your .env. Add [bold]{required}[/bold] using one of these?", default=False):
                chosen_var = candidates[0]
                console.print(f"  Injecting [bold]{required}[/bold] into the command.")
                modified_command_parts.extend([required, os.environ[chosen_var]])
                parsed_args = parse_cli_args(modified_command_parts)
                continue
            console.print(f"[bold red]Validation Error:[/] Missing required argument: {required}")
            return False, modified_command_parts
    for arg_name, arg_schema in schema.get('arg_schemas', {}).items():
        if arg_name in parsed_args:
            value = parsed_args[arg_name]
            if '$ref' in arg_schema:
                resolved_schema = resolve_schema_ref(arg_schema['$ref'], common_schemas)
                if not resolved_schema: continue
                arg_schema = resolved_schema
            if value is None and arg_schema.get('type') != 'boolean':
                console.print(f"[bold red]Validation Error:[/] Arg '{arg_name}' expects a value.")
                return False, modified_command_parts
            try:
                instance = load_json_from_value(value) if arg_schema.get('type') in ['object', 'array'] else value
                validate(instance=instance, schema=arg_schema)
            except ValidationError as e:
                console.print(f"[bold red]Validation Error in argument '{arg_name}':[/] {e.message}")
                return False, modified_command_parts
            except Exception as e:
                console.print(f"[bold red]Validation Error in argument '{arg_name}':[/] {e}")
                return False, modified_command_parts
    console.print("[green]✅ Command passed all structural and format validation checks.[/green]")
    return True, modified_command_parts

# --- HELPER & EXECUTION LOGIC ---
def resolve_variables(command_parts: list[str], ci_mode: bool) -> list[str] | None:
    resolved_parts = []
    available_vars = {**os.environ}
    for part in command_parts:
        clean_part = part.strip("'\"")
        if clean_part.startswith('$'):
            var_name = clean_part.strip('${}')
            if var_name in available_vars:
                value_from_env = available_vars[var_name]
                resolved_parts.append(str(Path(value_from_env).expanduser()))
            else:
                if ci_mode:
                    console.print(f"[bold red]Error:[/] Env var '{var_name}' not found in CI mode.")
                    return None
                console.print(f"[yellow]Warning:[/] Env var '[bold]{var_name}[/]' not found.")
                closest_match, score, _ = process.extractOne(var_name, available_vars.keys(), scorer=fuzz.ratio)
                if score > 70 and typer.confirm(f"Did you mean '[cyan]{closest_match}[/]'?", default=False):
                    value_from_env = available_vars[closest_match]
                    resolved_parts.append(str(Path(value_from_env).expanduser()))
                    console.print(f"Using value for [cyan]{closest_match}[/].")
                else: return None
        else: resolved_parts.append(part)
    return resolved_parts

def preflight_file_check(command_parts: list[str]) -> bool:
    for i, part in enumerate(command_parts):
        if part in constants.FILE_PATH_FLAGS:
            if i + 1 < len(command_parts):
                file_path_str = command_parts[i + 1]
                if not Path(file_path_str).is_file():
                    console.print(f"[bold red]Pre-flight Error:[/] File for '{part}' not found: '[cyan]{file_path_str}[/]'")
                    return False
    return True

def redact_output(output: str) -> str:
    redacted_output = re.sub(constants.OCID_PATTERN, "[REDACTED_OCID]", output, flags=re.IGNORECASE)
    redacted_output = re.sub(constants.IP_PATTERN, "[REDACTED_IP]", redacted_output)
    return redacted_output

def execute_command(command: list[str]) -> tuple[int, str, str]:
    try:
        env = os.environ.copy()
        env['OCI_CLI_PAGER'] = 'cat'
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def analyze_failure_and_suggest_fix(stderr: str) -> tuple[str, str] | None:
    match = re.search(r"Missing option\(s\)\s+(--[a-zA-Z0-9-]+)", stderr)
    if match:
        missing_flag = match.group(1)
        search_key = missing_flag.strip('-').replace('-', '_').upper()
        for env_var in os.environ:
            if search_key in env_var:
                return missing_flag, env_var
    return None

def find_id_argument_in_command(command_parts: list[str]) -> str | None:
    """Finds the first argument in a command that looks like an ID flag."""
    for part in command_parts:
        if part.startswith('--') and part.endswith('-id'):
            return part
    return None

# --- LEARNING LOGIC ---
def infer_schema_from_instance(instance: any) -> dict:
    if isinstance(instance, dict): return {'type': 'object', 'properties': {k: infer_schema_from_instance(v) for k, v in instance.items()}}
    elif isinstance(instance, list): return {'type': 'array', 'items': infer_schema_from_instance(instance[0]) if instance else {}}
    elif isinstance(instance, str): return {'type': 'string'}
    elif isinstance(instance, bool): return {'type': 'boolean'}
    elif isinstance(instance, int): return {'type': 'integer'}
    elif isinstance(instance, float): return {'type': 'number'}
    else: return {}

def learn_from_command(command: list[str], templates_dir: Path, common_schemas: dict):
    console.print("🎓 [bold]Learning Mode:[/bold] I will run this command to verify it succeeds.")
    resolved_command = resolve_variables(command, ci_mode=True)
    if resolved_command is None:
        console.print("[bold red]Error:[/] Variable resolution failed."); raise typer.Exit(1)
    result = subprocess.run(resolved_command, capture_output=True, text=True, check=False, env={'OCI_CLI_PAGER': 'cat'})
    if result.returncode != 0:
        console.print("[bold red]Error:[/] The provided command failed. I can only learn from successful commands.")
        console.print(redact_output(result.stderr or result.stdout))
        raise typer.Exit(1)
    console.print("[green]✅ Command execution was successful. Now, let's build the template.[/green]")
    command_base_list = [p for p in resolved_command if not p.startswith('--')][:4]
    command_base_str = ' '.join(command_base_list)
    command_key = "_".join(command_base_list)
    schema_path = templates_dir / f"{command_key}.yaml"
    schema = {'command': command_base_str, 'required_args': [], 'arg_schemas': {}}
    parsed_args = parse_cli_args(resolved_command)
    console.print("\n[bold yellow]--- Interactive Schema Builder ---[/bold yellow]")
    for flag, value in parsed_args.items():
        console.print(f"\nProcessing flag: [cyan]{flag}[/cyan]")
        if typer.confirm(f"  Should this be a [bold]required[/bold] argument?", default=False):
            schema['required_args'].append(flag)
        if not value: continue
        if value.startswith("ocid1."):
            ocid_type = value.split('.')[1]
            ref_path = f"common_oci_args.{ocid_type}_id"
            if resolve_schema_ref(ref_path, common_schemas) and typer.confirm(f"  Use common schema '[yellow]$ref: {ref_path}[/yellow]'?", default=True):
                schema['arg_schemas'][flag] = {'$ref': ref_path}
                continue
        try:
            json_data = load_json_from_value(value)
            source = "file" if str(value).startswith('file://') else "inline JSON"
            if typer.confirm(f"  Value is valid {source}. Infer a validation schema?", default=False):
                inferred = infer_schema_from_instance(json_data)
                schema['arg_schemas'][flag] = inferred
        except Exception: pass
    if command_base_str in BEST_PRACTICE_ARGS:
        console.print("\n[bold yellow]--- Best Practice Suggestions ---[/bold yellow]")
        for item in BEST_PRACTICE_ARGS[command_base_str]:
            flag = item['arg']
            if flag not in schema['required_args'] and typer.confirm(f"💡 {item['description']}\n   Add '[cyan]{flag}[/cyan]' as a required argument?", default=False):
                schema['required_args'].append(flag)
    if not schema['required_args'] and not schema['arg_schemas']:
        console.print("\n[yellow]No validation rules were defined. Template creation aborted.[/yellow]"); return
    with open(schema_path, 'w') as f:
        yaml.dump(schema, f, sort_keys=False, indent=2, default_flow_style=False)
    console.print(f"\n[bold green]✅ Success![/] New validation template saved to: [cyan]{schema_path}[/cyan]")