
import os
import subprocess
import typer
from dotenv import load_dotenv

# Load environment variables from our .env file
load_dotenv()

# --- Configuration ---
# Read ONLY the project-specific variables from the environment
try:
    # This is our toolkit's default compartment.
    # The OCI CLI will handle auth from ~/.oci/config on its own.
    DEFAULT_COMPARTMENT_ID = os.environ["OCI_COMPARTMENT_ID"]
except KeyError as e:
    print(f"FATAL: Environment variable {e} not set in .env file.")
    print("This should be the OCID of the compartment you work in most often.")
    exit(1)


# --- CLI Application Setup ---
app = typer.Typer(
    help="Archie's Personal OCI Toolkit: A reliable wrapper for common OCI tasks."
)
vm_app = typer.Typer(name="vm", help="Commands for managing Compute VMs (Instances).")
app.add_typer(vm_app)


# --- CLI Commands ---
@vm_app.command("list")
def vm_list():
    """
    Lists all VMs in the default compartment specified in your .env file.
    """
    print(f"✅ Fetching VMs in default compartment: {DEFAULT_COMPARTMENT_ID[:25]}...")

    # The OCI CLI will automatically use your default profile from ~/.oci/config
    # for authentication, since we are not overriding it with environment variables.
    command = [
        "oci", "compute", "instance", "list",
        "--compartment-id", DEFAULT_COMPARTMENT_ID
    ]

    subprocess.run(command)


if __name__ == "__main__":
    app()
