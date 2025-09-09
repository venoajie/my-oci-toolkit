# Project Blueprint: MyOCI Toolkit

<!-- Version: 1.0 -->
<!-- This document outlines the architecture and operational principles of the MyOCI Toolkit. -->

## 1. System Overview and Core Purpose

This document is the canonical source of truth for the architectural principles and governance of the MyOCI Toolkit.

MyOCI is a standalone, user-centric command-line application designed to act as an intelligent wrapper or "personal architect" for the native Oracle Cloud Infrastructure (`oci`) CLI. Its primary purpose is to **make interactions with the OCI CLI safer, more reliable, and self-documenting, especially within workflows driven by AI-generated commands.** It is not a replacement for the OCI CLI, but rather a smart, stateful proxy that sits between the user and the underlying tool.

### 1.1. Ecosystem Glossary

-   **Validator Mode (`myoci run`):** The primary operational mode of the tool. It intercepts a raw `oci` command string and subjects it to a series of validation, correction, and execution steps.
-   **Troubleshooting Session:** The interactive, stateful loop that is triggered when a command fails in non-CI mode. It allows the user to iteratively correct a command until it succeeds.
-   **Cookbook (`cookbook.md`):** A local, version-controlled Markdown file that serves as the tool's long-term memory. It stores successfully corrected commands, creating a knowledge base of proven, working syntax.
-   **CI / AI Mode (`--ci` flag):** A non-interactive execution mode designed for machine or script-based usage. In this mode, the tool fails with explicit error codes instead of prompting for user input.
-   **Redaction Mode (`--redact` flag):** A safety feature, enabled by default, that scrubs sensitive data (OCIDs, IP addresses) from all terminal output. This is designed to protect the user during "human-in-the-middle" workflows.

---

## 2. Core Architectural Principles

### 2.1. Augmentation, Not Replacement
The tool **MUST NOT** re-implement the OCI CLI's functionality. It is designed as a thin, intelligent wrapper that ultimately constructs and executes the real `oci` command. This ensures that the full power and feature set of the underlying tool remain available and that MyOCI does not fall out of sync with new OCI CLI releases.

### 2.2. The Interactive Learning Loop
The core value proposition is the `Fail -> Fix -> Succeed -> Document` workflow. The tool is designed to learn from user corrections. Every failed command that is successfully fixed becomes a candidate for permanent documentation in the Cookbook, turning mistakes into a valuable, persistent asset.

### 2.3. Safe by Default
User safety is paramount. PII redaction is enabled by default to prevent the accidental exposure of sensitive identifiers when sharing output. The user must explicitly disable this feature (`--no-redact`) to receive raw data.

### 2.4. Context-Aware Execution
The tool's behavior **MUST** adapt based on its invocation context. The use of the `--ci` and `--redact` flags fundamentally changes its operational logic from an interactive human assistant to a strict, non-interactive script component.

### 2.5. Configuration via Environment
All user-specific, machine-specific, or secret data (e.g., the default Compartment OCID) **MUST** be externalized from the application code into a `.env` file. The application code itself should remain generic and portable.

---

## 3. System Architecture & Components

MyOCI is a single-entrypoint application that orchestrates a pipeline of validation and execution helpers.

```
+----------+     +---------------------------------------------------------------------------------+
| User/AI  |---->|                           MyOCI Toolkit (`myoci run`)                           |
| (Inputs  |     |                                                                                 |
| Command) |     |  [1. Resolve Vars] -> [2. Check Cookbook] -> [3. Execute & Learn] -> [4. Redact]  |
+----------+     |                                                                                 |
                 +---------------------------------+-----------------------------------------------+
                                                   | (Executes Corrected Command)
                                                   |
                                     +-------------v-------------+
                                     |   Native OCI CLI Tool     |
                                     +---------------------------+
```

-   **Typer CLI Application (`myoci.py`):** The main entry point, responsible for parsing commands, arguments, and flags.
-   **Core Logic Engine (`run_and_learn`):** The stateful function that orchestrates the execution, failure detection, and interactive troubleshooting loop.
-   **Helper Modules (Functions):**
    -   **Variable Resolver:** Scans the input command for `$VAR` syntax and substitutes values from the environment, offering suggestions for near misses.
    -   **Cookbook Checker:** Compares the input command against the `cookbook.md` to find known-good alternatives.
    -   **PII Redactor:** A regex-based filter that scrubs sensitive data from output streams.
-   **Configuration & State Files:**
    -   **`.env`:** Stores user-specific variables (e.g., `OCI_COMPARTMENT_ID`). Read-only.
    -   **`cookbook.md`:** Stores successfully corrected commands. Append-only.
    -   **`~/.oci/config`:** The external, canonical configuration for the underlying OCI CLI (authentication). Read-only.

---

## 4. The Command Lifecycle (Validator Workflow)

This sequence describes the step-by-step process for the `myoci run` command.

**Stage 1: Invocation**
*   A user or AI agent invokes the tool with a raw OCI command string (e.g., `myoci run oci compute instance list...`).

**Stage 2: Variable Resolution**
*   The tool parses the command string, identifying all parts prefixed with `$`.
*   It attempts to substitute each variable with a corresponding value from the environment (`.env` file).
*   If a variable is not found and `ci_mode` is OFF, it searches for close matches and prompts the user for confirmation. If `ci_mode` is ON, it fails with an error.

**Stage 3: Proactive Cookbook Check**
*   If `ci_mode` is OFF, the tool takes the variable-resolved command and calculates its similarity to commands stored in `cookbook.md`.
*   If a high-confidence match is found, it presents the known-good command to the user and asks if they would prefer to run it instead.

**Stage 4: Execution & The Learning Loop**
*   The tool executes the final command string as a subprocess.
*   **On Success:** The tool prints the (potentially redacted) output and the session ends. If the successful command was the result of a user correction, it proceeds to Stage 5.
*   **On Failure:**
    *   If `ci_mode` is ON, it prints the redacted error to `stderr` and exits with a non-zero status code.
    *   If `ci_mode` is OFF, it enters the **Troubleshooting Session**, displaying the error and prompting the user for a corrected command. The process loops back to the start of Stage 4 with the new command.

**Stage 5: Documentation**
*   If a command succeeded as a result of a user correction within the Troubleshooting Session, the tool prompts the user to save the final, working command to `cookbook.md`.

---

## 5. CLI Contract

The tool is defined by its command-line interface.

### 5.1. `myoci run [OCI_COMMAND_STRING...]`
-   **Purpose:** The primary entry point for the Validator workflow.
-   **Arguments:**
    -   `OCI_COMMAND_STRING`: (string, required) The raw OCI command and its arguments, which are captured as a list of strings.
-   **Flags / Options:**
    -   `--ci`: (boolean, default: `False`) Enables non-interactive mode. The tool will fail on ambiguity instead of prompting.
    -   `--redact` / `--no-redact`: (boolean, default: `True`) Toggles PII redaction on all `stdout` and `stderr` produced by the tool.

---

## 6. Build System & Packaging

-   **Dependency Management:** All dependencies are managed in `pyproject.toml` and are intended to be installed with `uv` or `pip`.
-   **Packaging:** The `[project.scripts]` table in `pyproject.toml` defines the `myoci` console script entry point.
-   **Installation:** The canonical installation method is via `pipx install .`. This installs the application and its dependencies into an isolated environment while making the `myoci` executable globally available in the user's path, without requiring virtual environment activation for day-to-day use.

---

## 7. Operational Model

-   **User Responsibilities:**
    -   The user is responsible for the initial installation and configuration of the underlying OCI CLI (`~/.oci/config`).
    -   The user must maintain the local `.env` file with their specific configuration.
    -   To share learnings across machines, the user is responsible for committing the `cookbook.md` file to a version control system (e.g., Git) and synchronizing it.
```
