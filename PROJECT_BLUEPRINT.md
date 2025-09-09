# Project Blueprint: MyOCI Toolkit

<!-- Version: 2.0 -->
<!-- This document outlines the architecture and operational principles of the MyOCI Toolkit, reflecting the evolution to a schema-based validation system. -->

## 1. System Overview and Core Purpose

This document is the canonical source of truth for the architectural principles and governance of the MyOCI Toolkit.

MyOCI is a standalone, user-centric command-line application designed to act as an intelligent wrapper or "personal architect" for the native Oracle Cloud Infrastructure (`oci`) CLI. Its primary purpose is to **make interactions with the OCI CLI safer, more reliable, and self-documenting by validating commands against known-good templates *before* execution.** It is specifically tailored to improve workflows driven by AI-generated or manually written commands that are often "99% correct."

It is not a replacement for the OCI CLI, but rather a smart, stateful proxy that sits between the user and the underlying tool.

### 1.1. Ecosystem Glossary

-   **Validator Mode (`myoci run`):** The primary operational mode. It intercepts a raw `oci` command and subjects it to a multi-stage validation pipeline before execution.
-   **Learning Mode (`myoci learn`):** The mechanism for capturing knowledge. A user provides a proven, working `oci` command, and the tool interactively helps build a reusable validation template from it.
-   **Validation Templates (`templates/*.yaml`):** Local, version-controlled YAML files that serve as the tool's long-term memory. Each template defines the structure, required arguments, and data formats for a specific `oci` command (e.g., `oci_compute_instance_launch.yaml`).
-   **Common Schemas (`templates/common_schemas.yaml`):** A central, reusable library of validation rules for common arguments like Compartment OCIDs or Tenancy OCIDs, referenced by individual templates.
-   **CI / AI Mode (`--ci` flag):** A non-interactive execution mode. The tool fails with explicit error codes instead of prompting for user input (e.g., for correcting variable typos).
-   **Redaction Mode (`--redact` flag):** A safety feature, enabled by default, that scrubs sensitive data (OCIDs, IP addresses) from all terminal output, including debug messages.

---

## 2. Core Architectural Principles

### 2.1. Augmentation, Not Replacement
The tool **MUST NOT** re-implement the OCI CLI's functionality. It is designed as a thin, intelligent wrapper that ultimately constructs and executes the real `oci` command. This ensures the full power of the underlying tool remains available and that MyOCI does not fall out of sync with new OCI CLI releases.

### 2.2. The Proactive Learning Loop
The core value proposition is the `Succeed -> Learn -> Validate -> Prevent Future Failures` workflow. The tool is designed to learn from user success. Every working command can be transformed by `myoci learn` into a permanent validation template, turning one-time successes into a persistent, automated safety net.

### 2.3. Safe by Default
User safety is paramount. PII redaction is enabled by default on all output, including the "Final command executed" debug message. This prevents accidental exposure of sensitive identifiers when sharing output with AI assistants or colleagues. The user must explicitly disable this feature (`--no-redact`).

### 2.4. Context-Aware Execution
The tool's behavior **MUST** adapt based on its invocation context. The `--ci` and `--redact` flags fundamentally change its operational logic from an interactive human assistant to a strict, non-interactive script component.

### 2.5. Configuration via Environment
All user-specific, machine-specific, or secret data (e.g., Compartment OCID, Subnet OCID, SSH key path) **MUST** be externalized into a `.env` file. The application code itself remains generic and portable.

---

## 3. System Architecture & Components

MyOCI is a single-entrypoint application that orchestrates a pipeline of validation and execution helpers.

```
+----------+     +----------------------------------------------------------------------------------------------------+
| User/AI  |---->|                                 MyOCI Toolkit (`myoci run`)                                        |
| (Inputs  |     |                                                                                                    |
| Command) |     | [1. Resolve Vars] -> [2. Pre-flight Checks] -> [3. Validate w/ Schema] -> [4. Execute] -> [5. Redact] |
+----------+     |                                                                                                    |
                 +--------------------------------------+-------------------------------------------------------------+
                                                        | (Executes Corrected Command)
                                                        |
                                          +-------------v-------------+
                                          |   Native OCI CLI Tool     |
                                          +---------------------------+
```

-   **Typer CLI Application (`myoci.py`):** The main entry point, responsible for parsing commands (`run`, `learn`), arguments, and flags.
-   **Validation Pipeline Engine (`run_command`):** The stateful function that orchestrates the pre-execution validation steps.
-   **Helper Modules (Functions):**
    -   **Variable Resolver:** Scans the input command for `$VAR` syntax, substitutes values from the environment, suggests corrections for typos, and expands tilde (`~`) in file paths.
    -   **Pre-flight Checker:** Verifies that local files referenced in the command (e.g., via `--ssh-authorized-keys-file`) exist before proceeding.
    -   **Schema Validator:** The core validation engine. Finds a matching template in `templates/`, checks for required arguments, and validates data formats against schemas, resolving `$ref` links to `common_schemas.yaml`.
    -   **PII Redactor:** A regex-based filter that scrubs sensitive data from output streams.
-   **Configuration & State Files:**
    -   **`.env`:** Stores user-specific variables. Read-only.
    -   **`templates/*.yaml`:** Stores learned validation schemas for specific commands. Append-only (user adds new files via `learn`).
    -   **`templates/common_schemas.yaml`:** Stores reusable validation rules for common arguments.
    -   **`~/.oci/config`:** The external configuration for the underlying OCI CLI. Read-only.

---

## 4. The Command Lifecycle (Validator Workflow)

This sequence describes the step-by-step process for the `myoci run` command.

**Stage 1: Invocation**
*   A user or AI agent invokes the tool, separating MyOCI options from the OCI command with `--`. Example: `myoci run --no-redact -- oci compute instance list...`

**Stage 2: Variable Resolution**
*   The tool parses the command, identifying `$VAR` placeholders.
*   It substitutes each variable with a corresponding value from the `.env` file. During substitution, it automatically expands the tilde (`~`) character in file paths to the user's home directory.
*   If a variable is not found in non-CI mode, it searches for close matches and prompts the user for correction.

**Stage 3: Pre-flight File Check**
*   The tool scans the resolved command for flags that expect file paths.
*   It verifies that each specified local file exists on the filesystem. If any file is missing, the process aborts with a clear error.

**Stage 4: Schema Validation**
*   The tool attempts to find a matching `.yaml` template in the `templates/` directory based on the command's signature (e.g., `oci compute instance launch`).
*   **If a schema is found:**
    *   It checks for the presence of all `required_args`.
    *   It validates the format of arguments against their schemas, resolving `$ref` links to `common_schemas.yaml` for common types like OCIDs.
    *   If any validation fails, the process aborts with a specific error.
*   **If no schema is found:** The tool prints an informational message and proceeds to the next stage without performing deep validation.

**Stage 5: Execution**
*   The tool executes the final, fully-resolved command string as a subprocess.
*   **On Success:** The tool prints the (potentially redacted) output from the OCI CLI and exits.
*   **On Failure:** The tool prints a failure message, followed by the **redacted, final command that was executed** for debugging. It then prints the redacted error from the OCI CLI and exits with a non-zero status code.

---

## 5. CLI Contract

The tool is defined by its command-line interface.

### 5.1. `myoci run [--ci] [--redact|--no-redact] -- [OCI_COMMAND_STRING...]`
-   **Purpose:** The primary entry point for the Validator workflow.
-   **Separator:** The `--` is **mandatory** to separate `myoci run`'s options from the OCI command it is wrapping.
-   **Arguments:**
    -   `OCI_COMMAND_STRING`: The raw OCI command and its arguments.
-   **Flags / Options:**
    -   `--ci`: Enables non-interactive mode.
    -   `--redact` / `--no-redact`: Toggles PII redaction (default: `--redact`).

### 5.2. `myoci learn -- [OCI_COMMAND_STRING...]`
-   **Purpose:** The entry point for the Learning Mode.
-   **Separator:** The `--` is **mandatory**.
-   **Arguments:**
    -   `OCI_COMMAND_STRING`: A complete, proven-to-work OCI command.
-   **Process:** The tool first runs the command to confirm its success. It then interactively prompts the user to identify required arguments and create basic schemas, saving the result to a new file in the `templates/` directory.

---

## 6. Build System & Packaging

-   **Dependency Management:** All dependencies are managed in `pyproject.toml`.
-   **Packaging:** The `[project.scripts]` table in `pyproject.toml` defines the `myoci` console script entry point.
-   **Installation:** The canonical installation method is via `pipx install .`.

---

## 7. Operational Model

-   **User Responsibilities:**
    -   The user is responsible for the initial installation and configuration of the underlying OCI CLI (`~/.oci/config`).
    -   The user must maintain the local `.env` file with their specific configuration.
    -   To share learnings, the user is responsible for committing the entire `templates/` directory to a version control system (e.g., Git).