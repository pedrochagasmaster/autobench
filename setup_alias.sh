#!/bin/bash

# setup_alias.sh
# Helper script to set up the 'peer_benchmark' alias for the user

# Get the absolute path to the run_tool.sh script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
TOOL_SCRIPT="$SCRIPT_DIR/run_tool.sh"

# Try to make the tool script executable (may fail for non-owners on shared filesystems)
# This is non-critical if the file already has execute permissions
if ! chmod +x "$TOOL_SCRIPT" 2>/dev/null; then
    echo "Note: Could not modify permissions (you may not be the file owner)."
    if [ -x "$TOOL_SCRIPT" ]; then
        echo "      The script is already executable - continuing."
    else
        echo "WARNING: $TOOL_SCRIPT is not executable and could not be made executable."
        echo "         Ask the file owner to run: chmod +x $TOOL_SCRIPT"
    fi
fi

# Determine shell config file
# Check for kshrc first since the user seems to be using ksh
if [ -f "$HOME/.kshrc" ]; then
    SHELL_RC="$HOME/.kshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -f "$HOME/.bash_profile" ]; then
    SHELL_RC="$HOME/.bash_profile"
elif [ -f "$HOME/.profile" ]; then
    SHELL_RC="$HOME/.profile"
else
    # Default to .profile if nothing else exists, as it's widely supported
    SHELL_RC="$HOME/.profile"
fi

# Check if function already exists in the config file
if grep -q "peer_benchmark()" "$SHELL_RC"; then
    echo "Function 'peer_benchmark' already exists in $SHELL_RC"
    echo "Please verify it points to: $TOOL_SCRIPT"
else
    echo "Adding function to $SHELL_RC..."
    echo "" >> "$SHELL_RC"
    echo "# Peer Benchmark Tool Function" >> "$SHELL_RC"
    echo "peer_benchmark() {" >> "$SHELL_RC"
    echo "    \"$TOOL_SCRIPT\" \"\$@\"" >> "$SHELL_RC"
    echo "}" >> "$SHELL_RC"
    echo "Function added successfully."
fi

echo "---------------------------------------------------"
echo "Setup complete."
echo "To use the tool immediately, run:"
echo "source $SHELL_RC"
echo "Then you can type 'peer_benchmark' to start the tool."
echo "---------------------------------------------------"
