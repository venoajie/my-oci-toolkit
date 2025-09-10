
<!-- FILENAME: PROJECT_BLUEPRINT.md -->
```markdown
# Project Blueprint: MyOCI Toolkit

<!-- Version: 4.0 -->
<!-- This document outlines the architecture and operational principles of the MyOCI Toolkit, reflecting the evolution to a safety-first "Architect" philosophy. -->

## 1. System Overview and Core Purpose

This document is the canonical source of truth for the architectural principles and governance of the MyOCI Toolkit.

MyOCI is a standalone, user-centric command-line application designed to act as a personal architect for the native Oracle Cloud Infrastructure (`oci`) CLI. Its primary purpose is to **make interactions with the OCI CLI safer, more reliable, and self-documenting by providing a predictable and safe execution environment.** It is specifically tailored to prevent frustrating debugging cycles and to help users build a personal, trusted library of known-good commands.

It is not a replacement for the OCI CLI, but rather a smart, stateful proxy that sits between the user and the underlying tool.

### 1.1. Ecosystem Glossary

-   **Validator Mode (`myoci run`):** The primary operational mode. It intercepts a raw `oci` command and subjects it to a multi-stage validation and execution pipeline.
-   **Learning Mode (`myoci learn`):** The mechanism for capturing knowledge. A user provides a working `oci` command, and the tool interactively helps build a reusable validation template.
-   **Template Management Commands (`myoci templates`):** A command group (`list`, `show`, `delete`) that allows users to safely manage their local library of validation templates.
-   **Validation Templates (`myoci/templates/*.yaml`):** Local, version-controlled YAML files that serve as the tool's long-term memory for command syntax.
-   **Interactive Failure Recovery:** A feature that analyzes specific OCI CLI error messages (e.g., "Missing option") and offers to retry the command *only if* a high-confidence fix (e.g., an exact environment variable match) is available.

---

## 2. Core Architectural Principles (Non-Negotiable)

### 2.1. Augmentation, Not Replacement
The tool **MUST NOT** re-implement the OCI CLI's functionality. It is a thin, intelligent wrapper that ultimately constructs and executes the real `oci` command.

### 2.2. Predictability Over Magic
The tool **MUST NOT** attempt to guess the user's intent. Ambiguous inputs, such as misspelled environment variables, **MUST** result in an immediate and clear failure. Features like fuzzy matching are explicitly forbidden. The tool's behavior must be completely deterministic.

### 2.3. The Proactive Learning Loop
The core value proposition is the `Succeed -> Learn -> Validate` workflow. Every successful command is an opportunity for the tool to prompt the user to `learn` from it, thereby building a personal, trusted, and version-controllable knowledge base.

### 2.4. Safe by Default
User safety is paramount. PII redaction is enabled by default on all output, including debug messages and retry commands. All interactive prompts that could lead to a state change **MUST** default to "No". The path of least resistance must always be the safest one.

---

## 3. System Architecture & Components

MyOCI is a single-entrypoint application that orchestrates a pipeline of validation, execution, and post-execution analysis.

-   **Typer CLI Application (`myoci/cli.py`):** The main entry point and workflow orchestrator. Manages the `run`, `learn`, and `templates` command groups.
-   **Core Logic (`myoci/core.py`):** Contains the application's "brain."
    -   **Validation Helpers:** Functions for parsing commands and validating them against schemas. Includes robust error handling for malformed template files.
    -   **Execution Helpers:** The `execute_command` function, which reliably captures output by setting the `OCI_CLI_PAGER` environment variable.
    -   **Analysis Helpers:** Functions that analyze command results (`analyze_failure_and_suggest_fix`) based on strict, high-confidence patterns.
    -   **Knowledge Dictionaries:** Internal data structures (`BEST_PRACTICE_ARGS`) that store low-risk, opinionated suggestions for the `learn` workflow.
-   **Configuration & State Files:**
    -   **`.env`:** Stores user-specific variables.
    -   **`myoci/templates/*.yaml`:** Stores learned validation schemas for command syntax.

---

## 4. The Command Lifecycle (Validator Workflow)

This sequence describes the step-by-step process for the `myoci run` command.

**Stage 1-3: Pre-Execution**
*   The tool resolves `$VARIABLES` from the environment. If a variable is not found, the process fails immediately.
*   It performs pre-flight file checks.
*   It validates the command against a matching template if one exists. A malformed template will cause a hard failure.

**Stage 4: Execution**
*   The tool executes the final, fully-resolved command string as a subprocess, setting `OCI_CLI_PAGER='cat'` to ensure reliable output capture.

**Stage 5: Post-Execution Analysis**
*   The tool analyzes the result (`return_code`, `stdout`, `stderr`) to determine the next action.
*   **On Success with Output:** The (redacted) output is printed. If no template was used, the tool offers to run the `learn` command.
*   **On Success with NO Output:** The tool prints a clear message stating that the command succeeded but found no resources (e.g., `myoci note: ...`). The session then concludes successfully. The tool **MUST NOT** suggest alternative command scopes or parameters.
*   **On Failure:** The tool prints the (redacted) failure details. It then checks if the failure is a known, fixable pattern. If a pattern matches AND a high-confidence solution exists (e.g., an exact environment variable match for a missing option), it offers to retry the command. Otherwise, it reports the failure and exits.
```
