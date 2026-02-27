"""
settings.py – Persistent hotkey settings and session state.

Settings are stored as JSON so they are human-readable and easy to edit by
hand.  A single :class:`HotkeySettings` object is kept in memory by the main
application; call :meth:`HotkeySettings.save` to write it to disk and
:meth:`HotkeySettings.load` to restore it.
"""

import json
import os
from typing import Dict, Optional

DEFAULT_SETTINGS_PATH = "hotkey_settings.json"


class HotkeySettings:
    """Container for all user-adjustable settings."""

    def __init__(self) -> None:
        # Maps a single keyboard character (lowercase) to a tag name.
        self.hotkey_map: Dict[str, str] = {}
        # The last image folder that was open.
        self.last_folder: Optional[str] = None
        # Index of the image the user was viewing when they last saved.
        self.last_image_index: int = 0
        # Path of the CSV file associated with the last session.
        self.last_csv_path: Optional[str] = None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str = DEFAULT_SETTINGS_PATH) -> None:
        """Write settings to *path* as JSON."""
        data = {
            "hotkey_map": self.hotkey_map,
            "last_folder": self.last_folder,
            "last_image_index": self.last_image_index,
            "last_csv_path": self.last_csv_path,
        }
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2)

    def load(self, path: str = DEFAULT_SETTINGS_PATH) -> bool:
        """Read settings from *path*.

        Returns ``True`` on success, ``False`` when the file does not exist or
        cannot be parsed.
        """
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r") as fh:
                data = json.load(fh)
            self.hotkey_map = data.get("hotkey_map", {})
            self.last_folder = data.get("last_folder")
            self.last_image_index = data.get("last_image_index", 0)
            self.last_csv_path = data.get("last_csv_path")
            return True
        except (json.JSONDecodeError, KeyError, TypeError):
            return False
