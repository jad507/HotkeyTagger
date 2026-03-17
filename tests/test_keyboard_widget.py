"""Tests for the QWERTY keyboard widget and layout constants."""

import os
import sys

import pytest

# Run with an offscreen platform so no display is needed
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

from hotkey_tagger import KEYBOARD_LAYOUT, KEYBOARD_ORDER


def test_keyboard_layout_has_four_rows():
    assert len(KEYBOARD_LAYOUT) == 4


def test_keyboard_layout_row_lengths():
    assert len(KEYBOARD_LAYOUT[0]) == 12  # 1234567890-=
    assert len(KEYBOARD_LAYOUT[1]) == 12  # qwertyuiop[]
    assert len(KEYBOARD_LAYOUT[2]) == 11  # asdfghjkl;'
    assert len(KEYBOARD_LAYOUT[3]) == 10  # zxcvbnm,./


def test_keyboard_layout_row1_content():
    assert KEYBOARD_LAYOUT[0] == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="]


def test_keyboard_layout_row2_content():
    assert KEYBOARD_LAYOUT[1] == ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]"]


def test_keyboard_layout_row3_content():
    assert KEYBOARD_LAYOUT[2] == ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'"]


def test_keyboard_layout_row4_content():
    assert KEYBOARD_LAYOUT[3] == ["z", "x", "c", "v", "b", "n", "m", ",", ".", "/"]


def test_keyboard_layout_all_lowercase():
    for row in KEYBOARD_LAYOUT:
        for key in row:
            assert key == key.lower(), f"Key '{key}' is not lowercase"


def test_keyboard_order_covers_all_keys():
    all_keys = [k for row in KEYBOARD_LAYOUT for k in row]
    assert set(KEYBOARD_ORDER.keys()) == set(all_keys)


def test_keyboard_order_is_sequential():
    all_keys = [k for row in KEYBOARD_LAYOUT for k in row]
    for idx, key in enumerate(all_keys):
        assert KEYBOARD_ORDER[key] == idx


def test_keyboard_order_row_monotonic():
    """Keys within each row should have strictly increasing order indices."""
    for row in KEYBOARD_LAYOUT:
        indices = [KEYBOARD_ORDER[k] for k in row]
        assert indices == sorted(indices)


# ---------------------------------------------------------------------------
# KeyboardWidget (requires a QApplication)
# ---------------------------------------------------------------------------

from PyQt5.QtWidgets import QApplication

from hotkey_tagger import KeyboardWidget

_app = None  # module-level so it is created once


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _app
    _app = QApplication.instance() or QApplication(sys.argv)
    yield _app


def test_keyboard_widget_creates_button_for_every_key():
    kb = KeyboardWidget({})
    all_keys = [k for row in KEYBOARD_LAYOUT for k in row]
    for key in all_keys:
        assert key in kb._buttons, f"No button created for key '{key}'"


def test_keyboard_widget_unassigned_key_is_disabled():
    kb = KeyboardWidget({})
    for key in ["q", "a", "z", "1"]:
        assert not kb._buttons[key].isEnabled(), f"Unassigned key '{key}' should be disabled"


def test_keyboard_widget_assigned_key_is_enabled():
    kb = KeyboardWidget({"q": "galaxy", "1": "star"})
    assert kb._buttons["q"].isEnabled()
    assert kb._buttons["1"].isEnabled()


def test_keyboard_widget_assigned_key_shows_tag():
    kb = KeyboardWidget({"w": "nebula"})
    text = kb._buttons["w"].text()
    assert "W" in text
    assert "nebula" in text


def test_keyboard_widget_unassigned_key_shows_only_label():
    kb = KeyboardWidget({})
    text = kb._buttons["e"].text().strip()
    assert text == "E"


def test_keyboard_widget_update_map_enables_new_keys():
    kb = KeyboardWidget({})
    assert not kb._buttons["s"].isEnabled()
    kb.update_map({"s": "supernova"})
    assert kb._buttons["s"].isEnabled()
    assert "supernova" in kb._buttons["s"].text()


def test_keyboard_widget_update_map_disables_removed_keys():
    kb = KeyboardWidget({"r": "galaxy"})
    assert kb._buttons["r"].isEnabled()
    kb.update_map({})
    assert not kb._buttons["r"].isEnabled()


def test_keyboard_widget_update_map_changes_tag_label():
    kb = KeyboardWidget({"t": "old_tag"})
    assert "old_tag" in kb._buttons["t"].text()
    kb.update_map({"t": "new_tag"})
    assert "new_tag" in kb._buttons["t"].text()
    assert "old_tag" not in kb._buttons["t"].text()


def test_keyboard_widget_key_clicked_signal_emitted():
    """Clicking an assigned key emits key_clicked with the correct key char."""
    kb = KeyboardWidget({"y": "yellow"})
    received = []
    kb.key_clicked.connect(received.append)
    kb._buttons["y"].click()
    assert received == ["y"]


def test_keyboard_widget_total_button_count():
    kb = KeyboardWidget({})
    total_keys = sum(len(row) for row in KEYBOARD_LAYOUT)
    assert len(kb._buttons) == total_keys
