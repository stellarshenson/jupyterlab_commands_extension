"""Compare the installed agent skill with the repository copy."""

import sys
from pathlib import Path

import pytest

SKILL_NAME = "jupyterlab-commands-extension"
INSTALLED_SKILL = (
    Path(sys.prefix)
    / "share"
    / "jupyter"
    / "agents"
    / "skills"
    / SKILL_NAME
    / "SKILL.md"
)
REPOSITORY_SKILL = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "skills"
    / SKILL_NAME
    / "SKILL.md"
)


@pytest.mark.skipif(
    not INSTALLED_SKILL.is_file(),
    reason="the agent skill is not installed under sys.prefix",
)
def test_installed_skill_matches_the_repository_copy():
    assert INSTALLED_SKILL.read_text(encoding="utf-8") == (
        REPOSITORY_SKILL.read_text(encoding="utf-8")
    )
