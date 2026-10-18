"""Check the facts ACC-DOCS-24 requires in the README."""

from pathlib import Path

from jupyterlab_commands_extension import cli

README = Path(__file__).resolve().parents[2] / "README.md"


def test_readme_states_the_cli_exit_codes_in_the_command_line_section():
    text = README.read_text(encoding="utf-8")
    section = text.split("## Command line", 1)[1].split("## Allowlist", 1)[0]
    assert (
        f"Exit codes: {cli.EXIT_OK} success, "
        f"{cli.EXIT_USAGE} discovery or usage error, "
        f"{cli.EXIT_NO_CLIENT} no browser client, "
        f"{cli.EXIT_NOT_ALLOWED} command not allowed, "
        f"{cli.EXIT_EXECUTION} execution error."
    ) in section
