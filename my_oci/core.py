# my_oci\core.py
import os
import subprocess
import typer
import re
import json
import yaml
import shlex
from pathlib import Path
from rich.console import Console
from rapidfuzz import process, fuzz
from jsonschema import validate, ValidationError

from . import constants

console = Console()

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
        else:
            return None
    return current_level

def find_schema_for_command(command_parts: list[str], templates_dir: Path) -> dict | None:
    command_base = [p for p in command_parts if not p.startswith('--')][:4]
    if not command_base:
        return None
    command_key = "_".join(command_base).replace(" ", "_")
    schema_path = templates_dir / f"{command_key}.yaml"
    if schema_path.is_file():
        with open(schema_path, 'r') as f:
            return yaml.safe_load(f)
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
                args[part] = None # A flag without a value
                i += 1
        else:
            i += 1
    return args

def load_json_from_value(value: str) -> any:
    if value.startswith('file://'):
        file_path = Path(value[7:]).expanduser()
        if not file_path.is_file():
            raise FileNotFoundError(f"The file specified in the command does not exist: {file_path}")
        with open(file_path, 'r') as f:
            return json.load(f)
    return json.loads(value)

def validate_command_with_schema(command_parts: list[str], templates_dir: Path, common_schemas: dict) -> tuple[bool | None, list[str]]:
    """
    Validates the command. Returns a tuple: (validation_success, modified_command_parts).
    """
    command_base = [p for p in command_parts if not p.startswith('--')][:4]
    schema = find_schema_for_command(command_base, templates_dir)
    if not schema:
        return None, command_parts

    console.print(f"✅ Found validation schema: [cyan]{schema['command']}[/cyan]")
    parsed_args = parse_cli_args(command_parts)
    modified_command_parts = list(command_parts) # Work on a copy

    for required in schema.get('required_args', []):
        if required not in parsed_args:
            console.print(f"[yellow]Warning:[/] Missing required argument: [bold]{required}[/bold]")
            
            # Create a search key from the flag (e.g., --compartment-id -> COMPARTMENT_ID)
            search_key = required.strip('-').replace('-', '_').upper()
            
            # Find candidate variables in the environment
            candidates = [v for v in os.environ if search_key in v]
            
            if candidates:
                if typer.confirm(f"  I found [cyan]{', '.join(candidates)}[/cyan] in your .env. Add [bold]{required}[/bold] using one of these?"):
                    # For simplicity, we'll use the first candidate found.
                    # A more advanced version could present a choice.
                    chosen_var = candidates[0]
                    console.print(f"  Injecting [bold]{required} '{os.environ[chosen_var]}'[/bold] into the command.")
                    modified_command_parts.extend([required, os.environ[chosen_var]])
                    # Re-parse args to acknowledge the addition for subsequent checks
                    parsed_args = parse_cli_args(modified_command_parts)
                    continue # Continue to the next required arg check
            
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
                console.print(f"[bold red]Validation Error in argument '{arg_name}':[/] Expected a value, but none was provided.")
                return False, modified_command_parts
            try:
                instance = load_json_from_value(value) if arg_schema.get('type') in ['object', 'array'] else value
                validate(instance=instance, schema=arg_schema)
            except ValidationError as e:
                console.print(f"[bold red]Validation Error in argument '{arg_name}':[/] {e.message}")
                if 'pattern' in arg_schema and arg_schema.get('description'): console.print(f"  [bold cyan]Hint:[/] {arg_schema['description']}")
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
                try: # Check if it's a JSON string first
                    json.loads(value_from_env)
                    resolved_parts.append(value_from_env)
                except json.JSONDecodeError: # Otherwise, treat as path or regular string
                    expanded_value = str(Path(value_from_env).expanduser())
                    resolved_parts.append(expanded_value)
            else:
                if ci_mode:
                    console.print(f"[bold red]Error:[/] Environment variable '{var_name}' not found in CI mode.")
                    return None
                console.print(f"[yellow]Warning:[/] Environment variable '[bold]{var_name}[/]' not found.")
                closest_match, score, _ = process.extractOne(var_name, available_vars.keys(), scorer=fuzz.ratio)
                if score > 70 and typer.confirm(f"Did you mean '[cyan]{closest_match}[/]'?"):
                    value_from_env = available_vars[closest_match]
                    resolved_parts.append(str(Path(value_from_env).expanduser()))
                    console.print(f"Using value for [cyan]{closest_match}[/].")
                else:
                    return None # Abort on user decline or no good match
        else:
            resolved_parts.append(part)
    return resolved_parts

def preflight_file_check(command_parts: list[str]) -> bool:
    for i, part in enumerate(command_parts):
        if part in constants.FILE_PATH_FLAGS:
            if i + 1 < len(command_parts):
                file_path_str = command_parts[i + 1]
                if not Path(file_path_str).is_file():
                    console.print(f"[bold red]Pre-flight Error:[/] The file specified for '{part}' does not exist: '[cyan]{file_path_str}[/]'")
                    return False
    return True

def redact_output(output: str) -> str:
    redacted_output = re.sub(constants.OCID_PATTERN, "[REDACTED_OCID]", output, flags=re.IGNORECASE)
    redacted_output = re.sub(constants.IP_PATTERN, "[REDACTED_IP]", redacted_output)
    return redacted_output

def execute_command(command: list[str]) -> tuple[int, str, str]:
    """
    Executes a command and returns its return code, stdout, and stderr.
    This function NO LONGER prints to the console.
    """
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        # In case of a catastrophic failure (e.g., command not found), return an error.
        return 1, "", str(e)

def analyze_failure_and_suggest_fix(stderr: str) -> tuple[str, str] | None:
    """Parses stderr for missing argument errors and suggests a fix from .env"""
    # This regex looks for common "missing argument" phrases from OCI CLI
    match = re.search(r"Missing option\(s\)\s+(--[a-zA-Z0-9-]+)", stderr)
    if not match:
        match = re.search(r"Missing required parameter\s+(--[a-zA-Z0-9-]+)", stderr)

    if match:
        missing_flag = match.group(1)
        search_key = missing_flag.strip('-').replace('-', '_').upper()
        
        for env_var in os.environ:
            if search_key in env_var:
                return missing_flag, env_var
    return None

# --- LEARNING LOGIC ---

def infer_schema_from_instance(instance: any) -> dict:
    if isinstance(instance, dict):
        return {'type': 'object', 'properties': {k: infer_schema_from_instance(v) for k, v in instance.items()}}
    elif isinstance(instance, list):
        return {'type': 'array', 'items': infer_schema_from_instance(instance[0]) if instance else {}}
    elif isinstance(instance, str): return {'type': 'string'}
    elif isinstance(instance, bool): return {'type': 'boolean'}
    elif isinstance(instance, int): return {'type': 'integer'}
    elif isinstance(instance, float): return {'type': 'number'}
    else: return {}

def learn_from_command(command: list[str], templates_dir: Path, common_schemas: dict):
    console.print("🎓 [bold]Learning Mode:[/bold] I will run this command to verify it succeeds.")
    
    resolved_command = resolve_variables(command, ci_mode=True)
    if resolved_command is None:
        console.print("[bold red]Error:[/] Variable resolution failed. Ensure all variables are in your .env file.")
        raise typer.Exit(1)

    result = subprocess.run(resolved_command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        console.print("[bold red]Error:[/] The provided command failed to execute. I can only learn from successful commands.")
        error_message = (result.stderr.strip() + "\n" + result.stdout.strip()).strip()
        console.print(redact_output(error_message))
        raise typer.Exit(1)

    console.print("[green]✅ Command execution was successful. Now, let's build the template.[/green]")
    
    command_base = [p for p in resolved_command if not p.startswith('--')][:4]
    command_key = "_".join(command_base)
    schema_path = templates_dir / f"{command_key}.yaml"
    schema = {'command': ' '.join(command_base), 'required_args': [], 'arg_schemas': {}}
    
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
            if resolve_schema_ref(ref_path, common_schemas) and typer.confirm(f"  Value looks like an OCID. Use common schema '[yellow]$ref: {ref_path}[/yellow]'?"):
                schema['arg_schemas'][flag] = {'$ref': ref_path}
                continue

        try:
            json_data = load_json_from_value(value)
            source = "file" if str(value).startswith('file://') else "inline JSON"
            if typer.confirm(f"  Value is valid {source}. Infer a validation schema from its structure?"):
                inferred = infer_schema_from_instance(json_data)
                schema['arg_schemas'][flag] = inferred
                console.print(f"  Added inferred [bold]{inferred['type']}[/bold] schema for [cyan]{flag}[/].")
        except (json.JSONDecodeError, FileNotFoundError):
            pass # Not JSON, just a regular argument
        except Exception as e:
            console.print(f"[yellow]Warning:[/] Could not parse value for '{flag}' to infer a JSON schema: {e}")

    # --- NEW LOGIC: Abort if no validation rules were created ---
    if not schema['required_args'] and not schema['arg_schemas']:
        console.print("\n[yellow]No validation rules were defined. Template creation aborted.[/yellow]")
        return

    with open(schema_path, 'w') as f:
        yaml.dump(schema, f, sort_keys=False, indent=2, default_flow_style=False)
    
    console.print(f"\n[bold green]✅ Success![/] New validation template saved to: [cyan]{schema_path}[/cyan]")