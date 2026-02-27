"""
hotkey_tagger.py – Main PyQt5 GUI for hand-classifying image sets.

Usage
-----
    python hotkey_tagger.py

Workflow
--------
1. Click **Open Folder** and choose a directory that contains your images.
2. Click **Configure Hotkeys** to bind single-key shortcuts to tag names
   (e.g. `g` → `galaxy`, `s` → `star`).
3. Press the hotkeys while browsing images to toggle tags.
4. Click **Save CSV** (or let the close-dialog do it automatically) to write
   `tags.csv` in the chosen image folder.
5. Click **Save Settings** to persist your hotkey map and current position so
   you can resume the session later.

On next launch the application automatically restores the last folder, CSV,
and image index (if the settings file is present).
"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap
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
)

from csv_manager import load_tags, repair_csv, save_tags
from settings import DEFAULT_SETTINGS_PATH, HotkeySettings


# File extensions treated as images
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".fits"}


# --------------------------------------------------------------------------- #
# Hotkey configuration dialog
# --------------------------------------------------------------------------- #

class HotkeyConfigDialog(QDialog):
    """Dialog that lets the user map single keys to tag names."""

    def __init__(self, hotkey_map: Dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Hotkeys")
        self._init_ui(hotkey_map)

    def _init_ui(self, hotkey_map: Dict[str, str]) -> None:
        layout = QVBoxLayout(self)

        # Instruction label
        instructions = QLabel(
            "Map a single key to a tag name. "
            "Press a key while viewing an image to toggle that tag."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Two-column table: Key | Tag Name
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Key", "Tag Name"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        for key, tag in sorted(hotkey_map.items()):
            self._add_row(key, tag)
        layout.addWidget(self.table)

        # Row management buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        add_btn.clicked.connect(self._add_empty_row)
        remove_btn = QPushButton("Remove Selected Row")
        remove_btn.clicked.connect(self._remove_selected_row)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setMinimumWidth(420)
        self.setMinimumHeight(300)

    def _add_row(self, key: str = "", tag: str = "") -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(key))
        self.table.setItem(row, 1, QTableWidgetItem(tag))

    def _add_empty_row(self) -> None:
        self._add_row()

    def _remove_selected_row(self) -> None:
        selected = self.table.selectedItems()
        if selected:
            self.table.removeRow(selected[0].row())

    def get_hotkey_map(self) -> Dict[str, str]:
        """Return the validated hotkey→tag mapping from the table."""
        result: Dict[str, str] = {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            tag_item = self.table.item(row, 1)
            if key_item and tag_item:
                key = key_item.text().strip().lower()
                tag = tag_item.text().strip()
                if key and tag:
                    result[key] = tag
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

        self._init_ui()
        self._auto_restore()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _init_ui(self) -> None:
        self.setWindowTitle("HotkeyTagger")
        self.setMinimumSize(900, 650)

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
        next_btn = QPushButton("Next ▶")
        next_btn.clicked.connect(self.next_image)
        self.progress_label = QLabel("0 / 0")
        self.progress_label.setAlignment(Qt.AlignCenter)
        nav.addWidget(prev_btn)
        nav.addWidget(self.progress_label, stretch=1)
        nav.addWidget(next_btn)
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

        # ---- Hotkey hint ----
        self.hotkey_hint = QLabel("")
        self.hotkey_hint.setWordWrap(True)
        self.hotkey_hint.setStyleSheet("color: #666; font-size: 9pt;")
        main_layout.addWidget(self.hotkey_hint)

        # ---- Status bar ----
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

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

                idx = self.settings.last_image_index
                if 0 <= idx < len(self.image_files):
                    self.current_index = idx
                if self.image_files:
                    self._show_current_image()
                    self.status_bar.showMessage(f"Resumed session from {folder}")

    # ------------------------------------------------------------------ #
    # Folder / image management
    # ------------------------------------------------------------------ #

    def open_folder(self) -> None:
        folder_str = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if not folder_str:
            return

        folder = Path(folder_str)
        self._load_folder(folder)

        # Default CSV path next to images
        self.csv_path = folder / "tags.csv"
        if self.csv_path.exists():
            self.tags_dict = load_tags(self.csv_path)
            repair_csv(self.csv_path)

        # Persist paths to settings (use POSIX for portability)
        self.settings.last_folder = folder.as_posix()
        self.settings.last_csv_path = self.csv_path.as_posix() if self.csv_path else ""

    def _load_folder(self, folder: Path) -> None:
        self.folder = folder

        # Non-recursive listing (match prior behavior)
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
            return abs_path.name  # type: ignore[return-value]

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
        if dialog.exec_() == QDialog.Accepted:
            self.settings.hotkey_map = dialog.get_hotkey_map()
            self._update_hotkey_hint()
            self.status_bar.showMessage("Hotkeys updated")

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
        self.settings.last_image_index = self.current_index
        # Store folder in settings as POSIX string for portability
        if self.folder:
            self.settings.last_folder = self.folder.as_posix()
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
            hints = "  ".join(f"[{k}] → {v}" for k, v in sorted(self.settings.hotkey_map.items()))
            self.hotkey_hint.setText(f"Hotkeys: {hints}")
        else:
            self.hotkey_hint.setText(
                'No hotkeys configured. Click "Configure Hotkeys" to set them up.'
            )

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
    app = QApplication(sys.argv)
    window = HotkeyTagger()
    window.show()
    sys.exit(app.exec_())