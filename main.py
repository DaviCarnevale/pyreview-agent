#!/usr/bin/env python3
"""Main CLI entrypoint for PyReview Agent — AI-Powered Python Code Reviewer."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from agent.core import ReviewAgent
from agent.tools import CodeInspector
from config.settings import get_settings


# ANSI Color Codes for enhanced terminal aesthetics
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_banner() -> None:
    """Print welcoming ASCII banner."""
    print(f"""
{CYAN}{BOLD}==================================================================
  🔍 PyReview Agent — AI-Powered Python Code Reviewer
  Automated Architectural, Security, and Code Quality Inspection
=================================================================={RESET}
""")


def progress_logger(status: str) -> None:
    """Callback to display agent tool execution steps in real time."""
    print(f"{YELLOW}  ➜ {status}{RESET}")


def interactive_session(agent: ReviewAgent) -> None:
    """Run an interactive conversation loop allowing developer follow-up questions."""
    print(f"\n{GREEN}{BOLD}💬 Interactive Session Active{RESET}")
    print(f"{DIM}Ask follow-up questions about the review, request refactoring, or type 'exit' to quit.{RESET}\n")

    while True:
        try:
            user_input = input(f"{CYAN}{BOLD}You › {RESET}").strip()
            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit", "q"}:
                print(f"\n{CYAN}👋 Thank you for using PyReview Agent. Happy coding!{RESET}\n")
                break

            if user_input.lower() == "clear":
                print("\033[H\033[J", end="")
                continue

            print(f"\n{DIM}Thinking and inspecting...{RESET}")
            response = agent.ask(user_input, progress_callback=progress_logger)
            print(f"\n{BOLD}🤖 PyReview Agent:{RESET}\n")
            print(response)
            print(f"\n{DIM}{'-' * 60}{RESET}\n")

        except KeyboardInterrupt:
            print(f"\n\n{CYAN}Session interrupted by user. Exiting PyReview Agent.{RESET}\n")
            break
        except Exception as err:
            print(f"\n{RED}Error processing request: {err}{RESET}\n")


def main() -> None:
    """Parse CLI arguments, initialize components, and launch code review."""
    parser = argparse.ArgumentParser(
        description="PyReview Agent: Inspect and review local Python projects with AI."
    )
    parser.add_argument(
        "--path",
        "-p",
        type=str,
        default=None,
        help="Path to the Python project directory to analyze (default: prompts in terminal).",
    )
    parser.add_argument(
        "--focus",
        "-f",
        type=str,
        default=None,
        help="Optional specific focus for review (e.g., 'security', 'error handling', 'performance').",
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        help="OpenAI model override (e.g. gpt-4o, gpt-4o-mini).",
    )

    args = parser.parse_args()
    print_banner()

    # Load and validate settings
    try:
        settings = get_settings()
        if args.model:
            settings.openai_model = args.model

        # Check API key
        if not settings.openai_api_key:
            print(f"{RED}{BOLD}Error:{RESET} OPENAI_API_KEY environment variable not found.")
            print(f"Please create a {BOLD}.env{RESET} file based on {BOLD}.env.example{RESET} or export OPENAI_API_KEY.\n")
            sys.exit(1)

    except Exception as exc:
        print(f"{RED}Failed to load configuration:{RESET} {exc}")
        sys.exit(1)

    # Resolve target directory
    target_input = args.path
    if not target_input:
        target_input = input(f"{BOLD}Enter project directory to review [default: current directory (.):]{RESET} ").strip()
        if not target_input:
            target_input = "."

    project_dir = Path(target_input).resolve()
    if not project_dir.exists():
        print(f"\n{RED}Error:{RESET} Directory '{project_dir}' does not exist.")
        sys.exit(1)
    if not project_dir.is_dir():
        print(f"\n{RED}Error:{RESET} '{project_dir}' is not a directory.")
        sys.exit(1)

    # Initialize sandboxed CodeInspector
    try:
        inspector = CodeInspector(
            base_dir=project_dir,
            max_file_lines=settings.max_file_lines,
            max_file_bytes=settings.max_file_bytes,
        )
    except Exception as exc:
        print(f"\n{RED}Failed to initialize CodeInspector:{RESET} {exc}")
        sys.exit(1)

    # Pre-flight check: list files
    preview = inspector.list_python_files()
    total_files = preview.get("total_files", 0)
    print(f"\n{BOLD}Target Project:{RESET} {project_dir}")
    print(f"{BOLD}Model:{RESET} {settings.openai_model}")
    print(f"{BOLD}Discovered Python Files:{RESET} {total_files}")

    if total_files == 0:
        print(f"{YELLOW}Warning: No Python (.py) files found in '{project_dir}'.{RESET}")
        confirm = input("Do you still want to proceed? (y/N): ").strip().lower()
        if confirm != "y":
            print("Exiting.")
            sys.exit(0)

    # Initialize ReviewAgent
    agent = ReviewAgent(inspector=inspector, settings=settings)

    print(f"\n{CYAN}{BOLD}Starting autonomous code review...{RESET}")
    report = agent.review_project(
        custom_instructions=args.focus,
        progress_callback=progress_logger,
    )

    print(f"\n{GREEN}{BOLD}==================== REVIEW REPORT ===================={RESET}\n")
    print(report)
    print(f"\n{GREEN}{BOLD}======================================================={RESET}\n")

    # Enter interactive session
    interactive_session(agent)


if __name__ == "__main__":
    main()
