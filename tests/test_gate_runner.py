"""Tests for gate runner command parsing and expectation enforcement."""

import shlex


def test_gate_command_parser_preserves_quoted_entity_names() -> None:
    command = 'py benchmark.py share --entity "BANCO SANTANDER" --csv data/readme_demo.csv'

    parsed = ["/usr/bin/python3"] + shlex.split(command[3:])

    assert parsed[3] == "--entity"
    assert parsed[4] == "BANCO SANTANDER"


def test_gate_command_parser_handles_single_word_entity() -> None:
    command = "py benchmark.py share --entity Target --csv data/readme_demo.csv"

    parsed = ["/usr/bin/python3"] + shlex.split(command[3:])

    assert parsed[3] == "--entity"
    assert parsed[4] == "Target"


def test_shlex_split_preserves_paths_with_spaces() -> None:
    command = 'benchmark.py share --csv "data/my data/file.csv" --entity Target'

    parsed = shlex.split(command)

    assert parsed[2] == "--csv"
    assert parsed[3] == "data/my data/file.csv"
