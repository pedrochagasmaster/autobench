from __future__ import annotations

import sys

from tools.prod_tui.harness import main as harness_main


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: py -m tools.prod_tui <command> [args...]")
        print("")
        print("Commands:")
        print("  smoke      Run configured SSH/tmux smoke checks and write a JSON report")
        print("  drift      Build a deployable-file drift manifest for comparison")
        print("  help       Show this help")
        return 1
    if sys.argv[1] == "help":
        sys.argv = [sys.argv[0]]
        return main()
    return harness_main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
