"""Entry point for the tools.prod_tui CLI.

Provides a unified interface to the production TUI test harness.
"""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m tools.prod_tui <command> [args...]")
        print("")
        print("Commands:")
        print("  tmux       Manage the local tmux session (start, stop, send, capture)")
        print("  smoke      Run Level 1 and 2 smoke tests")
        print("  job        Run the Level 3 controlled job")
        print("  level      Run Level 4-6 controlled scenarios (--level 4|5|6)")
        return 1

    command = sys.argv[1]
    argv = sys.argv[2:]

    if command == "tmux":
        from tools.prod_tui.robocop_tmux import main as tmux_main
        return tmux_main(argv)
    elif command == "smoke":
        from tools.prod_tui.smoke_test import main as smoke_main
        return smoke_main(argv)
    elif command == "job":
        from tools.prod_tui.controlled_job import main as job_main
        return job_main(argv)
    elif command == "level":
        from tools.prod_tui.levels import main as level_main
        return level_main(argv)
    else:
        print(f"Unknown command: {command}")
        print("Available commands: tmux, smoke, job, level")
        return 1


if __name__ == "__main__":
    sys.exit(main())
