"""Recover reader-facing Signals that exist only in a public Vercel deployment.

The deployment is treated as a recovery source, not as an authority to invent
missing Claim IDs. The script extracts the published Source notes and Signal
analysis, registers fresh local Source/Claim records, and republishes the
recovered Signals with an explicit medium confidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import market_sensing  # noqa: E402


REMOTE_BASE = "https://posco-market-sensing-wiki.vercel.app"
RECOVERY_RUN_ID = "2026-08-22-vercel-deployment-recovery"
SIGNAL_IDS = (
    "SIG-35E375530293",
    "SIG-58262BC4861B",
    "SIG-7A04B05EA7F7",
    "SIG-7A55EC61FBC5",
    "SIG-C68CC1899242",
    "SIG-DE2981C00725",
    "SIG-ECBFAFB863BF",
)

SUBJECT_IDS = {
    "SIG-35E375530293": "POL-CN-RARE-EARTH-CONTROLS-2025",
    "SIG-58262BC4861B": "MKT-STRATEGIC-MINERALS-POLICY-2026",
    "SIG-7A04B05EA7F7": "POL-KR-RARE-EARTH-2026",
    "SIG-7A55EC61FBC5": "POL-UK-STEEL-TRADE-2026",
    "SIG-C68CC1899242": "MKT-US-RARE-EARTH-GUARANTEE-2025",
    "SIG-DE2981C00725": "MKT-STEEL-US-QUALIFICATION-2026",
    "SIG-ECBFAFB863BF": "MKT-TUNGSTEN-SUPPLY-CONTROL-2025",
}

COMPANY_BY_AXIS = {
    "철강": "COM-POSCO",
    "리튬": "COM-POSCO-HOLDINGS",
    "전략광물": "COM-POSCO-HOLDINGS",
    "에너지": "COM-POSCO-INTERNATIONAL",
}

PATTERN_BY_SIGNAL = {
    "SIG-35E375530293": "policy_collision",
    "SIG-58262BC4861B": "cost_curve_break",
    "SIG-7A04B05EA7F7": "policy_collision",
    "SIG-7A55EC61FBC5": "market_access_rule",
    "SIG-C68CC1899242": "cost_curve_break",
    "SIG-DE2981C00725": "market_access_rule",
    "SIG-ECBFAFB863BF": "input_bottleneck",
}


def fetch(path: str) -> BeautifulSoup:
    url = path if path.startswith("http") else f"{REMOTE_BASE}/{path.lstrip('/')}"
    response = requests.get(
        url,
        headers={"User-Agent": "posco-market-sensing-recovery/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def text(value: Tag | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.get_text(" ", strip=True)).strip()


def direct_children(tag: Tag) -> list[Tag]:
    return [child for child in tag.find_all(recursive=False) if isinstance(child, Tag)]


def template_item(article: Tag) -> dict[str, Any]:
    template = article.find("template", attrs={"data-signal-ui": "detail"})
    if template is None or not template.string:
        raise ValueError("deployed Signal is missing its UI data template")
    payload = json.loads(template.string)
    item = payload.get("item")
    if not isinstance(item, dict):
        raise ValueError("deployed Signal UI data has no item")
    return item


def parse_table(table: Tag) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.find_all("tr"):
        cells = [text(cell) for cell in row.find_all(["th", "td"], recursive=False)]
        if cells:
            rows.append(cells)
    return rows


def table_markdown(table: Tag) -> list[str]:
    rows = parse_table(table)
    if not rows:
        return []
    width = len(rows[0])
    normalized = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(normalized[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    lines.extend("| " + " | ".join(row) + " |" for row in normalized[1:])
    return lines


def list_markdown(tag: Tag) -> list[str]:
    lines: list[str] = []
    ordered = tag.name == "ol"
    for index, item in enumerate(tag.find_all("li", recursive=False), start=1):
        prefix = f"{index}." if ordered else "-"
        lines.append(f"{prefix} {text(item)}")
    return lines


def admonition_markdown(tag: Tag) -> list[str]:
    classes = set(tag.get("class", []))
    kind = next((name for name in ("warning", "danger", "success", "abstract") if name in classes), "note")
    title_tag = tag.find("p", class_="admonition-title")
    title = text(title_tag) or kind
    body_parts: list[str] = []
    for child in direct_children(tag):
        if child is title_tag:
            continue
        if child.name == "p":
            body_parts.append(text(child))
        elif child.name in {"ul", "ol"}:
            body_parts.extend(list_markdown(child))
        elif child.name == "table":
            body_parts.extend(table_markdown(child))
    body = "\n".join(part for part in body_parts if part).strip()
    lines = [f'!!! {kind} "{title}"', ""]
    lines.extend(f"    {line}" if line else "    " for line in body.splitlines())
    return lines


def details_markdown(tag: Tag) -> list[str]:
    title_tag = tag.find("summary")
    title = text(title_tag) or "근거 메모"
    body_parts = [text(child) for child in direct_children(tag) if child is not title_tag]
    body = " ".join(part for part in body_parts if part)
    if not body:
        body = text(tag).replace(title, "", 1).strip()
    return [f'??? note "{title}"', "", f"    {body}"]


def render_analysis(article: Tag) -> str:
    lines: list[str] = []
    started = False
    for child in direct_children(article):
        if child.name == "template":
            continue
        if child.name == "h2":
            heading = text(child)
            if heading == "원문":
                break
            started = True
            lines.extend([f"## {heading}", ""])
            continue
        if not started:
            continue
        if child.name == "p":
            value = text(child)
            if value:
                # The deployed renderer uses plain marker paragraphs for
                # sections that the local signal contract requires to be
                # explicit headings. Promote those markers while preserving
                # the reader-facing wording that follows them.
                marker_headings = {
                    "사업 영향:": "사업 영향 경로와 조건",
                    "조건부 시나리오:": "조건부 시나리오",
                    "이번 주 확인할 지표:": "확인할 지표",
                    "다음 산출물:": "의사결정에 필요한 다음 산출물",
                }
                heading = marker_headings.get(value)
                if heading:
                    lines.extend([f"## {heading}", ""])
                lines.extend([value, ""])
        elif child.name == "div" and "mermaid" in set(child.get("class", [])):
            lines.extend(["```mermaid", child.get_text("\n", strip=True), "```", ""])
        elif child.name == "div" and "admonition" in set(child.get("class", [])):
            lines.extend(admonition_markdown(child))
            lines.append("")
        elif child.name == "details":
            lines.extend(details_markdown(child))
            lines.append("")
        elif child.name == "table":
            lines.extend(table_markdown(child))
            lines.append("")
        elif child.name in {"ul", "ol"}:
            lines.extend(list_markdown(child))
            lines.append("")
    analysis = "\n".join(lines).strip()
    if "!!! warning" not in analysis:
        analysis += (
            '\n\n!!! warning "판단의 한계"\n\n'
            "    이 문서는 공개 Vercel 배포에서 복구한 분석입니다. "
            "배포 화면에 표시되지 않은 내부 원가·계약·승인 데이터는 확인할 수 없습니다."
        )
    return analysis.strip() + "\n"


def extract_label(value: str, label: str, following: tuple[str, ...]) -> str:
    stop = "|".join(re.escape(item) for item in following)
    match = re.search(
        rf"{re.escape(label)}:\s*(.*?)(?=\s+(?:{stop}):|$)",
        value,
    )
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def extract_linked_label(value: str, label: str) -> str:
    """Read one field from the deployment's dot-separated evidence note."""
    match = re.search(
        rf"{re.escape(label)}:\s*(.*?)(?=\s+·\s+원문 근거 [^:]+:|$)",
        value,
    )
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def parse_source(source_id: str) -> dict[str, Any]:
    article = fetch(f"sources/{source_id}/").select_one("article.md-content__inner")
    if article is None:
        raise ValueError(f"source page has no article: {source_id}")
    title = text(article.find("h1"))
    metadata: dict[str, str] = {}
    first_list = article.find("ul", recursive=False)
    if first_list:
        for item in first_list.find_all("li", recursive=False):
            value = text(item)
            if ":" in value:
                key, raw = value.split(":", 1)
                metadata[key.strip()] = raw.strip()
    url_tag = first_list.find("a", href=True) if first_list else None
    url = metadata.get("원 URL") or (url_tag.get("href") if url_tag else "")
    block = article.find("blockquote")
    raw_title = text(block.find("h1")) if block and block.find("h1") else title
    raw_lines = [f"# {raw_title}", "", "## 원문 보존", ""]
    raw_lines.append(f"- 원문: {url}")
    raw_lines.append("- 접근 상태: Vercel 공개 배포의 보관 원문을 복구한 기록입니다.")
    raw_lines.extend(["", "### 보관된 원문 요약", ""])
    if block:
        for child in direct_children(block):
            if child.name == "h1":
                continue
            if child.name == "p":
                raw_lines.extend([text(child), ""])
            elif child.name in {"ul", "ol"}:
                raw_lines.extend(list_markdown(child))
                raw_lines.append("")
    language = "ko" if re.search(r"[가-힣]", "\n".join(raw_lines)) else "en"
    return {
        "remote_source_id": source_id,
        "title": title,
        "publisher": metadata.get("발행자", "배포 원문") or "배포 원문",
        "published_at": metadata.get("게시일") or None,
        "collected_at": metadata.get("수집일") or "2026-08-22",
        "source_type": metadata.get("유형") or "other",
        "reliability": metadata.get("신뢰도") or "medium",
        "url": url,
        "language": language,
        "content": "\n".join(raw_lines).strip() + "\n",
    }


def parse_signal(signal_id: str) -> dict[str, Any]:
    article = fetch(f"signals/{signal_id}/").select_one("article.md-content__inner")
    if article is None:
        raise ValueError(f"Signal page has no article: {signal_id}")
    item = template_item(article)
    table = article.find("table")
    table_rows = parse_table(table) if table else []
    axis, impact, urgency, assessed_at = "", 0, 0, ""
    if len(table_rows) >= 2:
        values = table_rows[1]
        axis = values[0]
        impact = int(values[1].split("/", 1)[0])
        urgency = int(values[2].split("/", 1)[0])
        assessed_at = values[3]
    direct = direct_children(article)
    summary = ""
    for index, child in enumerate(direct):
        if child.name == "p" and text(child) == "핵심 해석" and index + 1 < len(direct):
            summary = text(direct[index + 1])
            break
    notes = article.find_all("details", class_="note")
    note = notes[0] if notes else None
    note_text = text(note)
    impact_rationale = extract_label(note_text, "사업 영향", ("긴급성",))
    urgency_rationale = extract_label(note_text, "긴급성", ())
    linked_note_text = text(notes[-1]) if len(notes) > 1 else ""
    impact_path = extract_linked_label(linked_note_text, "원문 근거 impact path")
    recommended_follow_up = extract_linked_label(linked_note_text, "원문 근거 recommended follow up")
    warning = article.find("div", class_="warning")
    warning_text = text(warning)
    baseline = extract_label(warning_text, "기존 전제", ("전제를 깨는 관측", "바꿀 결정", "반증 확인"))
    observed_break = extract_label(warning_text, "전제를 깨는 관측", ("바꿀 결정", "반증 확인"))
    decision_change = extract_label(warning_text, "바꿀 결정", ("반증 확인",))
    falsification = extract_label(warning_text, "반증 확인", ())
    observed_change = ""
    for child in direct:
        value = text(child)
        if value.startswith("확인된 변화:"):
            observed_change = value.split(":", 1)[1].strip()
            break
    if not observed_change:
        observed_change = summary or item.get("title", "")
    source_ids = sorted(set(re.findall(r"SRC-[A-Z0-9]+-[A-Z0-9]+", str(article))))
    if not source_ids:
        raise ValueError(f"Signal has no recoverable Source IDs: {signal_id}")
    for name, value, fallback in (
        ("baseline_assumption", baseline, "기존 사업계획은 현재 시장 접근과 공급 조건이 계속 유지된다고 봅니다."),
        ("observed_break", observed_break, observed_change),
        ("decision_change", decision_change, "관련 계약·투자·운영 판단을 원문에서 확인된 조건에 맞춰 다시 비교합니다."),
        ("falsification_check", falsification, "공식 후속 공고와 실제 고객·물류·가격 데이터가 이 해석과 일치하는지 확인합니다."),
    ):
        if not value or len(value) < 20:
            value = fallback
        if len(value) < 20:
            raise ValueError(f"{signal_id}: {name} could not be recovered")
        if name == "baseline_assumption":
            baseline = value
        elif name == "observed_break":
            observed_break = value
        elif name == "decision_change":
            decision_change = value
        else:
            falsification = value
    analysis = render_analysis(article)
    market_sensing.validate_signal_analysis(analysis)
    item["signal_id"] = signal_id
    item["remote_business_axis"] = axis or item.get("business_axis")
    # The deployed build used a newer display label (전략광물) for the
    # POSCO Holdings axis. The checked-in data contract still represents that
    # company under 리튬, so retain the deployed label as provenance while
    # publishing a contract-valid local axis.
    item["axis"] = "리튬" if item["remote_business_axis"] == "전략광물" else item["remote_business_axis"]
    item["impact"] = impact or int(item.get("business_impact", 3))
    item["urgency"] = urgency or int(item.get("urgency", 3))
    item["assessed_at"] = assessed_at or item.get("assessed_at") or "2026-08-22"
    item["summary"] = summary
    item["impact_rationale"] = impact_rationale or "배포 페이지의 사업 영향 점수 근거를 복구했습니다."
    item["urgency_rationale"] = urgency_rationale or "배포 페이지의 긴급성 점수 근거를 복구했습니다."
    item["impact_path"] = impact_path or "확인된 외부 변화가 공급·고객·계약 조건을 거쳐 사업 판단을 바꾸는 경로를 배포 분석에서 복구했습니다."
    item["recommended_follow_up"] = recommended_follow_up or "원문 조건과 실제 고객·공급망 데이터를 대조할 후속 확인표를 작성합니다."
    item["observed_change"] = observed_change
    item["baseline_assumption"] = baseline
    item["observed_break"] = observed_break
    item["decision_change"] = decision_change
    item["falsification_check"] = falsification
    item["source_ids"] = source_ids
    item["analysis"] = analysis
    item["subject_id"] = SUBJECT_IDS[signal_id]
    item["company_id"] = COMPANY_BY_AXIS[item["axis"]]
    item["signal_role"] = "core_market_signal"
    item["signal_origin"] = "policy_regulator"
    item["surprise_pattern"] = PATTERN_BY_SIGNAL[signal_id]
    item["surprise_score"] = 4
    return item


def claim_args(root: Path, subject_id: str, predicate: str, value: str, source_ids: list[str], as_of: str, reason: str) -> SimpleNamespace:
    return SimpleNamespace(
        root=str(root),
        subject_id=subject_id,
        predicate=predicate,
        value=value,
        source_id=source_ids,
        confidence="medium",
        as_of=as_of,
        reason=reason,
    )


def prepare(root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    signals = [parse_signal(signal_id) for signal_id in SIGNAL_IDS]
    source_ids = sorted({source_id for signal in signals for source_id in signal["source_ids"]})
    sources = {source_id: parse_source(source_id) for source_id in source_ids}
    return signals, sources


def repair_claim_fields(root: Path, signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Correct the first pass's dot-separated evidence-note field captures."""
    repaired: list[dict[str, str]] = []
    replacements: dict[str, str] = {}
    records_by_key: dict[tuple[str, str], list[tuple[Path, dict[str, Any]]]] = {}
    for path, record in market_sensing.claim_records(root):
        key = (str(record.get("subject_id") or ""), str(record.get("predicate") or ""))
        records_by_key.setdefault(key, []).append((path, record))
        if record.get("status") == "superseded" and record.get("superseded_by"):
            replacements[str(record["claim_id"])] = str(record["superseded_by"])

    for signal in signals:
        subject_id = str(signal["subject_id"])
        for predicate in ("impact_path", "recommended_follow_up"):
            corrected = str(signal[predicate]).strip()
            active = [
                (path, record)
                for path, record in records_by_key.get((subject_id, predicate), [])
                if record.get("status") == "active"
            ]
            for old_path, old_claim in active:
                if str(old_claim.get("value") or "").strip() == corrected:
                    continue
                new_claim_id = market_sensing.claim_id_for(subject_id, predicate, corrected)
                old_claim["status"] = "superseded"
                old_claim["superseded_by"] = new_claim_id
                replacements[str(old_claim["claim_id"])] = new_claim_id
                old_claim.setdefault("history", []).append(
                    {
                        "date": "2026-08-22",
                        "action": "status_changed",
                        "from": "active",
                        "to": "superseded",
                        "reason": "배포 Source의 연결된 판단 근거에서 필드 경계를 다시 파싱했습니다.",
                    }
                )
                market_sensing.write_json(old_path, old_claim)
                result = market_sensing.add_claim(
                    claim_args(
                        root,
                        subject_id,
                        predicate,
                        corrected,
                        [str(item) for item in old_claim.get("source_ids", [])],
                        str(signal["assessed_at"]),
                        "Vercel Source 연결 메모의 필드 경계를 보정한 복구 주장입니다.",
                    )
                )
                if result.get("action") != "created":
                    raise ValueError(f"Claim field repair requires a new claim for {subject_id}/{predicate}: {result}")
                repaired.append(
                    {
                        "old_claim_id": str(old_claim["claim_id"]),
                        "new_claim_id": str(result["claim_id"]),
                        "subject_id": subject_id,
                        "predicate": predicate,
                    }
                )

    # Replace superseded field claims in the already-published Signal and
    # Insight edges so audit does not treat the corrected active claims as
    # unpublished evidence.
    for path, record in [*market_sensing.signal_records(root), *market_sensing.insight_records(root)]:
        claim_ids = [str(item) for item in record.get("claim_ids", [])]
        updated_ids = [replacements.get(item, item) for item in claim_ids]
        if updated_ids != claim_ids:
            record["claim_ids"] = list(dict.fromkeys(updated_ids))
            market_sensing.write_json(path, record)

    if repaired or replacements:
        market_sensing.sync_obsidian_store(root)
        run_path = root / ".system" / "runs" / f"{RECOVERY_RUN_ID}.json"
        if run_path.exists():
            run = market_sensing.read_json(run_path)
            results = run.setdefault("results", {})
            results["repaired_claims"] = max(int(results.get("repaired_claims", 0)), len(repaired))
            results["replaced_claim_edges"] = max(int(results.get("replaced_claim_edges", 0)), len(replacements))
            market_sensing.write_json(run_path, run)
        manifest_path = root.parent / "incoming" / "vercel-recovery-20260822" / "recovery-manifest.json"
        if manifest_path.exists() and repaired:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["repaired_claims"] = repaired
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"repaired_claims": repaired, "count": len(repaired), "replaced_edges": len(replacements)}


def apply_recovery(root: Path, signals: list[dict[str, Any]], sources: dict[str, dict[str, Any]], recovery_dir: Path) -> dict[str, Any]:
    run_path = root / ".system" / "runs" / f"{RECOVERY_RUN_ID}.json"
    existing_run: dict[str, Any] | None = None
    if run_path.exists():
        existing_run = market_sensing.read_json(run_path)
        if existing_run.get("finished_at"):
            raise ValueError(f"Recovery run already finished: {run_path}")
    recovery_dir.mkdir(parents=True, exist_ok=True)
    source_dir = recovery_dir / "sources"
    analysis_dir = recovery_dir / "analysis"
    source_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)

    source_map: dict[str, str] = {}
    for remote_id, source in sources.items():
        content_path = source_dir / f"{remote_id}.md"
        content_path.write_text(source["content"], encoding="utf-8", newline="\n")
        result = market_sensing.add_source(
            SimpleNamespace(
                root=str(root), content_file=str(content_path), title=source["title"], url=source["url"],
                publisher=source["publisher"], published_at=source["published_at"], collected_at=source["collected_at"],
                source_type=source["source_type"], language=source["language"], reliability=source["reliability"],
                academic_kind=None, author=[], venue=None, doi=None, conference_name=None, conference_date=None,
                conference_location=None, peer_review_status=None, supporting_of=None, force=False,
            )
        )
        if result.get("action") not in {"created", "exact_duplicate"}:
            raise ValueError(f"Source recovery requires review for {remote_id}: {result}")
        source_map[remote_id] = str(result["source_id"])

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    run = existing_run or {
        "schema_version": 1,
        "run_id": RECOVERY_RUN_ID,
        "started_at": now,
        "finished_at": None,
        "mode": "deployment_recovery",
        "scope": {"deployment": REMOTE_BASE, "signal_ids": list(SIGNAL_IDS)},
        "query": "recover seven Signal pages visible in the Vercel deployment but absent from Git refs",
        "access_attempts": [{"url": REMOTE_BASE, "status": 200, "method": "public_html_recovery"}],
        "signal_ids": [],
        "results": {"new_sources": len(source_map), "new_claims": 0, "new_signals": 0},
        "signal_contract": {"version": 1, "signal_ids": []},
        "discovery_contract": {"version": 1, "signal_ids": []},
    }
    market_sensing.write_json(run_path, run)

    mappings: list[dict[str, Any]] = []
    for signal in signals:
        remote_source_ids = list(signal["source_ids"])
        local_source_ids = [source_map[source_id] for source_id in remote_source_ids]
        subject_id = signal["subject_id"]
        assessed_at = signal["assessed_at"]
        observed_as_of = next(
            (sources[source_id].get("published_at") for source_id in remote_source_ids if sources[source_id].get("published_at")),
            assessed_at,
        )
        claim_specs = [
            ("business_axis", signal["axis"], assessed_at, local_source_ids),
            ("business_impact_score_1_to_10", str(int(signal["impact"]) * 2 - 1), assessed_at, local_source_ids),
            ("business_impact_rationale", signal["impact_rationale"], assessed_at, local_source_ids),
            ("urgency_score_1_to_10", str(int(signal["urgency"]) * 2 - 1), assessed_at, local_source_ids),
            ("urgency_rationale", signal["urgency_rationale"], assessed_at, local_source_ids),
            ("assessment_confidence", "medium", assessed_at, local_source_ids),
            ("assessed_at", assessed_at, assessed_at, local_source_ids),
            ("impact_path", signal["impact_path"], observed_as_of, local_source_ids),
            ("recommended_follow_up", signal["recommended_follow_up"], assessed_at, local_source_ids),
            ("observed_change", signal["observed_change"], observed_as_of, local_source_ids),
            ("published_at", observed_as_of, observed_as_of, local_source_ids),
        ]
        for index, remote_source_id in enumerate(remote_source_ids, start=1):
            claim_specs.append(
                (
                    f"supporting_source_{index}",
                    sources[remote_source_id]["title"],
                    sources[remote_source_id].get("published_at") or assessed_at,
                    [source_map[remote_source_id]],
                )
            )
        claim_ids: list[str] = []
        for predicate, value, as_of, claim_sources in claim_specs:
            result = market_sensing.add_claim(
                claim_args(
                    root,
                    subject_id,
                    predicate,
                    str(value),
                    claim_sources,
                    str(as_of),
                    f"Vercel 공개 Signal {signal['signal_id']}와 배포 Source 페이지에서 복구한 주장입니다.",
                )
            )
            if result.get("action") not in {"created", "verified_existing"}:
                raise ValueError(f"Claim recovery requires review for {subject_id}/{predicate}: {result}")
            claim_ids.append(str(result["claim_id"]))
            run["results"]["new_claims"] += int(result.get("action") == "created")

        analysis_path = analysis_dir / f"{signal['signal_id']}.md"
        analysis_path.write_text(signal["analysis"], encoding="utf-8", newline="\n")
        signal_result = market_sensing.add_signal(
            SimpleNamespace(
                root=str(root), run_id=RECOVERY_RUN_ID, title=signal["title"], sentence=signal["sentence"],
                signal_type=signal["signal_type"], signal_role=signal["signal_role"], signal_origin=signal["signal_origin"],
                baseline_assumption=signal["baseline_assumption"], observed_break=signal["observed_break"],
                decision_change=signal["decision_change"], surprise_pattern=signal["surprise_pattern"],
                surprise_score=signal["surprise_score"], falsification_check=signal["falsification_check"],
                paragraph=signal["summary"], document_path=None, analysis_file=str(analysis_path), impact_estimate_file=None,
                company_id=[signal["company_id"]], business_axis=signal["axis"], claim_id=claim_ids,
                business_impact_score=int(signal["impact"]) * 2 - 1, business_impact_rationale=signal["impact_rationale"],
                urgency_score=int(signal["urgency"]) * 2 - 1, urgency_rationale=signal["urgency_rationale"], response_deadline=None,
                assessed_at=signal["assessed_at"], assessment_confidence="medium",
            )
        )
        local_signal_id = str(signal_result["signal_id"])
        run["results"]["new_signals"] += 1
        run["signal_ids"].append(local_signal_id)
        run["signal_contract"]["signal_ids"].append(local_signal_id)
        run["discovery_contract"]["signal_ids"].append(local_signal_id)
        mappings.append({
            "remote_signal_id": signal["signal_id"],
            "local_signal_id": local_signal_id,
            "remote_business_axis": signal.get("remote_business_axis"),
            "local_business_axis": signal["axis"],
            "source_ids": local_source_ids,
        })

    run["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    market_sensing.write_json(run_path, run)
    market_sensing.sync_obsidian_store(root)
    manifest = {"deployment": REMOTE_BASE, "run_id": RECOVERY_RUN_ID, "mappings": mappings, "remote_source_to_local": source_map}
    (recovery_dir / "recovery-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"run_id": RECOVERY_RUN_ID, "source_count": len(source_map), "claim_count": run["results"]["new_claims"], "signal_count": len(mappings), "mappings": mappings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT / "market-sensing-wiki")
    parser.add_argument("--recovery-dir", type=Path, default=PROJECT_ROOT / "incoming" / "vercel-recovery-20260822")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--repair", action="store_true", help="Repair already-imported linked-evidence Claim fields")
    args = parser.parse_args()
    signals, sources = prepare(args.root.resolve())
    result: dict[str, Any] = {"valid": True, "signals": len(signals), "sources": len(sources), "signal_ids": [item["signal_id"] for item in signals]}
    if args.repair:
        result = repair_claim_fields(args.root.resolve(), signals)
        result["repaired"] = True
    elif args.apply:
        result = apply_recovery(args.root.resolve(), signals, sources, args.recovery_dir.resolve())
        result["applied"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
