"""Replace staged daily Signal analyses through the canonical update API."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
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
    parser.add_argument("packet_file", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = packet_rows(args.packet_file)
    preflight_rows(rows)
    root = market_sensing.require_store(Path(args.root))
    signals_by_key = {
        str(signal.get("canonical_key")): signal
        for _, signal in market_sensing.signal_records(root)
        if signal.get("canonical_key")
    }
    missing = [
        row["signal"]["canonical_key"]
        for row in rows
        if row["signal"]["canonical_key"] not in signals_by_key
    ]
    if missing:
        raise ValueError(f"staged analyses reference unknown canonical keys: {missing[:5]}")

    updated = []
    with tempfile.TemporaryDirectory(prefix="daily-analysis-update-") as temp_name:
        temp_dir = Path(temp_name)
        analysis_file = temp_dir / "analysis.md"
        structured_file = temp_dir / "structured.json"
        for index, row in enumerate(rows, start=1):
            analysis_file.write_text(row["analysis_markdown"], encoding="utf-8")
            structured_file.write_text(
                json.dumps(row["analysis_structured"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            signal = signals_by_key[row["signal"]["canonical_key"]]
            result = market_sensing.set_signal_analysis(
                Namespace(
                    root=str(root),
                    signal_id=signal["signal_id"],
                    analysis_file=str(analysis_file),
                    structured_analysis_file=str(structured_file),
                    claim_id=[],
                )
            )
            updated.append(result["signal_id"])
            if index % 25 == 0:
                print(f"updated {index}/{len(rows)}", flush=True)

    print(
        json.dumps(
            {"action": "daily_signal_analyses_updated", "updated": len(updated)},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
