# Contributing to Autobench

Development ends with a reviewed GitHub pull request. Deployment is a separate
Release Operator responsibility.

## Contributor

Local developers and Cursor agents follow the same path:

```bash
git switch main
git pull --ff-only origin main
git switch -c <short-branch-name>
python -m pip install -e ".[dev]"
python -m pytest
```

Commit the focused change, push the branch to GitHub, and open a pull request
against `main`. Contributors without write access may use a fork.

Include the test result and release risk in the pull request. Do not commit
generated workbooks, CSVs, audit packages, reports, local data, credentials, or
passcodes.

`requirements.txt` and `constraints.txt` are production offline-bundle inputs;
they are not contributor setup files.

## Maintainer

Merge only after CI passes on Python 3.10 and 3.12 and one human Maintainer
approves. Use squash merge and delete the merged branch. Do not push directly
to `main`.

Release work starts only after merge and is documented in
[docs/release-workflow.md](docs/release-workflow.md).
