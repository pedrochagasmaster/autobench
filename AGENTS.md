# Autobench Agent Guide

Autobench is a privacy-compliant peer benchmark tool. Its CLI is `benchmark.py`,
its TUI is `tui_app.py`, and shared behavior belongs in `core/`.

Follow [CONTRIBUTING.md](CONTRIBUTING.md). Work from current GitHub `main`, use a
short-lived branch, run `python -m pytest`, and finish with a GitHub pull
request.

Agents may create branches, commit, push a branch, and open a pull request when
requested. Agents must not merge, change branch protection, create release
tags, push Bitbucket, or deploy without explicit Release Operator instruction.

Do not weaken privacy enforcement, bypass publishable-output validation, or
commit generated artifacts, reports, credentials, RSA passcodes, or Kerberos
secrets.

Release Operators use [docs/release-workflow.md](docs/release-workflow.md).
