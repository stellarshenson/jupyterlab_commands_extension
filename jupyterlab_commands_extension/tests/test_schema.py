"""Check the shipped settings schema."""

import json
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "plugin.json"


def test_default_allowed_commands_include_workspace_page_open():
    default = json.loads(SCHEMA.read_text(encoding="utf-8"))["properties"][
        "allowedCommands"
    ]["default"]
    assert "workspace-page:open" in default


def test_default_allowed_commands_end_with_the_voice_capture_commands():
    # ACC-PLAYER-64: the player command is allowed, and its retired predecessors are gone.
    default = json.loads(SCHEMA.read_text(encoding="utf-8"))["properties"][
        "allowedCommands"
    ]["default"]
    assert default[-3:] == [
        "voice-capture:enable",
        "voice-capture:disable",
        "voice-capture:player",
    ]
    assert "voice-capture:play-file" not in default
    assert "voice-capture:stop-playback" not in default
