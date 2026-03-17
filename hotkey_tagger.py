"""
hotkey_tagger.py – Main PyQt5 GUI for hand-classifying image sets.

Usage
-----
    python hotkey_tagger.py

Workflow
--------
1. Click **Open Folder** and choose a directory that contains your images.
2. Click **Configure Hotkeys** to bind single-key shortcuts to tag names
   (e.g. `g` → `galaxy`, `s` → `star`). You can enter multiple keys per tag
   like `5,q` or `5q`.
3. Press the hotkeys while browsing images to toggle tags.
4. Click **Save CSV** (or let the close-dialog do it automatically) to write
   `tags.csv` in the chosen image folder.
5. Click **Save Settings** to persist your current position and write this
   folder's hotkeys to `hotkeys.json`.

On next launch the app restores the last folder and index (if available), and
will load per-folder hotkeys from `hotkeys.json` when a folder is opened.
If a folder lacks `hotkeys.json`, the hotkey map starts blank.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QShortcut,
    QCheckBox
)

from csv_manager import load_tags, repair_csv, save_tags
from settings import DEFAULT_SETTINGS_PATH, HotkeySettings


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

# File extensions treated as images (non-recursive listing)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".fits"}

# Per-folder hotkeys file name
HOTKEYS_FILENAME = "hotkeys.json"


# --------------------------------------------------------------------------- #
# Utilities for multi-key bindings and safe UI handling
# --------------------------------------------------------------------------- #

RESERVED_KEYS = {"left", "right"}  # handled via QShortcuts (navigation)
RESERVED_CHARS = {" ", "\r", "\n", "\t"}  # whitespace variants

# --------------------------------------------------------------------------- #
# QWERTY keyboard layout
# --------------------------------------------------------------------------- #

# Four rows of keys in standard QWERTY order (lowercase for map lookups).
KEYBOARD_LAYOUT: List[List[str]] = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'"],
    ["z", "x", "c", "v", "b", "n", "m", ",", ".", "/"],
]

# Flat ordered index for each key (used for keyboard-order sorting later).
KEYBOARD_ORDER: Dict[str, int] = {
    key: idx
    for idx, key in enumerate(k for row in KEYBOARD_LAYOUT for k in row)
}

# Row stagger offsets (fraction of one key+gap width) mirroring a real keyboard.
_KEY_ROW_OFFSETS = [0.0, 0.5, 0.75, 1.0]

# Key state colours
_KEY_COLOR_ASSIGNED = "#96BEE6"
_KEY_COLOR_UNASSIGNED = "#CCCCCC"
_KEY_COLOR_PRESSED = "#001E44"

# Default key button dimensions (pixels)
_KEY_W = 64
_KEY_H = 56
_KEY_GAP = 3


def group_keys_by_tag(hotkey_map: Dict[str, str]) -> Dict[str, List[str]]:
    """Invert key->tag to tag->sorted unique list(keys), stable order."""
    by_tag: Dict[str, List[str]] = {}
    for k, tag in hotkey_map.items():
        by_tag.setdefault(tag, []).append(k)
    for tag in by_tag:
        # sort case-insensitively, dedupe preserving order
        seen: List[str] = []
        for k in sorted(by_tag[tag], key=lambda x: (x.lower(), x)):
            if k not in seen:
                seen.append(k)
        by_tag[tag] = seen
    # sort tags for stable display
    return dict(sorted(by_tag.items(), key=lambda kv: kv[0].lower()))


def parse_keys_field(s: str) -> List[str]:
    """
    Parse a keys cell like '5,q' or '5q' into a list of single-character keys.
    - Lowercases.
    - Comma-separated; if no commas, splits into characters.
    - Strips whitespace.
    - Deduplicates preserving order.
    - Skips reserved/whitespace characters and multi-char tokens.
    """
    s = (s or "").strip()
    if not s:
        return []
    if "," in s:
        parts = [p.strip().lower() for p in s.split(",") if p.strip()]
    else:
        parts = [ch.lower() for ch in s.replace(" ", "")]
    clean: List[str] = []
    for k in parts:
        if len(k) != 1:
            continue  # drop tokens like "enter"
        if k in RESERVED_CHARS:
            continue
        clean.append(k)
    # dedupe preserving order
    seen = set()
    out: List[str] = []
    for k in clean:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


# --------------------------------------------------------------------------- #
# QWERTY keyboard widget
# --------------------------------------------------------------------------- #

class KeyboardWidget(QWidget):
    """Displays a QWERTY keyboard layout showing hotkey assignments.

    Unassigned keys are greyed out and non-interactive.  Assigned keys are
    highlighted light-blue and emit :attr:`key_clicked` when the user clicks
    them.  Call :meth:`update_map` whenever the underlying hotkey map changes.

    The widget is intentionally data-driven: all colour/label logic lives in
    :meth:`_refresh_button` so future per-tag colour schemes can be added with
    minimal changes.
    """

    key_clicked = pyqtSignal(str)  # emits the lowercase key character

    def __init__(
        self,
        hotkey_map: Dict[str, str],
        parent=None,
        key_w: int = _KEY_W,
        key_h: int = _KEY_H,
    ) -> None:
        super().__init__(parent)
        self._hotkey_map: Dict[str, str] = dict(hotkey_map)
        self._buttons: Dict[str, QPushButton] = {}
        self._key_w = key_w
        self._key_h = key_h
        self._init_ui()

    def _init_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(_KEY_GAP)
        outer.setContentsMargins(4, 4, 4, 4)

        for row_idx, row_keys in enumerate(KEYBOARD_LAYOUT):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(_KEY_GAP)

            # Stagger each row to mimic a real keyboard
            offset_px = int(_KEY_ROW_OFFSETS[row_idx] * (self._key_w + _KEY_GAP))
            if offset_px:
                row_layout.addSpacing(offset_px)

            for key in row_keys:
                btn = QPushButton(self)
                btn.setFixedSize(self._key_w, self._key_h)
                # Multi-line button text is achieved via embedded '\n'; Qt5
                # renders each line centred within the button automatically.
                font = QFont()
                font.setPointSize(8)
                btn.setFont(font)
                self._buttons[key] = btn
                # lambda default-captures key to avoid late-binding closure
                btn.clicked.connect(
                    lambda _checked=False, k=key: self.key_clicked.emit(k)
                )
                row_layout.addWidget(btn)

            row_layout.addStretch()
            outer.addLayout(row_layout)

        self._update_all_buttons()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_map(self, hotkey_map: Dict[str, str]) -> None:
        """Refresh the keyboard display with a new hotkey mapping."""
        self._hotkey_map = dict(hotkey_map)
        self._update_all_buttons()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_all_buttons(self) -> None:
        for key, btn in self._buttons.items():
            self._refresh_button(key, btn)

    def _refresh_button(self, key: str, btn: QPushButton) -> None:
        """Apply the correct visual state (colour + label) for *key*."""
        tag = self._hotkey_map.get(key)
        display = key.upper()

        if tag:
            # Show key label on the first line, tag name below
            btn.setText(f"{display}\n{tag}")
            btn.setToolTip(f"Key: {display}  →  Tag: {tag}")
            btn.setEnabled(True)
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {_KEY_COLOR_ASSIGNED};"
                f"  border: 1px solid #5599CC;"
                f"  border-radius: 4px;"
                f"  font-size: 8pt;"
                f"  padding: 2px;"
                f"}}"
                f"QPushButton:pressed {{"
                f"  background-color: {_KEY_COLOR_PRESSED};"
                f"  color: #FFFFFF;"
                f"}}"
            )
        else:
            btn.setText(display)
            btn.setToolTip("")
            btn.setEnabled(False)
            btn.setStyleSheet(
                f"QPushButton:disabled {{"
                f"  background-color: {_KEY_COLOR_UNASSIGNED};"
                f"  border: 1px solid #999;"
                f"  border-radius: 4px;"
                f"  color: #888;"
                f"  font-size: 8pt;"
                f"}}"
            )


# --------------------------------------------------------------------------- #
# Hotkey configuration dialog
# --------------------------------------------------------------------------- #

class HotkeyConfigDialog(QDialog):
    """Dialog that lets the user map single or multiple keys to a tag."""

    def __init__(self, hotkey_map: Dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Hotkeys")
        self._init_ui(hotkey_map)

    def _init_ui(self, hotkey_map: Dict[str, str]) -> None:
        layout = QVBoxLayout(self)

        # ---- Keyboard preview (QWERTY layout) ----
        kb_label = QLabel("Keyboard preview (updates as you edit the table below):")
        kb_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(kb_label)

        self._keyboard_widget = KeyboardWidget(hotkey_map, parent=self, key_w=52, key_h=45)
        layout.addWidget(self._keyboard_widget)

        # ---- Instruction label ----
        instructions = QLabel(
            "Map keys to a tag. You can enter multiple keys per row like '5,q' or '5q'.\n"
            "Reserved navigation keys (Left/Right/Space/Enter) are not allowed."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Two-column table: Key(s) | Tag Name
        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Key(s)", "Tag Name"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        # Aggregate existing map into rows (keys grouped by tag)
        by_tag = group_keys_by_tag(hotkey_map)
        for tag, keys in by_tag.items():
            keys_text = ",".join(keys)
            self._add_row(keys_text, tag)

        # Connect table edits to live keyboard preview (block signals during
        # programmatic insertions to avoid redundant refreshes)
        self.table.cellChanged.connect(self._refresh_keyboard_preview)

        layout.addWidget(self.table)

        # Row management buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Row", self)
        add_btn.clicked.connect(self._add_empty_row)
        remove_btn = QPushButton("Remove Selected Row", self)
        remove_btn.clicked.connect(self._remove_selected_row)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Wide enough to comfortably display the keyboard (52 px × 12 keys + offsets)
        self.setMinimumWidth(760)
        self.setMinimumHeight(560)

    # ------------------------------------------------------------------
    # Keyboard preview refresh (silent – no warning dialogs)
    # ------------------------------------------------------------------

    def _refresh_keyboard_preview(self) -> None:
        """Re-parse the table silently and update the keyboard preview."""
        preview_map: Dict[str, str] = {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            tag_item = self.table.item(row, 1)
            if not key_item or not tag_item:
                continue
            tag = (tag_item.text() or "").strip()
            if not tag:
                continue
            for k in parse_keys_field(key_item.text()):
                if k not in RESERVED_CHARS:
                    preview_map[k] = tag  # last-row-wins, silently
        self._keyboard_widget.update_map(preview_map)

    def _add_row(self, keys: str = "", tag: str = "") -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(keys))
        self.table.setItem(row, 1, QTableWidgetItem(tag))

    def _add_empty_row(self) -> None:
        self._add_row()

    def _remove_selected_row(self) -> None:
        # Be robust if selection spans multiple cells/rows
        selected = self.table.selectedRanges()
        if not selected:
            return
        for r in reversed(selected):
            for row in range(r.topRow(), r.bottomRow() + 1):
                if 0 <= row < self.table.rowCount():
                    self.table.removeRow(row)

    def get_hotkey_map(self) -> Dict[str, str]:
        """
        Return a flattened key->tag map.
        Accepts '5,q' or '5q' in the Key(s) column.
        Skips invalid/reserved entries and resolves duplicates by 'last row wins'.
        """
        result: Dict[str, str] = {}
        conflicts: List[str] = []

        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            tag_item = self.table.item(row, 1)
            if not key_item or not tag_item:
                continue

            keys_raw = key_item.text()
            tag = (tag_item.text() or "").strip()
            if not tag:
                continue

            keys = parse_keys_field(keys_raw)
            # Disallow space/enter even if typed as characters (safety)
            filtered = [k for k in keys if k not in RESERVED_CHARS]

            for k in filtered:
                if k in result and result[k] != tag:
                    conflicts.append(f"'{k}' (was '{result[k]}', now '{tag}')")
                result[k] = tag

        if conflicts:
            QMessageBox.warning(
                self,
                "Key Conflicts",
                "Some keys were rebound to different tags:\n" + "\n".join(conflicts)
            )

        return result


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #

class HotkeyTagger(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.settings = HotkeySettings()

        # Current dataset folder
        self.folder: Optional[Path] = None

        # List of image files (absolute Paths)
        self.image_files: List[Path] = []

        # Mapping of relative Paths (relative to self.folder) -> tags
        self.tags_dict: Dict[Path, List[str]] = {}

        self.current_index: int = 0
        self.csv_path: Optional[Path] = None

        # Hold shortcuts to keep them from being GC'd
        self._shortcuts: List[QShortcut] = []

        self._init_ui()
        self._init_shortcuts()
        self._auto_restore()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _init_ui(self) -> None:
        self.setWindowTitle("HotkeyTagger")
        # Expanded minimum size to accommodate the QWERTY keyboard panel.
        self.setMinimumSize(950, 900)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ---- Toolbar ----
        toolbar = QHBoxLayout()
        for label, slot in [
            ("Open Folder", self.open_folder),
            ("Configure Hotkeys", self.configure_hotkeys),
            ("Save CSV", self.save_csv),
            ("Save Settings", self.save_settings),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)
        toolbar.addStretch()
        main_layout.addLayout(toolbar)

        # ---- Image display ----
        self.image_label = QLabel("Open a folder to start tagging")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumHeight(420)
        self.image_label.setStyleSheet("background-color: #1e1e1e; color: #aaa;")

        scroll = QScrollArea()
        scroll.setWidget(self.image_label)
        scroll.setWidgetResizable(True)
        main_layout.addWidget(scroll, stretch=1)

        # ---- Navigation row ----
        nav = QHBoxLayout()
        prev_btn = QPushButton("◀ Prev")
        prev_btn.clicked.connect(self.prev_image)

        self.next_btn = QPushButton("Next ▶")  # keep a reference; we change its label
        self.next_btn.clicked.connect(self.next_action)

        # NEW: checkbox to toggle "next untagged" mode
        self.chk_next_untagged = QCheckBox("Next = untagged")
        self.chk_next_untagged.stateChanged.connect(self._on_next_mode_changed)

        self.progress_label = QLabel("0 / 0")
        self.progress_label.setAlignment(Qt.AlignCenter)

        nav.addWidget(prev_btn)
        nav.addWidget(self.progress_label, stretch=1)
        nav.addWidget(self.chk_next_untagged)  # <-- add checkbox in the row
        nav.addWidget(self.next_btn)
        main_layout.addLayout(nav)

        # ---- Tags display ----
        tags_row = QHBoxLayout()
        tags_row.addWidget(QLabel("Tags:"))
        self.tags_display = QLabel("(none)")
        self.tags_display.setWordWrap(True)
        bold = QFont()
        bold.setBold(True)
        self.tags_display.setFont(bold)
        tags_row.addWidget(self.tags_display, stretch=1)
        main_layout.addLayout(tags_row)

        # ---- Hotkey hint (compact text summary) ----
        self.hotkey_hint = QLabel("")
        self.hotkey_hint.setWordWrap(True)
        self.hotkey_hint.setStyleSheet("color: #666; font-size: 9pt;")
        main_layout.addWidget(self.hotkey_hint)

        # ---- QWERTY keyboard panel ----
        kb_header = QLabel("Hotkeys (click a highlighted key to apply its tag):")
        kb_header.setStyleSheet("font-weight: bold; font-size: 9pt;")
        main_layout.addWidget(kb_header)

        self._keyboard_widget = KeyboardWidget(
            self.settings.hotkey_map, parent=self
        )
        self._keyboard_widget.key_clicked.connect(self._on_keyboard_key_clicked)
        main_layout.addWidget(self._keyboard_widget)

        # ---- Status bar ----
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _init_shortcuts(self) -> None:
        """Register navigation shortcuts (Prev/Next)."""

        def add(seq: str, fn):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)

        # Previous / Next
        add("Left", self.prev_image)
        add("Right", self.next_action)

        # Also advance with Space and Enter/Return
        add("Space", self.next_action)
        add("Return", self.next_action)
        add("Enter", self.next_action)

    # ------------------------------------------------------------------ #
    # Session restore
    # ------------------------------------------------------------------ #

    def _auto_restore(self) -> None:
        """Load the default settings file if present and resume the session."""
        if not self.settings.load(DEFAULT_SETTINGS_PATH):
            self._update_hotkey_hint()
            return

        self._update_hotkey_hint()

        last_folder_str = self.settings.last_folder
        if last_folder_str:
            folder = Path(last_folder_str)
            if folder.is_dir():
                self._load_folder(folder)

                last_csv_str = self.settings.last_csv_path
                if last_csv_str:
                    csv_path = Path(last_csv_str)
                    if csv_path.exists():
                        self.csv_path = csv_path
                        # Load tags (relative Paths) and repair CSV schema
                        self.tags_dict = load_tags(csv_path)
                        repair_csv(csv_path)
                        # Refresh display now that tags are loaded
                        self._show_current_image()

                # Load per-folder hotkeys (blank if none)
                self._load_folder_hotkeys()

                idx = self.settings.last_image_index
                if 0 <= idx < len(self.image_files):
                    self.current_index = idx
                    self._show_current_image()
                elif self.image_files:
                    self._show_current_image()

                if self.image_files:
                    self.status_bar.showMessage(f"Resumed session from {folder}")

    # ------------------------------------------------------------------ #
    # Folder / image management
    # ------------------------------------------------------------------ #

    def open_folder(self) -> None:
        # Choose new folder
        folder_str = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if not folder_str:
            return
        new_folder = Path(folder_str)

        # If switching away from an open folder, save current CSV and folder hotkeys
        if self.folder and self.csv_path:
            try:
                if self.tags_dict:
                    save_tags(self.csv_path, self.tags_dict)
                self._save_folder_hotkeys()
            except Exception as e:
                QMessageBox.warning(self, "Warning", f"Failed to save current folder state:\n{e}")

        # Clear in-memory state before loading the next folder
        self.tags_dict = {}
        self.image_files = []
        self.current_index = 0
        self.csv_path = None

        # Load new folder (this will show the first image once)
        self._load_folder(new_folder)

        # Default CSV path next to images
        self.csv_path = new_folder / "tags.csv"
        if self.csv_path.exists():
            self.tags_dict = load_tags(self.csv_path)
            repair_csv(self.csv_path)
            # Refresh display now that tags are loaded
            self._show_current_image()

        # Load this folder's hotkeys (blank if not present)
        self._load_folder_hotkeys()

        # Persist last folder / csv path
        self.settings.last_folder = new_folder.as_posix()
        self.settings.last_csv_path = self.csv_path.as_posix() if self.csv_path else ""

    def _load_folder(self, folder: Path) -> None:
        self.folder = folder

        # Non-recursive listing
        self.image_files = sorted(
            [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS],
            key=lambda p: p.name.lower(),
        )

        self.current_index = 0
        if self.image_files:
            self.status_bar.showMessage(f"Loaded {len(self.image_files)} image(s) from {folder}")
            self._show_current_image()
        else:
            self.image_label.setText("No supported images found in the selected folder")
            self.status_bar.showMessage("No images found")
            self._update_progress()

    # Helpers for per-folder hotkeys
    def _hotkeys_path(self) -> Optional[Path]:
        return self.folder / HOTKEYS_FILENAME if self.folder else None

    def _load_folder_hotkeys(self) -> None:
        """Reset hotkeys to blank, then load this folder's hotkeys.json if present."""
        # Always start with a blank map
        self.settings.hotkey_map = {}

        p = self._hotkeys_path()
        if p and p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Normalize keys to lower-case single characters
                    self.settings.hotkey_map = {str(k).lower(): str(v) for k, v in data.items()}
                    self.status_bar.showMessage(f"Loaded hotkeys from {p.name}")
            except Exception as e:
                QMessageBox.warning(self, "Hotkeys", f"Failed to load {p}:\n{e}")

        # Reflect the current (possibly blank) map in the UI
        self._update_hotkey_hint()

    def _save_folder_hotkeys(self) -> None:
        """Save current hotkeys into this folder's hotkeys.json."""
        p = self._hotkeys_path()
        if not p:
            return
        try:
            p.write_text(json.dumps(self.settings.hotkey_map, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Hotkeys", f"Failed to save {p}:\n{e}")

    # Helper: relative path for the *current* image (key in tags_dict)
    def _current_relpath(self) -> Optional[Path]:
        if not self.folder or not self.image_files:
            return None
        abs_path = self.image_files[self.current_index]
        try:
            # Prefer paths relative to the dataset root (portable in CSV)
            return abs_path.relative_to(self.folder)
        except ValueError:
            # Fallback if outside (shouldn't happen)
            return Path(abs_path.name)

    def _show_current_image(self) -> None:
        if not self.image_files:
            return

        path = self.image_files[self.current_index]  # absolute Path
        pixmap = QPixmap(str(path))  # QPixmap accepts str path
        if pixmap.isNull():
            self.image_label.setText(f"Cannot display: {path.name}")
        else:
            scaled = pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)

        self.setWindowTitle(f"HotkeyTagger – {path.name}")
        self._update_tags_display()
        self._update_progress()

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #

    def prev_image(self) -> None:
        if self.image_files and self.current_index > 0:
            self.current_index -= 1
            self._show_current_image()
            self.settings.last_image_index = self.current_index

    def next_image(self) -> None:
        if self.image_files and self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self._show_current_image()
            self.settings.last_image_index = self.current_index

    def _on_next_mode_changed(self, state) -> None:
        """Update the Next button label when the mode changes."""
        if self.chk_next_untagged.isChecked():
            self.next_btn.setText("Next Untagged ▶")
            self.status_bar.showMessage("Next mode: jump to next untagged image")
        else:
            self.next_btn.setText("Next ▶")
            self.status_bar.showMessage("Next mode: sequential")

    def next_action(self) -> None:
        """Delegate to sequential next or next-untagged based on checkbox."""
        if self.chk_next_untagged.isChecked():
            self.next_untagged()
        else:
            self.next_image()

    def _is_current_tagged(self) -> bool:
        """Return True if the current image has any tags."""
        rel = self._current_relpath()
        if rel is None:
            return False
        tags = self.tags_dict.get(rel, [])
        return bool(tags)

    def next_untagged(self) -> None:
        """Jump to the next image (after current) that has no tags."""
        if not self.image_files:
            return

        start = self.current_index + 1
        found = None
        for i in range(start, len(self.image_files)):
            rel = self._relpath_for_index(i)
            if rel is not None and not self.tags_dict.get(rel, []):
                found = i
                break

        if found is None:
            self.status_bar.showMessage("No untagged images ahead")
            return

        self.current_index = found
        self._show_current_image()
        self.settings.last_image_index = self.current_index

    def _relpath_for_index(self, idx: int) -> Optional[Path]:
        """Get the relative-path key for tags_dict for the given image index."""
        if not self.folder or not (0 <= idx < len(self.image_files)):
            return None
        abs_path = self.image_files[idx]
        try:
            return abs_path.relative_to(self.folder)
        except ValueError:
            return Path(abs_path.name)

    # ------------------------------------------------------------------ #
    # Tagging
    # ------------------------------------------------------------------ #

    def keyPressEvent(self, event) -> None:
        key = event.text().lower()
        if key and key in self.settings.hotkey_map:
            self._toggle_tag(self.settings.hotkey_map[key])
        else:
            super().keyPressEvent(event)

    def _toggle_tag(self, tag: str) -> None:
        if not self.image_files:
            return

        rel = self._current_relpath()
        if rel is None:
            return

        # Ensure dictionary uses relative Path keys
        tags = self.tags_dict.setdefault(rel, [])
        if tag in tags:
            tags.remove(tag)
            self.status_bar.showMessage(f"Removed tag '{tag}' from {rel.as_posix()}")
        else:
            tags.append(tag)
            self.status_bar.showMessage(f"Added tag '{tag}' to {rel.as_posix()}")

        self._update_tags_display()

    # ------------------------------------------------------------------ #
    # Hotkey configuration
    # ------------------------------------------------------------------ #

    def configure_hotkeys(self) -> None:
        dialog = HotkeyConfigDialog(self.settings.hotkey_map, self)
        try:
            result = dialog.exec_()  # modal; returns QDialog.Accepted/Rejected
        except Exception as e:
            QMessageBox.critical(self, "Configure Hotkeys", f"Dialog failed:\n{e}")
            return

        if result == QDialog.Accepted:
            try:
                new_map = dialog.get_hotkey_map()
                self.settings.hotkey_map = new_map
                self._update_hotkey_hint()
                self._save_folder_hotkeys()  # write to this folder's hotkeys.json
                self.status_bar.showMessage("Hotkeys updated")
            except Exception as e:
                QMessageBox.critical(self, "Configure Hotkeys", f"Failed to apply hotkeys:\n{e}")

    # ------------------------------------------------------------------ #
    # Save / export
    # ------------------------------------------------------------------ #

    def save_csv(self) -> None:
        if not self.csv_path:
            # Default to saving next to the opened folder
            default = Path("tags.csv")
            path_str, _ = QFileDialog.getSaveFileName(
                self, "Save Tags CSV", str(default), "CSV Files (*.csv)"
            )
            if not path_str:
                return
            self.csv_path = Path(path_str)

        # Ensure we always write relative paths in CSV (portable)
        save_tags(self.csv_path, self.tags_dict)
        self.status_bar.showMessage(f"Tags saved to {self.csv_path}")

        # Persist path (POSIX string)
        self.settings.last_csv_path = self.csv_path.as_posix()

    def save_settings(self) -> None:
        # Save image index and per-folder hotkeys
        self.settings.last_image_index = self.current_index
        if self.folder:
            self.settings.last_folder = self.folder.as_posix()
        self._save_folder_hotkeys()
        self.settings.save(DEFAULT_SETTINGS_PATH)
        self.status_bar.showMessage("Settings saved")

    # ------------------------------------------------------------------ #
    # Display helpers
    # ------------------------------------------------------------------ #

    def _update_tags_display(self) -> None:
        if not self.image_files:
            return

        rel = self._current_relpath()
        if rel is None:
            self.tags_display.setText("(none)")
            return

        tags = self.tags_dict.get(rel, [])
        self.tags_display.setText(", ".join(tags) if tags else "(none)")

    def _update_progress(self) -> None:
        if self.image_files:
            self.progress_label.setText(f"{self.current_index + 1} / {len(self.image_files)}")
        else:
            self.progress_label.setText("0 / 0")

    def _update_hotkey_hint(self) -> None:
        if self.settings.hotkey_map:
            by_tag = group_keys_by_tag(self.settings.hotkey_map)
            chunks = [f"[{','.join(keys)}] → {tag}" for tag, keys in by_tag.items()]
            self.hotkey_hint.setText("Hotkeys:  " + "    ".join(chunks))
        else:
            self.hotkey_hint.setText(
                'No hotkeys configured. Click "Configure Hotkeys" to set them up.'
            )
        # Keep the keyboard panel in sync
        self._keyboard_widget.update_map(self.settings.hotkey_map)

    # ------------------------------------------------------------------ #
    # Keyboard panel interactions
    # ------------------------------------------------------------------ #

    def _on_keyboard_key_clicked(self, key: str) -> None:
        """Apply/remove the tag bound to *key* on the current image."""
        tag = self.settings.hotkey_map.get(key)
        if tag:
            self._toggle_tag(tag)

    # ------------------------------------------------------------------ #
    # Close event
    # ------------------------------------------------------------------ #

    def closeEvent(self, event) -> None:
        if self.image_files:
            reply = QMessageBox.question(
                self,
                "Save Before Exit",
                "Save tags and settings before exiting?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Yes:
                self.save_csv()
                self.save_settings()
        event.accept()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    window = HotkeyTagger()
    window.show()
    sys.exit(app.exec_())