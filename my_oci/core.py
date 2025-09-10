# myoci/core.py
import os
import subprocess
import typer
import re
import json
import yaml
from pathlib import Path
from rich.console import Console
from jsonschema import validate, ValidationError

from . import constants

console = Console()

# --- KNOWLEDGE BASE: Best Practice Argument Suggestions ---
# This is user-managed knowledge, acceptable within the "Personal Architect" scope.
BEST_PRACTICE_ARGS = {
    "oci compute instance list": [
        {"arg": "--output", "description": "Specify output format (e.g., table, json)."},
        {"arg": "--all", "description": "Fetch all records."},
    ]
}

# --- SCHEMA & VALIDATION LOGIC ---
def load_common_schemas(common_schemas_path: Path) -> dict:
    """Safely loads and parses the common_schemas.yaml file."""
    if not common_schemas_path.is_file():
        return {}
    try:
        with open(common_schemas_path, 'r') as f:
            schemas = yaml.safe_load(f)
            console.print(f"✅ Loaded common schemas from [cyan]{common_schemas_path.name}[/cyan]")
            return schemas
    except yaml.YAMLError as e:
        console.print(f"[bold red]Error:[/] Failed to parse [cyan]{common_schemas_path.name}[/cyan]. It may be malformed.")
        console.print(f"[dim]{e}[/dim]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Error:[/] Could not read [cyan]{common_schemas_path.name}[/cyan].")
        console.print(f"[dim]{e}[/dim]")
        raise typer.Exit(1)

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
        try:
            with open(schema_path, 'r') as f: return yaml.safe_load(f)
        except (yaml.YAMLError, IOError) as e:
            console.print(f"[bold red]Error:[/] Failed to load or parse template [cyan]{schema_path.name}[/cyan].")
            console.print(f"[dim]{e}[/dim]")
            raise typer.Exit(1)
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
                args[part] = True # Treat flags without values as booleans
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
            if search_key in os.environ:
                prompt = f"  Found exact match [cyan]${search_key}[/cyan] in your environment. Add it to the command?"
                if typer.confirm(prompt, default=False):
                    console.print(f"  Injecting [bold]{required}[/bold] into the command.")
                    modified_command_parts.extend([required, os.environ[search_key]])
                    parsed_args = parse_cli_args(modified_command_parts) # Re-parse after modification
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
            if value is True and arg_schema.get('type') != 'boolean':
                console.print(f"[bold red]Validation Error:[/] Arg '{arg_name}' expects a value but received none.")
                return False, modified_command_parts
            try:
                instance = load_json_from_value(value) if arg_schema.get('type') in ['object', 'array'] else value
                validate(instance=instance, schema=arg_schema)
            except (ValidationError, Exception) as e:
                msg = e.message if isinstance(e, ValidationError) else str(e)
                console.print(f"[bold red]Validation Error in argument '{arg_name}':[/] {msg}")
                return False, modified_command_parts

    return True, modified_command_parts

# --- HELPER & EXECUTION LOGIC ---
def resolve_variables(command_parts: list[str]) -> list[str] | None:
    """Replaces $VARS with values from os.environ. Fails on miss."""
    resolved_parts = []
    for part in command_parts:
        clean_part = part.strip("'\"")
        if clean_part.startswith('$'):
            var_name = clean_part.strip('${}')
            if var_name in os.environ:
                value_from_env = os.environ[var_name]
                resolved_parts.append(str(Path(value_from_env).expanduser()))
            else:
                console.print(f"[bold red]Error:[/] Environment variable '[bold]{var_name}[/]' not found.")
                console.print("[dim]MyOCI does not guess variables. Please ensure it is set in your .env file or shell.[/dim]")
                return None
        else:
            resolved_parts.append(part)
    return resolved_parts

def preflight_file_check(command_parts: list[str]) -> bool:
    for i, part in enumerate(command_parts):
        if part in constants.FILE_PATH_FLAGS:
            if i + 1 < len(command_parts):
                file_path_str = command_parts[i + 1]
                # Resolve ~ character in paths
                expanded_path = Path(file_path_str).expanduser()
                if not expanded_path.is_file():
                    console.print(f"[bold red]Pre-flight Error:[/] File for '{part}' not found: '[cyan]{expanded_path}[/]'")
                    return False
    return True

def _partially_redact_ocid(match: re.Match) -> str:
    """
    Replacement function for re.sub to perform context-aware partial redaction.
    Turns "ocid1.tenancy.oc1..uniqueidentifierstring" into
    "ocid1.tenancy.oc1..uniq...ring".
    """
    ocid = match.group(0)
    parts = ocid.rsplit('.', 1)
    if len(parts) != 2:
        return "[REDACTED_OCID]" # Fallback for malformed OCIDs

    prefix, unique_id = parts
    if len(unique_id) > 8:
        # Show first 4 and last 4 characters of the unique part
        redacted_id = f"{unique_id[:4]}...{unique_id[-4:]}"
        return f"{prefix}.{redacted_id}"
    else:
        # If the unique part is too short, fully redact to be safe
        return f"{prefix}.[REDACTED]"


def redact_output(output: str) -> str:
    """
    Redacts sensitive information from a string.
    - OCIDs are partially redacted to preserve context for debugging.
    - IP addresses are fully redacted.
    """
    redacted_output = re.sub(constants.OCID_PATTERN, _partially_redact_ocid, output, flags=re.IGNORECASE)
    redacted_output = re.sub(constants.IP_PATTERN, "[REDACTED_IP]", redacted_output)
    return redacted_output

def execute_command(command: list[str]) -> tuple[int, str, str]:
    try:
        env = os.environ.copy()
        # This is critical for reliable output capture
        env['OCI_CLI_PAGER'] = 'cat'
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def analyze_failure_and_suggest_fix(stderr: str) -> tuple[str, str] | None:
    """Analyzes stderr for a 'Missing option' error and suggests a fix from env vars."""
    match = re.search(r"Missing option\(s\)\s+(--[a-zA-Z0-9-]+)", stderr)
    if match:
        missing_flag = match.group(1)
        # Convert flag like '--compartment-id' to 'COMPARTMENT_ID' for env var search
        search_key = missing_flag.strip('-').replace('-', '_').upper()
        if search_key in os.environ:
            return missing_flag, search_key
    return None

# --- LEARNING & TEMPLATE MANAGEMENT LOGIC ---
def infer_schema_from_instance(instance: any) -> dict:
    if isinstance(instance, dict): return {'type': 'object', 'properties': {k: infer_schema_from_instance(v) for k, v in instance.items()}}
    elif isinstance(instance, list): return {'type': 'array', 'items': infer_schema_from_instance(instance[0]) if instance else {}}
    elif isinstance(instance, str): return {'type': 'string'}
    elif isinstance(instance, bool): return {'type': 'boolean'}
    elif isinstance(instance, int): return {'type': 'integer'}
    elif isinstance(instance, float): return {'type': 'number'}
    else: return {}

def learn_from_command(command: list[str], templates_dir: Path, common_schemas: dict):
    console.print("🎓 [bold]Learning Mode:[/bold] Verifying command success before creating template.")
    resolved_command = resolve_variables(command)
    if resolved_command is None:
        console.print("[bold red]Error:[/] Variable resolution failed."); raise typer.Exit(1)

    return_code, stdout, stderr = execute_command(resolved_command)
    if return_code != 0:
        console.print("[bold red]Error:[/] The provided command failed. I can only learn from successful commands.")
        console.print(redact_output(stderr or stdout))
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
        if value is True: continue # Skip flags without values

        if str(value).startswith("ocid1."):
            ocid_type = str(value).split('.')[1]
            ref_path = f"common_oci_args.{ocid_type}_id"
            if resolve_schema_ref(ref_path, common_schemas) and typer.confirm(f"  Use common schema '[yellow]$ref: {ref_path}[/yellow]'?", default=True):
                schema['arg_schemas'][flag] = {'$ref': ref_path}
                continue
        try:
            json_data = load_json_from_value(str(value))
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

def list_templates(templates_dir: Path) -> list[Path]:
    """Lists all user-defined template files."""
    return [p for p in templates_dir.glob("*.yaml") if p.name != constants.COMMON_SCHEMAS_FILENAME]

def get_template_path(command_name: str, templates_dir: Path) -> Path:
    """Constructs the expected path for a given command name."""
    return templates_dir / f"{command_name.replace(' ', '_')}.yaml"