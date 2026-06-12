"""
comfyui_params_manager.py – Persist ComfyUI generation parameters to a CSV file.

File format — ``comfyui_params.csv``
-------------------------------------
One row per image.  Columns:

    filename, steps, cfg, denoise, sampler, scheduler, models, loras

- ``filename``: POSIX string relative to the image folder (same convention as tags.csv).
- ``steps``: integer, or empty if unknown.
- ``cfg``: float, or empty (CFG-free workflows have no CFG value).
- ``denoise``: float, or empty.
- ``sampler``, ``scheduler``: string, or empty.
- ``models``: ``|``-joined list of model filename stems; empty if none.
- ``loras``: ``|``-joined list of ``name:strength`` pairs; empty if none.

Example row::

    test images/img.png,46,7.0,1.0,exponential/res_2s,normal,modelA,loraA:0.8|loraB:1.0
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

PARAMS_FILENAME = "comfyui_params.csv"

_FIELDNAMES = ["filename", "steps", "cfg", "denoise", "sampler", "scheduler", "models", "loras"]


@dataclass
class ComfyUIParamsRecord:
    """User-confirmed generation parameters for one image."""

    steps: Optional[int] = None
    cfg: Optional[float] = None
    denoise: Optional[float] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    models: List[str] = field(default_factory=list)
    loras: List[Tuple[str, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_models(models: List[str]) -> str:
    return "|".join(m for m in models if m)


def _deserialize_models(s: str) -> List[str]:
    if not s:
        return []
    return [m for m in s.split("|") if m]


def _serialize_loras(loras: List[Tuple[str, float]]) -> str:
    return "|".join(f"{name}:{strength}" for name, strength in loras if name)


def _deserialize_loras(s: str) -> List[Tuple[str, float]]:
    if not s:
        return []
    result: List[Tuple[str, float]] = []
    for part in s.split("|"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, _, strength_str = part.rpartition(":")
            try:
                result.append((name, float(strength_str)))
            except ValueError:
                result.append((name, 1.0))
        else:
            result.append((part, 1.0))
    return result


def _record_to_row(rel_path: Path, record: ComfyUIParamsRecord) -> Dict[str, str]:
    return {
        "filename": rel_path.as_posix(),
        "steps": str(record.steps) if record.steps is not None else "",
        "cfg": str(record.cfg) if record.cfg is not None else "",
        "denoise": str(record.denoise) if record.denoise is not None else "",
        "sampler": record.sampler or "",
        "scheduler": record.scheduler or "",
        "models": _serialize_models(record.models),
        "loras": _serialize_loras(record.loras),
    }


def _row_to_record(row: Dict[str, str]) -> Tuple[Path, ComfyUIParamsRecord]:
    steps: Optional[int] = None
    if row.get("steps"):
        try:
            steps = int(row["steps"])
        except ValueError:
            pass

    cfg: Optional[float] = None
    if row.get("cfg"):
        try:
            cfg = float(row["cfg"])
        except ValueError:
            pass

    denoise: Optional[float] = None
    if row.get("denoise"):
        try:
            denoise = float(row["denoise"])
        except ValueError:
            pass

    return Path(row["filename"]), ComfyUIParamsRecord(
        steps=steps,
        cfg=cfg,
        denoise=denoise,
        sampler=row.get("sampler") or None,
        scheduler=row.get("scheduler") or None,
        models=_deserialize_models(row.get("models", "")),
        loras=_deserialize_loras(row.get("loras", "")),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_params(csv_path: Path, records: Dict[Path, ComfyUIParamsRecord]) -> None:
    """Write all records to *csv_path* (overwrites any existing file).

    Parameters
    ----------
    csv_path:
        Destination path for ``comfyui_params.csv``.
    records:
        Mapping from relative ``Path`` keys to :class:`ComfyUIParamsRecord` values.
    """
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for rel_path, record in records.items():
            writer.writerow(_record_to_row(rel_path, record))


def load_params(csv_path: Path) -> Dict[Path, ComfyUIParamsRecord]:
    """Parse *csv_path* and return a mapping of relative paths to records.

    Returns an empty dict if the file does not exist.
    """
    if not csv_path.exists():
        return {}
    records: Dict[Path, ComfyUIParamsRecord] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("filename"):
                continue
            try:
                rel_path, record = _row_to_record(row)
                records[rel_path] = record
            except Exception:
                continue
    return records


def upsert_param(
    csv_path: Path, rel_path: Path, record: ComfyUIParamsRecord
) -> None:
    """Load existing records, update/insert *rel_path*, and save back.

    Creates the file if it does not exist.
    """
    records = load_params(csv_path)
    records[rel_path] = record
    save_params(csv_path, records)
