"""Tests for settings.py"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from settings import HotkeySettings


# ---------------------------------------------------------------------------
# Default state
# ---------------------------------------------------------------------------

def test_default_state():
    s = HotkeySettings()
    assert s.hotkey_map == {}
    assert s.last_folder is None
    assert s.last_image_index == 0
    assert s.last_csv_path is None


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------

def test_save_and_load_roundtrip():
    s = HotkeySettings()
    s.hotkey_map = {"g": "galaxy", "s": "star"}
    s.last_folder = "/data/images"
    s.last_image_index = 42
    s.last_csv_path = "/data/images/tags.csv"

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = Path(f.name)

    try:
        s.save(path)

        s2 = HotkeySettings()
        result = s2.load(path)

        assert result is True
        assert s2.hotkey_map == {"g": "galaxy", "s": "star"}
        assert s2.last_folder == "/data/images"
        assert s2.last_image_index == 42
        assert s2.last_csv_path == "/data/images/tags.csv"
    finally:
        os.unlink(path)


def test_load_returns_false_for_missing_file():
    s = HotkeySettings()
    assert s.load(Path("/nonexistent/path/settings.json")) is False


def test_load_returns_false_for_corrupt_json():
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w"
    ) as f:
        f.write("not valid json {{")
        path = Path(f.name)
    try:
        s = HotkeySettings()
        assert s.load(path) is False
    finally:
        os.unlink(path)


def test_save_produces_valid_json():
    s = HotkeySettings()
    s.hotkey_map = {"n": "nebula"}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = Path(f.name)
    try:
        s.save(path)
        with open(path) as fh:
            data = json.load(fh)
        assert data["hotkey_map"] == {"n": "nebula"}
        assert "last_folder" in data
        assert "last_image_index" in data
        assert "last_csv_path" in data
    finally:
        os.unlink(path)


def test_load_partial_json_uses_defaults():
    """Settings file may only contain some keys; missing keys get defaults."""
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w"
    ) as f:
        json.dump({"hotkey_map": {"x": "xray"}}, f)
        path = Path(f.name)
    try:
        s = HotkeySettings()
        assert s.load(path) is True
        assert s.hotkey_map == {"x": "xray"}
        assert s.last_folder is None
        assert s.last_image_index == 0
        assert s.last_csv_path is None
    finally:
        os.unlink(path)


def test_hotkey_map_survives_multiple_saves():
    s = HotkeySettings()
    s.hotkey_map = {"a": "asteroid", "b": "binary_star"}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = Path(f.name)
    try:
        s.save(path)
        s.hotkey_map["c"] = "comet"
        s.save(path)

        s2 = HotkeySettings()
        s2.load(path)
        assert s2.hotkey_map == {"a": "asteroid", "b": "binary_star", "c": "comet"}
    finally:
        os.unlink(path)
