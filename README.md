# MyOCI Toolkit

MyOCI is a personal Cloud-CLI architect, designed to make interacting with the OCI (Oracle Cloud Infrastructure) command-line interface safer, smarter, and more reliable. It acts as an intelligent wrapper around the native `oci` command, validating your commands against known-good templates *before* they are executed to prevent common errors. It is specifically tailored for complex workflows and for use with AI-generated commands.

## Core Features

-   **Pre-Execution Validation (`myoci run`):** Catches errors in your command *locally* before they are ever sent to the OCI API. It checks for missing required arguments, incorrect data formats (like using a Tenancy OCID instead of a Compartment OCID), and missing local files.
-   **Intelligent Learning (`myoci learn`):** When you finally get a complex command to work, `myoci learn` helps you save its structure as a reusable YAML validation template. This turns your one-time success into a permanent, automated safety net for the future.
-   **Centralized, Reusable Schemas:** Define validation rules for common arguments (like `--compartment-id`) once in `templates/common_schemas.yaml` and reference them from any command template, keeping your knowledge base DRY (Don't Repeat Yourself).
-   **Robust Variable Handling:** Automatically detects and substitutes `$VARIABLES` from your `.env` file, correctly handling file paths (expanding `~`) and complex JSON strings.
-   **Typo Detection:** If you make a typo in a variable name (e.g., `$COMPARTMEN_ID`), the tool intelligently suggests the correct one from your `.env` file.
-   **Safe by Default:** All output, including error messages and debug information, is **automatically redacted** to prevent accidental leakage of sensitive OCIDs when copy-pasting results to an AI or a colleague.
-   **Machine & AI Ready:** A `--ci` flag enables non-interactive mode for use in scripts, failing with clear errors instead of prompting for input.
-   **Transparent Debugging:** If a command fails, MyOCI shows you the final, fully-resolved (and redacted) command that it tried to execute, taking the guesswork out of debugging.

## Installation

This tool is designed to be installed as a global command, making it available everywhere in your terminal. The recommended method is using `pipx`.

### Prerequisites
-   Python 3.8+
-   `pipx` (Install with `pip install --user pipx` and `pipx ensurepath`)
-   The OCI CLI must be installed and configured (`~/.oci/config`).

### Steps
1.  Clone this repository:
    ```bash
    git clone <your-repo-url>
    cd myoci-toolkit
    ```

2.  Install the tool using `pipx`:
    ```bash
    pipx install .
    ```
    This will create an isolated environment for the tool and add the `myoci` command to your path.

3.  Configure your environment:
    ```bash
    # Copy the example .env file
    cp .env.example .env

    # Edit .env and add your most-used OCI variables.
    # Use raw values without quotes for paths and JSON.
    OCI_COMPARTMENT_ID=ocid1.compartment.oc1..aaaa...
    OCI_SUBNET_ID=ocid1.subnet.oc1..bbbb...
    OCI_SSH_PUBLIC_KEY_PATH=~/.ssh/id_rsa.pub
    OCI_SHAPE_CONFIG={"ocpus": 1, "memoryInGBs": 6}
    ```

## Usage

The `myoci` command is now available globally. The most important syntax rule is to use `--` to separate `myoci`'s own options from the `oci` command you want to run.

### 1. The "Learn -> Validate -> Run" Workflow

This is the core loop of MyOCI.

**Step 1: Get a complex command to work once.**
After some trial and error, you have a working command to launch a VM:
```bash
# This is a raw, working OCI command
oci compute instance launch \
  --display-name "MyWebApp" \
  --compartment-id "ocid1.compartment..." \
  --subnet-id "ocid1.subnet..." \
  --ssh-authorized-keys-file ~/.ssh/id_rsa.pub \
  # ... and all other required parameters
```

**Step 2: Teach it to `myoci learn`.**
Save this knowledge forever. Use your `.env` variables and single quotes.
```bash
myoci learn -- oci compute instance launch \
  --display-name "MyWebApp" \
  --compartment-id '$OCI_COMPARTMENT_ID' \
  --subnet-id '$OCI_SUBNET_ID' \
  --ssh-authorized-keys-file '$OCI_SSH_PUBLIC_KEY_PATH' \
  # ... etc
```
The tool will guide you to create `templates/oci_compute_instance_launch.yaml`. You can then edit this file to add more specific validation, like referencing common schemas.

**Step 3: Run it safely with `myoci run`.**
The next time you (or an AI) need to run this command, you can do so with confidence.
```bash
# MyOCI will now validate this against your template before running.
myoci run -- oci compute instance launch \
  --display-name "MyNewWebApp" \
  --compartment-id '$OCI_COMPARTMENT_ID' \
  --subnet-id '$OCI_SUBNET_ID' \
  --ssh-authorized-keys-file '$OCI_SSH_PUBLIC_KEY_PATH' \
  # ... etc
```
If you forget `--subnet-id`, MyOCI will stop you with a clear error *before* calling the API.

### 2. The AI-to-Human Workflow (Safe Execution)

You get a command from an AI. You want to run it safely.

```bash
# AI suggests: oci compute instance list -c $OCI_COMPARTMENT_ID
# You run it with MyOCI:
myoci run -- oci compute instance list --compartment-id '$OCI_COMPARTMENT_ID'
```
The tool will:
1.  Substitute `$OCI_COMPARTMENT_ID` from your `.env` file.
2.  If a validation template exists, it will validate the command.
3.  Execute the command.
4.  The output you see will be **redacted**, safe to copy back to the AI.

### 3. Getting Raw Output for Scripts

An AI agent or a script needs raw, machine-readable data.

```bash
myoci run --no-redact --ci -- oci compute instance list --compartment-id '$OCI_COMPARTMENT_ID' --output json
```
-   `--no-redact`: Ensures the output JSON contains the real, full OCIDs for the script to process.
-   `--ci`: Ensures the script will fail with an error code instead of prompting if a variable is missing or has a typo.