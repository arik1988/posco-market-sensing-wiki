"""Validate Luna backfill bundles before they enter the governed Wiki store."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import market_sensing  # noqa: E402


REQUIRED_MANIFEST_FIELDS = {
    "title",
    "url",
    "canonical_url",
    "publisher",
    "published_at",
    "source_type",
    "language",
    "reliability",
    "access_status",
    "key_original_sentence",
    "cross_verification_urls",
    "duplicate_candidates",
    "collected_at",
}
EARLIEST_PUBLICATION = date(2024, 8, 19)
LATEST_PUBLICATION = date(2026, 8, 19)


def validate_bundle(bundle: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = bundle / "manifest.json"
    source_path = bundle / "source.md"
    analysis_path = bundle / "candidate.md"

    for path in (manifest_path, source_path, analysis_path):
        if not path.is_file():
            errors.append(f"{bundle.name}: missing {path.name}")
    if errors:
        return errors

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [f"{bundle.name}: invalid manifest.json: {exc}"]

    missing = sorted(REQUIRED_MANIFEST_FIELDS - set(manifest))
    if missing:
        errors.append(f"{bundle.name}: manifest missing {', '.join(missing)}")

    try:
        published_at = date.fromisoformat(str(manifest.get("published_at", "")))
        if not EARLIEST_PUBLICATION <= published_at <= LATEST_PUBLICATION:
            errors.append(f"{bundle.name}: published_at outside two-year window")
    except ValueError:
        errors.append(f"{bundle.name}: published_at must be YYYY-MM-DD")

    if manifest.get("collected_at") != "2026-08-19":
        errors.append(f"{bundle.name}: collected_at must preserve the actual backfill date")
    if not str(manifest.get("url", "")).startswith(("http://", "https://")):
        errors.append(f"{bundle.name}: source URL is not HTTP(S)")
    if not str(manifest.get("key_original_sentence", "")).strip():
        errors.append(f"{bundle.name}: key original sentence is empty")
    if not isinstance(manifest.get("cross_verification_urls"), list):
        errors.append(f"{bundle.name}: cross_verification_urls must be a list")

    source_text = source_path.read_text(encoding="utf-8").strip()
    if len(source_text) < 500:
        errors.append(f"{bundle.name}: source.md is too thin ({len(source_text)} chars)")

    analysis_text = analysis_path.read_text(encoding="utf-8").strip()
    try:
        market_sensing.validate_signal_analysis(analysis_text)
    except ValueError as exc:
        errors.append(f"{bundle.name}: analysis contract: {exc}")

    impact_path = bundle / "impact-estimate.json"
    if impact_path.is_file():
        try:
            impact = json.loads(impact_path.read_text(encoding="utf-8"))
            market_sensing.validate_impact_estimate(impact)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            errors.append(f"{bundle.name}: impact contract: {exc}")

    return errors


def validate_aggregate_manifest(path: Path) -> tuple[int, list[str]]:
    """Validate an axis-level list whose files live in analysis/ and sources/."""
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return 0, [f"{path.parent.name}: invalid aggregate manifest: {exc}"]
    if not isinstance(records, list):
        return 0, []

    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        label = str(record.get("candidate_id") or f"{path.parent.name}-{index}")
        required = REQUIRED_MANIFEST_FIELDS - {"key_original_sentence"}
        missing = sorted(required - set(record))
        if missing:
            errors.append(f"{label}: manifest missing {', '.join(missing)}")
        if not record.get("key_original_sentence") and not record.get("key_original_sentences"):
            errors.append(f"{label}: key original sentence is empty")
        for field in ("source_file", "analysis_file"):
            relative = record.get(field)
            file_path = path.parent / str(relative or "")
            if not relative or not file_path.is_file():
                errors.append(f"{label}: missing {field}")
                continue
            text = file_path.read_text(encoding="utf-8").strip()
            if field == "source_file" and len(text) < 500:
                errors.append(f"{label}: source file is too thin ({len(text)} chars)")
            if field == "analysis_file":
                try:
                    market_sensing.validate_signal_analysis(text)
                except ValueError as exc:
                    errors.append(f"{label}: analysis contract: {exc}")
        impact = record.get("impact_estimate")
        if impact:
            try:
                market_sensing.validate_impact_estimate(impact)
            except ValueError as exc:
                errors.append(f"{label}: impact contract: {exc}")
    return len(records), errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=PROJECT_ROOT / "incoming" / "backfill-2024-2026",
    )
    args = parser.parse_args()
    manifests = list(args.root.rglob("manifest.json"))
    bundles = sorted(
        path.parent
        for path in manifests
        if len(path.relative_to(args.root).parts) >= 3
    )
    errors = [error for bundle in bundles for error in validate_bundle(bundle)]
    aggregate_count = 0
    for path in manifests:
        if len(path.relative_to(args.root).parts) != 2:
            continue
        count, aggregate_errors = validate_aggregate_manifest(path)
        aggregate_count += count
        errors.extend(aggregate_errors)
    candidate_count = len(bundles) + aggregate_count
    result = {
        "root": str(args.root),
        "bundle_count": candidate_count,
        "valid_bundle_count": max(
            0,
            candidate_count
            - len({error.split(":", 1)[0] for error in errors}),
        ),
        "error_count": len(errors),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors or not candidate_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
