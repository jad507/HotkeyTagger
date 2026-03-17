# Copilot Instructions for HotkeyTagger

## Project Overview

HotkeyTagger is a Python/PyQt5 desktop application for hand-classifying image
datasets using keyboard hotkeys. Users open a folder of images, bind single
keys to tag names (e.g. `g` → `galaxy`), and step through images pressing
hotkeys to toggle tags. Classifications are saved to a CSV file for use in
supervised machine learning workflows.

## Repository Structure

```
hotkey_tagger.py   – Main PyQt5 GUI application (entry point: python hotkey_tagger.py)
csv_manager.py     – Save/load/repair the tags CSV
settings.py        – Persistent session state stored as JSON (hotkeys, last folder, last index)
datasetDL.py       – Helper script to download scikit-learn test datasets (digits, Olivetti faces)
requirements.txt   – Runtime dependencies (PyQt5 >= 5.15)
tests/
  conftest.py      – Adds project root to sys.path so tests can import modules directly
  test_csv_manager.py
  test_settings.py
```

## How to Run

```bash
# Install dependencies (Python 3.8+)
pip install -r requirements.txt

# Launch the GUI
python hotkey_tagger.py

# Download sample datasets for manual testing
python datasetDL.py
```

## How to Test

Tests use **pytest** and cover `csv_manager.py` and `settings.py` only
(no PyQt5 is imported in tests).

```bash
# From the repository root
pip install pytest
pytest tests/
```

All tests must pass before submitting a pull request. Do not delete or weaken
existing tests.

## Coding Conventions

- **Python version**: 3.8+. Use `from __future__ import annotations` at the
  top of every module for PEP-563 postponed evaluation of annotations.
- **Type hints**: Annotate all function signatures and module-level variables.
  Use `typing` imports (`Dict`, `List`, `Optional`, `Set`) for compatibility.
- **Pathlib**: Use `pathlib.Path` for all file-system interactions. Never build
  paths with string concatenation.
- **POSIX serialization**: Store paths as POSIX strings (`path.as_posix()`) in
  JSON and CSV files. Reconstruct with `Path(posix_str)` on load. This keeps
  files cross-platform.
- **Docstrings**: Every module, public class, and public function must have a
  docstring. Module docstrings explain purpose and any file-format details.
- **Style**: PEP 8. Prefer explicit over implicit. Keep lines ≤ 100 characters.

## Architecture Notes

### `settings.py` (`HotkeySettings`)
Stores the global application state that persists between runs:
- `hotkey_map`: `Dict[str, str]` — maps a single lowercase key character to a
  tag name.
- `last_folder` / `last_image_index` / `last_csv_path` — restore the previous
  session on next launch.
- Per-folder hotkeys are stored in a `hotkeys.json` file inside each image
  folder, so different folders can have independent hotkey sets.

### `csv_manager.py`
- One row per image file. First column `filename` (POSIX string), then one
  binary (`0`/`1`) column per tag.
- Tags are always written in **sorted** order.
- `repair_csv` handles the case where new tags are added after rows were
  already written: it fills missing cells with `0` and is **idempotent**.

### `hotkey_tagger.py`
- PyQt5 `QMainWindow` subclass; no direct test coverage (requires a display).
- Key bindings support multi-key syntax (`5,q` or `5q`) so multiple keys can
  map to the same tag.
- Reserved navigation keys (`left`, `right`) advance/retreat through images
  and cannot be bound to tags.
- Supported image formats: `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`,
  `.tif`, `.fits`.

## Pull Request Guidelines

- Keep changes focused and minimal — avoid unrelated refactors in the same PR.
- Add or update tests in `tests/` for any logic added to `csv_manager.py` or
  `settings.py`.
- GUI changes in `hotkey_tagger.py` do not require automated tests but should
  be manually verified.
- Update this file if project structure or conventions change.
