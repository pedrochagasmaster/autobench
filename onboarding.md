# Dispatch Onboarding

Welcome to Dispatch. After the administrator deploys the shared
`/ads_storage/dispatch` tree, each user only needs to run the installer once.

## Install

Run the installer directly from the deployed tree:

```bash
cd /ads_storage/dispatch
./install.sh
```

Do not run it with `source`. The installer creates your personal Dispatch
runtime under `/ads_storage/$USER/.dispatch`, writes the `dispatch` launcher to
`~/.local/bin/dispatch`, and updates your shell profile so new sessions can find
the command.

If the installer says:

```bash
To use dispatch in this shell now:
  export PATH="$HOME/.local/bin:$PATH"
```

copy and run that one command. Otherwise, open a new SSH session.

## Launch Your First Job

Go to the directory that contains your SQL files and start Dispatch:

```bash
cd /path/to/your/sql/files
dispatch
```

If the TUI opens, setup is complete.

## Quick Checks

If `dispatch` is not found:

```bash
export PATH="$HOME/.local/bin:$PATH"
which dispatch
```

If `which dispatch` still prints nothing, rerun the installer and keep the full
output for support:

```bash
cd /ads_storage/dispatch
./install.sh
```

If Dispatch opens but reports Kerberos problems, run `kinit`, confirm the ticket
with `klist`, then launch `dispatch` again.
