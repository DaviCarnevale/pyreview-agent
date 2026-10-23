# PyReview Agent — AI-Powered Python Code Reviewer

[![Python Version](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)
[![Code Style](https://img.shields.io/badge/code%20style-pep8-brightgreen.svg)](https://pep8.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-17%20passed-success.svg)](#running-tests)

An autonomous AI agent designed to perform in-depth architectural, security, and quality code reviews of local Python projects. Unlike static linters or superficial LLM chatbots, **PyReview Agent** uses **autonomous tool calling (function calling)** to dynamically explore directory trees, read source files, and reason about real codebases with full situational context before generating actionable reviews.

---

## Table of Contents

- [Key Features](#key-features)
- [How the Agent Works](#how-the-agent-works)
- [Architecture & File Structure](#architecture--file-structure)
- [Tech Stack](#tech-stack)
- [Installation & Setup](#installation--setup)
- [Usage Guide](#usage-guide)
  - [Basic Review](#basic-review)
  - [Targeting a Specific Project](#targeting-a-specific-project)
  - [Focusing on Specific Aspects](#focusing-on-specific-aspects)
  - [Interactive Q&A Session](#interactive-qa-session)
- [Security & Sandboxing](#security--sandboxing)
- [Running Tests](#running-tests)
- [Known Limitations & Future Roadmap](#known-limitations--future-roadmap)
- [License](#license)

---

## Key Features

- **Autonomous Project Discovery:** Scans project directories and discovers relevant Python source files while safely ignoring noisy directories (`.git`, `.venv`, `__pycache__`, `build`, etc.).
- **Dynamic File Inspection:** Uses native OpenAI tool calling (`list_python_files`, `read_python_file`) to inspect only the files it decides are necessary for a comprehensive review.
- **Holistic Code Quality Evaluation:**
  - **Bugs & Edge Cases:** Identifies unhandled exceptions, race conditions, and logical flaws.
  - **Design & Architecture:** Evaluates OOP principles, SOLID guidelines, modularity, and separation of concerns.
  - **Pythonic Idioms:** Checks adherence to PEP 8, type hints, docstrings, and modern Python features.
  - **Security Auditing:** Flags insecure path operations, exposed credentials, and potential injection risks.
- **Structured Review Reports:** Emits prioritized reports with executive summaries, strengths, issues categorized by severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), and concrete refactored code snippets.
- **Interactive Multi-Turn Session:** Developer can ask follow-up questions, request specific refactoring examples, or query particular modules without losing conversation context.
- **Hardened Sandboxing:** Strict path traversal prevention, symlink boundary checks, file size caps, and iteration limits ensure that the agent runs safely on untrusted codebases.

---

## How the Agent Works

Rather than dumping entire codebases into an LLM prompt (which triggers token exhaustion) or using opaque multi-agent frameworks, **PyReview Agent** implements an explicit, transparent reasoning and tool execution loop:

```
                  ┌───────────────────────────────┐
                  │       Developer Input         │
                  │   (Project Path & Request)    │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Agent Loop (ReviewAgent)                    │
│                                                                 │
│  1. Prompt Engine: Builds System Prompt + Guidelines            │
│  2. LLM Call: Sends conversation + OpenAI Tools schema           │
│                                                                 │
│       ┌───────────── Model Decision ─────────────┐              │
│       ▼                                          ▼              │
│  [Tool Calls Requested]                    [Final Response]     │
│       │                                          │              │
│       ▼                                          ▼              │
│  3. CodeInspector Execution:              Terminate loop and    │
│     - list_python_files()                 deliver markdown      │
│     - read_python_file()                  report to developer   │
│       │                                                         │
│       ▼                                                         │
│  4. Append tool results to history                              │
│  5. Loop back to step 2 (within max_iterations safety bound)    │
└─────────────────────────────────────────────────────────────────┘
```

1. **Step 1 — Discovery:** The model receives the user request and invokes `list_python_files` to understand the directory layout and module distribution.
2. **Step 2 — Selective Reading:** The model examines file names and decides which source files to read by invoking `read_python_file`.
3. **Step 3 — Analysis:** Having seen the code, the model synthesizes findings across modules and generates a structured, prioritized report.
4. **Step 4 — Q&A Continuity:** The conversation remains active in memory, allowing developers to ask follow-up questions about specific recommendations.

---

## Architecture & File Structure

```
pyreview-agent/
├── agent/
│   ├── __init__.py         # Public exports for the agent package
│   ├── core.py             # Agent loop orchestration, system prompts & OpenAI integration
│   └── tools.py            # Sandboxed inspection tools & OpenAI function schemas
├── config/
│   ├── __init__.py         # Config package initialization
│   └── settings.py         # Pydantic-validated environment configuration
├── tests/
│   ├── __init__.py
│   ├── test_agent.py       # Unit and mock tests for agent loop and error handling
│   └── test_tools.py       # Unit tests for CodeInspector, path safety & exclusions
├── .env.example            # Configuration template
├── .gitignore              # Standard Python and environment exclusions
├── main.py                 # CLI interface with interactive terminal loop
├── README.md               # Project documentation
└── requirements.txt        # Production and testing dependencies
```

### Module Responsibilities

- **`agent/core.py` (`ReviewAgent`)**: Manages the message history, calls the OpenAI API, handles rate limits and connection errors, and coordinates the execution loop.
- **`agent/tools.py` (`CodeInspector`)**: Executes file-system read operations with path sandboxing, size limits, and canonicalization.
- **`config/settings.py` (`Settings`)**: Validates environment variables (`OPENAI_API_KEY`, model selection, temperature, iteration limits) using Pydantic.
- **`main.py`**: Provides the CLI interface, real-time tool progress logging, ANSI color formatting, and the interactive terminal Q&A loop.

---

## Tech Stack

- **Language:** Python 3.13+
- **LLM Integration:** Official OpenAI Python SDK (`openai>=1.12.0`)
- **Data & Config Validation:** `pydantic>=2.0.0`
- **Environment Management:** `python-dotenv>=1.0.0`
- **Testing Suite:** `pytest>=8.0.0`

> **Design Choice:** We deliberately avoided heavy agent frameworks (such as LangChain or CrewAI) to demonstrate a transparent, robust implementation of the agentic tool-calling cycle from scratch.

---

## Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/your-username/pyreview-agent.git
cd pyreview-agent
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
Copy `.env.example` to `.env` and insert your OpenAI API key:
```bash
cp .env.example .env
```

Edit `.env`:
```env
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.2
MAX_AGENT_ITERATIONS=12
MAX_FILE_LINES=800
MAX_FILE_BYTES=200000
```

---

## Usage Guide

### Basic Review
Run the agent without arguments to be prompted interactively for a project path:
```bash
python main.py
```

### Targeting a Specific Project
Specify the project path directly using `--path` (or `-p`):
```bash
python main.py --path /path/to/my-python-project
```

### Focusing on Specific Aspects
You can instruct the agent to concentrate on specific areas (e.g. security, error handling, performance):
```bash
python main.py --path ./my_project --focus "security vulnerabilities and exception handling"
```

### Overriding the Model
```bash
python main.py --path ./my_project --model gpt-4o
```

### Interactive Q&A Session
Once the initial report is rendered, the agent enters an interactive shell:
```
💬 Interactive Session Active
Ask follow-up questions about the review, request refactoring, or type 'exit' to quit.

You › How can I refactor calculate_total in billing.py using the Strategy Pattern?
  ➜ 📖 Inspecting code in 'billing.py'...

🤖 PyReview Agent:
Here is a refactored implementation using the Strategy Pattern...
```

Type `exit`, `quit`, or press `Ctrl+C` to terminate the session.

---

## Security & Sandboxing

When reviewing arbitrary or unfamiliar repositories, security is paramount:

1. **Path Traversal Defense:** Every input path is resolved using `Path.resolve()` and strictly verified with `path.relative_to(base_dir)`. Attempts to escape via `../` or `/etc/...` are blocked immediately.
2. **Symlink Escape Defense:** Canonical resolution dereferences symlinks; if a symlink inside the project points outside the project boundary, it is rejected with a `SecurityError`.
3. **No Code Execution:** The agent **never** executes inspected files or shell commands. It treats all Python code strictly as inert text data.
4. **Prompt Injection Defense:** System prompt instructions mandate that any instructions found inside reviewed files (e.g. within comments or strings) must be treated as untrusted text, preventing prompt hijacking.
5. **Resource Limits:** File reads are capped by line count (`MAX_FILE_LINES`) and byte size (`MAX_FILE_BYTES`) to prevent denial-of-service and token exhaustion. Loop iterations are capped by `MAX_AGENT_ITERATIONS`.
6. **Credential Protection:** Review reports and logs never display the `OPENAI_API_KEY` or environment secrets.

---

## Running Tests

PyReview Agent includes a test suite covering tools, security boundaries, edge cases, and the agent loop (using mock OpenAI responses so **no active API key or quota is required**):

```bash
pytest -v
```

### Test Coverage Highlights:
- ✅ Directory listing excluding ignored folders (`.git`, `.venv`, `__pycache__`).
- ✅ Path traversal defense (`../`, `../../`, absolute paths).
- ✅ Symlink escape rejection.
- ✅ Handling of non-existent files and unauthorized extensions.
- ✅ Max line truncation and byte size limits.
- ✅ Complete multi-turn agent tool-calling loop.
- ✅ Interactive context retention across turns.
- ✅ Error handling for `AuthenticationError`, `RateLimitError`, and `APIConnectionError`.
- ✅ Max loop iterations guard.

---

## Known Limitations & Future Roadmap

### Current Limitations:
- **Scope per Turn:** Focuses strictly on `.py` files. Config files like `pyproject.toml` or `Dockerfile` are not yet inspected by default.
- **Model Token Limits:** Projects with dozens of very large files require targeted inspection rather than exhaustive reading of every line.
- **Model Dependency:** Analysis depth and nuance rely on the capabilities of the configured model (e.g., `gpt-4o` vs `gpt-4o-mini`).

### Future Roadmap:
- [ ] Support for non-Python manifests (`pyproject.toml`, `setup.cfg`, `Dockerfile`).
- [ ] Integration with AST parsing tools (`ast` module) to provide syntax-tree summaries before reading raw lines.
- [ ] Automated generation of git diff patches (`.patch`) for suggested fixes.
- [ ] HTML / PDF export for generated audit reports.

---

## License

This project is licensed under the [MIT License](LICENSE).
