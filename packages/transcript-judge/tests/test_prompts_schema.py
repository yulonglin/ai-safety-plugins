"""Prompt files: what is accepted, and what is refused outright.

`evidence_mode` is declared per field or the run does not start. The tempting
shortcut -- inferring polarity from the field name -- is what these tests exist
to keep out, because `omits_warning` and `fails_to_acknowledge` read as
positives and would fail in the direction that flatters the result.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from transcript_judge.models import JudgeSpec
from transcript_judge.prompts import (
    VALID_EVIDENCE_MODES,
    PromptSchemaError,
    load_spec,
    parse_model_ref,
    split_frontmatter,
    validate_response_fields,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_valid_evidence_modes_are_pinned():
    assert VALID_EVIDENCE_MODES == ("positive_quote", "hand_validation")


# --- frontmatter -------------------------------------------------------------


def test_frontmatter_splits_into_mapping_and_body():
    meta, body = split_frontmatter("---\nname: x\n---\n\nthe body\n")
    assert meta == {"name": "x"}
    assert body == "the body\n"


def test_a_file_without_an_opening_fence_is_refused():
    with pytest.raises(PromptSchemaError, match="must open with"):
        split_frontmatter("name: x\n\nbody\n")


def test_an_unclosed_fence_is_refused():
    with pytest.raises(PromptSchemaError, match="not closed"):
        split_frontmatter("---\nname: x\n\nbody\n")


# --- model references --------------------------------------------------------


def test_provider_and_model_split_on_the_first_colon():
    assert parse_model_ref("anthropic:claude-sonnet-5") == ("anthropic", "claude-sonnet-5")


def test_an_openrouter_id_with_a_slash_survives_intact():
    assert parse_model_ref("openrouter:openai/gpt-5.6-sol") == (
        "openrouter",
        "openai/gpt-5.6-sol",
    )


def test_a_bare_model_needs_a_default_provider():
    assert parse_model_ref("claude-sonnet-5", default_provider="anthropic") == (
        "anthropic",
        "claude-sonnet-5",
    )
    with pytest.raises(PromptSchemaError, match="names no provider"):
        parse_model_ref("claude-sonnet-5")


def test_an_empty_half_is_refused():
    with pytest.raises(PromptSchemaError, match="malformed"):
        parse_model_ref("anthropic:")


# --- loading a valid spec ----------------------------------------------------


def test_a_valid_spec_loads_with_its_declared_fields():
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    assert spec.name == "alpha"
    assert spec.provider == "anthropic"
    assert spec.model_id == "claude-sonnet-5"
    assert spec.surface == "full"
    assert spec.params == {"temperature": 0.0, "max_tokens": 1024}
    assert [f.name for f in spec.schema_fields] == [
        "flags_protocol_error",
        "omits_safety_caveat",
    ]
    assert [f.evidence_mode for f in spec.schema_fields] == [
        "positive_quote",
        "hand_validation",
    ]


def test_the_body_excludes_the_frontmatter():
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    assert spec.prompt_text.startswith("You review one transcript")
    assert "default_model" not in spec.prompt_text


def test_the_sha_covers_the_whole_file_including_frontmatter():
    import hashlib

    path = FIXTURES / "judge_alpha.v1.md"
    spec = load_spec(path)
    assert spec.prompt_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    # A temperature change is as much a change to the instrument as a rubric
    # change, so it must not hash to the same value as the body alone.
    assert spec.prompt_sha256 != hashlib.sha256(spec.prompt_text.encode("utf-8")).hexdigest()


def test_an_explicit_model_overrides_the_frontmatter_default():
    spec = load_spec(
        FIXTURES / "judge_alpha.v1.md",
        provider="openrouter",
        model_id="openai/gpt-5.6-sol",
    )
    assert (spec.provider, spec.model_id) == ("openrouter", "openai/gpt-5.6-sol")


def test_one_prompt_under_two_models_gives_two_cells_sharing_a_prompt_sha():
    a = load_spec(FIXTURES / "judge_alpha.v1.md")
    b = load_spec(
        FIXTURES / "judge_alpha.v1.md", provider="openrouter", model_id="openai/gpt-5.6-sol"
    )
    assert a.prompt_sha256 == b.prompt_sha256
    assert a.cell != b.cell
    assert a.cell.model_id == "claude-sonnet-5"
    assert b.cell.model_id == "openai/gpt-5.6-sol"


def test_the_beta_fixture_pins_the_verified_openrouter_id():
    spec = load_spec(FIXTURES / "judge_beta.v1.md")
    assert (spec.provider, spec.model_id) == ("openrouter", "openai/gpt-5.6-sol")


# --- refusals ----------------------------------------------------------------


def test_a_field_without_an_evidence_mode_is_refused_not_guessed_from_its_name():
    # The field is called `never_acknowledges_uncertainty`. A name-pattern rule
    # would happily classify it; there is no such rule.
    with pytest.raises(PromptSchemaError) as excinfo:
        load_spec(FIXTURES / "judge_missing_mode.v1.md")
    message = str(excinfo.value)
    assert "never_acknowledges_uncertainty" in message
    assert "no 'evidence_mode'" in message
    assert "never inferred from the field name" in message


def test_an_unrecognised_evidence_mode_is_refused():
    with pytest.raises(PromptSchemaError, match="unrecognised evidence_mode 'vibes'"):
        load_spec(FIXTURES / "judge_bad_mode.v1.md")


def test_pinning_model_id_in_frontmatter_is_refused():
    with pytest.raises(PromptSchemaError, match="default_model"):
        load_spec(FIXTURES / "judge_pinned_model.v1.md")


def test_a_missing_name_is_refused(tmp_path):
    path = tmp_path / "p.md"
    path.write_text(
        "---\nsurface: full\ndefault_model: anthropic:claude-sonnet-5\n"
        "schema:\n  - name: f\n    evidence_mode: positive_quote\n---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(PromptSchemaError, match="needs a 'name'"):
        load_spec(path)


def test_an_unknown_surface_is_refused(tmp_path):
    path = tmp_path / "p.md"
    path.write_text(
        "---\nname: p\nsurface: cot_only\ndefault_model: anthropic:claude-sonnet-5\n"
        "schema:\n  - name: f\n    evidence_mode: positive_quote\n---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(PromptSchemaError, match="surface 'cot_only'"):
        load_spec(path)


def test_an_empty_schema_is_refused(tmp_path):
    path = tmp_path / "p.md"
    path.write_text(
        "---\nname: p\ndefault_model: anthropic:claude-sonnet-5\nschema: []\n---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(PromptSchemaError, match="non-empty 'schema' list"):
        load_spec(path)


def test_a_duplicate_field_name_is_refused(tmp_path):
    path = tmp_path / "p.md"
    path.write_text(
        "---\nname: p\ndefault_model: anthropic:claude-sonnet-5\nschema:\n"
        "  - name: f\n    evidence_mode: positive_quote\n"
        "  - name: f\n    evidence_mode: hand_validation\n---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(PromptSchemaError, match="duplicate schema field 'f'"):
        load_spec(path)


def test_no_model_and_no_default_is_refused(tmp_path):
    path = tmp_path / "p.md"
    path.write_text(
        "---\nname: p\nschema:\n  - name: f\n    evidence_mode: positive_quote\n---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(PromptSchemaError, match="no 'default_model'"):
        load_spec(path)


# --- response validation -----------------------------------------------------


def _spec() -> JudgeSpec:
    return load_spec(FIXTURES / "judge_alpha.v1.md")


def test_answering_every_declared_field_once_validates():
    parsed = {
        "findings": [
            {"field": "flags_protocol_error"},
            {"field": "omits_safety_caveat"},
        ]
    }
    assert validate_response_fields(parsed, _spec()) is None


def test_an_undeclared_field_is_refused():
    parsed = {
        "findings": [
            {"field": "flags_protocol_error"},
            {"field": "omits_safety_caveat"},
            {"field": "invented_field"},
        ]
    }
    with pytest.raises(PromptSchemaError, match="undeclared field\\(s\\): invented_field"):
        validate_response_fields(parsed, _spec())


def test_an_omitted_field_is_refused():
    parsed = {"findings": [{"field": "flags_protocol_error"}]}
    with pytest.raises(
        PromptSchemaError, match="omitted declared field\\(s\\): omits_safety_caveat"
    ):
        validate_response_fields(parsed, _spec())


def test_a_field_answered_twice_is_refused():
    parsed = {
        "findings": [
            {"field": "flags_protocol_error"},
            {"field": "flags_protocol_error"},
            {"field": "omits_safety_caveat"},
        ]
    }
    with pytest.raises(PromptSchemaError, match="more than once: flags_protocol_error"):
        validate_response_fields(parsed, _spec())
