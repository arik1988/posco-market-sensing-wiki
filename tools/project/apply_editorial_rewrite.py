"""Atomically migrate every Signal to schema v2 reader-facing copy and type."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import market_sensing  # noqa: E402


AXIS_COMPANY = {
    "철강": "COM-POSCO",
    "리튬": "COM-POSCO-HOLDINGS",
    "전략광물": "COM-POSCO-HOLDINGS",
    "에너지": "COM-POSCO-INTERNATIONAL",
    "식량·팜": "COM-POSCO-INTERNATIONAL",
    "건설·인프라": "COM-POSCO-ENC",
    "이차전지소재": "COM-POSCO-FUTURE-M",
    "철강·원료 물류": "COM-POSCO-FLOW",
    "구동모터코아·강건재가공": "COM-POSCO-MOBILITY-SOLUTION",
    "도금·컬러강판": "COM-POSCO-STEELEON",
}


def load_items(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("items") or value.get("signals")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{path}: expected a JSON list or an object with an items list")
    return value


def validate_proposals(
    paths: list[Path], wiki_root: Path
) -> tuple[list[dict[str, Any]], list[str]]:
    signals = {
        str(record.get("signal_id")): (path, record)
        for path, record in market_sensing.signal_records(wiki_root)
    }
    insights = {
        str(record.get("insight_id")): (path, record)
        for path, record in market_sensing.insight_records(wiki_root)
    }
    proposals: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    seen_sentences: set[str] = set()

    for source_path in paths:
        try:
            items = load_items(source_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))
            continue
        for index, item in enumerate(items, start=1):
            label = f"{source_path.name} item {index}"
            signal_id = str(item.get("signal_id") or "")
            if signal_id in seen_ids:
                errors.append(f"{label}: duplicate signal_id {signal_id}")
                continue
            seen_ids.add(signal_id)
            current = signals.get(signal_id)
            if current is None:
                errors.append(f"{label}: unknown signal_id {signal_id}")
                continue
            _, signal = current
            insight_pair = insights.get(str(signal.get("insight_id") or ""))
            if insight_pair is None:
                errors.append(f"{label}: linked insight is missing")
                continue
            _, insight = insight_pair
            old_title = str(item.get("old_title") or "").strip()
            if old_title != str(insight.get("title") or "").strip():
                errors.append(f"{label}: old_title does not match the current insight")
            axis = str(signal.get("business_axis") or "")
            if AXIS_COMPANY.get(axis) not in signal.get("company_ids", []):
                errors.append(f"{label}: invalid company/business-axis link")
            title = str(item.get("title") or "").strip()
            sentence = str(item.get("sentence") or "").strip()
            summary = str(item.get("summary") or "").strip()
            analysis = str(item.get("analysis_markdown") or "").strip()
            try:
                signal_type = market_sensing.validate_signal_type(item.get("signal_type"))
            except ValueError as exc:
                errors.append(f"{label}: {exc}")
                signal_type = ""
            current_analysis = str(insight.get("analysis_markdown") or "").strip()
            try:
                market_sensing.validate_signal_copy(title, sentence, summary)
                market_sensing.validate_signal_analysis(analysis)
            except ValueError as exc:
                errors.append(f"{label}: {exc}")
            minimum_analysis_length = max(1200, int(len(current_analysis) * 0.75))
            if len(analysis) < minimum_analysis_length:
                errors.append(
                    f"{label}: rewritten analysis is too compressed "
                    f"({len(analysis)} < {minimum_analysis_length} characters)"
                )
            if "```mermaid" in current_analysis and "```mermaid" not in analysis:
                errors.append(f"{label}: rewritten analysis removed an existing Mermaid diagram")
            normalized_title = market_sensing.normalize_text(title)
            normalized_sentence = market_sensing.normalize_text(sentence)
            if normalized_title in seen_titles:
                errors.append(f"{label}: duplicate proposed title")
            if normalized_sentence in seen_sentences:
                errors.append(f"{label}: duplicate proposed sentence")
            seen_titles.add(normalized_title)
            seen_sentences.add(normalized_sentence)
            proposals.append(
                {
                    "source_path": str(source_path),
                    "signal_path": str(current[0]),
                    "insight_path": str(insight_pair[0]),
                    "signal_id": signal_id,
                    "insight_id": str(insight.get("insight_id") or ""),
                    "business_axis": axis,
                    "signal_type": signal_type,
                    "old_title": old_title,
                    "title": title,
                    "sentence": sentence,
                    "summary": summary,
                    "analysis_markdown": analysis,
                }
            )
    if set(signals) != seen_ids:
        missing = sorted(set(signals) - seen_ids)
        errors.append(
            f"proposal set must cover all {len(signals)} signals; missing {len(missing)}: "
            + ", ".join(missing)
        )
    return proposals, errors


def apply_proposals(proposals: list[dict[str, Any]], wiki_root: Path, backup: Path) -> None:
    """Apply the complete proposal set or restore every touched record on failure."""
    current_signal_ids = {
        str(record.get("signal_id") or path.stem)
        for path, record in market_sensing.signal_records(wiki_root)
    }
    proposed_signal_ids = {str(item.get("signal_id") or "") for item in proposals}
    if proposed_signal_ids != current_signal_ids or len(proposals) != len(current_signal_ids):
        missing = sorted(current_signal_ids - proposed_signal_ids)
        extra = sorted(proposed_signal_ids - current_signal_ids)
        raise ValueError(
            "atomic migration requires the complete current Signal set"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; unknown: {', '.join(extra)}" if extra else "")
        )

    backup_payload: list[dict[str, Any]] = []
    original_text: dict[Path, str] = {}
    updated_records: dict[Path, dict[str, Any]] = {}
    now = market_sensing.timestamp()
    for proposal in proposals:
        signal_path = Path(proposal["signal_path"])
        insight_path = Path(proposal["insight_path"])
        for target in (signal_path, insight_path):
            if target in original_text:
                raise ValueError(f"migration target is referenced more than once: {target}")
            original_text[target] = target.read_text(encoding="utf-8")
        signal = market_sensing.read_json(signal_path)
        insight = market_sensing.read_json(insight_path)
        if str(signal.get("signal_id") or "") != proposal["signal_id"]:
            raise ValueError(f"Signal identity changed before migration: {signal_path}")
        if str(insight.get("insight_id") or "") != proposal["insight_id"]:
            raise ValueError(f"Insight identity changed before migration: {insight_path}")
        if str(insight.get("title") or "").strip() != proposal["old_title"]:
            raise ValueError(f"Insight title changed before migration: {insight_path}")
        signal_type = market_sensing.validate_signal_type(proposal["signal_type"])
        market_sensing.validate_signal_copy(
            proposal["title"], proposal["sentence"], proposal["summary"]
        )
        market_sensing.validate_signal_analysis(proposal["analysis_markdown"])
        backup_payload.append(
            {
                "signal_id": proposal["signal_id"],
                "signal_path": str(signal_path.relative_to(wiki_root)),
                "insight_path": str(insight_path.relative_to(wiki_root)),
                "signal_schema_version": signal.get("schema_version"),
                "insight_schema_version": insight.get("schema_version"),
                "signal_type": signal.get("signal_type"),
                "sentence": signal.get("sentence"),
                "title": insight.get("title"),
                "summary": insight.get("summary"),
                "analysis_markdown": insight.get("analysis_markdown"),
                "analysis_structured": insight.get("analysis_structured"),
            }
        )
        signal["schema_version"] = market_sensing.SIGNAL_SCHEMA_VERSION
        signal["signal_type"] = signal_type
        signal["sentence"] = proposal["sentence"]
        signal["updated_at"] = now
        insight["schema_version"] = (
            market_sensing.INSIGHT_SCHEMA_VERSION
            if insight.get("analysis_structured") is not None
            else market_sensing.LEGACY_INSIGHT_SCHEMA_VERSION
        )
        insight["title"] = proposal["title"]
        insight["summary"] = proposal["summary"]
        insight["analysis_markdown"] = proposal["analysis_markdown"]
        insight["updated_at"] = now
        updated_records[signal_path] = signal
        updated_records[insight_path] = insight

    market_sensing.atomic_write_text(
        backup,
        json.dumps(backup_payload, ensure_ascii=False, indent=2) + "\n",
    )

    written: list[Path] = []
    try:
        for target in sorted(updated_records, key=lambda path: str(path)):
            written.append(target)
            market_sensing.write_json(target, updated_records[target])
    except Exception as exc:
        rollback_errors: list[str] = []
        for target in reversed(written):
            try:
                market_sensing.atomic_write_text(target, original_text[target])
            except Exception as rollback_exc:  # pragma: no cover - catastrophic I/O path
                rollback_errors.append(f"{target}: {rollback_exc}")
        if rollback_errors:
            raise RuntimeError(
                "Signal migration failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposals", nargs="+", type=Path)
    parser.add_argument("--wiki-root", type=Path, default=PROJECT_ROOT / "market-sensing-wiki")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--backup",
        type=Path,
        default=PROJECT_ROOT / "tmp" / "editorial-rewrite" / "before-rewrite.json",
    )
    args = parser.parse_args()
    proposals, errors = validate_proposals(args.proposals, args.wiki_root)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    if args.apply:
        apply_proposals(proposals, args.wiki_root, args.backup)
    counts = {
        axis: sum(1 for item in proposals if item["business_axis"] == axis)
        for axis in AXIS_COMPANY
    }
    type_counts = {
        signal_type: sum(1 for item in proposals if item["signal_type"] == signal_type)
        for signal_type in market_sensing.SIGNAL_TYPES
    }
    print(
        json.dumps(
            {
                "valid": True,
                "applied": args.apply,
                "proposal_count": len(proposals),
                "counts": counts,
                "type_counts": type_counts,
                "backup": str(args.backup) if args.apply else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
