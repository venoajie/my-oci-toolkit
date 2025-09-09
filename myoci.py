import os
import sys
import subprocess
import typer
import shlex
import re
import difflib
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule
from rapidfuzz import process, fuzz

# A simple in-memory cache for command flags
FLAG_CACHE = {}

# --- SETUP & CONFIGURATION ---
console = Console()

# Path-aware configuration to ensure the script can be run from anywhere
try:
    SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    SCRIPT_DIR = Path.cwd() # Fallback for interactive interpreters

DOTENV_PATH = SCRIPT_DIR / ".env"
COOKBOOK_PATH = SCRIPT_DIR / "cookbook.md"
load_dotenv(dotenv_path=DOTENV_PATH)

# --- HELPER FUNCTIONS ---

def get_valid_flags_for_command(command_parts: list[str]) -> list[str]:
    """
    Runs the --help command for a given OCI command path and caches the valid flags.
    """
    command_key = " ".join(command_parts)
    if command_key in FLAG_CACHE:
        return FLAG_CACHE[command_key]

    try:
        help_command = command_parts + ["--help"]
        result = subprocess.run(help_command, capture_output=True, text=True, check=True)
        # Use regex to find all lines starting with --option
        valid_flags = re.findall(r"^\s+(--[a-zA-Z0-9-]+)", result.stdout, re.MULTILINE)
        FLAG_CACHE[command_key] = valid_flags
        return valid_flags
    except (subprocess.CalledProcessError, FileNotFoundError):
        # If we can't get help, we can't check. Return empty list.
        return []

def preflight_syntax_check(command_parts: list[str]) -> list[str] | None:
    """
    Checks for flag typos using Levenshtein distance before execution.
    """
    # Find the command path (e.g., ['oci', 'compute', 'instance', 'list'])
    command_path = []
    for part in command_parts:
        if part.startswith('--'):
            break
        command_path.append(part)
    
    valid_flags = get_valid_flags_for_command(command_path)
    if not valid_flags:
        return command_parts # Cannot check, proceed as is

    corrected_parts = []
    for part in command_parts:
        if part.startswith('--') and "=" not in part: # Check simple flags like --compartment-id
            if part not in valid_flags:
                # Find the best match with a high score threshold
                best_match = process.extractOne(part, valid_flags, scorer=fuzz.WRatio, score_cutoff=80)
                if best_match:
                    suggestion = best_match[0]
                    if typer.confirm(f"⚠️ Syntax Warning: Invalid flag [yellow]'{part}'[/]. Did you mean [green]'{suggestion}'[/]?"):
                        corrected_parts.append(suggestion)
                        continue
        corrected_parts.append(part)
    
    return corrected_parts

def redact_all_pii(text: str) -> str:
    """Redacts OCIDs and IPv4 addresses from a string."""
    if not text:
        return ""
    # Redact OCIDs: ocid1.resource.realm..uniqueID -> ocid1.resource.realm..aaaa****
    text = re.sub(r"(ocid1\.[a-z]+\.oc1\.\.[a-z0-9]{4})[a-z0-9]+", r"\1****", text)
    # Redact IPv4 addresses
    text = re.sub(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", "[REDACTED_IP]", text)
    return text

def resolve_variables(command_parts: list[str], ci_mode: bool) -> list[str] | None:
    """
    Parses command for $VARS, resolves them from the environment,
    and suggests corrections for near misses.
    """
    resolved_parts = []
    available_vars = {k: v for k, v in os.environ.items() if k.startswith("OCI_")}

    for part in command_parts:
        if part.startswith('$'):
            var_name = part.strip('$')
            if var_name in available_vars:
                resolved_parts.append(available_vars[var_name])
            else:
                matches = difflib.get_close_matches(var_name, available_vars.keys())
                if matches and not ci_mode:
                    suggestion = matches[0]
                    if typer.confirm(
                        f"⚠️ Variable [bold yellow]${var_name}[/] not found. Did you mean [bold green]${suggestion}[/]?"
                    ):
                        resolved_parts.append(available_vars[suggestion])
                    else:
                        console.print("[bold red]Aborting due to unresolved variable.[/]")
                        return None
                else:
                    err_msg = f"Error: Variable ${var_name} not found."
                    if matches:
                        err_msg += f" A close match '{matches[0]}' exists. Aborting in non-interactive mode."
                    console.print(f"[bold red]{err_msg}[/]")
                    return None
        else:
            resolved_parts.append(part)
    return resolved_parts

def check_cookbook_for_similar(command_to_check: list[str]) -> list[str] | None:
    """
    Reads cookbook.md and finds if a similar, known-good command exists.
    """
    if not COOKBOOK_PATH.exists():
        return None
    try:
        content = COOKBOOK_PATH.read_text()
        code_blocks = re.findall(r"```bash\n(.*?)\n```", content, re.DOTALL)
        known_commands = [cmd.strip() for cmd in code_blocks]
        command_str_to_check = " ".join(command_to_check)
        matches = difflib.get_close_matches(command_str_to_check, known_commands, n=1, cutoff=0.8)
        if matches:
            return shlex.split(matches[0])
        return None
    except Exception as e:
        console.print(f"[yellow]Warning: Could not parse cookbook.md: {e}[/]")
        return None

def run_and_learn(command: list[str], ci_mode: bool, redact_mode: bool):
    """
    Executes a command, captures its output, and if it fails,
    starts an interactive troubleshooting session (unless in CI mode).
    """
    original_command_str = ' '.join(command)
    console.print(f"▶️  Running: [cyan]{original_command_str}[/]")

    while True:
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode == 0:
            output = redact_all_pii(result.stdout) if redact_mode else result.stdout
            console.print("[bold green]✅ Success![/]")
            print(output)

            # If the command succeeded after a failure, ask to save it.
            if ' '.join(command) != original_command_str:
                if not ci_mode and typer.confirm("\n[bold yellow]✨ This corrected command worked. Save it to your cookbook?[/]"):
                    with open(COOKBOOK_PATH, "a") as f:
                        f.write(f"## Corrected Command\n\n")
                        f.write("**Successfully Executed:**\n")
                        f.write("```bash\n")
                        f.write(' '.join(command) + "\n")
                        f.write("```\n\n")
                    console.print(f"✅ Saved to [green]{COOKBOOK_PATH}[/]")
            break

        # --- FAILURE PATH ---
        stderr_output = redact_all_pii(result.stderr.strip()) if redact_mode else result.stderr.strip()
        
        if ci_mode:
            console.print(f"[bold red]❌ Command Failed in CI Mode (Exit Code: {result.returncode})[/]", file=sys.stderr)
            console.print(f"--- Error ---", file=sys.stderr)
            console.print(stderr_output, file=sys.stderr)
            raise typer.Exit(result.returncode)
        
        # --- INTERACTIVE TROUBLESHOOTING ---
        console.print(Rule("[bold red]❌ Command Failed[/]", style="red"))
        console.print("[yellow]--- OCI Error ---[/]")
        console.print(stderr_output)
        console.print("[yellow]-----------------[/]")
        
        failing_command_str = redact_all_pii(' '.join(command)) if redact_mode else ' '.join(command)
        console.print(f"The failing command was: [cyan]{failing_command_str}[/]")

        new_command_str = typer.prompt("\nEnter the corrected command, or type 'q' to quit")
        if new_command_str.lower() in ['q', 'quit']:
            console.print("[bold]Aborting session.[/]")
            break
        
        command = shlex.split(new_command_str)

# --- CLI APPLICATION ---
app = typer.Typer(
    help="MyOCI: Your intelligent partner for the OCI CLI.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)

@app.command("run")
def run_raw_command(
    ctx: typer.Context,
    ci: bool = typer.Option(False, "--ci", help="Enable non-interactive CI/AI mode."),
    redact: bool = typer.Option(True, "--redact/--no-redact", help="Enable/disable PII redaction in output.")
):
    """
    Validates and executes a raw OCI command string.
    Safe by default (interactive, redacted).
    Use --ci for machine execution.
    Use --no-redact for raw data output.
    """
    raw_command_parts = ctx.args
    if not raw_command_parts:
        console.print("[bold red]Error:[/] Please provide the raw OCI command to run after 'run'.")
        raise typer.Exit(1)

    console.rule("[bold cyan]MyOCI Validator Session Started[/]", style="cyan")
    
    # --- STEP 0: Pre-flight Syntax Check ---
    console.print("[0/4] ✈️  [bold]Running pre-flight syntax check...[/bold]")
    corrected_by_preflight = preflight_syntax_check(raw_command_parts)
    if not corrected_by_preflight:
        # This would happen if the user rejects a suggestion
        console.rule("[bold red]Session Aborted[/]", style="red")
        raise typer.Exit(1)
    console.print("[green]✅ Pre-flight check complete.[/green]\n")
      
    # Step 1: Variable Resolution    
    console.print("[1/4] 🔍 [bold]Resolving environment variables...[/bold]")
    resolved_command = resolve_variables(corrected_by_preflight, ci_mode=ci)

    if not resolved_command:
        console.rule("[bold red]Session Aborted[/]", style="red")
        raise typer.Exit(1)
    console.print("[green]✅ Variables resolved successfully.[/green]\n")

    # Step 2: Cookbook Check
    final_command = resolved_command
    if not ci:
        console.print("[2/3] 📖 [bold]Checking cookbook for known-good commands...[/bold]")
        similar_command = check_cookbook_for_similar(resolved_command)
        if similar_command:
            console.print("💡 [yellow]Heads up![/] A very similar command was found in your cookbook:")
            console.print(f"   [cyan]{' '.join(similar_command)}[/]")
            if typer.confirm("Do you want to run this known-good version instead?"):
                final_command = similar_command
                console.print("[green]✅ Switched to known-good command.[/green]\n")
            else:
                console.print("👍 Continuing with the original command.\n")
        else:
            console.print("✅ No similar commands found. Proceeding.\n")

    # Step 3: Execution and Learning
    console.print("[3/3] ▶️  [bold]Executing command...[/bold]")
    run_and_learn(final_command, ci_mode=ci, redact_mode=redact)

    console.rule("[bold cyan]Validator Session Ended[/]", style="cyan")

if __name__ == "__main__":
    app()
