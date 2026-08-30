"""Apply revised staged assessment scores to already-published daily Signals."""

from __future__ import annotations

import argparse
import json
import sys
from argparse import Namespace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import market_sensing  # noqa: E402
from publish_daily_signal_packets import packet_rows, preflight_rows  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("packet_file", type=Path, nargs="+")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = [row for path in args.packet_file for row in packet_rows(path)]
    preflight_rows(rows)
    root = market_sensing.require_store(Path(args.root))
    signals_by_key = {
        str(signal.get("canonical_key")): signal
        for _, signal in market_sensing.signal_records(root)
        if signal.get("canonical_key")
    }
    changed = []
    for row in rows:
        staged = row["signal"]
        existing = signals_by_key.get(staged["canonical_key"])
        if existing is None:
            continue
        current = (
            int((existing.get("business_impact") or {}).get("score") or 0),
            int((existing.get("urgency") or {}).get("score") or 0),
            str((existing.get("business_impact") or {}).get("rationale") or ""),
            str((existing.get("urgency") or {}).get("rationale") or ""),
        )
        proposed = (
            int(staged["business_impact_score"]),
            int(staged["urgency_score"]),
            staged["business_impact_rationale"],
            staged["urgency_rationale"],
        )
        if current == proposed:
            continue
        result = market_sensing.set_signal_assessment(
            Namespace(
                root=str(root),
                signal_id=existing["signal_id"],
                business_impact_score=proposed[0],
                business_impact_rationale=proposed[2],
                urgency_score=proposed[1],
                urgency_rationale=proposed[3],
                assessment_confidence=staged["assessment_confidence"],
                assessed_at=staged["assessed_at"],
                reason=(
                    "6개월 일별 Signal 포트폴리오 검토에서 사건 직접성, 회사 노출과 "
                    "대응시한을 개별 근거로 다시 평가했습니다."
                ),
                enterprise_scope=None,
                immediate_action=None,
                delay_loss=None,
                irreversibility=None,
            )
        )
        changed.append(result["signal_id"])
        if len(changed) % 10 == 0:
            print(f"reassessed {len(changed)}", flush=True)

    print(
        json.dumps(
            {"action": "daily_signal_assessments_applied", "changed": len(changed)},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
