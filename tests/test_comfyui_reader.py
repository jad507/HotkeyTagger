"""Tests for comfyui_reader.py"""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pytest

from comfyui_reader import (
    ComfyUIMetadata,
    _extract_lora_nodes,
    _extract_model_nodes,
    _extract_sampler_params,
    _normalize_token,
    _resolve_value,
    load_danbooru_tags,
    match_danbooru_tags,
    read_metadata,
)

# ---------------------------------------------------------------------------
# Fixtures / paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent.parent
TEST_IMAGES_DIR = _HERE / "comfyui" / "test images"
DANBOORU_PATH = _HERE / "comfyui" / "danbooru_tags.txt"
IMAGE1 = TEST_IMAGES_DIR / "151143_1.0_46_7_1.00.png"
IMAGE2 = TEST_IMAGES_DIR / "2026-06-10_105616_anima_00001_.png"

_IMAGES_PRESENT = IMAGE1.exists() and IMAGE2.exists()
_DANBOORU_PRESENT = DANBOORU_PATH.exists()

requires_images = pytest.mark.skipif(not _IMAGES_PRESENT, reason="test images not present")
requires_danbooru = pytest.mark.skipif(not _DANBOORU_PRESENT, reason="danbooru_tags.txt not present")


# ===========================================================================
# Group A — read_metadata integration (requires real PNG files)
# ===========================================================================

@requires_images
def test_read_metadata_image1_not_none():
    assert read_metadata(IMAGE1) is not None


@requires_images
def test_read_metadata_image1_steps():
    meta = read_metadata(IMAGE1)
    assert meta is not None
    assert meta.steps == 46


@requires_images
def test_read_metadata_image1_sampler():
    meta = read_metadata(IMAGE1)
    assert meta is not None
    assert meta.sampler == "exponential/res_2s"


@requires_images
def test_read_metadata_image1_cfg():
    meta = read_metadata(IMAGE1)
    assert meta is not None
    assert meta.cfg == pytest.approx(7.0, abs=0.01)


@requires_images
def test_read_metadata_image1_denoise():
    meta = read_metadata(IMAGE1)
    assert meta is not None
    assert meta.denoise == pytest.approx(1.0, abs=0.001)


@requires_images
def test_read_metadata_image1_model():
    meta = read_metadata(IMAGE1)
    assert meta is not None
    assert any("ultrarealFineTune_v20AnimaBase1" in m for m in meta.models)


@requires_images
def test_read_metadata_image1_loras_present():
    meta = read_metadata(IMAGE1)
    assert meta is not None
    lora_names = [name for name, _ in meta.loras]
    assert any("lenovo_ultrareal_anima_base1" in n for n in lora_names)


@requires_images
def test_read_metadata_image1_positive_prompt_contains_1girl():
    meta = read_metadata(IMAGE1)
    assert meta is not None
    assert meta.positive_prompt is not None
    assert "1girl" in meta.positive_prompt.lower()


@requires_images
def test_read_metadata_image1_negative_prompt_not_none():
    meta = read_metadata(IMAGE1)
    assert meta is not None
    assert meta.negative_prompt is not None


@requires_images
def test_read_metadata_image2_not_none():
    assert read_metadata(IMAGE2) is not None


@requires_images
def test_read_metadata_image2_steps():
    meta = read_metadata(IMAGE2)
    assert meta is not None
    assert meta.steps == 8


@requires_images
def test_read_metadata_image2_scheduler():
    meta = read_metadata(IMAGE2)
    assert meta is not None
    assert meta.scheduler == "simple"


@requires_images
def test_read_metadata_image2_cfg_is_none():
    meta = read_metadata(IMAGE2)
    assert meta is not None
    assert meta.cfg is None


@requires_images
def test_read_metadata_image2_models():
    meta = read_metadata(IMAGE2)
    assert meta is not None
    assert len(meta.models) >= 2


@requires_images
def test_read_metadata_image2_negative_is_none():
    meta = read_metadata(IMAGE2)
    assert meta is not None
    assert meta.negative_prompt is None


def test_read_metadata_non_comfyui_png_returns_none():
    from PIL import Image as PilImage
    buf = io.BytesIO()
    PilImage.new("RGB", (10, 10)).save(buf, "PNG")
    buf.seek(0)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(buf.getvalue())
        tmp = Path(f.name)
    try:
        assert read_metadata(tmp) is None
    finally:
        os.unlink(tmp)


def test_read_metadata_nonexistent_file_returns_none():
    assert read_metadata(Path("/nonexistent/fake_12345.png")) is None


# ===========================================================================
# Group B — _resolve_value unit tests (mock graphs)
# ===========================================================================

def test_resolve_literal_string():
    assert _resolve_value("hello", {}) == "hello"


def test_resolve_literal_int():
    assert _resolve_value(42, {}) == 42


def test_resolve_literal_float():
    assert _resolve_value(3.14, {}) == pytest.approx(3.14)


def test_resolve_primitive_node():
    graph = {"1": {"class_type": "PrimitiveNode", "inputs": {"value": 99}}}
    assert _resolve_value(["1", 0], graph) == 99


def test_resolve_impact_wildcard_populated_text():
    graph = {"5": {"class_type": "ImpactWildcardProcessor",
                   "inputs": {"populated_text": "46", "wildcard_text": "{46|60}"}}}
    assert _resolve_value(["5", 0], graph) == "46"


def test_resolve_impact_convert_via_wildcard():
    graph = {
        "3": {"class_type": "ImpactConvertDataType", "inputs": {"value": ["5", 0]}},
        "5": {"class_type": "ImpactWildcardProcessor",
              "inputs": {"populated_text": "7.0", "wildcard_text": "{3|7}"}},
    }
    assert _resolve_value(["3", 1], graph) == "7.0"


def test_resolve_string_concatenate():
    graph = {
        "A": {"class_type": "StringConcatenate",
              "inputs": {"string_a": "hello", "string_b": "world", "delimiter": " "}},
    }
    assert _resolve_value(["A", 0], graph) == "hello world"


def test_resolve_depth_limit_returns_none():
    # Chain of depth > 4 should return None instead of infinite-looping
    graph = {str(i): {"class_type": "ImpactConvertDataType",
                      "inputs": {"value": [str(i + 1), 0]}} for i in range(10)}
    assert _resolve_value(["0", 0], graph) is None


def test_resolve_missing_node_returns_none():
    assert _resolve_value(["nonexistent", 0], {}) is None


def test_resolve_empty_list_returns_none():
    assert _resolve_value([], {}) is None


# ===========================================================================
# Group C — LoRA extraction (mock graphs)
# ===========================================================================

def test_extract_int8_lora_stack_single():
    graph = {"1": {"class_type": "INT8LoraLoaderStack", "inputs": {
        "lora_1": "my_lora.safetensors", "strength_1": 0.8,
        "lora_2": "None", "strength_2": 1.0,
    }}}
    loras = _extract_lora_nodes(graph)
    assert len(loras) == 1
    assert loras[0][0] == "my_lora"
    assert loras[0][1] == pytest.approx(0.8)


def test_extract_rgthree_lora_stack():
    graph = {"1": {"class_type": "Lora Loader Stack (rgthree)", "inputs": {
        "lora_01": "None", "strength_01": 0.0,
        "lora_02": "alpha.safetensors", "strength_02": 0.6,
    }}}
    loras = _extract_lora_nodes(graph)
    assert len(loras) == 1
    assert loras[0][0] == "alpha"
    assert loras[0][1] == pytest.approx(0.6)


def test_extract_loras_deduplication():
    graph = {
        "1": {"class_type": "INT8LoraLoaderStack", "inputs": {
            "lora_1": "same.safetensors", "strength_1": 0.5,
            "lora_2": "None", "strength_2": 1.0,
        }},
        "2": {"class_type": "Lora Loader Stack (rgthree)", "inputs": {
            "lora_01": "same.safetensors", "strength_01": 0.5,
        }},
    }
    loras = _extract_lora_nodes(graph)
    assert len(loras) == 1


def test_extract_loras_empty_graph():
    assert _extract_lora_nodes({}) == []


def test_extract_loras_none_entries_skipped():
    graph = {"1": {"class_type": "INT8LoraLoaderStack", "inputs": {
        "lora_1": "None", "strength_1": 1.0,
        "lora_2": "None", "strength_2": 1.0,
    }}}
    assert _extract_lora_nodes(graph) == []


def test_extract_lora_strength_reference_resolution():
    graph = {
        "conv": {"class_type": "ImpactConvertDataType", "inputs": {"value": ["wc", 0]}},
        "wc": {"class_type": "ImpactWildcardProcessor",
               "inputs": {"populated_text": "0.75", "wildcard_text": "{0.75|1.0}"}},
        "1": {"class_type": "INT8LoraLoaderStack", "inputs": {
            "lora_1": "test.safetensors", "strength_1": ["conv", 1],
            "lora_2": "None", "strength_2": 1.0,
        }},
    }
    loras = _extract_lora_nodes(graph)
    assert len(loras) == 1
    assert loras[0][1] == pytest.approx(0.75)


# ===========================================================================
# Group D — Danbooru matching
# ===========================================================================

@requires_danbooru
def test_load_danbooru_tags_returns_dict():
    tags = load_danbooru_tags(DANBOORU_PATH)
    assert isinstance(tags, dict)
    assert len(tags) > 90_000


@requires_danbooru
def test_load_danbooru_tags_caching():
    tags1 = load_danbooru_tags(DANBOORU_PATH)
    tags2 = load_danbooru_tags(DANBOORU_PATH)
    assert tags1 is tags2


@requires_danbooru
def test_danbooru_has_known_tag():
    tags = load_danbooru_tags(DANBOORU_PATH)
    assert "1girl" in tags
    assert tags["1girl"] > 6_000_000


def test_match_danbooru_tags_basic():
    tags = {"1girl": 6268955, "breasts": 3600421, "blush": 3070609}
    result = match_danbooru_tags("1girl, breasts, blush", tags)
    assert result == ["1girl", "breasts", "blush"]


def test_match_danbooru_tags_spaces_to_underscores():
    tags = {"bare_shoulders": 1017448, "small_breasts": 515150}
    result = match_danbooru_tags("bare shoulders, small breasts", tags)
    assert "bare_shoulders" in result


def test_match_danbooru_tags_attention_stripping():
    tags = {"loli": 154289, "breasts": 3600421}
    result = match_danbooru_tags("(loli:1.2), [breasts]", tags)
    assert "loli" in result
    assert "breasts" in result


def test_match_danbooru_tags_at_prefix_filtered():
    result = match_danbooru_tags("@nsfw, 1girl", {"1girl": 6268955, "nsfw": 123})
    assert "nsfw" not in result
    assert "1girl" in result


@requires_danbooru
def test_match_danbooru_tags_hyphenated():
    tags = load_danbooru_tags(DANBOORU_PATH)
    result = match_danbooru_tags("dark-skinned female", tags)
    assert "dark-skinned_female" in result


def test_match_danbooru_tags_empty_prompt():
    assert match_danbooru_tags("", {"1girl": 1}) == []


def test_match_danbooru_tags_multiline():
    tags = {"breasts": 1, "ponytail": 2}
    result = match_danbooru_tags("breasts\nponytail", tags)
    assert "breasts" in result
    assert "ponytail" in result


def test_normalize_token_basic():
    assert _normalize_token("  BREASTS  ") == "breasts"


def test_normalize_token_attention():
    assert _normalize_token("(loli:1.2)") == "loli"


def test_normalize_token_spaces_to_underscores():
    assert _normalize_token("dark skin") == "dark_skin"


def test_normalize_token_at_prefix():
    assert _normalize_token("@nsfw") == ""


def test_normalize_token_hyphen_preserved():
    assert _normalize_token("dark-skinned female") == "dark-skinned_female"


def test_normalize_token_bracket():
    assert _normalize_token("[breasts]") == "breasts"


# ===========================================================================
# Group E — Sampler extraction (mock graphs)
# ===========================================================================

def test_extract_ksampler_literal_steps():
    graph = {"1": {"class_type": "KSampler", "inputs": {
        "steps": 20, "sampler_name": "euler", "scheduler": "karras",
        "denoise": 1.0, "cfg": 7.0,
    }}}
    params = _extract_sampler_params(graph)
    assert params["steps"] == 20
    assert params["sampler"] == "euler"
    assert params["scheduler"] == "karras"
    assert params["cfg"] == pytest.approx(7.0)
    assert params["denoise"] == pytest.approx(1.0)


def test_extract_basic_scheduler():
    graph = {"s": {"class_type": "BasicScheduler", "inputs": {
        "scheduler": "simple", "steps": 8, "denoise": 1.0, "model": ["m", 0],
    }}}
    params = _extract_sampler_params(graph)
    assert params["steps"] == 8
    assert params["scheduler"] == "simple"
    assert params.get("cfg") is None


def test_extract_sampler_empty_graph():
    assert _extract_sampler_params({}) == {}


def test_extract_model_nodes_unet():
    graph = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "mymodel.safetensors"}}}
    models = _extract_model_nodes(graph)
    assert models == ["mymodel"]


def test_extract_model_nodes_checkpoint():
    graph = {"1": {"class_type": "CheckpointLoaderSimple",
                   "inputs": {"ckpt_name": "v1-5.safetensors"}}}
    models = _extract_model_nodes(graph)
    assert models == ["v1-5"]


def test_extract_model_nodes_deduplication():
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "same.safetensors"}},
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "same.safetensors"}},
    }
    assert len(_extract_model_nodes(graph)) == 1
