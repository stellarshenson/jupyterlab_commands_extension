"""Compare the installed agent skill with the repository copy."""

import re
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


def test_skill_states_that_activity_marks_the_server_active_once():
    text = REPOSITORY_SKILL.read_text(encoding="utf-8")
    rule = next(
        line for line in text.splitlines() if line.startswith("- `activity`")
    )
    assert not re.search(r"alive|session", rule, re.IGNORECASE)
    assert "marks the server active once" in rule
    assert "idle timeout counted from the last mark" in rule
    assert "repeat it at an interval the user names" in rule
    assert "never loop without the user's word" in rule


def test_skill_description_names_the_hub_session():
    text = REPOSITORY_SKILL.read_text(encoding="utf-8")
    description = next(
        line for line in text.splitlines() if line.startswith("description:")
    )
    assert "JupyterHub session" in description
    assert "culled as idle" in description
    assert "`activity`" in description


def test_skill_description_names_the_file_download():
    text = REPOSITORY_SKILL.read_text(encoding="utf-8")
    description = next(
        line for line in text.splitlines() if line.startswith("description:")
    )
    assert "`file:download`" in description
    assert "download a lab file to the user computer" in description
    assert "through their browser" in description
