"""Overlap export: `overlap.json` plus a self-contained `overlap.html`.

Two kinds of Venn, kept visually distinct because they answer different
questions and only one of them is a reliability claim:

* **reliability** -- one construct, model A against model B. How much do two
  measurements of the same thing agree?
* **exploratory** -- construct against construct, each side the union of that
  construct's models. Suggestive only, and labelled as such on the page.

The JSON is inlined into the HTML: a published artifact runs under a CSP that
blocks every external host, so a `fetch` for a sibling file would silently show
an empty page.
"""

from __future__ import annotations

import json
from typing import Any

from transcript_judge.models import LabelRow
from transcript_judge.persist import utc_now

#: v1 stores character spans only; token indices are a render-time concern.
TOKENIZER_HINT = None


def _positive_keys(labels: list[LabelRow], *, construct: str, model_id: str | None) -> set[str]:
    return {
        lab.sample_key
        for lab in labels
        if lab.label == construct
        and lab.value
        and lab.evidence_mode == "positive_quote"
        and (model_id is None or lab.model_id == model_id)
    }


def _queried_keys(labels: list[LabelRow], *, construct: str, model_id: str | None) -> set[str]:
    return {
        lab.sample_key
        for lab in labels
        if lab.label == construct and (model_id is None or lab.model_id == model_id)
    }


def build_overlap(
    *,
    labels: list[LabelRow],
    run_id: str,
    blinded: bool,
    rationales: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the overlap payload from grounded labels."""
    rationales = rationales or {}
    constructs = sorted({lab.label for lab in labels if lab.evidence_mode == "positive_quote"})
    models = sorted({lab.model_id for lab in labels})

    label_index: dict[str, dict[str, Any]] = {}
    for lab in labels:
        label_index[lab.label_id] = {
            "label_id": lab.label_id,
            "sample_key": lab.sample_key,
            "label": lab.label,
            "value": lab.value,
            "model_id": lab.model_id,
            "judge_name": lab.judge_name,
            "prompt_sha256": lab.prompt_sha256,
            "surface": lab.surface,
            "judge_quote": lab.judge_quote,
            "source_excerpt": lab.source_excerpt,
            "message_index": lab.message_index,
            "char_start": lab.char_start,
            "char_end": lab.char_end,
            "resolved": lab.resolved,
            "resolution_tier": lab.resolution_tier,
            "rationale": rationales.get(lab.label_id, ""),
        }

    def region(a_keys: set[str], b_keys: set[str]) -> dict[str, list[str]]:
        return {
            "only_a": sorted(a_keys - b_keys),
            "only_b": sorted(b_keys - a_keys),
            "both": sorted(a_keys & b_keys),
        }

    reliability = []
    if len(models) >= 2:
        model_a, model_b = models[0], models[1]
        for construct in constructs:
            a_keys = _positive_keys(labels, construct=construct, model_id=model_a)
            b_keys = _positive_keys(labels, construct=construct, model_id=model_b)
            queried = _queried_keys(labels, construct=construct, model_id=model_a) & _queried_keys(
                labels, construct=construct, model_id=model_b
            )
            reliability.append(
                {
                    "kind": "reliability",
                    "construct": construct,
                    "label_a": f"{construct} / {model_a}",
                    "label_b": f"{construct} / {model_b}",
                    "model_a": model_a,
                    "model_b": model_b,
                    "n_paired": len(queried),
                    **region(a_keys, b_keys),
                }
            )

    exploratory = []
    for i, ca in enumerate(constructs):
        for cb in constructs[i + 1 :]:
            exploratory.append(
                {
                    "kind": "exploratory",
                    "label_a": ca,
                    "label_b": cb,
                    **region(
                        _positive_keys(labels, construct=ca, model_id=None),
                        _positive_keys(labels, construct=cb, model_id=None),
                    ),
                }
            )

    keys_by_sample: dict[str, list[str]] = {}
    for lab in labels:
        if lab.value:
            keys_by_sample.setdefault(lab.sample_key, []).append(lab.label_id)

    return {
        "run_id": run_id,
        "generated_utc": utc_now(),
        "blinded": blinded,
        "tokenizer_hint": TOKENIZER_HINT,
        "constructs": constructs,
        "models": models,
        "reliability": reliability,
        "exploratory": exploratory,
        "labels": label_index,
        "labels_by_sample": {k: sorted(v) for k, v in keys_by_sample.items()},
    }


HTML_TEMPLATE = """<title>Transcript judge overlap — {run_id}</title>
<style>
:root {{
  --bg: #ffffff; --fg: #1a1a1a; --muted: #5c5c5c; --line: #d8d5cf;
  --card: #f7f5f2; --a: #d97757; --b: #6a9fb5; --accent: #bd5d3a;
}}
:root:not([data-theme="light"]) {{
  @media (prefers-color-scheme: dark) {{
    --bg: #1c1b19; --fg: #f0eee9; --muted: #a3a09a; --line: #3a3733;
    --card: #262421; --a: #e08c6f; --b: #7fb3c8; --accent: #e08c6f;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #1c1b19; --fg: #f0eee9; --muted: #a3a09a; --line: #3a3733;
  --card: #262421; --a: #e08c6f; --b: #7fb3c8; --accent: #e08c6f;
}}
* {{ box-sizing: border-box; }}
body {{
  background: var(--bg); color: var(--fg); margin: 0; padding: 2rem 1.25rem;
  font: 16px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}}
main {{ max-width: 62rem; margin: 0 auto; }}
h1 {{ font-size: 1.5rem; margin: 0 0 .25rem; }}
.sub {{ color: var(--muted); margin: 0 0 2rem; font-size: .9rem; }}
.warn {{
  border: 1px solid var(--accent); border-radius: .5rem; padding: .75rem 1rem;
  margin-bottom: 1.5rem; font-size: .9rem;
}}
h2 {{ font-size: 1.1rem; margin: 2.5rem 0 .25rem; }}
.note {{ color: var(--muted); font-size: .85rem; margin: 0 0 1rem; }}
.venn {{
  background: var(--card); border: 1px solid var(--line); border-radius: .75rem;
  padding: 1rem; margin-bottom: 1.25rem; overflow-x: auto;
}}
.venn h3 {{ font-size: .95rem; margin: 0 0 .5rem; }}
svg {{ display: block; max-width: 100%; height: auto; }}
.region {{ cursor: pointer; }}
.region:hover {{ opacity: .82; }}
.count {{ font-weight: 600; pointer-events: none; }}
.legend {{ font-size: .8rem; fill: var(--muted); pointer-events: none; }}
.detail {{
  margin-top: .75rem; border-top: 1px solid var(--line); padding-top: .75rem;
  font-size: .9rem; display: none;
}}
.detail.open {{ display: block; }}
.lab {{ border-left: 3px solid var(--accent); padding: .35rem .75rem; margin: .6rem 0; }}
.lab .k {{ font-family: ui-monospace, monospace; font-size: .78rem; color: var(--muted); }}
blockquote {{
  margin: .35rem 0; padding: .3rem .6rem; background: var(--bg);
  border-radius: .3rem; font-size: .88rem;
}}
</style>
<main>
<h1>Transcript judge overlap</h1>
<p class="sub">run <code>{run_id}</code> · generated {generated}</p>
{blinding_warning}
<h2>Reliability</h2>
<p class="note">One construct, two models. Both sides measure the same thing, so the
overlap is an agreement estimate. Counts are samples.</p>
<div id="reliability"></div>
<h2>Exploratory</h2>
<p class="note"><strong>Exploratory only.</strong> Two different constructs, each the union
of its models. Overlap here describes co-occurrence, not agreement, and no reliability
claim follows from it.</p>
<div id="exploratory"></div>
</main>
<script id="overlap-data" type="application/json">{payload}</script>
<script>
const DATA = JSON.parse(document.getElementById("overlap-data").textContent);

function venn(spec, idx) {{
  const wrap = document.createElement("div");
  wrap.className = "venn";
  const title = spec.kind === "reliability"
    ? `${{spec.construct}} — ${{spec.model_a}} vs ${{spec.model_b}} (n paired = ${{spec.n_paired}})`
    : `${{spec.label_a}} vs ${{spec.label_b}}`;
  const h = document.createElement("h3");
  h.textContent = title;
  wrap.appendChild(h);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 460 220");
  svg.setAttribute("role", "img");
  svg.innerHTML = `
    <circle cx="180" cy="110" r="85" fill="var(--a)" fill-opacity="0.38" stroke="var(--a)"/>
    <circle cx="280" cy="110" r="85" fill="var(--b)" fill-opacity="0.38" stroke="var(--b)"/>
    <rect class="region" x="70" y="25" width="80" height="170" fill="transparent" data-r="only_a"/>
    <rect class="region" x="200" y="25" width="60" height="170" fill="transparent" data-r="both"/>
    <rect class="region" x="310" y="25" width="80" height="170" fill="transparent" data-r="only_b"/>
    <text class="count" x="130" y="115" text-anchor="middle"
          fill="var(--fg)">${{spec.only_a.length}}</text>
    <text class="count" x="230" y="115" text-anchor="middle"
          fill="var(--fg)">${{spec.both.length}}</text>
    <text class="count" x="330" y="115" text-anchor="middle"
          fill="var(--fg)">${{spec.only_b.length}}</text>
    <text class="legend" x="130" y="212" text-anchor="middle">${{spec.label_a}}</text>
    <text class="legend" x="330" y="212" text-anchor="middle">${{spec.label_b}}</text>`;
  wrap.appendChild(svg);

  const detail = document.createElement("div");
  detail.className = "detail";
  wrap.appendChild(detail);

  svg.querySelectorAll(".region").forEach(node => {{
    node.addEventListener("click", () => {{
      const keys = spec[node.dataset.r];
      detail.classList.add("open");
      detail.innerHTML = keys.length
        ? `<p><strong>${{keys.length}}</strong> sample(s) in this region</p>` +
          keys.map(renderSample).join("")
        : "<p>No samples in this region.</p>";
    }});
  }});
  return wrap;
}}

function renderSample(sampleKey) {{
  const ids = DATA.labels_by_sample[sampleKey] || [];
  const rows = ids.map(id => DATA.labels[id]).filter(Boolean).map(l => `
    <div class="lab">
      <div class="k">${{esc(l.label)}} · ${{esc(l.model_id)}} · msg ${{l.message_index}}
        [${{l.char_start}},${{l.char_end}}) · ${{esc(l.resolution_tier)}}</div>
      ${{l.source_excerpt ? `<blockquote>${{esc(l.source_excerpt)}}</blockquote>` : ""}}
      ${{l.rationale ? `<div>${{esc(l.rationale)}}</div>` : ""}}
    </div>`).join("");
  return `<div><div class="k">${{esc(sampleKey)}}</div>${{rows}}</div>`;
}}

function esc(s) {{
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}})[c]);
}}

DATA.reliability.forEach((s, i) => document.getElementById("reliability").appendChild(venn(s, i)));
DATA.exploratory.forEach((s, i) => document.getElementById("exploratory").appendChild(venn(s, i)));
if (!DATA.reliability.length) {{
  document.getElementById("reliability").innerHTML =
    "<p class='note'>Fewer than two models in this run — no reliability comparison available.</p>";
}}
</script>
"""

BLINDING_WARNING = (
    '<div class="warn"><strong>This run was not blinded.</strong> One or more judges saw '
    "material excluded by the blinding perimeter, so agreement figures on this page do not "
    "mean what they appear to and must not be reported as reliability.</div>"
)


def render_html(overlap: dict[str, Any]) -> str:
    return HTML_TEMPLATE.format(
        run_id=overlap["run_id"],
        generated=overlap["generated_utc"],
        blinding_warning="" if overlap.get("blinded", True) else BLINDING_WARNING,
        payload=json.dumps(overlap, ensure_ascii=False).replace("</", "<\\/"),
    )
