"""
csv_manager.py – Utilities for saving, loading, and repairing the tags CSV.

CSV format
----------
Each row represents one image file.  The first column is ``filename``.
Every subsequent column is a tag name; its cell value is ``1`` when the tag
is applied to that image and ``0`` otherwise.

When new tags are introduced after some rows have already been written the
``repair_csv`` function fills in the missing columns with ``0`` so that the
file never becomes malformed.
"""

import csv
import os
from typing import Dict, List


def get_all_tags(tags_dict: Dict[str, List[str]]) -> List[str]:
    """Return a sorted list of every unique tag across all files."""
    all_tags: set = set()
    for tags in tags_dict.values():
        all_tags.update(tags)
    return sorted(all_tags)


def save_tags(csv_path: str, tags_dict: Dict[str, List[str]]) -> None:
    """Save *tags_dict* to *csv_path*.

    Parameters
    ----------
    csv_path:
        Destination file path (created or overwritten).
    tags_dict:
        Mapping of ``filename → [tag, …]``.
    """
    all_tags = get_all_tags(tags_dict)
    with open(csv_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["filename"] + all_tags)
        for filename in sorted(tags_dict.keys()):
            tags = tags_dict[filename]
            row = [filename] + [1 if tag in tags else 0 for tag in all_tags]
            writer.writerow(row)


def load_tags(csv_path: str) -> Dict[str, List[str]]:
    """Load a tags CSV previously written by :func:`save_tags`.

    Returns an empty dict when the file does not exist.
    """
    if not os.path.exists(csv_path):
        return {}

    tags_dict: Dict[str, List[str]] = {}
    with open(csv_path, "r", newline="") as fh:
        reader = csv.DictReader(fh)
        tag_columns = [col for col in (reader.fieldnames or []) if col != "filename"]
        for row in reader:
            filename = row["filename"]
            tags = [tag for tag in tag_columns if row.get(tag, "0") == "1"]
            tags_dict[filename] = tags
    return tags_dict


def repair_csv(csv_path: str) -> None:
    """Repair *csv_path* so that every row contains every tag column.

    This handles the common situation where new tags were added to the hotkey
    map after some images had already been classified: rows written before the
    new tag existed will be missing that column.  The function reads the full
    file, determines the union of all columns, then rewrites the file filling
    any missing cells with ``0``.

    The function is a no-op when the file does not exist.
    """
    if not os.path.exists(csv_path):
        return

    rows: List[Dict[str, str]] = []
    all_columns: set = set()

    with open(csv_path, "r", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames:
            all_columns = set(reader.fieldnames)
        for row in reader:
            rows.append(dict(row))
            all_columns.update(row.keys())

    tag_columns = sorted(col for col in all_columns if col is not None and col != "filename")
    fieldnames = ["filename"] + tag_columns

    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            complete_row = {col: (row.get(col) or "0") for col in fieldnames}
            writer.writerow(complete_row)
