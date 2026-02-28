"""
settings.py – Persistent hotkey settings and session state.

Settings are stored as JSON so they are human-readable and easy to edit by
hand. A single :class:`HotkeySettings` object is kept in memory by the main
application; call :meth:`HotkeySettings.save` to write it to disk and
:meth:`HotkeySettings.load` to restore it.

All file system interactions use pathlib.Path. Paths are serialized to JSON
as POSIX strings for cross-platform portability (Windows accepts forward
slashes). When loading, POSIX strings are converted back into Path objects
via helper properties.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


# Default settings file location (in the working directory by default)
DEFAULT_SETTINGS_PATH: Path = Path("hotkey_settings.json")


class HotkeySettings:
    """Container for all user-adjustable settings."""

    def __init__(self) -> None:
        # Maps a single keyboard character (lowercase) to a tag name.
        self.hotkey_map: Dict[str, str] = {}

        # Stored as POSIX strings in JSON (see save/load). Internally we expose
        # helper properties to get/set as Path objects when needed by the app.
        self.last_folder: Optional[str] = None
        self.last_image_index: int = 0
        self.last_csv_path: Optional[str] = None

    # ------------------------------------------------------------------
    # Convenience helpers to work with Path objects in the app code
    # ------------------------------------------------------------------

    @property
    def last_folder_path(self) -> Optional[Path]:
        """Return last_folder as a Path (or None)."""
        return Path(self.last_folder) if self.last_folder else None

    @last_folder_path.setter
    def last_folder_path(self, value: Optional[Path]) -> None:
        """Set last_folder from a Path (stored as POSIX string)."""
        self.last_folder = value.as_posix() if value else None

    @property
    def last_csv_path_obj(self) -> Optional[Path]:
        """Return last_csv_path as a Path (or None)."""
        return Path(self.last_csv_path) if self.last_csv_path else None

    @last_csv_path_obj.setter
    def last_csv_path_obj(self, value: Optional[Path]) -> None:
        """Set last_csv_path from a Path (stored as POSIX string)."""
        self.last_csv_path = value.as_posix() if value else None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path = DEFAULT_SETTINGS_PATH) -> None:
        """Write settings to *path* as JSON."""
        # Ensure parent exists
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            # Hotkey map is a simple dict[str, str]
            "hotkey_map": self.hotkey_map,

            # Store paths as POSIX strings for portability
            "last_folder": self.last_folder,
            "last_image_index": self.last_image_index,
            "last_csv_path": self.last_csv_path,
        }

        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self, path: Path = DEFAULT_SETTINGS_PATH) -> bool:
        """
        Read settings from *path*.

        Returns True on success, False when the file does not exist or
        cannot be parsed.
        """
        if not path.exists():
            return False

        try:
            data = json.loads(path.read_text(encoding="utf-8"))

            # Defensive parsing with defaults
            self.hotkey_map = dict(data.get("hotkey_map", {}))
            # These are stored as POSIX strings; leave them as strings here
            # and convert to Path on demand using helper properties.
            self.last_folder = data.get("last_folder")
            self.last_image_index = int(data.get("last_image_index", 0))
            self.last_csv_path = data.get("last_csv_path")

            return True
        except (json.JSONDecodeError, TypeError, ValueError):
            return False