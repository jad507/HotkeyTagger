"""Tests for comfyui_params_manager.py"""
from __future__ import annotations

from pathlib import Path

import pytest

from comfyui_params_manager import (
    ComfyUIParamsRecord,
    _deserialize_loras,
    _deserialize_models,
    _serialize_loras,
    _serialize_models,
    load_params,
    save_params,
    upsert_param,
)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def test_serialize_models_basic():
    assert _serialize_models(["modelA", "modelB"]) == "modelA|modelB"


def test_serialize_models_empty():
    assert _serialize_models([]) == ""


def test_deserialize_models_basic():
    assert _deserialize_models("modelA|modelB") == ["modelA", "modelB"]


def test_deserialize_models_empty_string():
    assert _deserialize_models("") == []


def test_serialize_loras_basic():
    assert _serialize_loras([("loraA", 0.8), ("loraB", 1.0)]) == "loraA:0.8|loraB:1.0"


def test_serialize_loras_empty():
    assert _serialize_loras([]) == ""


def test_deserialize_loras_basic():
    result = _deserialize_loras("loraA:0.8|loraB:1.0")
    assert result == [("loraA", pytest.approx(0.8)), ("loraB", pytest.approx(1.0))]


def test_deserialize_loras_empty_string():
    assert _deserialize_loras("") == []


def test_deserialize_loras_no_strength():
    # Lora entry without a colon defaults to strength 1.0
    result = _deserialize_loras("loraA")
    assert result == [("loraA", pytest.approx(1.0))]


def test_models_round_trip():
    original = ["modelA", "modelB", "modelC"]
    assert _deserialize_models(_serialize_models(original)) == original


def test_loras_round_trip():
    original = [("loraA", 0.8), ("loraB", 1.0)]
    result = _deserialize_loras(_serialize_loras(original))
    assert len(result) == len(original)
    for (name, strength), (exp_name, exp_strength) in zip(result, original):
        assert name == exp_name
        assert strength == pytest.approx(exp_strength)


# ---------------------------------------------------------------------------
# save_params / load_params round-trip
# ---------------------------------------------------------------------------

def _make_record(**kwargs) -> ComfyUIParamsRecord:
    return ComfyUIParamsRecord(**kwargs)


def test_save_load_round_trip(tmp_path):
    csv_path = tmp_path / "comfyui_params.csv"
    records = {
        Path("img1.png"): _make_record(steps=46, cfg=7.0, denoise=1.0,
                                        sampler="euler", scheduler="karras",
                                        models=["modelA"],
                                        loras=[("loraA", 0.8)]),
        Path("img2.png"): _make_record(steps=8, cfg=None, denoise=1.0,
                                        sampler="SamplerER_SDE", scheduler="simple",
                                        models=["modelA", "modelB"],
                                        loras=[]),
    }
    save_params(csv_path, records)
    loaded = load_params(csv_path)

    assert set(loaded.keys()) == set(records.keys())

    r1 = loaded[Path("img1.png")]
    assert r1.steps == 46
    assert r1.cfg == pytest.approx(7.0)
    assert r1.denoise == pytest.approx(1.0)
    assert r1.sampler == "euler"
    assert r1.scheduler == "karras"
    assert r1.models == ["modelA"]
    assert len(r1.loras) == 1
    assert r1.loras[0][0] == "loraA"
    assert r1.loras[0][1] == pytest.approx(0.8)

    r2 = loaded[Path("img2.png")]
    assert r2.steps == 8
    assert r2.cfg is None
    assert r2.models == ["modelA", "modelB"]
    assert r2.loras == []


def test_load_params_missing_file_returns_empty(tmp_path):
    result = load_params(tmp_path / "nonexistent.csv")
    assert result == {}


def test_save_load_none_cfg(tmp_path):
    csv_path = tmp_path / "comfyui_params.csv"
    record = _make_record(cfg=None, steps=10)
    save_params(csv_path, {Path("img.png"): record})
    loaded = load_params(csv_path)
    assert loaded[Path("img.png")].cfg is None


def test_posix_path_roundtrip(tmp_path):
    csv_path = tmp_path / "comfyui_params.csv"
    key = Path("subdir/image.png")
    save_params(csv_path, {key: _make_record(steps=5)})
    loaded = load_params(csv_path)
    # Key must survive POSIX serialization
    assert Path("subdir/image.png") in loaded


# ---------------------------------------------------------------------------
# upsert_param
# ---------------------------------------------------------------------------

def test_upsert_creates_file(tmp_path):
    csv_path = tmp_path / "comfyui_params.csv"
    assert not csv_path.exists()
    upsert_param(csv_path, Path("img.png"), _make_record(steps=1))
    assert csv_path.exists()


def test_upsert_adds_new_entry(tmp_path):
    csv_path = tmp_path / "comfyui_params.csv"
    upsert_param(csv_path, Path("img1.png"), _make_record(steps=10))
    upsert_param(csv_path, Path("img2.png"), _make_record(steps=20))
    loaded = load_params(csv_path)
    assert loaded[Path("img1.png")].steps == 10
    assert loaded[Path("img2.png")].steps == 20


def test_upsert_updates_existing_entry(tmp_path):
    csv_path = tmp_path / "comfyui_params.csv"
    upsert_param(csv_path, Path("img.png"), _make_record(steps=10))
    upsert_param(csv_path, Path("img.png"), _make_record(steps=99))
    loaded = load_params(csv_path)
    assert loaded[Path("img.png")].steps == 99
    assert len(loaded) == 1  # not duplicated


def test_upsert_preserves_other_rows(tmp_path):
    csv_path = tmp_path / "comfyui_params.csv"
    upsert_param(csv_path, Path("a.png"), _make_record(steps=1))
    upsert_param(csv_path, Path("b.png"), _make_record(steps=2))
    upsert_param(csv_path, Path("a.png"), _make_record(steps=99))
    loaded = load_params(csv_path)
    assert loaded[Path("b.png")].steps == 2
    assert loaded[Path("a.png")].steps == 99
