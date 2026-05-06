import shlex


def test_gate_command_parser_preserves_quoted_entity_names() -> None:
    command = 'py benchmark.py share --entity "BANCO SANTANDER" --csv data/readme_demo.csv'

    parsed = ["/usr/bin/python3"] + shlex.split(command[3:])

    assert parsed[3] == "--entity"
    assert parsed[4] == "BANCO SANTANDER"
