#!/bin/bash

# run_tool.sh
# Wrapper script to run the Peer Benchmark Tool TUI from any location

# Get the directory where this script is located
# Use $0 instead of BASH_SOURCE for better portability across shells
SCRIPT_DIR="$( cd "$( dirname "$0" )" &> /dev/null && pwd )"

# Define paths
VENV_DIR="$SCRIPT_DIR/.venv"
TUI_APP="$SCRIPT_DIR/tui_app.py"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Error: Virtual environment not found at $VENV_DIR"
    echo "Please run setup_remote_env.sh first."
    exit 1
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Run the TUI application
# We pass all arguments to the Python script, though TUI usually doesn't take many
py "$TUI_APP" "$@"

# Deactivate virtual environment (optional, as script exit will handle it)
deactivate
