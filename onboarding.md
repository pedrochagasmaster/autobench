# Autobench Onboarding

After the operator deploys the shared `/ads_storage/autobench` tree, each user
runs the installer once. The installer keeps your personal runtime under
`/ads_storage/$USER/.autobench`.

## Install

```bash
cd /ads_storage/autobench
./install.sh
```

Do not run it with `source`. If the installer prints this command, run it in the
current shell or open a new SSH session:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Launch

Start the guided terminal UI from the directory where you keep inputs and
outputs:

```bash
cd /path/to/my/work
autobench
```

The CLI is available as `autobench-cli`:

```bash
autobench-cli config list
autobench-cli share --help
```

## Quick Checks

If `autobench` is not found:

```bash
export PATH="$HOME/.local/bin:$PATH"
which autobench
```

If the TUI opens but file paths fail, confirm the CSV path is readable from the
Edge Node session and rerun from a working directory where you can write output
files.

If setup still fails, send the installer output and the result of
`which autobench` to the tool owner.
