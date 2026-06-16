"""Command-line entry point for Dispatch."""

import argparse

from .app import DispatchApp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dispatch",
        description="Server-side TUI for launching and supervising Impala Jobs.",
    )
    parser.parse_args()
    DispatchApp().run()


if __name__ == "__main__":
    main()
