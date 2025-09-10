# myoci/cli.py
import shlex
import typer
import os
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import core, constants

# --- APP SETUP & CONFIGURATION ---
console = Console()
app = typer.Typer(help="MyOCI: Your personal SRE architect for the OCI CLI.")
templates_app = typer.Typer(help="Manage your local command validation templates.")
app.add_typer(templates_app, name="templates")

try:
    APP_SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    APP_SCRIPT_DIR = Path.cwd()

PROJECT_ROOT_DIR = APP_SCRIPT_DIR.parent
DOTENV_PATH = PROJECT_ROOT_DIR / ".env"
TEMPLATES_DIR = APP_SCRIPT_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)
load_dotenv(dotenv_path=DOTENV_PATH)

COMMON_SCHEMAS_PATH = TEMPLATES_DIR / constants.COMMON_SCHEMAS_FILENAME
COMMON_SCHEMAS = core.load_common_schemas(COMMON_SCHEMAS_PATH)

# --- CLI COMMANDS ---

@app.command("run")
def run_command(
    oci_command: list[str] = typer.Argument(..., help="The raw OCI command and its arguments.", metavar="OCI_COMMAND_STRING..."),
    ci: bool = typer.Option(False, "--ci", help="Enable non-interactive (CI) mode. Fails on ambiguity."),
    redact: bool = typer.Option(True, "--redact/--no-redact", help="Toggle PII redaction on output. Default: enabled.")
):
    """Validates and executes an OCI command against your personal known-good templates."""
    console.rule("[bold cyan]MyOCI Validator Session Started[/]", style="cyan")

    console.print("[1/4] 🔍 [bold]Resolving environment variables...[/bold]")
    resolved_cmd = core.resolve_variables(oci_command)
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

    # --- Post-Execution Analysis ---
    if return_code == 0:
        console.print("[bold green]✅ Command Succeeded![/]")
        output_to_print = core.redact_output(stdout) if redact else stdout
        if output_to_print.strip():
            print(output_to_print.strip())
        else:
            console.print("[dim]myoci note: The OCI command was successful but returned no resources matching your query.[/dim]")
    else:
        human_readable_cmd = shlex.join(resolved_cmd)
        final_cmd_display = core.redact_output(human_readable_cmd) if redact else human_readable_cmd
        stderr_display = core.redact_output(stderr) if redact else stderr

        # MODIFIED: Reordered output for better readability on failure.
        console.print(f"[cyan]{final_cmd_display}[/cyan]")
        console.print("[bold red]❌ Command Failed![/]")

        if stderr_display.strip():
            console.print() # Add a newline for separation
            console.print(stderr_display.strip())

        if not ci:
            suggestion = core.analyze_failure_and_suggest_fix(stderr)
            if suggestion:
                missing_flag, env_var = suggestion
                console.print()
                prompt = (f"💡 It seems the command failed because it was missing [bold cyan]{missing_flag}[/bold].\n"
                          f"I found an exact match [bold green]${env_var}[/bold] in your environment. Would you like to retry?")
                if typer.confirm(prompt, default=False):
                    final_command = resolved_cmd + [missing_flag, os.environ[env_var]]
                    display_cmd_str = shlex.join(final_command)
                    if redact: display_cmd_str = core.redact_output(display_cmd_str)

                    console.print(f"\n[bold]Re-running with suggested fix:[/bold]\n[cyan]{display_cmd_str}[/cyan]")
                    return_code, stdout, stderr = core.execute_command(final_command)

                    if return_code == 0:
                        console.print("[bold green]✅ Retry Succeeded![/]")
                        output_to_print = core.redact_output(stdout) if redact else stdout
                        if output_to_print.strip(): print(output_to_print.strip())
                        else: console.print("[dim]myoci note: The OCI command was successful but returned no resources.[/dim]")
                    else:
                        console.print("[bold red]❌ Retry Failed.[/]")
                        stderr_display = core.redact_output(stderr.strip()) if redact else stderr.strip()
                        if stderr_display: console.print(stderr_display)

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
    """Learns the structure of a successful command to create a new validation template."""
    core.learn_from_command(oci_command, TEMPLATES_DIR, COMMON_SCHEMAS)

@templates_app.command("list")
def templates_list():
    """Lists all available command templates."""
    console.print("[bold]Available Command Templates:[/bold]")
    templates = core.list_templates(TEMPLATES_DIR)
    if not templates:
        console.print("  No templates found. Use 'myoci learn' to create one.")
        return

    table = Table("Command Name", "File Name")
    for template_path in templates:
        command_name = template_path.stem.replace('_', ' ')
        table.add_row(command_name, template_path.name)
    console.print(table)

@templates_app.command("show")
def templates_show(command: str = typer.Argument(..., help="The command name to show (e.g., 'oci compute instance list').")):
    """Displays the contents of a specific template."""
    template_path = core.get_template_path(command, TEMPLATES_DIR)
    if not template_path.is_file():
        console.print(f"[bold red]Error:[/] Template for '{command}' not found at '{template_path}'.")
        raise typer.Exit(1)
    console.print(f"--- Contents of [cyan]{template_path.name}[/cyan] ---")
    console.print(template_path.read_text())

@templates_app.command("delete")
def templates_delete(command: str = typer.Argument(..., help="The command name to delete (e.g., 'oci compute instance list').")):
    """Deletes a specific template after confirmation."""
    template_path = core.get_template_path(command, TEMPLATES_DIR)
    if not template_path.is_file():
        console.print(f"[bold red]Error:[/] Template for '{command}' not found.")
        raise typer.Exit(1)

    console.print(f"You are about to delete the template: [bold yellow]{template_path.name}[/bold yellow]")
    if typer.confirm("Are you sure?", default=False):
        try:
            template_path.unlink()
            console.print(f"[green]✅ Template '{template_path.name}' deleted.[/green]")
        except OSError as e:
            console.print(f"[bold red]Error:[/] Could not delete template: {e}")
            raise typer.Exit(1)
    else:
        console.print("Deletion cancelled.")

if __name__ == "__main__":
    app()