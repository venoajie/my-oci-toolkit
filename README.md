
# MyOCI Toolkit

MyOCI is a personal Cloud-CLI architect, designed to make interacting with the OCI (Oracle Cloud Infrastructure) command-line interface safer, smarter, and more reliable. It acts as an intelligent wrapper around the native `oci` command, specifically tailored for workflows involving AI-generated commands.

## Core Features

-   **Validator Mode:** The primary `myoci run` command allows you to safely execute raw `oci` commands copied from any source (like an AI assistant).
-   **Intelligent Variable Resolution:** Automatically detects `$VARIABLES` in commands and substitutes them from your `.env` file. If it finds a typo, it will suggest a correction (e.g., `$COMPARTMENT_OCID` -> `$OCI_COMPARTMENT_ID`).
-   **Interactive Troubleshooting:** If a command fails, the tool doesn't just quit. It starts an interactive session, shows you the error, and lets you try a corrected command until you succeed.
-   **Automatic Cookbook:** When you successfully correct a failed command, the tool asks to save the working version to a local `cookbook.md` file, building a personal, version-controlled knowledge base of commands that are proven to work for you.
-   **Proactive Assistance:** Before running a new command, it checks your `cookbook.md` for similar, known-good commands and offers to run the proven version instead.
-   **Safe by Default:** Output is automatically redacted to prevent accidental leakage of sensitive information (OCIDs, IP addresses) when copy-pasting results.
-   **Machine & AI Ready:** A `--ci` flag enables non-interactive mode for use in scripts or by an AI agent, failing with clear errors instead of prompting for input.
-   **Flexible Output:** A `--no-redact` flag allows you to get raw, unmodified output when needed for debugging or machine parsing.

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

    # Edit .env and add your most-used OCI Compartment OCID
    # OCI_COMPARTMENT_ID="ocid1.compartment.oc1..aaaa..."
    ```

## Usage

The `myoci` command is now available globally.

### 1. The AI-to-Human Workflow (Default)

You get a command from an AI, and you want to run it safely.

```bash
# AI suggests: oci compute instance list -c $COMPARTMENT_OCID --auth instance_principal
# You prefix it with 'myoci run':
myoci run oci compute instance list -c $COMPARTMENT_OCID --auth instance_principal
```

The tool will:
1.  Notice `$COMPARTMENT_OCID` is not in your `.env` and ask if you meant `$OCI_COMPARTMENT_ID`.
2.  After you confirm, it will run the corrected command.
3.  If it fails (e.g., `--auth instance_principal` is wrong for your setup), it will start the troubleshooting session.
4.  Once you fix it, it will offer to save the working command to `cookbook.md`.
5.  The output you see will be **redacted**, safe to copy back to the AI.

### 2. The AI Direct Execution Workflow

An AI agent needs to run a command and get raw, machine-readable data.

```bash
myoci run --ci --no-redact oci compute instance list -c $OCI_COMPARTMENT_ID --output json
```
-   `--ci`: Ensures the script will fail with an error code instead of prompting if `$OCI_COMPARTMENT_ID` is missing.
-   `--no-redact`: Ensures the output JSON contains the real, full OCIDs for the AI to process.

### 3. Personal Debugging

You need to see the full, unredacted error message to debug a problem.

```bash
myoci run --no-redact oci iam user list
```
The tool will still be interactive and help you, but all output will be raw.
```