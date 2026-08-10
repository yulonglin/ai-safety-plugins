"""Versioned judge prompt files: bytes on disk -> a validated `JudgeSpec`.

A prompt file is YAML frontmatter plus a markdown body. `prompt_sha256` is
computed over the **entire file bytes**, frontmatter included -- changing a
temperature is as much a change to the measurement instrument as changing the
rubric, and both must show up as a cache miss.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from transcript_judge.models import EvidenceMode, JudgeSpec, SchemaField
from transcript_judge.normalize import sha256_bytes
from transcript_judge.render import SURFACES

VALID_EVIDENCE_MODES: tuple[EvidenceMode, ...] = ("positive_quote", "hand_validation")

FRONTMATTER_FENCE = "---"


class PromptSchemaError(ValueError):
    """A prompt file the runner refuses to use. Always exits non-zero."""


def split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith(FRONTMATTER_FENCE):
        raise PromptSchemaError("prompt file must open with a '---' YAML frontmatter fence")
    parts = raw.split(FRONTMATTER_FENCE, 2)
    if len(parts) < 3:
        raise PromptSchemaError("prompt file frontmatter is not closed by a second '---' fence")
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise PromptSchemaError("prompt frontmatter must be a YAML mapping")
    return meta, parts[2].lstrip("\n")


def parse_model_ref(ref: str, *, default_provider: str | None = None) -> tuple[str, str]:
    """``"anthropic:claude-sonnet-5"`` -> ``("anthropic", "claude-sonnet-5")``.

    Split on the first colon only: OpenRouter ids such as
    ``openai/gpt-5.6-sol`` contain a slash, not a colon, and must survive intact.
    """
    if ":" in ref:
        provider, _, model_id = ref.partition(":")
        provider, model_id = provider.strip(), model_id.strip()
        if not provider or not model_id:
            raise PromptSchemaError(
                f"malformed model reference {ref!r}; expected 'provider:model_id'"
            )
        return provider, model_id
    if default_provider:
        return default_provider, ref.strip()
    raise PromptSchemaError(
        f"model reference {ref!r} names no provider; write it as 'provider:model_id' "
        "(for example 'anthropic:claude-sonnet-5' or 'openrouter:openai/gpt-5.6-sol')"
    )


def _parse_schema(meta: dict[str, Any], path: Path) -> list[SchemaField]:
    declared = meta.get("schema")
    if not isinstance(declared, list) or not declared:
        raise PromptSchemaError(f"{path}: frontmatter needs a non-empty 'schema' list")

    fields: list[SchemaField] = []
    seen: set[str] = set()
    for entry in declared:
        if not isinstance(entry, dict):
            raise PromptSchemaError(f"{path}: each 'schema' entry must be a mapping")
        name = entry.get("name")
        if not name:
            raise PromptSchemaError(f"{path}: a 'schema' entry is missing 'name'")
        if name in seen:
            raise PromptSchemaError(f"{path}: duplicate schema field {name!r}")
        seen.add(name)

        mode = entry.get("evidence_mode")
        if mode is None:
            raise PromptSchemaError(
                f"{path}: schema field {name!r} has no 'evidence_mode'. Declare one of "
                f"{', '.join(VALID_EVIDENCE_MODES)} explicitly -- polarity is never "
                "inferred from the field name, because 'omits_warning' and "
                "'fails_to_acknowledge' read as positives and would fail open."
            )
        if mode not in VALID_EVIDENCE_MODES:
            raise PromptSchemaError(
                f"{path}: schema field {name!r} has unrecognised evidence_mode {mode!r}; "
                f"expected one of {', '.join(VALID_EVIDENCE_MODES)}"
            )

        fields.append(
            SchemaField(
                name=str(name),
                description=str(entry.get("description", "")),
                evidence_mode=mode,
            )
        )
    return fields


def load_spec(
    path: str | Path,
    *,
    provider: str | None = None,
    model_id: str | None = None,
) -> JudgeSpec:
    """Read and validate one prompt file.

    `provider`/`model_id` override the file's `default_model`, which is how one
    prompt fans out across several models to form several judge cells.
    """
    target = Path(path)
    raw_bytes = target.read_bytes()
    prompt_sha256 = sha256_bytes(raw_bytes)
    meta, body = split_frontmatter(raw_bytes.decode("utf-8"))

    if "model_id" in meta:
        raise PromptSchemaError(
            f"{target}: frontmatter sets 'model_id'. Use 'default_model' instead -- the "
            "model is part of the judge cell and is chosen per run via --model, so "
            "pinning it in the prompt file would silently collapse the model dimension."
        )

    name = meta.get("name")
    if not name:
        raise PromptSchemaError(f"{target}: frontmatter needs a 'name'")

    surface = meta.get("surface", "full")
    if surface not in SURFACES:
        raise PromptSchemaError(
            f"{target}: surface {surface!r} is not one of {', '.join(SURFACES)}"
        )

    if provider is None or model_id is None:
        default_model = meta.get("default_model")
        if not default_model:
            raise PromptSchemaError(
                f"{target}: no --model given and frontmatter has no 'default_model'"
            )
        provider, model_id = parse_model_ref(str(default_model))

    params = meta.get("params") or {}
    if not isinstance(params, dict):
        raise PromptSchemaError(f"{target}: 'params' must be a mapping")

    return JudgeSpec(
        name=str(name),
        prompt_path=str(target),
        prompt_text=body,
        prompt_sha256=prompt_sha256,
        provider=provider,
        model_id=model_id,
        surface=surface,
        params=params,
        schema_fields=_parse_schema(meta, target),
    )


def validate_response_fields(parsed: dict[str, Any], spec: JudgeSpec) -> None:
    """Every declared field answered exactly once, and nothing invented."""
    declared = {f.name for f in spec.schema_fields}
    returned = [f["field"] for f in parsed.get("findings", [])]

    unknown = sorted(set(returned) - declared)
    if unknown:
        raise PromptSchemaError(f"judge returned undeclared field(s): {', '.join(unknown)}")

    missing = sorted(declared - set(returned))
    if missing:
        raise PromptSchemaError(f"judge omitted declared field(s): {', '.join(missing)}")

    duplicated = sorted({f for f in returned if returned.count(f) > 1})
    if duplicated:
        raise PromptSchemaError(f"judge answered field(s) more than once: {', '.join(duplicated)}")
