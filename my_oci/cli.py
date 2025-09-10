# my_oci\cli.py

import shlex
import typer
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console

from . import core

# --- APP SETUP & CONFIGURATION ---
console = Console()
app = typer.Typer(help="MyOCI: Your personal architect for the OCI CLI.")

try:
    APP_SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    APP_SCRIPT_DIR = Path.cwd()

PROJECT_ROOT_DIR = APP_SCRIPT_DIR.parent
DOTENV_PATH = PROJECT_ROOT_DIR / ".env"
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
    elif validation_result is True:
        console.print("[green]✅ Command passed all structural and format validation checks.[/green]")
    else:
        console.print("[yellow]Info: No validation schema found. Proceeding without deep validation.[/yellow]")

    console.print("\n[4/4] ▶️  [bold]Executing command...[/bold]")
    return_code, stdout, stderr = core.execute_command(resolved_cmd)
    initial_stderr = stderr # Keep a copy of the original error

    if return_code != 0 and validation_result is None and not ci:
        suggestion = core.analyze_failure_and_suggest_fix(stderr)
        if suggestion:
            missing_flag, env_var = suggestion
            console.print()
            prompt_text = (
                f"💡 It seems the command failed because it was missing [bold cyan]{missing_flag}[/bold].\n"
                f"I found [bold green]${env_var}[/bold] in your environment. Would you like to retry with this argument added?"
            )
            if typer.confirm(prompt_text, default=False):
                corrected_command = resolved_cmd + [missing_flag, f'${env_var}']
                console.print("\n[bold]Re-running with suggested fix...[/bold]")
                
                final_command = core.resolve_variables(corrected_command, ci)
                if final_command:
                    # Update the state variables with the result of the retry
                    return_code, stdout, stderr = core.execute_command(final_command)

    if return_code == 0:
        console.print("[bold green]✅ Command Succeeded![/]")
        output_to_print = core.redact_output(stdout) if redact else stdout
        if output_to_print:
            print(output_to_print.strip())
    else:
        # This block handles both initial failures and retry failures
        human_readable_cmd = shlex.join(resolved_cmd)
        final_stderr = stderr if stderr else initial_stderr # Use the most recent error
        
        if redact:
            human_readable_cmd = core.redact_output(human_readable_cmd)
            final_stderr = core.redact_output(final_stderr)

        console.print("[bold red]❌ Command Failed![/]")
        console.print(f"[bold yellow]🔎 Final command executed:[/bold yellow]\n[cyan]{human_readable_cmd}[/cyan]\n")
        if final_stderr.strip():
            console.print(final_stderr.strip())

    console.rule("[bold cyan]Validator Session Ended[/]", style="cyan")

    if return_code == 0 and validation_result is None and not ci:
        console.print()
        if typer.confirm("✨ This unvalidated command succeeded. Would you like to create a validation template from it now?", default=False):
            core.learn_from_command(oci_command, TEMPLATES_DIR, COMMON_SCHEMAS)

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