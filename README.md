<!-- FILENAME: README.md -->
```markdown
# MyOCI Toolkit

MyOCI is a personal Cloud-CLI architect, designed to make interacting with the OCI (Oracle Cloud Infrastructure) command-line interface safer, smarter, and more reliable. It acts as an intelligent assistant that wraps the native `oci` command, helping you succeed by validating inputs, analyzing results, and guiding you toward the correct command. It is specifically tailored to prevent the frustrating, time-consuming debugging cycles common in complex CLI workflows, especially when working with AI-generated commands.

## Core Features

-   **Pre-Execution Validation (`myoci run`):** Catches errors in your command *locally* before they are ever sent to the OCI API. It checks for missing required arguments and incorrect data formats.
-   **Interactive Failure Recovery:** If a command fails with a "Missing option" error, MyOCI analyzes the error and intelligently suggests a fix using a variable from your `.env` file, turning failure into success.
-   **Intelligent Broadening:** If a `list` command for a compartment succeeds but returns no results, MyOCI offers to automatically re-run the command against the entire tenancy, helping you find resources you may have misplaced.
-   **Intelligent Learning (`myoci learn`):** When you get a command to work, `myoci learn` helps you save its structure as a reusable YAML validation template. It even suggests best-practice arguments (like `--output table` or `--all`) to make your future commands more effective.
-   **Proactive Learning:** After any unvalidated command succeeds, MyOCI prompts you to save that success as a new validation template, effortlessly growing your knowledge base.
-   **Safe by Default:** All output, including error messages, retry commands, and debug information, is **automatically redacted** to prevent accidental leakage of sensitive OCIDs when copy-pasting results to an AI or a colleague.
-   **Clear, Unambiguous Feedback:** If a command succeeds but produces no output, MyOCI explicitly tells you, removing the guesswork of whether an error occurred.
-   **Robust Variable Handling:** Automatically detects and substitutes `$VARIABLES` from your `.env` file, correctly handling file paths (expanding `~`) and complex JSON strings.
-   **Machine & AI Ready:** A `--ci` flag enables non-interactive mode for use in scripts, failing with clear errors instead of prompting for input.

## Installation

This tool is designed to be installed as a global command, making it available everywhere in your terminal. The recommended method is using `pipx`.

### Prerequisites
-   Python 3.8+
-   `pipx` (Install with `pip install --user pipx` and `pipx ensurepath`)
-   The OCI CLI must be installed and configured (`~/.oci/config`).

### Steps
1.  Clone this repository and navigate into the directory.
2.  Install the tool using `pipx`:
    ```bash
    pipx install .
    ```
3.  Configure your environment by copying `.env.example` to `.env` and adding your most-used OCI variables, such as `OCI_COMPARTMENT_ID` and `OCI_TENANCY_ID`.

## Usage

The `myoci` command is now available globally. Use `--` to separate `myoci`'s own options from the `oci` command you want to run.

### 1. The "Fail -> Fix -> Succeed -> Learn" Workflow

This is the ultimate safety net. You run a command suggested by an AI that's missing an argument.

**Step 1: Run the incomplete command.**
```bash
# AI suggests: oci compute instance list
myoci run -- oci compute instance list
```

**Step 2: Let MyOCI guide you.**
MyOCI runs the command, sees it fail, analyzes the error, and offers a fix.
```
> ❌ Command Failed!
> Error: Missing option(s) --compartment-id.
>
> 💡 It seems the command failed because it was missing --compartment-id.
> I found $OCI_COMPARTMENT_ID in your environment. Would you like to retry? [y/N]: y
```

**Step 3: Succeed and Learn.**
MyOCI re-runs the corrected command. It succeeds, and then offers to save this new knowledge.
```
> ✅ Retry Succeeded!
> { ... (redacted JSON output of your instances) ... }
>
> ✨ This unvalidated command succeeded. Would you like to create a validation template from it now? [y/N]: y
```
You are then guided to create a permanent safety net for `oci compute instance list`.

### 2. The "Empty -> Broaden -> Succeed" Workflow

You're looking for an instance but can't remember which compartment it's in.

**Step 1: Search a specific (but empty) compartment.**
```bash
myoci run -- oci compute instance list --compartment-id '$MY_EMPTY_COMPARTMENT_ID'
```

**Step 2: Accept the intelligent suggestion.**
MyOCI sees the command succeeded but found nothing, and offers a next step.
```
> ✅ Command Succeeded!
> myoci note: The OCI command was successful but returned no instances in this compartment.
>
> 💡 I found no instances here. Would you like to search the entire tenancy ($OCI_TENANCY_ID) instead? [y/N]: y
```

**Step 3: Find your resources.**
MyOCI re-runs the command with the broader scope, and you find your instance.
```
> Re-running with a broader scope:
> oci compute instance list --compartment-id [REDACTED_TENANCY_OCID]
>
> ✅ Retry Succeeded!
> { ... (redacted JSON output of your instances) ... }
```

### 3. Getting Raw Output for Scripts

An AI agent or a script needs raw, machine-readable data.

```bash
myoci run --no-redact --ci -- oci compute instance list --compartment-id '$OCI_COMPARTMENT_ID' --output json
```
-   `--no-redact`: Ensures the output JSON contains the real, full OCIDs.
-   `--ci`: Ensures the script will fail with an error code instead of prompting.
```
