"""The Stop hook that notices a findings document with no working figure.

Every case here drives the real script as a subprocess over stdin, because the
contract the harness relies on is the process contract: JSON in, an optional
`systemMessage` object out, exit 0 always.

The discriminating case is the zero-byte image. A hook that checks only whether
the referenced path exists passes it, and the reader still sees a broken image.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "nudge_report_figures.py"

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000100055f9f2d000000"
    "0049454e44ae426082"
)


def write_transcript(tmp_path: Path, *edited: Path) -> Path:
    """A transcript in which the assistant wrote each of `edited`."""
    path = tmp_path / "transcript.jsonl"
    lines = [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": str(target), "content": "..."},
                        }
                    ]
                },
            }
        )
        for target in edited
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_hook(payload: dict) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return proc.returncode, proc.stdout


def fire(tmp_path: Path, *edited: Path, **overrides) -> tuple[int, str]:
    payload = {
        "transcript_path": str(write_transcript(tmp_path, *edited)),
        "cwd": str(tmp_path),
        "session_id": "s1",
    }
    payload.update(overrides)
    return run_hook(payload)


def nudged(stdout: str) -> bool:
    return "Report written without a working figure" in stdout


@pytest.fixture
def report(tmp_path) -> Path:
    path = tmp_path / "analysis-report.md"
    path.write_text(
        "# Findings\n\nAccuracy fell from 0.81 to 0.62.\n", encoding="utf-8"
    )
    return path


# --- the figure actually has to be there -------------------------------------


def test_a_real_non_empty_figure_silences_the_nudge(tmp_path, report):
    (tmp_path / "fig.png").write_bytes(PNG_BYTES)
    report.write_text("# Findings\n\n![accuracy](fig.png)\n", encoding="utf-8")

    code, out = fire(tmp_path, report)

    assert code == 0
    assert out.strip() == ""


def test_a_referenced_but_absent_figure_still_nudges(tmp_path, report):
    report.write_text("# Findings\n\n![accuracy](fig.png)\n", encoding="utf-8")
    assert not (tmp_path / "fig.png").exists()

    code, out = fire(tmp_path, report)

    assert code == 0
    assert nudged(out)


def test_a_zero_byte_figure_still_nudges(tmp_path, report):
    """The case `path.exists()` gets wrong: the file is there and shows nothing."""
    (tmp_path / "fig.png").write_bytes(b"")
    report.write_text("# Findings\n\n![accuracy](fig.png)\n", encoding="utf-8")

    code, out = fire(tmp_path, report)

    assert code == 0
    assert nudged(out)


def test_a_report_with_no_figure_markup_at_all_nudges(tmp_path, report):
    code, out = fire(tmp_path, report)

    assert code == 0
    assert nudged(out)
    assert str(report) in out


def test_an_html_image_tag_counts_when_the_file_has_bytes(tmp_path, report):
    (tmp_path / "fig.png").write_bytes(PNG_BYTES)
    report.write_text(
        '# Findings\n\n<img src="fig.png" alt="accuracy">\n', encoding="utf-8"
    )

    assert fire(tmp_path, report)[1].strip() == ""


def test_an_html_image_tag_pointing_nowhere_nudges(tmp_path, report):
    report.write_text(
        '# Findings\n\n<img src="fig.png" alt="accuracy">\n', encoding="utf-8"
    )

    assert nudged(fire(tmp_path, report)[1])


# --- mermaid is a figure -----------------------------------------------------


def test_a_mermaid_fence_counts_as_a_figure(tmp_path, report):
    report.write_text(
        "# Findings\n\n```mermaid\nflowchart TD\n  A --> B\n```\n", encoding="utf-8"
    )

    code, out = fire(tmp_path, report)

    assert code == 0
    assert out.strip() == ""


def test_a_non_mermaid_code_fence_is_not_a_figure(tmp_path, report):
    report.write_text("# Findings\n\n```python\nprint(0.62)\n```\n", encoding="utf-8")

    assert nudged(fire(tmp_path, report)[1])


# --- which files count as reports --------------------------------------------


def test_a_source_file_is_never_a_report(tmp_path):
    code = tmp_path / "analysis.py"
    code.write_text("x = 1\n", encoding="utf-8")

    assert fire(tmp_path, code)[1].strip() == ""


def test_a_markdown_file_that_is_not_findings_is_left_alone(tmp_path):
    notes = tmp_path / "meeting-notes.md"
    notes.write_text("# Notes\n\nWe talked.\n", encoding="utf-8")

    assert fire(tmp_path, notes)[1].strip() == ""


def test_a_reports_directory_makes_its_markdown_a_report(tmp_path):
    (tmp_path / "reports").mkdir()
    doc = tmp_path / "reports" / "week-3.md"
    doc.write_text("# Week 3\n\nNo pictures.\n", encoding="utf-8")

    assert nudged(fire(tmp_path, doc)[1])


def test_every_bare_report_is_listed_not_just_the_first(tmp_path):
    first = tmp_path / "a-report.md"
    second = tmp_path / "b-findings.md"
    for doc in (first, second):
        doc.write_text("# X\n\nnothing\n", encoding="utf-8")

    out = fire(tmp_path, first, second)[1]

    assert str(first) in out
    assert str(second) in out


def test_a_relative_path_resolves_against_the_session_cwd(tmp_path):
    doc = tmp_path / "results.md"
    doc.write_text("# R\n\nnothing\n", encoding="utf-8")

    payload = {
        "transcript_path": str(write_transcript(tmp_path, Path("results.md"))),
        "cwd": str(tmp_path),
    }

    assert nudged(run_hook(payload)[1])


# --- it never takes the session down -----------------------------------------


def test_the_loop_guard_suppresses_the_second_pass(tmp_path, report):
    code, out = fire(tmp_path, report, stop_hook_active=True)

    assert code == 0
    assert out.strip() == ""


def test_a_missing_transcript_is_silent_rather_than_fatal(tmp_path):
    code, out = run_hook(
        {"transcript_path": str(tmp_path / "gone.jsonl"), "cwd": str(tmp_path)}
    )

    assert code == 0
    assert out.strip() == ""


def test_garbage_on_stdin_exits_clean(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not json at all",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_an_unparseable_transcript_line_does_not_stop_the_scan(tmp_path, report):
    transcript = write_transcript(tmp_path, report)
    transcript.write_text(
        "{ broken\n" + transcript.read_text(encoding="utf-8"), encoding="utf-8"
    )

    code, out = run_hook({"transcript_path": str(transcript), "cwd": str(tmp_path)})

    assert code == 0
    assert nudged(out)


def test_the_output_is_a_single_json_object_with_only_a_system_message(
    tmp_path, report
):
    out = fire(tmp_path, report)[1]

    payload = json.loads(out)
    assert list(payload) == ["systemMessage"]
