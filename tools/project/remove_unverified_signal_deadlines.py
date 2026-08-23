"""Remove deadline values that have no stored public-evidence link.

This migration is intentionally narrow: it does not touch event/effective dates or
dated facts. It only clears Signal.response_deadline and date suffixes attached to
analyst-created ``다음 산출물`` list items. A JSON backup is written before apply.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


OUTPUT_DATE = re.compile(r"\s+[—-]\s+20\d{2}-\d{2}-\d{2}\s*$")


def scrub_outputs(markdown: str) -> tuple[str, int]:
    lines = markdown.splitlines()
    in_outputs = False
    changed = 0
    for index, line in enumerate(lines):
        if re.match(r"^\*\*(?:다음 산출물|의사결정에 필요한 다음 산출물):\*\*", line):
            in_outputs = True
            continue
        if in_outputs and (line.startswith("## ") or line.startswith("!!! ")):
            in_outputs = False
        if in_outputs and re.match(r"^\d+\.\s+", line):
            scrubbed = OUTPUT_DATE.sub("", line)
            if scrubbed != line:
                lines[index] = scrubbed
                changed += 1
    return "\n".join(lines), changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wiki-root", type=Path, default=Path("market-sensing-wiki"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.wiki_root.resolve()
    backups: list[dict[str, object]] = []
    writes: list[tuple[Path, dict[str, object]]] = []

    insights = {
        path.stem: path
        for path in sorted((root / ".system" / "insights").glob("INS-*.json"))
    }
    for signal_path in sorted((root / ".system" / "signals").glob("SIG-*.json")):
        signal = json.loads(signal_path.read_text(encoding="utf-8"))
        deadline = signal.get("urgency", {}).get("response_deadline")
        insight_path = insights[str(signal["insight_id"])]
        insight = json.loads(insight_path.read_text(encoding="utf-8"))
        revised, removed_output_dates = scrub_outputs(str(insight.get("analysis_markdown") or ""))
        if not deadline and not removed_output_dates:
            continue
        backups.append(
            {
                "signal_path": str(signal_path.relative_to(root.parent)),
                "insight_path": str(insight_path.relative_to(root.parent)),
                "response_deadline": deadline,
                "analysis_markdown": insight.get("analysis_markdown"),
            }
        )
        signal.get("urgency", {}).pop("response_deadline", None)
        insight["analysis_markdown"] = revised
        writes.extend(((signal_path, signal), (insight_path, insight)))

    print(json.dumps({"signals": len(backups), "files": len(writes)}, ensure_ascii=False))
    if not args.apply or not writes:
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = root.parent / "tmp" / f"signal-deadline-backup-{stamp}.json"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(backups, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path, payload in writes:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"backup": str(backup_path), "applied": len(writes)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
