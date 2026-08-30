"""Validate staged daily Signal packets before canonical SQLite publication."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path


SCRIPT_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "market-sensing-intelligence"
    / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))

import market_sensing  # noqa: E402
from signal_analytics import CANONICAL_KEY_PATTERN  # noqa: E402


TOP_LEVEL_KEYS = {
    "candidate_date",
    "detected_at",
    "source",
    "claim",
    "signal",
    "analysis_markdown",
    "analysis_structured",
    "quantification_decision",
    "discovery",
}
SOURCE_KEYS = {
    "title",
    "url",
    "publisher",
    "published_at",
    "source_type",
    "source_modality",
    "language",
    "reliability",
    "raw_markdown",
}
CLAIM_KEYS = {"subject_id", "predicate", "value", "confidence", "as_of"}
SIGNAL_KEYS = {
    "canonical_key",
    "title",
    "sentence",
    "paragraph",
    "company_id",
    "business_axis",
    "signal_type",
    "signal_role",
    "signal_origin",
    "business_impact_score",
    "business_impact_rationale",
    "urgency_score",
    "urgency_rationale",
    "assessment_confidence",
    "assessed_at",
    "impact_path",
    "recommended_follow_up",
    "baseline_assumption",
    "observed_break",
    "decision_change",
    "surprise_pattern",
    "surprise_score",
    "falsification_check",
}
DISCOVERY_KEYS = {"query", "executed_at", "channel", "change_types"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet_file", type=Path)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--minimum-per-day", type=int, default=3)
    return parser.parse_args()


def require_keys(value: object, keys: set[str], field: str, line_no: int) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"line {line_no}: {field} must be an object")
    missing = sorted(key for key in keys if value.get(key) in (None, "", []))
    if missing:
        raise ValueError(f"line {line_no}: {field} missing {', '.join(missing)}")
    return value


def main() -> None:
    args = parse_args()
    start = date.fromisoformat(args.date_from)
    end = date.fromisoformat(args.date_to)
    if start > end:
        raise ValueError("date-from must not be after date-to")

    rows = []
    for line_no, raw_line in enumerate(
        args.packet_file.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        row = require_keys(json.loads(raw_line), TOP_LEVEL_KEYS, "packet", line_no)
        source = require_keys(row["source"], SOURCE_KEYS, "source", line_no)
        claim = require_keys(row["claim"], CLAIM_KEYS, "claim", line_no)
        signal = require_keys(row["signal"], SIGNAL_KEYS, "signal", line_no)
        discovery = require_keys(row["discovery"], DISCOVERY_KEYS, "discovery", line_no)

        candidate_date = date.fromisoformat(str(row["candidate_date"]))
        if not start <= candidate_date <= end:
            raise ValueError(f"line {line_no}: candidate_date outside requested period")
        market_sensing.validate_date(row["detected_at"], "detected_at")
        market_sensing.validate_date(source["published_at"], "published_at")
        market_sensing.validate_date(claim["as_of"], "claim.as_of")
        if "T" not in str(discovery["executed_at"]):
            raise ValueError(f"line {line_no}: discovery.executed_at must be a timestamp")
        if discovery["channel"] not in market_sensing.RESEARCH_EVIDENCE_CHANNELS:
            raise ValueError(f"line {line_no}: invalid discovery.channel")
        market_sensing.canonicalize_url(source["url"])
        if source["source_type"] not in market_sensing.SOURCE_TYPES:
            raise ValueError(f"line {line_no}: invalid source_type")
        market_sensing.validate_modality(source["source_modality"])
        if source["reliability"] not in market_sensing.SOURCE_RELIABILITY:
            raise ValueError(f"line {line_no}: invalid reliability")
        if claim["confidence"] not in market_sensing.CLAIM_CONFIDENCE:
            raise ValueError(f"line {line_no}: invalid claim confidence")
        if not market_sensing.company_supports_business_axis(
            signal["company_id"], signal["business_axis"]
        ):
            raise ValueError(f"line {line_no}: invalid company/business-axis pair")
        if not CANONICAL_KEY_PATTERN.fullmatch(str(signal["canonical_key"])):
            raise ValueError(f"line {line_no}: invalid signal.canonical_key")
        market_sensing.validate_signal_type(signal["signal_type"])
        market_sensing.validate_signal_classification(
            signal["signal_role"], signal["signal_origin"]
        )
        if signal["signal_role"] == "core_market_signal":
            market_sensing.validate_assumption_challenge(
                {
                    "schema_version": market_sensing.ASSUMPTION_CHALLENGE_SCHEMA_VERSION,
                    "baseline_assumption": signal["baseline_assumption"],
                    "observed_break": signal["observed_break"],
                    "decision_change": signal["decision_change"],
                    "pattern": signal["surprise_pattern"],
                    "surprise_score": signal["surprise_score"],
                    "falsification_check": signal["falsification_check"],
                }
            )
        market_sensing.validate_signal_copy(
            signal["title"], signal["sentence"], signal["paragraph"]
        )
        market_sensing.validate_score_rationale(
            "business_impact",
            int(signal["business_impact_score"]),
            signal["business_impact_rationale"],
        )
        market_sensing.validate_score_rationale(
            "urgency", int(signal["urgency_score"]), signal["urgency_rationale"]
        )
        market_sensing.validate_signal_analysis(row["analysis_markdown"])
        decision = market_sensing.validate_quantification_decision(
            row["quantification_decision"], row.get("impact_estimate")
        )
        if row.get("impact_estimate") is not None:
            market_sensing.validate_impact_estimate(row["impact_estimate"])
        market_sensing.validate_structured_analysis(
            row["analysis_structured"],
            require_current_schema=True,
            importance_score=max(
                int(signal["business_impact_score"]),
                int(signal["urgency_score"]),
            ),
        )
        if (
            market_sensing.structured_quantification_status(row["analysis_structured"])
            != decision["status"]
        ):
            raise ValueError(f"line {line_no}: structured quantification status mismatch")
        rows.append(row)

    per_day = Counter(str(row["candidate_date"]) for row in rows)
    cursor = start
    gaps = []
    while cursor <= end:
        actual = per_day[cursor.isoformat()]
        if actual < args.minimum_per_day:
            gaps.append(f"{cursor.isoformat()}={actual}/{args.minimum_per_day}")
        cursor += timedelta(days=1)
    if gaps:
        raise ValueError("daily published Signal packet gaps: " + ", ".join(gaps))

    duplicate_checks = {
        "canonical_key": [row["signal"]["canonical_key"] for row in rows],
        "source URL": [row["source"]["url"] for row in rows],
        "Signal title": [row["signal"]["title"] for row in rows],
        "observed claim": [
            "\x1f".join(
                [row["claim"][key] for key in ("subject_id", "predicate", "value")]
            )
            for row in rows
        ],
    }
    for label, values in duplicate_checks.items():
        duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate {label}: {duplicates[:5]}")

    machine_titles = [
        row["signal"]["title"]
        for row in rows
        if re.search(r"\s[A-F0-9]{6,12}$", row["signal"]["title"])
    ]
    if machine_titles:
        raise ValueError(
            "Signal titles must describe the event rather than expose generated IDs: "
            + repr(machine_titles[:5])
        )

    normalized_analyses = [
        (
            row["signal"]["canonical_key"],
            market_sensing.normalize_text(row["analysis_markdown"]),
        )
        for row in rows
    ]
    for index, (canonical_key, analysis) in enumerate(normalized_analyses):
        for other_key, other_analysis in normalized_analyses[index + 1 :]:
            matcher = SequenceMatcher(None, analysis, other_analysis)
            if matcher.quick_ratio() < 0.9:
                continue
            similarity = matcher.ratio()
            if similarity >= 0.9:
                raise ValueError(
                    "analysis_markdown is too similar across Signals: "
                    f"{canonical_key} / {other_key} = {similarity:.0%}"
                )

    maximum_scores = [
        max(
            int(row["signal"]["business_impact_score"]),
            int(row["signal"]["urgency_score"]),
        )
        for row in rows
    ]
    score_counts = Counter(maximum_scores)
    total = len(maximum_scores)
    if total:
        observation_ratio = sum(score <= 4 for score in maximum_scores) / total
        management_ratio = sum(5 <= score <= 7 for score in maximum_scores) / total
        executive_ratio = sum(score >= 8 for score in maximum_scores) / total
        single_score_ratio = max(score_counts.values()) / total
        if observation_ratio < 0.2:
            raise ValueError("Signal packet omits the required 1-4 observation band")
        if management_ratio < 0.2:
            raise ValueError("Signal packet omits the required 5-7 management band")
        if executive_ratio > 0.5:
            raise ValueError("Signal packet over-concentrates the 8-10 executive band")
        if single_score_ratio > 0.5:
            raise ValueError("Signal packet assigns one maximum score to more than 50%")

    print(
        json.dumps(
            {
                "status": "valid",
                "signals": len(rows),
                "calendar_days": (end - start).days + 1,
                "minimum_per_day": min(per_day.values(), default=0),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
