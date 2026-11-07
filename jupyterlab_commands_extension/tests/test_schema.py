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
    default = json.loads(SCHEMA.read_text(encoding="utf-8"))["properties"][
        "allowedCommands"
    ]["default"]
    assert default[-4:] == [
        "voice-capture:play-file",
        "voice-capture:enable",
        "voice-capture:disable",
        "voice-capture:stop-playback",
    ]
