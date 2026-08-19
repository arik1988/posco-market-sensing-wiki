"""Validate and publish normalized retrospective market-sensing plans."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from types import SimpleNamespace
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import market_sensing  # noqa: E402


REQUIRED_CLAIMS = market_sensing.REQUIRED_SIGNAL_PREDICATES
COMPANY_AXES = market_sensing.MARKET_SENSING_AXES


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def replace_source_placeholder(value: Any, source_id: str) -> Any:
    if isinstance(value, str):
        return source_id if value == "$SOURCE_ID" else value
    if isinstance(value, list):
        return [replace_source_placeholder(item, source_id) for item in value]
    if isinstance(value, dict):
        return {
            key: replace_source_placeholder(item, source_id)
            for key, item in value.items()
        }
    return value


def normalized_plan_paths(paths: list[Path]) -> list[Path]:
    return [path.resolve() for path in paths]


def validate_plans(paths: list[Path], wiki_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    plans: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_subjects: set[str] = set()
    seen_urls: set[str] = set()
    seen_plan_sources: list[tuple[str, set[str], str]] = []
    source_records = market_sensing.source_records(wiki_root)
    existing_hashes = {
        str(record.get("content_sha256") or "") for _, record in source_records
    }
    existing_sentences = {
        str(record.get("sentence") or "")
        for _, record in market_sensing.signal_records(wiki_root)
    }

    for path in paths:
        try:
            plan = load_json(path)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
            continue
        if not isinstance(plan, dict) or not isinstance(plan.get("items"), list):
            errors.append(f"{path}: plan must contain an items list")
            continue
        run = plan.get("run")
        if not isinstance(run, dict) or not str(run.get("run_id") or "").strip():
            errors.append(f"{path}: plan.run.run_id is required")
            continue

        base = path.parent
        for index, item in enumerate(plan["items"], start=1):
            label = f"{path.name} item {index}"
            source = item.get("source") if isinstance(item, dict) else None
            signal = item.get("signal") if isinstance(item, dict) else None
            claims = item.get("claims") if isinstance(item, dict) else None
            if not isinstance(source, dict) or not isinstance(signal, dict) or not isinstance(claims, list):
                errors.append(f"{label}: source, signal, and claims are required")
                continue

            subject_id = str(item.get("subject_id") or "")
            if not subject_id.startswith(("MKT-", "POL-", "OPS-", "PRJ-")):
                errors.append(f"{label}: invalid subject_id {subject_id!r}")
            if subject_id in seen_subjects:
                errors.append(f"{label}: duplicate subject_id {subject_id}")
            seen_subjects.add(subject_id)

            source_path = base / str(source.get("content_file") or "")
            analysis_path = base / str(item.get("analysis_file") or "")
            if not source_path.is_file():
                errors.append(f"{label}: missing source file {source_path}")
            else:
                source_text = source_path.read_text(encoding="utf-8", errors="replace")
                source_hash = market_sensing.normalized_sha256(source_text)
                source_tokens = market_sensing.token_set(source_text)
                for previous_title, previous_tokens, previous_label in seen_plan_sources:
                    title_score = SequenceMatcher(
                        None,
                        market_sensing.normalize_text(str(source.get("title") or "")),
                        market_sensing.normalize_text(previous_title),
                    ).ratio()
                    content_score = market_sensing.jaccard(source_tokens, previous_tokens)
                    if content_score >= 0.90 or (
                        title_score >= 0.90 and content_score >= 0.72
                    ):
                        errors.append(
                            f"{label}: near-duplicate planned source requires review ({previous_label})"
                        )
                seen_plan_sources.append(
                    (str(source.get("title") or ""), source_tokens, label)
                )
                if source_hash not in existing_hashes:
                    candidates = market_sensing.near_duplicate_candidates(
                        wiki_root,
                        str(source.get("title") or ""),
                        source_text,
                        source_records,
                    )
                    if candidates:
                        candidate_ids = ", ".join(
                            str(candidate.get("source_id") or "unknown")
                            for candidate in candidates
                        )
                        errors.append(
                            f"{label}: near-duplicate source requires review ({candidate_ids})"
                        )
            if not analysis_path.is_file():
                errors.append(f"{label}: missing analysis file {analysis_path}")
            else:
                try:
                    market_sensing.validate_signal_analysis(
                        analysis_path.read_text(encoding="utf-8")
                    )
                except ValueError as exc:
                    errors.append(f"{label}: analysis contract: {exc}")

            canonical_url = market_sensing.canonicalize_url(source.get("url"))
            if not canonical_url:
                errors.append(f"{label}: source URL is required")
            elif canonical_url in seen_urls:
                errors.append(f"{label}: duplicate plan URL {canonical_url}")
            seen_urls.add(canonical_url)
            if source.get("source_type") not in market_sensing.SOURCE_TYPES:
                errors.append(
                    f"{label}: unsupported source_type {source.get('source_type')!r}"
                )
            if source.get("reliability") not in market_sensing.SOURCE_RELIABILITY:
                errors.append(
                    f"{label}: unsupported reliability {source.get('reliability')!r}"
                )

            company_id = str(signal.get("company_id") or "")
            if COMPANY_AXES.get(company_id) != signal.get("business_axis"):
                errors.append(f"{label}: invalid company/business-axis pair")
            try:
                market_sensing.validate_signal_type(signal.get("signal_type"))
                market_sensing.validate_signal_copy(
                    str(signal.get("title") or ""),
                    str(signal.get("sentence") or ""),
                    str(signal.get("paragraph") or ""),
                )
            except ValueError as exc:
                errors.append(f"{label}: signal contract: {exc}")
            if str(signal.get("sentence") or "") in existing_sentences:
                errors.append(f"{label}: signal sentence already exists")

            claims_by_predicate = {
                str(claim.get("predicate") or ""): claim
                for claim in claims
                if isinstance(claim, dict)
            }
            missing_claims = sorted(REQUIRED_CLAIMS - set(claims_by_predicate))
            if missing_claims:
                errors.append(f"{label}: missing required claims {', '.join(missing_claims)}")
            verified_at = str(source.get("collected_at") or "")
            stale_claim_dates = [
                str(claim.get("predicate") or "")
                for claim in claims
                if isinstance(claim, dict) and str(claim.get("as_of") or "") != verified_at
            ]
            if stale_claim_dates:
                errors.append(
                    f"{label}: claim as_of must equal collected_at for current backfill verification"
                )
            expected = {
                "business_axis": signal.get("business_axis"),
                "business_impact_score_1_to_5": signal.get("business_impact_score"),
                "business_impact_rationale": signal.get("business_impact_rationale"),
                "urgency_score_1_to_5": signal.get("urgency_score"),
                "urgency_rationale": signal.get("urgency_rationale"),
                "assessment_confidence": signal.get("assessment_confidence"),
                "assessed_at": signal.get("assessed_at"),
            }
            for predicate, expected_value in expected.items():
                claim = claims_by_predicate.get(predicate)
                actual = None if claim is None else claim.get("value")
                if market_sensing.normalize_text(str(actual or "")) != market_sensing.normalize_text(
                    str(expected_value or "")
                ):
                    errors.append(f"{label}: {predicate} disagrees with signal")

            impact_relative = item.get("impact_estimate_file")
            if impact_relative:
                impact_path = base / str(impact_relative)
                if not impact_path.is_file():
                    errors.append(f"{label}: missing impact estimate {impact_path}")
                else:
                    try:
                        impact = replace_source_placeholder(
                            load_json(impact_path), "SRC-20260819-00000000"
                        )
                        market_sensing.validate_impact_estimate(impact)
                    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                        errors.append(f"{label}: impact contract: {exc}")
        plan["_path"] = path
        plans.append(plan)
    return plans, errors


def source_args(wiki_root: Path, base: Path, source: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        root=str(wiki_root),
        content_file=str(base / source["content_file"]),
        title=source["title"],
        url=source.get("url"),
        publisher=source["publisher"],
        published_at=source.get("published_at"),
        collected_at=source.get("collected_at"),
        source_type=source["source_type"],
        language=source["language"],
        reliability=source["reliability"],
        academic_kind=None,
        author=[],
        venue=None,
        doi=None,
        conference_name=None,
        conference_date=None,
        conference_location=None,
        peer_review_status=None,
        supporting_of=None,
        force=False,
    )


def publish_plan(plan: dict[str, Any], wiki_root: Path) -> dict[str, Any]:
    path = Path(plan.pop("_path"))
    base = path.parent
    run = dict(plan["run"])
    run_id = str(run["run_id"])
    run_path = wiki_root / ".system" / "runs" / f"2026-08-19-{run_id}.json"
    if run_path.exists():
        raise ValueError(f"Run already exists: {run_path}")
    run.setdefault("results", {})
    run["results"].update({"new_sources": 0, "new_claims": 0, "new_signals": 0})
    run["signal_ids"] = []
    market_sensing.write_json(run_path, run)

    counts = {"new_sources": 0, "new_claims": 0, "new_signals": 0}
    for item in plan["items"]:
        source_result = market_sensing.add_source(
            source_args(wiki_root, base, item["source"])
        )
        if source_result["action"] not in {"created", "exact_duplicate"}:
            raise ValueError(
                f"Source requires review for {item['subject_id']}: {source_result}"
            )
        source_id = str(source_result["source_id"])
        if source_result["action"] == "created":
            counts["new_sources"] += 1

        claim_ids: list[str] = []
        for claim in item["claims"]:
            claim_result = market_sensing.add_claim(
                SimpleNamespace(
                    root=str(wiki_root),
                    subject_id=item["subject_id"],
                    predicate=str(claim["predicate"]),
                    value=str(claim["value"]),
                    source_id=[source_id],
                    confidence=claim["confidence"],
                    as_of=claim.get("as_of"),
                    reason=claim["reason"],
                )
            )
            if claim_result["action"] not in {"created", "verified_existing"}:
                raise ValueError(
                    f"Claim requires review for {item['subject_id']}: {claim_result}"
                )
            claim_ids.append(str(claim_result["claim_id"]))
            if claim_result["action"] == "created":
                counts["new_claims"] += 1

        impact_file = None
        if item.get("impact_estimate_file"):
            impact = replace_source_placeholder(
                load_json(base / item["impact_estimate_file"]), source_id
            )
            impact_dir = PROJECT_ROOT / "research" / "impact-estimates" / "backfill"
            impact_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(item["subject_id"].encode("utf-8")).hexdigest()[:10]
            impact_path = impact_dir / f"{item['subject_id'].lower()}-{digest}.json"
            market_sensing.write_json(impact_path, impact)
            impact_file = str(impact_path)

        signal = item["signal"]
        signal_result = market_sensing.add_signal(
            SimpleNamespace(
                root=str(wiki_root),
                run_id=run_id,
                title=signal["title"],
                sentence=signal["sentence"],
                signal_type=signal["signal_type"],
                signal_role=signal["signal_role"],
                signal_origin=signal["signal_origin"],
                baseline_assumption=signal.get("baseline_assumption"),
                observed_break=signal.get("observed_break"),
                decision_change=signal.get("decision_change"),
                surprise_pattern=signal.get("surprise_pattern"),
                surprise_score=signal.get("surprise_score"),
                falsification_check=signal.get("falsification_check"),
                paragraph=signal["paragraph"],
                document_path=None,
                analysis_file=str(base / item["analysis_file"]),
                impact_estimate_file=impact_file,
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
        counts["new_signals"] += 1
        run["signal_ids"].append(signal_result["signal_id"])

    run["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    run["results"].update(counts)
    market_sensing.write_json(run_path, run)
    return {"run_id": run_id, **counts, "signal_ids": run["signal_ids"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plans", nargs="+", type=Path)
    parser.add_argument("--wiki-root", type=Path, default=PROJECT_ROOT / "market-sensing-wiki")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    paths = normalized_plan_paths(args.plans)
    wiki_root = args.wiki_root.resolve()
    plans, errors = validate_plans(paths, wiki_root)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    if not args.apply:
        print(
            json.dumps(
                {"valid": True, "plans": len(plans), "items": sum(len(p["items"]) for p in plans)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    results = [publish_plan(plan, wiki_root) for plan in plans]
    market_sensing.sync_obsidian_store(wiki_root)
    print(json.dumps({"published": True, "runs": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
