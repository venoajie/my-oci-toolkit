<!-- FILENAME: PROJECT_BLUEPRINT.md -->
```markdown
# Project Blueprint: MyOCI Toolkit

<!-- Version: 3.0 -->
<!-- This document outlines the architecture and operational principles of the MyOCI Toolkit, reflecting the evolution to a "Guide" philosophy with post-execution analysis. -->

## 1. System Overview and Core Purpose

This document is the canonical source of truth for the architectural principles and governance of the MyOCI Toolkit.

MyOCI is a standalone, user-centric command-line application designed to act as an intelligent assistant or "personal architect" for the native Oracle Cloud Infrastructure (`oci`) CLI. Its primary purpose is to **make interactions with the OCI CLI safer, more reliable, and self-documenting by validating inputs, analyzing results, and guiding the user toward a successful outcome.** It is specifically tailored to prevent frustrating debugging cycles and to enhance workflows driven by AI-generated or manually written commands.

It is not a replacement for the OCI CLI, but rather a smart, stateful proxy that sits between the user and the underlying tool.

### 1.1. Ecosystem Glossary

-   **Validator Mode (`myoci run`):** The primary operational mode. It intercepts a raw `oci` command and subjects it to a multi-stage validation and execution pipeline.
-   **Learning Mode (`myoci learn`):** The mechanism for capturing knowledge. A user provides a working `oci` command, and the tool interactively helps build a reusable validation template, suggesting best practices along the way.
-   **Validation Templates (`templates/*.yaml`):** Local, version-controlled YAML files that serve as the tool's long-term memory for command syntax.
-   **Knowledge Dictionaries (`core.py`):** Internal Python data structures (`BEST_PRACTICE_ARGS`, `BROADENING_SUGGESTIONS`) that store the tool's semantic, workflow-related knowledge.
-   **Interactive Failure Recovery:** A feature that analyzes OCI CLI error messages (e.g., "Missing option") and offers to retry the command with a fix sourced from the user's `.env` file.
-   **Intelligent Broadening:** A feature that detects when a `list` command for a narrow scope (like a compartment) returns no results, and offers to re-run the search on a broader scope (like the tenancy).

---

## 2. Core Architectural Principles

### 2.1. Augmentation, Not Replacement
The tool **MUST NOT** re-implement the OCI CLI's functionality. It is a thin, intelligent wrapper that ultimately constructs and executes the real `oci` command.

### 2.2. Guidance Over Prevention (The "Guide" Philosophy)
The tool's primary goal is to help the user succeed. It **SHOULD NOT** preemptively block valid-but-ambiguous OCI CLI features (like using a Tenancy ID for a Compartment ID). Instead, it **MUST** analyze the *results* of such commands and offer intelligent, context-aware next steps to guide the user.

### 2.3. The Proactive Learning Loop
The core value proposition is the `Succeed -> Learn -> Validate` workflow, enhanced with proactive suggestions. Every successful command, whether on the first try or after a guided fix, is an opportunity for the tool to prompt the user to `learn` from it.

### 2.4. Safe by Default
User safety is paramount. PII redaction is enabled by default on all output, including debug messages and retry commands, to prevent accidental exposure of sensitive identifiers. The user must explicitly disable this feature (`--no-redact`).

---

## 3. System Architecture & Components

MyOCI is a single-entrypoint application that orchestrates a pipeline of validation, execution, and post-execution analysis.

-   **Typer CLI Application (`myoci/cli.py`):** The main entry point and workflow orchestrator.
-   **Core Logic & Knowledge (`myoci/core.py`):** Contains the application's "brain."
    -   **Validation Helpers:** Functions for parsing commands and validating them against schemas.
    -   **Execution Helpers:** The `execute_command` function, which reliably captures output by setting the `OCI_CLI_PAGER` environment variable.
    -   **Analysis Helpers:** Functions that analyze command results (`analyze_failure_and_suggest_fix`).
    -   **Knowledge Dictionaries:** The `BEST_PRACTICE_ARGS` and `BROADENING_SUGGESTIONS` data structures that drive the intelligent guidance features.
-   **Configuration & State Files:**
    -   **`.env`:** Stores user-specific variables.
    -   **`myoci/templates/*.yaml`:** Stores learned validation schemas for command syntax.

---

## 4. The Command Lifecycle (Validator Workflow)

This sequence describes the step-by-step process for the `myoci run` command.

**Stage 1-3: Pre-Execution**
*   The tool resolves variables, performs pre-flight file checks, and validates the command against a matching template if one exists.

**Stage 4: Execution**
*   The tool executes the final, fully-resolved command string as a subprocess, setting `OCI_CLI_PAGER='cat'` to ensure reliable output capture.

**Stage 5: Post-Execution Analysis & Guidance**
*   The tool analyzes the result (`return_code`, `stdout`, `stderr`) to determine the next action.
*   **On Success with Output:** The (redacted) output is printed. If no template was used, the tool offers to run the `learn` command.
*   **On Success with NO Output:** The tool prints a clear message stating that the command succeeded but found no resources. It then checks its `BROADENING_SUGGESTIONS` knowledge base. If a match is found, it offers to re-run the command with a broader scope.
*   **On Failure:** The tool prints the (redacted) failure details. It then checks if the failure is a known, fixable pattern (e.g., "Missing option"). If so, it offers to retry the command with a suggested fix.

---