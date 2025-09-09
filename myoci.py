import os
import subprocess
import typer
from dotenv import load_dotenv

# Load environment variables from our .env file
load_dotenv()

# --- Configuration ---
# Read the required variables from the environment
# The script will fail if any of these are not set in .env
try:
    COMPARTMENT_ID = os.environ["OCI_COMPARTMENT_ID"]
except KeyError as e:
    print(f"FATAL: Environment variable {e} not set in .env file. Please set it.")
    exit(1)


# --- CLI Application Setup ---
# This is the main application object
app = typer.Typer(
    help="Archie's Personal OCI Toolkit: A reliable wrapper for common OCI tasks."
)

# We create "sub-commands" or "groups". This one is for all VM-related actions.
vm_app = typer.Typer(name="vm", help="Commands for managing Compute VMs (Instances).")
app.add_typer(vm_app)


# --- CLI Commands ---
@vm_app.command("list")
def vm_list(
    # We can add options later, like --all-compartments
):
    """
    Lists all VMs in the default compartment specified in your .env file.
    """
    print(f"✅ Fetching VMs in compartment: {COMPARTMENT_ID[:25]}...") # Show truncated ID

    # This is where we build and run the actual OCI CLI command
    command = [
        "oci", "compute", "instance", "list",
        "--compartment-id", COMPARTMENT_ID
    ]

    # Execute the command
    # We use subprocess.run to call the external oci command
    subprocess.run(command)


if __name__ == "__main__":
    app()
