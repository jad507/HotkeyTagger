"""Tests for csv_manager.py"""

import csv
import os
import tempfile

import pytest

from csv_manager import get_all_tags, load_tags, repair_csv, save_tags


# ---------------------------------------------------------------------------
# get_all_tags
# ---------------------------------------------------------------------------

def test_get_all_tags_empty():
    assert get_all_tags({}) == []


def test_get_all_tags_single_file():
    assert get_all_tags({"a.jpg": ["galaxy", "bright"]}) == ["bright", "galaxy"]


def test_get_all_tags_multiple_files():
    tags_dict = {
        "a.jpg": ["galaxy", "star"],
        "b.jpg": ["nebula", "star"],
        "c.jpg": [],
    }
    result = get_all_tags(tags_dict)
    assert result == ["galaxy", "nebula", "star"]


def test_get_all_tags_returns_sorted():
    tags_dict = {"img.jpg": ["z_tag", "a_tag", "m_tag"]}
    assert get_all_tags(tags_dict) == ["a_tag", "m_tag", "z_tag"]


# ---------------------------------------------------------------------------
# save_tags / load_tags round-trip
# ---------------------------------------------------------------------------

def test_save_and_load_roundtrip():
    tags_dict = {
        "image1.jpg": ["galaxy", "bright"],
        "image2.jpg": ["star"],
        "image3.jpg": [],
    }
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        path = f.name
    try:
        save_tags(path, tags_dict)
        loaded = load_tags(path)
        assert loaded["image1.jpg"] == ["bright", "galaxy"]
        assert loaded["image2.jpg"] == ["star"]
        assert loaded["image3.jpg"] == []
    finally:
        os.unlink(path)


def test_save_tags_csv_structure():
    """The CSV must have a 'filename' header followed by sorted tag columns."""
    tags_dict = {"img.png": ["b_tag", "a_tag"]}
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        path = f.name
    try:
        save_tags(path, tags_dict)
        with open(path, newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            assert header == ["filename", "a_tag", "b_tag"]
            data_row = next(reader)
            assert data_row == ["img.png", "1", "1"]
    finally:
        os.unlink(path)


def test_save_tags_binary_values():
    """Files that don't have a tag should get 0; those that do should get 1."""
    tags_dict = {
        "a.jpg": ["galaxy"],
        "b.jpg": [],
    }
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        path = f.name
    try:
        save_tags(path, tags_dict)
        loaded_raw: list = []
        with open(path, newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                loaded_raw.append(row)
        galaxy_row = next(r for r in loaded_raw if r["filename"] == "a.jpg")
        no_tag_row = next(r for r in loaded_raw if r["filename"] == "b.jpg")
        assert galaxy_row["galaxy"] == "1"
        assert no_tag_row["galaxy"] == "0"
    finally:
        os.unlink(path)


def test_load_tags_missing_file():
    assert load_tags("/nonexistent/path/tags.csv") == {}


def test_load_tags_empty_csv():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        f.write("filename\n")
        path = f.name
    try:
        result = load_tags(path)
        assert result == {}
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# repair_csv
# ---------------------------------------------------------------------------

def test_repair_csv_noop_when_file_missing():
    """repair_csv must not raise when the file does not exist."""
    repair_csv("/nonexistent/path/tags.csv")  # should not raise


def test_repair_csv_adds_missing_columns():
    """
    Simulate a CSV that was written before a new tag ('nebula') was added.
    After repair every row should have the 'nebula' column filled with '0'.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".csv", delete=False, mode="w", newline=""
    ) as f:
        path = f.name
        writer = csv.writer(f)
        # Header already knows about 'nebula', but old_image.jpg row doesn't
        writer.writerow(["filename", "galaxy", "nebula"])
        writer.writerow(["old_image.jpg", "1"])        # missing nebula value
        writer.writerow(["new_image.jpg", "0", "1"])

    try:
        repair_csv(path)

        with open(path, newline="") as fh:
            reader = csv.DictReader(fh)
            assert set(reader.fieldnames) == {"filename", "galaxy", "nebula"}
            rows = list(reader)

        old_row = next(r for r in rows if r["filename"] == "old_image.jpg")
        new_row = next(r for r in rows if r["filename"] == "new_image.jpg")
        assert old_row["galaxy"] == "1"
        assert old_row["nebula"] == "0"   # filled in by repair
        assert new_row["nebula"] == "1"
        assert new_row["galaxy"] == "0"
    finally:
        os.unlink(path)


def test_repair_csv_idempotent():
    """Calling repair_csv twice produces the same result as calling it once."""
    tags_dict = {
        "a.jpg": ["galaxy", "bright"],
        "b.jpg": ["star"],
    }
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        path = f.name
    try:
        save_tags(path, tags_dict)
        repair_csv(path)
        repair_csv(path)
        loaded = load_tags(path)
        assert set(loaded["a.jpg"]) == {"galaxy", "bright"}
        assert loaded["b.jpg"] == ["star"]
    finally:
        os.unlink(path)


def test_repair_csv_preserves_all_rows():
    tags_dict = {f"img{i}.jpg": ["tag_a"] for i in range(10)}
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        path = f.name
    try:
        save_tags(path, tags_dict)
        repair_csv(path)
        loaded = load_tags(path)
        assert len(loaded) == 10
    finally:
        os.unlink(path)
