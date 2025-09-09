import os
import sys
import subprocess
import typer
import re
import json
import yaml
import shlex
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rapidfuzz import process, fuzz
from jsonschema import validate, ValidationError

# --- SETUP & CONFIGURATION ---
console = Console()
try:
    SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    SCRIPT_DIR = Path.cwd()

DOTENV_PATH = SCRIPT_DIR / ".env"
TEMPLATES_DIR = SCRIPT_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)
load_dotenv(dotenv_path=DOTENV_PATH)

FILE_PATH_FLAGS = ["--ssh-authorized-keys-file", "--file", "--from-json", "--actions"]

COMMON_SCHEMAS_PATH = TEMPLATES_DIR / "common_schemas.yaml"
COMMON_SCHEMAS = {}
if COMMON_SCHEMAS_PATH.is_file():
    with open(COMMON_SCHEMAS_PATH, 'r') as f:
        COMMON_SCHEMAS = yaml.safe_load(f)
        console.print(f"✅ Loaded common schemas from [cyan]{COMMON_SCHEMAS_PATH.name}[/cyan]")

# --- CORE VALIDATION LOGIC ---

def resolve_schema_ref(ref_path: str) -> dict | None:
    keys = ref_path.split('.')
    current_level = COMMON_SCHEMAS
    for key in keys:
        if isinstance(current_level, dict) and key in current_level:
            current_level = current_level[key]
        else:
            return None
    return current_level

def find_schema_for_command(command_parts: list[str]) -> dict | None:
    command_base = [p for p in command_parts if not p.startswith('--')][:4]
    if not command_base:
        return None
    command_key = "_".join(command_base).replace(" ", "_")
    schema_path = TEMPLATES_DIR / f"{command_key}.yaml"
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
                args[part] = None
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
    else:
        return json.loads(value)

# --- MODIFIED: This function now returns True, False, or None ---
def validate_command_with_schema(command_parts: list[str]) -> bool | None:
    """The main validation engine. Checks a command against its schema."""
    command_base = [p for p in command_parts if not p.startswith('--')][:4]
    schema = find_schema_for_command(command_base)
    if not schema:
        console.print("[yellow]Info: No validation schema found for this command. Proceeding without deep validation.[/yellow]")
        return None # <-- Return None for skipped validation

    console.print(f"✅ Found validation schema: [cyan]{schema['command']}[/cyan]")
    parsed_args = parse_cli_args(command_parts)

    for required in schema.get('required_args', []):
        if required not in parsed_args:
            console.print(f"[bold red]Validation Error:[/] Missing required argument: {required}")
            return False

    for arg_name, arg_schema in schema.get('arg_schemas', {}).items():
        if arg_name in parsed_args:
            value = parsed_args[arg_name]
            
            if '$ref' in arg_schema:
                resolved_schema = resolve_schema_ref(arg_schema['$ref'])
                if not resolved_schema:
                    console.print(f"[yellow]Warning: Could not resolve schema reference '{arg_schema['$ref']}' for '{arg_name}'. Skipping validation.[/yellow]")
                    continue
                arg_schema = resolved_schema

            if value is None and arg_schema.get('type') != 'boolean':
                console.print(f"[bold red]Validation Error in argument '{arg_name}':[/] Expected a value, but none was provided.")
                return False

            try:
                if arg_schema.get('type') in ['object', 'array']:
                    instance = load_json_from_value(value)
                    validate(instance=instance, schema=arg_schema)
                else:
                    instance = value
                    validate(instance=instance, schema=arg_schema)
            except ValidationError as e:
                if 'pattern' in arg_schema and 'does not match' in e.message:
                    console.print(f"[bold red]Validation Error in argument '{arg_name}':[/] Value does not match the required format.")
                    if arg_schema.get('description'):
                        console.print(f"  [bold cyan]Hint:[/] {arg_schema['description']}")
                else:
                    console.print(f"[bold red]Validation Error in argument '{arg_name}':[/] {e.message}")
                return False
            except Exception as e:
                console.print(f"[bold red]Validation Error in argument '{arg_name}':[/] {e}")
                return False
    
    console.print("[green]✅ Command passed all structural and format validation checks.[/green]")
    return True

# --- HELPER FUNCTIONS ---
def resolve_variables(command_parts: list[str], ci_mode: bool) -> list[str] | None:
    """Resolves $VAR, handles potential quotes, and expands tilde (~) in paths."""
    resolved_parts = []
    available_vars = {**os.environ}
    
    for part in command_parts:
        clean_part = part.strip("'\"") 
        
        if clean_part.startswith('$'):
            var_name = clean_part.strip('${}')
            if var_name in available_vars:
                value_from_env = available_vars[var_name]
                expanded_value = str(Path(value_from_env).expanduser())
                resolved_parts.append(expanded_value)
            else:
                if ci_mode:
                    console.print(f"[bold red]Error:[/] Environment variable '{var_name}' not found in CI mode.")
                    return None
                else:
                    console.print(f"[yellow]Warning:[/] Environment variable '[bold]{var_name}[/]' not found.")
                    closest_match, score = process.extractOne(var_name, available_vars.keys(), scorer=fuzz.ratio)
                    if score > 70 and typer.confirm(f"Did you mean '[cyan]{closest_match}[/]'?"):
                        value_from_env = available_vars[closest_match]
                        expanded_value = str(Path(value_from_env).expanduser())
                        resolved_parts.append(expanded_value)
                        console.print(f"Using value for [cyan]{closest_match}[/].")
                    else:
                        resolved_parts.append("")
        else:
            resolved_parts.append(part)
    return resolved_parts

def preflight_file_check(command_parts: list[str]) -> bool:
    for i, part in enumerate(command_parts):
        if part in FILE_PATH_FLAGS:
            if i + 1 < len(command_parts):
                file_path_str = command_parts[i + 1]
                if not file_path_str or file_path_str.isspace():
                    console.print(f"[bold red]Pre-flight Error:[/] Missing value for file path argument '{part}'.")
                    return False
                expanded_path = Path(file_path_str).expanduser()
                if not expanded_path.is_file():
                    console.print(f"[bold red]Pre-flight Error:[/] The file specified for '{part}' does not exist at the resolved path: '[cyan]{expanded_path}[/]'")
                    return False
    return True

def redact_output(output: str) -> str:
    ocid_pattern = r"ocid1\.[a-z0-9\.]+\.[a-z0-9]+\.[a-z0-9]+\.[a-z0-9]+\.[a-f0-9]{30,}"
    ip_pattern = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
    redacted_output = re.sub(ocid_pattern, "[REDACTED_OCID]", output, flags=re.IGNORECASE)
    redacted_output = re.sub(ip_pattern, "[REDACTED_IP]", redacted_output)
    return redacted_output

# --- CLI APPLICATION ---
app = typer.Typer(
    help="MyOCI: Your personal architect for the OCI CLI."
)

@app.command("run")
def run_command(oci_command: list[str] = typer.Argument(..., help="The raw OCI command and its arguments to be executed.", metavar="OCI_COMMAND_STRING..."), ci: bool = typer.Option(False, "--ci", help="Enable non-interactive (CI) mode. Fails on ambiguity."), redact: bool = typer.Option(True, "--redact/--no-redact", help="Toggle PII redaction on output.")):
    raw_command_parts = oci_command
    console.rule("[bold cyan]MyOCI Validator Session Started[/]", style="cyan")
    console.print("[1/4] 🔍 [bold]Resolving environment variables...[/bold]")
    resolved_command = resolve_variables(raw_command_parts, ci)
    if resolved_command is None:
        console.rule("[bold red]Session Aborted due to variable resolution failure.[/]", style="red")
        raise typer.Exit(1)
    console.print("[green]✅ Variables resolved.[/green]\n")
    console.print("[2/4] 📄 [bold]Running pre-flight file path check...[/bold]")
    if not preflight_file_check(resolved_command):
        console.rule("[bold red]Session Aborted due to missing file.[/]", style="red")
        raise typer.Exit(1)
    console.print("[green]✅ File paths are valid.[/green]\n")
    
    # --- MODIFIED: Smart validation flow ---
    console.print("[3/4] 📝 [bold]Validating command against schema...[/bold]")
    validation_result = validate_command_with_schema(resolved_command)
    if validation_result is False: # Explicitly check for failure
        console.rule("[bold red]Session Aborted due to validation failure.[/]", style="red")
        raise typer.Exit(1)
    if validation_result is True: # Only print success if it actually passed
        console.print("[green]✅ Validation successful.[/green]\n")
    else: # This handles the 'None' case
        console.print("") # Just add a newline for spacing

    console.print("[4/4] ▶️  [bold]Executing command...[/bold]")
    try:
        result = subprocess.run(resolved_command, capture_output=True, text=True, check=False)
        stdout_output = result.stdout
        stderr_output = result.stderr
        
        # Redact before printing anything
        if redact:
            stdout_output = redact_output(stdout_output)
            stderr_output = redact_output(stderr_output)
            
        if result.returncode == 0:
            console.print("[bold green]✅ Command Succeeded![/]")
            if stdout_output:
                print(stdout_output)
        else:
            console.print("[bold red]❌ Command Failed![/]")
            human_readable_command = shlex.join(resolved_command)
            # --- MODIFIED: Redact the debug command string ---
            if redact:
                human_readable_command = redact_output(human_readable_command)
            console.print(f"[bold yellow]🔎 Final command executed:[/bold yellow]\n[cyan]{human_readable_command}[/cyan]\n")
            
            error_message = (stderr_output.strip() + "\n" + stdout_output.strip()).strip()
            if error_message:
                console.print(error_message)
            else:
                console.print("[red]No error output from OCI CLI.[/red]")
    except FileNotFoundError:
        console.print("[bold red]Error:[/] 'oci' command not found. Is the OCI CLI installed in your PATH?")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred during command execution:[/]\n{e}")
        raise typer.Exit(1)
    
    console.rule("[bold cyan]Validator Session Ended[/]", style="cyan")
    if result.returncode != 0:
        raise typer.Exit(result.returncode)

# ... (learn command is unchanged) ...
@app.command("learn")
def learn_command(oci_command: list[str] = typer.Argument(..., help="A successful OCI command to learn from.", metavar="OCI_COMMAND_STRING...")):
    command_to_learn = oci_command
    # ... (rest of the learn function is the same) ...
    console.print("🎓 [bold]Learning Mode:[/bold] I will run this command to verify it succeeds.")
    resolved_command_for_learn = resolve_variables(command_to_learn, ci_mode=False)
    if resolved_command_for_learn is None:
        console.print("[bold red]Error:[/] Variable resolution failed for the command to learn. Aborting.")
        raise typer.Exit(1)
    result = subprocess.run(resolved_command_for_learn, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        console.print("[bold red]Error:[/] The provided command failed to execute. I can only learn from successful commands.")
        error_message = (result.stderr.strip() + "\n" + result.stdout.strip()).strip()
        console.print(error_message)
        raise typer.Exit(1)
    console.print("[green]✅ Command execution was successful. Now, let's build the template.[/green]")
    command_base = [p for p in resolved_command_for_learn if not p.startswith('--')][:4]
    if not command_base:
        console.print("[bold red]Error:[/] Could not determine base command for learning.")
        raise typer.Exit(1)
    command_key = "_".join(command_base).replace(" ", "_")
    schema_path = TEMPLATES_DIR / f"{command_key}.yaml"
    schema = {'command': ' '.join(command_base), 'required_args': [], 'arg_schemas': {}}
    parsed_args = parse_cli_args(resolved_command_for_learn)
    console.print("\n[bold yellow]--- Interactive Schema Builder ---[/bold yellow]")
    console.print("I will go through the arguments of your successful command.")
    for flag, value in parsed_args.items():
        console.print(f"\nProcessing flag: [cyan]{flag}[/]")
        if typer.confirm(f"Should '[cyan]{flag}[/]' be a [bold]required[/bold] argument for this command?"):
            schema['required_args'].append(flag)
        if value and (value.strip().startswith('{') or value.strip().startswith('[') or value.startswith('file://')):
            if typer.confirm(f"The value for '[cyan]{flag}[/]' looks like JSON/file. Should I create a validation schema for its structure?"):
                try:
                    json_data = load_json_from_value(value)
                    if isinstance(json_data, dict):
                        schema['arg_schemas'][flag] = {'type': 'object'}
                    elif isinstance(json_data, list):
                        schema['arg_schemas'][flag] = {'type': 'array'}
                    else: continue
                    console.print(f"Added a basic [bold]{schema['arg_schemas'][flag]['type']}[/bold] schema for [cyan]{flag}[/].")
                except Exception as e:
                    console.print(f"[bold red]Error:[/] Could not parse value for '{flag}' to infer schema: {e}")
    with open(schema_path, 'w') as f:
        yaml.dump(schema, f, sort_keys=False)
    
    console.print(f"\n[bold green]✅ Success![/] New validation template saved to: [cyan]{schema_path}[/cyan]")
    console.print(f"✨ [bold]Pro Tip:[/] You can make this template even more powerful by manually editing it to use common schemas. For example, for '--compartment-id', you can add: [yellow]$ref: \"common_oci_args.compartment_id\"[/yellow]")

if __name__ == "__main__":
    app()