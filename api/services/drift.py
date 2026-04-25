"""Compute drift (diff) between two audits on the same domain.

Used to answer: "Since last audit, did the SEO get better or worse, and
where?". Returns:
- Delta for the global score + per-axis scores.
- Findings resolved (present in baseline, gone in current).
- Findings appeared (new in current, absent in baseline).
- Findings persistent (present in both).

Finding matching is a best-effort on severity + normalized title (case-fold,
trimmed, punctuation collapsed). LLMs reword things between runs so we accept
fuzzy matches when the signal is clear.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from api.models import AuditResult, Finding, SectionResult


DeltaDirection = Literal["up", "down", "stable"]


@dataclass
class ScoreDelta:
    axis: str
    baseline: int
    current: int
    delta: int
    direction: DeltaDirection


@dataclass
class FindingsBucket:
    resolved: list[Finding] = field(default_factory=list)
    appeared: list[Finding] = field(default_factory=list)
    persistent: list[Finding] = field(default_factory=list)


@dataclass
class DriftReport:
    baseline_id: str
    baseline_date: str
    current_id: str
    current_date: str
    domain: str
    global_delta: ScoreDelta
    axis_deltas: list[ScoreDelta]
    per_axis_findings: dict[str, FindingsBucket]
    resolved_count: int
    appeared_count: int
    persistent_count: int


def compare(baseline: AuditResult, current: AuditResult) -> DriftReport:
    """Produce a DriftReport between two AuditResults."""
    global_delta = _score_delta("global", baseline.globalScore, current.globalScore)

    # Axis scores: baseline.scores is a dict, current.scores too; union of keys.
    axes = sorted(set(baseline.scores) | set(current.scores))
    axis_deltas = [
        _score_delta(a, baseline.scores.get(a, 0), current.scores.get(a, 0))
        for a in axes
    ]

    # Findings bucket per section (intersection of section names).
    baseline_sections = {s.section: s for s in baseline.sections}
    current_sections = {s.section: s for s in current.sections}
    all_section_names = sorted(set(baseline_sections) | set(current_sections))

    per_axis_findings: dict[str, FindingsBucket] = {}
    total_resolved = 0
    total_appeared = 0
    total_persistent = 0

    for name in all_section_names:
        b_sec = baseline_sections.get(name)
        c_sec = current_sections.get(name)
        bucket = _compare_findings(b_sec, c_sec)
        per_axis_findings[name] = bucket
        total_resolved += len(bucket.resolved)
        total_appeared += len(bucket.appeared)
        total_persistent += len(bucket.persistent)

    return DriftReport(
        baseline_id=baseline.id,
        baseline_date=baseline.createdAt,
        current_id=current.id,
        current_date=current.createdAt,
        domain=current.domain,
        global_delta=global_delta,
        axis_deltas=axis_deltas,
        per_axis_findings=per_axis_findings,
        resolved_count=total_resolved,
        appeared_count=total_appeared,
        persistent_count=total_persistent,
    )


def _score_delta(axis: str, baseline: int, current: int) -> ScoreDelta:
    delta = current - baseline
    if delta > 2:
        direction: DeltaDirection = "up"
    elif delta < -2:
        direction = "down"
    else:
        direction = "stable"
    return ScoreDelta(
        axis=axis,
        baseline=baseline,
        current=current,
        delta=delta,
        direction=direction,
    )


def _compare_findings(
    baseline: Optional[SectionResult],
    current: Optional[SectionResult],
) -> FindingsBucket:
    """Split findings into resolved / appeared / persistent buckets.

    Matching is done by a normalized (severity, title) key. We do not try to
    resolve wording changes across runs — a rephrased finding will show as
    one resolved + one appeared, which is the honest signal anyway.
    """
    base_findings = list(baseline.findings) if baseline else []
    curr_findings = list(current.findings) if current else []

    base_map: dict[tuple[str, str], Finding] = {
        (f.severity, _normalize(f.title)): f for f in base_findings
    }
    curr_map: dict[tuple[str, str], Finding] = {
        (f.severity, _normalize(f.title)): f for f in curr_findings
    }

    resolved_keys = base_map.keys() - curr_map.keys()
    appeared_keys = curr_map.keys() - base_map.keys()
    persistent_keys = base_map.keys() & curr_map.keys()

    return FindingsBucket(
        resolved=[base_map[k] for k in resolved_keys],
        appeared=[curr_map[k] for k in appeared_keys],
        persistent=[curr_map[k] for k in persistent_keys],
    )


_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = _PUNCT_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text
