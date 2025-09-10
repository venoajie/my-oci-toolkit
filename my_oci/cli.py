import typer
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console

from . import core

# --- APP SETUP & CONFIGURATION ---
console = Console()
app = typer.Typer(help="MyOCI: Your personal architect for the OCI CLI.")

try:
    # This determines the location of the currently running script
    APP_SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    # Fallback for environments where __file__ is not defined
    APP_SCRIPT_DIR = Path.cwd()

# The project root is one level up from the 'my_oci' package directory
PROJECT_ROOT_DIR = APP_SCRIPT_DIR.parent

# --- PATH DEFINITIONS ---
# .env file is in the project root
DOTENV_PATH = PROJECT_ROOT_DIR / ".env"
# Templates are now INSIDE the package, relative to this script file
TEMPLATES_DIR = APP_SCRIPT_DIR / "templates"

TEMPLATES_DIR.mkdir(exist_ok=True)
load_dotenv(dotenv_path=DOTENV_PATH)

COMMON_SCHEMAS_PATH = TEMPLATES_DIR / "common_schemas.yaml"
COMMON_SCHEMAS = core.load_common_schemas(COMMON_SCHEMAS_PATH)

# --- CLI COMMANDS ---
@app.command("run")
def run_command(
    oci_command: list[str] = typer.Argument(..., help="The raw OCI command and its arguments.", metavar="OCI_COMMAND_STRING..."),
    ci: bool = typer.Option(False, "--ci", help="Enable non-interactive (CI) mode. Fails on ambiguity."),
    redact: bool = typer.Option(True, "--redact/--no-redact", help="Toggle PII redaction on output.")
):
    """
    Validates and executes an OCI command against known-good templates.
    """
    console.rule("[bold cyan]MyOCI Validator Session Started[/]", style="cyan")

    console.print("[1/4] 🔍 [bold]Resolving environment variables...[/bold]")
    resolved_cmd = core.resolve_variables(oci_command, ci)
    if resolved_cmd is None:
        console.rule("[bold red]Session Aborted[/]", style="red"); raise typer.Exit(1)
    console.print("[green]✅ Variables resolved.[/green]\n")

    console.print("[2/4] 📄 [bold]Running pre-flight file path check...[/bold]")
    if not core.preflight_file_check(resolved_cmd):
        console.rule("[bold red]Session Aborted[/]", style="red"); raise typer.Exit(1)
    console.print("[green]✅ File paths are valid.[/green]\n")
    
    console.print("[3/4] 📝 [bold]Validating command against schema...[/bold]")
    validation_result, resolved_cmd = core.validate_command_with_schema(resolved_cmd, TEMPLATES_DIR, COMMON_SCHEMAS)
    if validation_result is False:
        console.rule("[bold red]Session Aborted[/]", style="red"); raise typer.Exit(1)
    
    console.print("\n[4/4] ▶️  [bold]Executing command...[/bold]")
    return_code = core.execute_command(resolved_cmd, redact)
        
    console.rule("[bold cyan]Validator Session Ended[/]", style="cyan")
    if return_code != 0:
        raise typer.Exit(return_code)

@app.command("learn")
def learn_command(
    oci_command: list[str] = typer.Argument(..., help="A successful OCI command to learn from.", metavar="OCI_COMMAND_STRING...")
):
    """
    Learns the structure of a successful command to create a new validation template.
    """
    core.learn_from_command(oci_command, TEMPLATES_DIR, COMMON_SCHEMAS)

if __name__ == "__main__":
    app()