"""Atomically apply the reviewed market-signal role/origin migration manifests."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


ROLE_MAP = {
    "core_external_market_signal": "core_market_signal",
    "supporting_execution_context": "execution_context",
    "core_market_signal": "core_market_signal",
    "execution_context": "execution_context",
}
ORIGIN_MAP = {
    "external_market": "external_market",
    "external_policy": "policy_regulator",
    "external_geopolitics_logistics": "external_market",
    "policy_regulator": "policy_regulator",
    "competitor_counterparty": "competitor_counterparty",
    "company_execution": "company_execution",
    "company_performance": "company_execution",
}
ALLOWED = {
    "core_market_signal": {
        "external_market",
        "policy_regulator",
        "competitor_counterparty",
    },
    "execution_context": {"company_execution"},
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, path)


def load_items(energy_manifest: Path, non_energy_manifest: Path) -> list[dict[str, Any]]:
    energy = read_json(energy_manifest).get("items")
    non_energy = read_json(non_energy_manifest).get("signals")
    if not isinstance(energy, list) or not isinstance(non_energy, list):
        raise ValueError("Migration manifests must contain items/signals arrays")
    return [*energy, *non_energy]


def normalized_classification(item: dict[str, Any]) -> tuple[str, str]:
    role = ROLE_MAP.get(str(item.get("role") or ""))
    origin = ORIGIN_MAP.get(str(item.get("origin") or ""))
    if not role or not origin or origin not in ALLOWED[role]:
        raise ValueError(
            f"Invalid classification for {item.get('signal_id')}: "
            f"{item.get('role')}/{item.get('origin')}"
        )
    return role, origin


def validate_copy(title: str, sentence: str, summary: str) -> None:
    if not 8 <= len(title) <= 45 or "…" in title or "..." in title:
        raise ValueError(f"Invalid rewritten title: {title}")
    if not 20 <= len(sentence) <= 180 or not re.search(r"[.!?]\s*$", sentence):
        raise ValueError(f"Invalid rewritten sentence: {sentence}")
    if not 70 <= len(summary) <= 500:
        raise ValueError(f"Invalid rewritten summary length: {title}")
    if len(re.findall(r"[.!?](?:\s|$)", summary)) not in range(2, 5):
        raise ValueError(f"Rewritten summary must contain 2-4 sentences: {title}")


def proposed_changes(root: Path, items: list[dict[str, Any]]) -> list[tuple[Path, dict[str, Any]]]:
    changes: list[tuple[Path, dict[str, Any]]] = []
    seen: set[str] = set()
    for item in items:
        signal_id = str(item.get("signal_id") or "")
        if not signal_id or signal_id in seen:
            raise ValueError(f"Missing or duplicate signal_id: {signal_id}")
        seen.add(signal_id)
        signal_path = root / ".system" / "signals" / f"{signal_id}.json"
        signal = read_json(signal_path)
        if signal.get("signal_id") != signal_id:
            raise ValueError(f"Signal ID mismatch: {signal_path}")
        insight_path = root / ".system" / "insights" / f"{signal['insight_id']}.json"
        insight = read_json(insight_path)
        current_title = str(item.get("current_title") or "")
        rewrite = item.get("editorial_rewrite")
        accepted_titles = {current_title}
        if isinstance(rewrite, dict):
            accepted_titles.add(str(rewrite.get("title") or "").strip())
        if current_title and insight.get("title") not in accepted_titles:
            raise ValueError(f"Stale title in manifest for {signal_id}")

        role, origin = normalized_classification(item)
        signal["signal_role"] = role
        signal["signal_origin"] = origin

        if isinstance(rewrite, dict):
            title = str(rewrite.get("title") or "").strip()
            sentence = str(rewrite.get("sentence") or "").strip()
            summary = str(rewrite.get("body_lead") or "").strip()
            validate_copy(title, sentence, summary)
            insight["title"] = title
            signal["sentence"] = sentence
            insight["summary"] = summary

        changes.extend([(signal_path, signal), (insight_path, insight)])

    existing = {path.stem for path in (root / ".system" / "signals").glob("SIG-*.json")}
    legacy_existing = existing - {
        "SIG-87E7FDAE469F",
        "SIG-578CFAD38D8A",
    }
    if seen != legacy_existing:
        missing = sorted(legacy_existing - seen)
        extra = sorted(seen - legacy_existing)
        raise ValueError(f"Manifest coverage mismatch; missing={missing}, extra={extra}")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="market-sensing-wiki")
    parser.add_argument(
        "--energy-manifest",
        default="tools/project/manifests/energy-signal-rebalance-20260819.json",
    )
    parser.add_argument(
        "--non-energy-manifest",
        default="tools/project/manifests/non-energy-signal-rebalance-20260819.json",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    items = load_items(Path(args.energy_manifest), Path(args.non_energy_manifest))
    changes = proposed_changes(root, items)
    role_counts: dict[str, int] = {}
    for index in range(0, len(changes), 2):
        role = str(changes[index][1]["signal_role"])
        role_counts[role] = role_counts.get(role, 0) + 1

    if args.apply:
        for path, value in changes:
            write_json_atomic(path, value)
    print(
        json.dumps(
            {
                "action": "applied" if args.apply else "validated",
                "legacy_signals": len(items),
                "records": len(changes),
                "role_counts": role_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
