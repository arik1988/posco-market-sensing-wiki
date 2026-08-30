"""Publish validated daily Signal JSONL packets through the canonical APIs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from argparse import Namespace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import market_sensing  # noqa: E402
from signal_analytics import CANONICAL_KEY_PATTERN  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("packet_file", type=Path)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def packet_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def preflight_rows(rows: list[dict]) -> None:
    """Run write-critical validators for every row before the first DB mutation."""
    for index, row in enumerate(rows, start=1):
        signal = row["signal"]
        try:
            if not CANONICAL_KEY_PATTERN.fullmatch(str(signal["canonical_key"])):
                raise ValueError("invalid signal.canonical_key")
            market_sensing.validate_signal_copy(
                signal["title"], signal["sentence"], signal["paragraph"]
            )
            role, _ = market_sensing.validate_signal_classification(
                signal["signal_role"], signal["signal_origin"]
            )
            if role == "core_market_signal":
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
            market_sensing.validate_signal_analysis(row["analysis_markdown"])
            market_sensing.validate_structured_analysis(
                row["analysis_structured"],
                require_current_schema=True,
                importance_score=max(
                    int(signal["business_impact_score"]),
                    int(signal["urgency_score"]),
                ),
            )
            market_sensing.validate_quantification_decision(
                row["quantification_decision"], row.get("impact_estimate")
            )
            if row.get("impact_estimate") is not None:
                market_sensing.validate_impact_estimate(row["impact_estimate"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"packet row {index} failed preflight: {error}") from error


def risk_factor_id(signal: dict) -> str:
    digest = hashlib.sha256(
        f"{signal['business_axis']}\0{signal['signal_type']}".encode("utf-8")
    ).hexdigest()[:12].upper()
    return f"RF-DAILY-{digest}"


def ensure_risk_factor(root: str, signal: dict) -> str:
    factor_id = risk_factor_id(signal)
    market_sensing.add_risk_factor(
        Namespace(
            root=root,
            risk_factor_id=factor_id,
            taxonomy_version=1,
            name=f"{signal['business_axis']} {signal['signal_type']} 변화",
            definition=(
                f"{signal['business_axis']} 사업의 가격·물량·원가·계약·투자·운영 판단에 "
                f"전달되는 {signal['signal_type']} 외부 변화입니다."
            ),
            category="DAILY_MARKET_SIGNAL",
            parent_risk_factor_id=None,
            alias=[],
            status="active",
            valid_from=None,
            valid_to=None,
        )
    )
    return factor_id


def add_packet_source(root: str, row: dict, temp_dir: Path) -> str:
    source = row["source"]
    content_file = temp_dir / "source.md"
    content_file.write_text(source["raw_markdown"], encoding="utf-8")
    result = market_sensing.add_source(
        Namespace(
            root=root,
            content_file=str(content_file),
            title=source["title"],
            url=source["url"],
            publisher=source["publisher"],
            published_at=source["published_at"],
            collected_at=row["detected_at"],
            source_type=source["source_type"],
            source_modality=source["source_modality"],
            language=source["language"],
            reliability=source["reliability"],
            supporting_of=None,
            force=True,
            academic_kind=None,
            doi=None,
            venue=None,
            event_name=None,
            event_date=None,
            event_location=None,
            peer_reviewed=None,
        )
    )
    return str(result["source_id"])


def add_claim(
    root: str,
    source_id: str,
    factor_id: str,
    subject_id: str,
    predicate: str,
    value: object,
    confidence: str,
    as_of: str,
    reason: str,
) -> str:
    result = market_sensing.add_claim(
        Namespace(
            root=root,
            subject_id=subject_id,
            predicate=predicate,
            value=str(value),
            source_id=[source_id],
            risk_factor_id=[factor_id],
            confidence=confidence,
            as_of=as_of,
            reason=reason,
        )
    )
    if result["action"] == "review_required":
        raise ValueError(
            f"claim review required for {subject_id}/{predicate}: {result['review_id']}"
        )
    return str(result["claim_id"])


def add_packet_claims(
    root: str, row: dict, source_id: str, factor_id: str
) -> list[str]:
    claim = row["claim"]
    signal = row["signal"]
    subject_id = claim["subject_id"]
    as_of = claim["as_of"]
    confidence = claim["confidence"]
    values = {
        claim["predicate"]: claim["value"],
        "business_axis": signal["business_axis"],
        "business_impact_score_1_to_10": signal["business_impact_score"],
        "business_impact_rationale": signal["business_impact_rationale"],
        "urgency_score_1_to_10": signal["urgency_score"],
        "urgency_rationale": signal["urgency_rationale"],
        "assessment_confidence": signal["assessment_confidence"],
        "assessed_at": signal["assessed_at"],
        "impact_path": signal["impact_path"],
        "recommended_follow_up": signal["recommended_follow_up"],
    }
    return [
        add_claim(
            root,
            source_id,
            factor_id,
            subject_id,
            predicate,
            value,
            confidence,
            as_of,
            "공개 원문과 회사 영향 경로를 확인해 일별 발행 Signal 근거로 등록했습니다.",
        )
        for predicate, value in values.items()
    ]


def add_packet_signal(
    root: str,
    run_id: str,
    row: dict,
    claim_ids: list[str],
    factor_id: str,
    temp_dir: Path,
) -> dict:
    signal = row["signal"]
    analysis_file = temp_dir / "analysis.md"
    structured_file = temp_dir / "structured.json"
    decision_file = temp_dir / "decision.json"
    estimate_file = temp_dir / "estimate.json"
    analysis_file.write_text(row["analysis_markdown"], encoding="utf-8")
    structured_file.write_text(
        json.dumps(row["analysis_structured"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    decision_file.write_text(
        json.dumps(row["quantification_decision"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    impact_estimate = row.get("impact_estimate")
    if impact_estimate is not None:
        estimate_file.write_text(
            json.dumps(impact_estimate, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return market_sensing.add_signal(
        Namespace(
            root=root,
            run_id=run_id,
            canonical_key=signal["canonical_key"],
            risk_factor_id=[factor_id],
            observation_id=[],
            event_id=[],
            title=signal["title"],
            sentence=signal["sentence"],
            signal_type=signal["signal_type"],
            signal_role=signal["signal_role"],
            signal_origin=signal["signal_origin"],
            baseline_assumption=signal["baseline_assumption"],
            observed_break=signal["observed_break"],
            decision_change=signal["decision_change"],
            surprise_pattern=signal["surprise_pattern"],
            surprise_score=int(signal["surprise_score"]),
            falsification_check=signal["falsification_check"],
            paragraph=signal["paragraph"],
            document_path=None,
            analysis_file=str(analysis_file),
            structured_analysis_file=str(structured_file),
            impact_estimate_file=str(estimate_file) if impact_estimate is not None else None,
            quantification_decision_file=(
                None if impact_estimate is not None else str(decision_file)
            ),
            company_id=[signal["company_id"]],
            business_axis=signal["business_axis"],
            claim_id=claim_ids,
            business_impact_score=int(signal["business_impact_score"]),
            business_impact_rationale=signal["business_impact_rationale"],
            urgency_score=int(signal["urgency_score"]),
            urgency_rationale=signal["urgency_rationale"],
            response_deadline=signal.get("response_deadline"),
            assessed_at=signal["assessed_at"],
            assessment_confidence=signal["assessment_confidence"],
        )
    )


def update_coverage(root: str, run_id: str, published: list[tuple[dict, dict]]) -> None:
    run_path, run = market_sensing.run_record_by_id(
        market_sensing.require_store(Path(root)), run_id
    )
    coverage = dict(run.get("coverage") or {})
    candidates = list(coverage.get("candidates") or [])
    candidate_ids = {str(item.get("candidate_id")) for item in candidates}
    cells = {
        (str(cell["company_id"]), str(cell["business_axis"])): dict(cell)
        for cell in coverage.get("cells_checked", [])
    }
    for row, result in published:
        signal = row["signal"]
        signal_id = str(result["signal_id"])
        candidate_id = f"CAN-V5-{signal_id.removeprefix('SIG-')}"
        if candidate_id not in candidate_ids:
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_date": row["candidate_date"],
                    "detected_at": row["detected_at"],
                    "company_id": signal["company_id"],
                    "business_axis": signal["business_axis"],
                    "change_type": signal["signal_type"],
                    "title": signal["title"],
                    "source_url": row["source"]["url"],
                    "disposition": "published_signal",
                    "signal_id": signal_id,
                }
            )
            candidate_ids.add(candidate_id)
        pair = (signal["company_id"], signal["business_axis"])
        cell = cells[pair]
        cell["status"] = "covered"
        cell["candidate_ids"] = list(
            dict.fromkeys([*cell.get("candidate_ids", []), candidate_id])
        )
        discovery = row["discovery"]
        cell["channels"] = list(
            dict.fromkeys([*cell.get("channels", []), discovery["channel"]])
        )
        strategies = list(cell.get("search_strategies", []))
        strategy_name = f"daily_signal_{row['candidate_date']}_{signal_id}"
        if strategy_name not in {
            str(item.get("strategy")) for item in strategies if isinstance(item, dict)
        }:
            strategies.append({
                "strategy": strategy_name,
                "channel": discovery["channel"],
                "query": discovery["query"],
                "executed_at": discovery["executed_at"],
                "change_types": discovery["change_types"],
                "new_candidates": 1,
                "new_high_impact_candidates": int(
                    max(
                        int(signal["business_impact_score"]),
                        int(signal["urgency_score"]),
                    )
                    >= 8
                ),
            })
        cell["search_strategies"] = strategies
        cell["limitations"] = list(cell.get("limitations", []))
        cell["next_trigger"] = signal["recommended_follow_up"]
        cells[pair] = cell
    coverage["candidates"] = candidates
    coverage["cells_checked"] = list(cells.values())
    coverage["high_risk_gaps"] = []
    coverage["limitations"] = list(coverage.get("limitations", []))
    coverage["next_triggers"] = list(coverage.get("next_triggers", []))
    coverage["no_signal_reasons_by_company"] = {}
    run["coverage"] = coverage
    run["coverage_updated_at"] = market_sensing.timestamp()
    market_sensing.write_json(run_path, run)


def main() -> None:
    args = parse_args()
    rows = packet_rows(args.packet_file)
    preflight_rows(rows)
    published = []
    for index, row in enumerate(rows, start=1):
        with tempfile.TemporaryDirectory(prefix="daily-signal-") as temp_name:
            temp_dir = Path(temp_name)
            factor_id = ensure_risk_factor(args.root, row["signal"])
            source_id = add_packet_source(args.root, row, temp_dir)
            claim_ids = add_packet_claims(
                args.root, row, source_id, factor_id
            )
            result = add_packet_signal(
                args.root,
                args.run_id,
                row,
                claim_ids,
                factor_id,
                temp_dir,
            )
            published.append((row, result))
        if index % 25 == 0:
            update_coverage(args.root, args.run_id, published)
            print(f"published {index}/{len(rows)}", flush=True)
    update_coverage(args.root, args.run_id, published)
    print(
        json.dumps(
            {
                "action": "daily_signal_packets_published",
                "run_id": args.run_id,
                "published": len(published),
                "signal_ids": [result["signal_id"] for _, result in published],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
