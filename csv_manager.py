"""
csv_manager.py – Utilities for saving, loading, and repairing the tags CSV.

CSV format
----------
Each row represents one image file. The first column is ``filename``.
Every subsequent column is a tag name; its cell value is ``1`` when the tag
is applied to that image and ``0`` otherwise.

Paths are stored as POSIX strings (forward slashes) to be cross-platform
portable. When loading, stored strings are converted back to ``pathlib.Path``
objects so callers can remain platform-agnostic.

When new tags are introduced after some rows have already been written the
``repair_csv`` function fills in the missing columns with ``0`` so that the
file never becomes malformed.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Set


# Type alias: mapping of image file path -> list of tag names
TagDict = Dict[Path, List[str]]


def get_all_tags(tags_dict: TagDict) -> List[str]:
    """Return a sorted list of every unique tag across all files."""
    all_tags: Set[str] = set()
    for tags in tags_dict.values():
        all_tags.update(tags)
    return sorted(all_tags)


def save_tags(csv_path: Path, tags_dict: TagDict) -> None:
    """Save *tags_dict* to *csv_path*.

    Parameters
    ----------
    csv_path:
        Destination file path (created or overwritten).
    tags_dict:
        Mapping of ``Path(filename) → [tag, …]``.
    """
    # Ensure parent directory exists
    if csv_path.parent:
        csv_path.parent.mkdir(parents=True, exist_ok=True)

    all_tags = get_all_tags(tags_dict)

    # Sort deterministically by POSIX path
    def _key(p: Path) -> str:
        return p.as_posix()

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["filename"] + all_tags)
        for filename in sorted(tags_dict.keys(), key=_key):
            tags = tags_dict[filename]
            # Store as POSIX path for portability
            filename_str = filename.as_posix()
            row = [filename_str] + [1 if tag in tags else 0 for tag in all_tags]
            writer.writerow(row)


def load_tags(csv_path: Path) -> TagDict:
    """Load a tags CSV previously written by :func:`save_tags`.

    Returns an empty dict when the file does not exist.

    Notes
    -----
    - ``filename`` values in the CSV are POSIX strings; this function converts
      them to ``Path`` objects appropriate for the current platform.
    """
    if not csv_path.exists():
        return {}

    tags_dict: TagDict = {}
    with csv_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        tag_columns = [col for col in fieldnames if col and col != "filename"]

        for row in reader:
            filename_str = row.get("filename", "")
            if not filename_str:
                # Skip malformed rows without a filename
                continue

            # Convert from stored POSIX string to a Path for this platform
            filename = Path(filename_str)

            tags = [tag for tag in tag_columns if row.get(tag, "0") == "1"]
            tags_dict[filename] = tags

    return tags_dict


def repair_csv(csv_path: Path) -> None:
    """Repair *csv_path* so that every row contains every tag column.

    This handles the common situation where new tags were added to the hotkey
    map after some images had already been classified: rows written before the
    new tag existed will be missing that column. The function reads the full
    file, determines the union of all columns, then rewrites the file filling
    any missing cells with ``0``.

    The function is a no-op when the file does not exist.
    """
    if not csv_path.exists():
        return

    rows: List[Dict[str, str]] = []
    all_columns: Set[str] = set()

    # Read all rows and discover the superset of columns
    with csv_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames:
            all_columns.update([c for c in reader.fieldnames if c is not None])

        for row in reader:
            # Keep a shallow copy to avoid iterator side effects
            row_copy = dict(row)
            rows.append(row_copy)
            all_columns.update([c for c in row_copy.keys() if c is not None])

    # Ensure 'filename' remains the first column; other columns (tags) sorted
    tag_columns = sorted(col for col in all_columns if col != "filename")
    fieldnames = ["filename"] + tag_columns

    # Rewrite the file with complete rows (fill missing as "0")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            # Preserve filename as-is; if missing, skip (malformed)
            filename_str = row.get("filename")
            if not filename_str:
                continue

            complete_row = {"filename": filename_str}
            for col in tag_columns:
                complete_row[col] = row.get(col, "0") or "0"
            writer.writerow(complete_row)