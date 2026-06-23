#!/bin/bash

# run_tool.sh
# Wrapper script to run the Peer Benchmark Tool from any location

# Get the directory where this script is located
# Use $0 instead of BASH_SOURCE for better portability across shells
SCRIPT_DIR="$( cd "$( dirname "$0" )" &> /dev/null && pwd )"

# Define paths
VENV_DIR="$SCRIPT_DIR/.venv"
TUI_APP="$SCRIPT_DIR/tui_app.py"
BENCHMARK_APP="$SCRIPT_DIR/benchmark.py"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Error: Virtual environment not found at $VENV_DIR"
    echo "Please run setup_remote_env.sh first."
    exit 1
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Run the requested interface.
# No arguments (or "tui") opens the Textual app. CLI subcommands are routed to
# benchmark.py so documented server smoke commands work through this wrapper.
case "${1:-tui}" in
    tui)
        if [ "${1:-}" = "tui" ]; then
            shift
        fi
        python "$TUI_APP" "$@"
        ;;
    share|rate|config)
        python "$BENCHMARK_APP" "$@"
        ;;
    *)
        echo "Usage: ./run_tool.sh [tui|share|rate|config] [options...]"
        echo "Examples:"
        echo "  ./run_tool.sh tui"
        echo "  ./run_tool.sh share --help"
        echo "  ./run_tool.sh config list"
        exit 2
        ;;
esac

# Deactivate virtual environment (optional, as script exit will handle it)
deactivate
