#!/bin/bash

# setup_alias.sh
# Helper script to set up the 'peer_benchmark' alias for the user

# Get the absolute path to the run_tool.sh script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
TOOL_SCRIPT="$SCRIPT_DIR/run_tool.sh"

# Make sure the tool script is executable
chmod +x "$TOOL_SCRIPT"

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
