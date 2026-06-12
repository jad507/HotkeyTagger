"""
comfyui_reader.py – Extract generation metadata from ComfyUI-generated PNG files.

ComfyUI embeds the workflow execution graph as JSON in the ``"prompt"`` PNG text chunk.
The graph is a flat dict ``{node_id: {class_type: str, inputs: dict}}``.  Input values
may be literals (int/float/str) or node references of the form ``[node_id, output_index]``.

Public API
----------
read_metadata(path)
    Parse a PNG and return a :class:`ComfyUIMetadata` or ``None``.

load_danbooru_tags(tags_file)
    Load a ``tag,count`` file into a cached ``{tag: count}`` dict.

match_danbooru_tags(prompt, tags)
    Tokenise a prompt and return matching Danbooru tags sorted by popularity.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

PromptGraph = Dict[str, Dict[str, Any]]


@dataclass
class ComfyUIMetadata:
    """Generation parameters extracted from a ComfyUI PNG."""

    steps: Optional[int] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    denoise: Optional[float] = None
    cfg: Optional[float] = None
    models: List[str] = field(default_factory=list)
    loras: List[Tuple[str, float]] = field(default_factory=list)
    positive_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None


# ---------------------------------------------------------------------------
# Danbooru tag cache
# ---------------------------------------------------------------------------

_DANBOORU_CACHE: Optional[Dict[str, int]] = None
_DANBOORU_CACHE_PATH: Optional[Path] = None


def load_danbooru_tags(tags_file: Path) -> Dict[str, int]:
    """Load a ``tag,count`` file into a ``{tag: count}`` dict; cached after first load.

    Parameters
    ----------
    tags_file:
        Path to the file with lines in ``tag_name,count`` format.
    """
    global _DANBOORU_CACHE, _DANBOORU_CACHE_PATH
    if _DANBOORU_CACHE is not None and _DANBOORU_CACHE_PATH == tags_file:
        return _DANBOORU_CACHE
    result: Dict[str, int] = {}
    for line in tags_file.read_text(encoding="utf-8").splitlines():
        if "," not in line:
            continue
        tag, _, count_str = line.rpartition(",")
        tag = tag.strip()
        if tag:
            try:
                result[tag] = int(count_str.strip())
            except ValueError:
                pass
    _DANBOORU_CACHE = result
    _DANBOORU_CACHE_PATH = tags_file
    return result


# ---------------------------------------------------------------------------
# Danbooru tag matching
# ---------------------------------------------------------------------------

# Strip attention-weight notation and bracket wrappers
_ATTENTION_RE = re.compile(
    r"^\(+|"       # leading (
    r"\)+$|"       # trailing )
    r"^\[+|"       # leading [
    r"\]+$|"       # trailing ]
    r":\d+\.?\d*$" # :weight suffix like :1.2 or :1
)


def _normalize_token(token: str) -> str:
    """Normalize a single prompt token for Danbooru lookup."""
    t = token.strip()
    # Strip attention marks iteratively (handles nested parens/brackets)
    prev = None
    while prev != t:
        prev = t
        t = _ATTENTION_RE.sub("", t).strip()
    t = t.lower()
    # Strip backslash-escaped chars used in SD attention (e.g. \( \))
    t = re.sub(r"\\.", "", t).strip()
    t = t.replace(" ", "_")
    if t.startswith("@"):
        return ""  # wildcard category refs are not Danbooru tags
    return t


def match_danbooru_tags(prompt: str, tags: Dict[str, int]) -> List[str]:
    """Return Danbooru tags found in *prompt*, sorted by tag count descending.

    Parameters
    ----------
    prompt:
        Raw positive prompt text from a ComfyUI generation.
    tags:
        Tag dict from :func:`load_danbooru_tags`.
    """
    if not prompt or not tags:
        return []

    matched: Dict[str, int] = {}
    for raw in re.split(r"[,\n]+", prompt):
        normalized = _normalize_token(raw)
        if not normalized:
            continue
        if normalized in tags:
            matched[normalized] = tags[normalized]

    return sorted(matched, key=lambda t: matched[t], reverse=True)


# ---------------------------------------------------------------------------
# Reference resolution
# ---------------------------------------------------------------------------

_MAX_RESOLVE_DEPTH = 4


def _resolve_value(ref: Any, graph: PromptGraph, depth: int = 0) -> Any:
    """Recursively resolve a node reference to a literal value.

    Parameters
    ----------
    ref:
        A literal value OR a ``[node_id, output_index]`` list reference.
    graph:
        The full flat prompt graph.
    depth:
        Current recursion depth; stops at :data:`_MAX_RESOLVE_DEPTH`.
    """
    if depth >= _MAX_RESOLVE_DEPTH:
        return None
    if not isinstance(ref, list):
        return ref
    if len(ref) < 2:
        return None

    node_id = str(ref[0])
    node = graph.get(node_id)
    if node is None:
        return None

    class_type: str = node.get("class_type", "")
    inputs: Dict[str, Any] = node.get("inputs", {})

    if class_type == "ImpactWildcardProcessor":
        # populated_text holds the resolved single value; prefer it over wildcard_text
        val = inputs.get("populated_text")
        return val if val is not None else inputs.get("wildcard_text")

    if class_type in {
        "PrimitiveNode", "PrimitiveString", "PrimitiveStringMultiline",
        "INT", "FLOAT", "PrimitiveFloat", "PrimitiveInt",
    }:
        return _resolve_value(inputs.get("value"), graph, depth + 1)

    if class_type == "ImpactConvertDataType":
        # output_idx 0=string, 1=float, 2=int — but the upstream value is the same;
        # call site coerces via int()/float() as needed
        return _resolve_value(inputs.get("value"), graph, depth + 1)

    if class_type == "StringConcatenate":
        a = _resolve_value(inputs.get("string_a"), graph, depth + 1)
        b = _resolve_value(inputs.get("string_b"), graph, depth + 1)
        delimiter = inputs.get("delimiter", "")
        if a is not None and b is not None:
            return str(a) + str(delimiter) + str(b)
        return a if a is not None else b

    if class_type == "Power Prompt (rgthree)":
        return _resolve_value(inputs.get("prompt"), graph, depth + 1)

    # Generic fallback: try common literal-holder fields
    for fname in ("text", "populated_text", "value"):
        val = inputs.get(fname)
        if val is not None:
            resolved = _resolve_value(val, graph, depth + 1)
            if resolved is not None:
                return resolved
    return None


# ---------------------------------------------------------------------------
# Sampler parameter extraction
# ---------------------------------------------------------------------------

_KSAMPLER_TYPES = frozenset({
    "KSampler",
    "KSamplerAdvanced",
    "ClownsharKSampler_Beta",
})

_SCHEDULER_TYPES = frozenset({"BasicScheduler"})


def _extract_sampler_params(graph: PromptGraph) -> Dict[str, Any]:
    """Return a dict with keys steps/sampler/scheduler/denoise/cfg from the graph.

    Tries KSampler-family nodes first; falls back to SamplerCustomAdvanced architecture.
    """
    result: Dict[str, Any] = {}

    # Pass 1 — KSampler-family
    for node in graph.values():
        if node.get("class_type") not in _KSAMPLER_TYPES:
            continue
        inp = node.get("inputs", {})

        if "steps" in inp and result.get("steps") is None:
            try:
                result["steps"] = int(_resolve_value(inp["steps"], graph))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass

        if "sampler_name" in inp and result.get("sampler") is None:
            raw = _resolve_value(inp["sampler_name"], graph)
            if isinstance(raw, str):
                result["sampler"] = raw

        if "scheduler" in inp and result.get("scheduler") is None:
            raw = _resolve_value(inp["scheduler"], graph)
            if isinstance(raw, str):
                result["scheduler"] = raw

        if "denoise" in inp and result.get("denoise") is None:
            try:
                result["denoise"] = float(_resolve_value(inp["denoise"], graph))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass

        if "cfg" in inp and result.get("cfg") is None:
            try:
                result["cfg"] = float(_resolve_value(inp["cfg"], graph))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass

        break  # use only the first sampler node found

    if result:
        return result

    # Pass 2 — SamplerCustomAdvanced: BasicScheduler + first Sampler* node
    for node in graph.values():
        if node.get("class_type") not in _SCHEDULER_TYPES:
            continue
        inp = node.get("inputs", {})
        if result.get("steps") is None:
            try:
                result["steps"] = int(_resolve_value(inp.get("steps"), graph))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
        if result.get("scheduler") is None:
            raw = _resolve_value(inp.get("scheduler"), graph)
            if isinstance(raw, str):
                result["scheduler"] = raw
        if result.get("denoise") is None:
            try:
                result["denoise"] = float(_resolve_value(inp.get("denoise"), graph))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
        break

    for node in graph.values():
        ct = node.get("class_type", "")
        if ct.startswith("Sampler") and ct not in _KSAMPLER_TYPES:
            result.setdefault("sampler", ct)
            break

    return result


# ---------------------------------------------------------------------------
# Model node extraction
# ---------------------------------------------------------------------------

_UNET_LOADER_TYPES = frozenset({"UNETLoader", "CheckpointLoaderSimple"})


def _extract_model_nodes(graph: PromptGraph) -> List[str]:
    """Return model filename stems from UNETLoader / CheckpointLoaderSimple nodes."""
    seen: set = set()
    results: List[str] = []
    for node in graph.values():
        ct = node.get("class_type", "")
        if ct not in _UNET_LOADER_TYPES:
            continue
        inp = node.get("inputs", {})
        name_key = "unet_name" if ct == "UNETLoader" else "ckpt_name"
        fname = inp.get(name_key, "")
        if isinstance(fname, str) and fname:
            stem = Path(fname).stem
            if stem not in seen:
                seen.add(stem)
                results.append(stem)
    return results


# ---------------------------------------------------------------------------
# LoRA node extraction
# ---------------------------------------------------------------------------

_SINGLE_LORA_TYPES = frozenset({"LoraLoader", "LoraLoaderModelOnly"})


def _extract_lora_nodes(graph: PromptGraph) -> List[Tuple[str, float]]:
    """Return ``(lora_stem, strength)`` tuples from all LoRA loader nodes.

    Handles INT8LoraLoaderStack, Lora Loader Stack (rgthree), CR LoRA Stack,
    and single LoraLoader nodes.  Skips ``"None"`` entries; deduplicates by stem.
    """
    results: List[Tuple[str, float]] = []
    seen: set = set()

    def _add(name: Any, strength_ref: Any) -> None:
        if not isinstance(name, str) or name.lower() in ("none", ""):
            return
        stem = Path(name).stem
        if stem in seen:
            return
        raw = _resolve_value(strength_ref, graph)
        try:
            strength = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            strength = 1.0
        seen.add(stem)
        results.append((stem, strength))

    for node in graph.values():
        ct = node.get("class_type", "")
        inp = node.get("inputs", {})

        if ct in _SINGLE_LORA_TYPES:
            _add(inp.get("lora_name"), inp.get("strength_model"))

        elif ct == "INT8LoraLoaderStack":
            for i in range(1, 11):
                _add(inp.get(f"lora_{i}"), inp.get(f"strength_{i}"))

        elif ct == "Lora Loader Stack (rgthree)":
            for i in range(1, 20):
                key = f"lora_{i:02d}"
                if key not in inp:
                    break
                _add(inp.get(key), inp.get(f"strength_{i:02d}"))

        elif ct == "CR LoRA Stack":
            for i in range(1, 20):
                key = f"lora_name_{i}"
                if key not in inp:
                    break
                _add(inp.get(key), inp.get(f"strength_{i}"))

    return results


# ---------------------------------------------------------------------------
# Prompt text extraction
# ---------------------------------------------------------------------------

def _find_conditioning_text(
    ref: Any, graph: PromptGraph, depth: int = 0
) -> Optional[str]:
    """Follow a conditioning reference back to its source text."""
    if depth > 6 or not isinstance(ref, list) or len(ref) < 1:
        return None
    node_id = str(ref[0])
    node = graph.get(node_id)
    if node is None:
        return None
    ct = node.get("class_type", "")
    inp = node.get("inputs", {})

    if ct == "CLIPTextEncode":
        raw = _resolve_value(inp.get("text"), graph)
        return str(raw) if raw is not None else None

    if ct == "Power Prompt (rgthree)":
        raw = _resolve_value(inp.get("prompt"), graph)
        return str(raw) if raw is not None else None

    if ct.startswith("Conditioning") or ct == "BasicGuider":
        return _find_conditioning_text(inp.get("conditioning"), graph, depth + 1)

    return None


def _extract_prompt_text(graph: PromptGraph) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(positive_prompt, negative_prompt)`` from the graph.

    Strategy 1: KSampler-family node → follow positive/negative conditioning inputs.
    Strategy 2: SamplerCustomAdvanced → follow guider chain; negative is None.
    """
    # Strategy 1
    for node in graph.values():
        if node.get("class_type") not in _KSAMPLER_TYPES:
            continue
        inp = node.get("inputs", {})
        positive = _find_conditioning_text(inp.get("positive"), graph)
        negative = _find_conditioning_text(inp.get("negative"), graph)
        return positive, negative

    # Strategy 2
    for node in graph.values():
        if node.get("class_type") != "SamplerCustomAdvanced":
            continue
        inp = node.get("inputs", {})
        positive = _find_conditioning_text(inp.get("guider"), graph)
        return positive, None

    return None, None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def read_metadata(path: Path) -> Optional[ComfyUIMetadata]:
    """Read ComfyUI generation metadata from a PNG file.

    Parameters
    ----------
    path:
        Path to a PNG file.

    Returns
    -------
    A :class:`ComfyUIMetadata` instance if the file contains a ComfyUI ``prompt``
    chunk, or ``None`` if the file is not a ComfyUI PNG or cannot be parsed.
    """
    try:
        from PIL import Image
        img = Image.open(path)
        raw_prompt = img.info.get("prompt")
        if raw_prompt is None:
            return None
        graph: PromptGraph = json.loads(raw_prompt)
    except Exception:
        return None

    try:
        sampler_params = _extract_sampler_params(graph)
        models = _extract_model_nodes(graph)
        loras = _extract_lora_nodes(graph)
        positive, negative = _extract_prompt_text(graph)

        return ComfyUIMetadata(
            steps=sampler_params.get("steps"),
            sampler=sampler_params.get("sampler"),
            scheduler=sampler_params.get("scheduler"),
            denoise=sampler_params.get("denoise"),
            cfg=sampler_params.get("cfg"),
            models=models,
            loras=loras,
            positive_prompt=positive,
            negative_prompt=negative,
        )
    except Exception:
        return None
