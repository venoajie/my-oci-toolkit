MyOCI is a personal, safety-focused wrapper for the Oracle Cloud Infrastructure (OCI) CLI. It acts as a local "Site Reliability Engineer" for your commands, designed to make your interactions with OCI safer, more predictable, and self-documenting. It helps you succeed by validating inputs locally, analyzing results clearly, and guiding you toward robust, repeatable commands.

This tool is built on SRE principles: **reliability over features, predictability over magic, and safety above all else.** It is designed for engineers who need to be effective and safe, especially during high-pressure situations.

## Core Philosophy

-   **Predictable:** The tool never guesses. If a variable is missing, it fails. If a command returns no results, it says so explicitly. There is no "magic."
-   **Safe by Default:** All output is automatically redacted to prevent accidental leakage of sensitive OCIDs and IP addresses. All interactive prompts default to "No" to prevent unintended actions.
-   **Reliable:** The tool helps you build a personal, version-controlled library of known-good commands, ensuring that what worked yesterday will work today.

## Features

-   **Pre-Execution Validation (`myoci run`):** Catches errors in your command *locally* before they are ever sent to the OCI API. It checks for missing required arguments and incorrect data formats based on templates you create.
-   **Safe Failure Recovery:** If a command fails with a "Missing option" error, MyOCI analyzes the error and offers a safe, targeted fix *only if* it finds an exact variable match in your `.env` file.
-   **Explicit Empty Results:** If a command succeeds but returns no resources, MyOCI prints a clear, unambiguous message, removing the guesswork of whether an error occurred.
-   **Reliable Learning (`myoci learn`):** When you run a successful command, `myoci learn` helps you save its structure as a reusable YAML validation template. This builds your personal, trusted knowledge base.
-   **Proactive Learning:** After any unvalidated command succeeds, MyOCI prompts you to save that success as a new validation template, effortlessly growing your library.
-   **Template Management (`myoci templates`):** A simple command group (`list`, `show`, `delete`) to easily manage your local library of validation templates.
-   **Robust Variable Handling:** Automatically detects and substitutes `$VARIABLES` from your `.env` file. It fails with a clear error if a variable is not found.
-   **CI/CD Ready:** A `--ci` flag enables non-interactive mode for use in scripts, failing with a clear error code instead of prompting for input.

## Installation

### Prerequisites
-   Python 3.9+
-   The OCI CLI must be installed and configured (`~/.oci/config`).

### Steps
1.  Clone this repository.
2.  Navigate into the repository directory.
3.  Install the tool using `pip`:
    ```bash
    pip install .
    ```
4.  Configure your environment by creating a `.env` file in the project root and adding your most-used OCI variables, such as `OCI_COMPARTMENT_ID` and `OCI_TENANCY_ID`.

## Usage

### 1. The "Fail -> Fix -> Succeed -> Learn" Workflow

This is the core safety net. You run a command that's missing a required argument.

**Step 1: Run the incomplete command.**
```bash
myoci run oci compute instance list
```

**Step 2: Let MyOCI guide you safely.**
MyOCI runs the command, sees it fail, analyzes the error, and offers a precise, safe fix.
```
> ❌ Command Failed!
> Error: Missing option(s) --compartment-id.
>
> 💡 It seems the command failed because it was missing --compartment-id.
> I found an exact match $OCI_COMPARTMENT_ID in your environment. Would you like to retry? [y/N]: y
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

### 2. Managing Your Knowledge Base

Use the `templates` command to manage your personal library of validated commands.

**List all learned commands:**
```bash
myoci templates list
```

**Inspect the rules for a specific command:**
```bash
myoci templates show "oci compute instance list"
```

**Delete an outdated template:**
```bash
myoci templates delete "oci compute instance list"
```

### 3. Getting Raw Output for Scripts

An automation script needs raw, machine-readable data.

```bash
myoci run --no-redact --ci -- oci compute instance list --compartment-id '$OCI_COMPARTMENT_ID' --output json
```
-   `--no-redact`: Ensures the output JSON contains the real, full OCIDs.
-   `--ci`: Ensures the script will fail with an error code instead of prompting for input.
```