"""MkDocs integration for the generated Obsidian-compatible wiki."""

from __future__ import annotations

import json
import os
import posixpath
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Any

from mkdocs.structure.files import File


WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\]]+))?\]\]")
SIGNAL_WIKILINK_RE = re.compile(
    r"\[\[signals/(?P<signal_id>SIG-[A-Z0-9]+)(?:\|[^\]]+)?\]\]"
)
HALF_YEAR_REPORT_TITLE_RE = re.compile(
    r"^(?P<period>\d{4}년 [상하]반기) 철강 신기술·프로젝트 동향$"
)
COMPANY_DISPLAY_NAMES = {
    "COM-POSCO": "POSCO",
    "COM-POSCO-HOLDINGS": "POSCO Holdings",
    "COM-POSCO-INTERNATIONAL": "POSCO International",
    "COM-POSCO-ENC": "POSCO E&C",
    "COM-POSCO-FUTURE-M": "POSCO Future M",
    "COM-POSCO-FLOW": "POSCO Flow",
    "COM-POSCO-MOBILITY-SOLUTION": "POSCO Mobility Solution",
    "COM-POSCO-STEELEON": "POSCO Steeleon",
}

_MARKET_MODULE: Any | None = None


def _database_path(root: Path) -> Path:
    configured = os.environ.get("MYPIN_DATABASE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (root / "data" / "market_sensing.db").resolve()


def _wiki_root(config: Any) -> Path:
    """Return the canonical SQLite wiki root, separate from watched docs."""
    return (Path(__file__).resolve().parents[2] / "market-sensing-wiki").resolve()


def _read_only_connection(root: Path) -> sqlite3.Connection:
    database = _database_path(root)
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _market_module() -> Any:
    """Load the existing deterministic renderers without materializing files."""
    global _MARKET_MODULE
    if _MARKET_MODULE is not None:
        return _MARKET_MODULE
    project_root = Path(__file__).resolve().parents[2]
    scripts_dir = project_root / "skills" / "market-sensing-intelligence" / "scripts"
    scripts_text = str(scripts_dir)
    if scripts_text not in sys.path:
        sys.path.insert(0, scripts_text)
    import market_sensing  # type: ignore[import-not-found]

    _MARKET_MODULE = market_sensing
    return market_sensing


def _records_by_id(records: list[dict[str, Any]], id_field: str) -> dict[str, dict[str, Any]]:
    return {
        str(record.get(id_field)): record
        for record in records
        if str(record.get(id_field) or "").strip()
    }


def _projection_data(root: Path) -> dict[str, Any]:
    data: dict[str, Any] = {
        "settings": {},
        "sources": [],
        "claims": [],
        "signals": [],
        "insights": [],
        "pending_reviews": [],
    }
    artifacts: list[dict[str, Any]] = []
    database = _database_path(root)
    if database.is_file():
        with closing(_read_only_connection(root)) as connection:
            settings_row = connection.execute(
                "SELECT payload_json FROM wiki_settings WHERE settings_id='watchlist'"
            ).fetchone()
            if settings_row:
                data["settings"] = json.loads(settings_row["payload_json"])
            for row in connection.execute(
                "SELECT collection, payload_json FROM wiki_records ORDER BY collection, record_id"
            ):
                collection = str(row["collection"])
                target = "pending_reviews" if collection == "reviews_pending" else collection
                if target in data and isinstance(data[target], list):
                    data[target].append(json.loads(row["payload_json"]))
            for row in connection.execute(
                "SELECT artifact_id, artifact_type, title, markdown_text, html_text, "
                "metadata_json, created_at, updated_at FROM wiki_artifacts ORDER BY updated_at DESC"
            ):
                artifact = dict(row)
                artifact["metadata"] = json.loads(artifact.pop("metadata_json") or "{}")
                artifacts.append(artifact)
    data["artifacts"] = artifacts
    return data


def convert_wikilinks(markdown: str, current_src_path: str) -> str:
    """Convert vault-root Obsidian links to page-relative Markdown links."""
    normalized_current = current_src_path.replace("\\", "/")
    current_dir = PurePosixPath(normalized_current).parent.as_posix()
    if current_dir == ".":
        current_dir = ""

    def replace(match: re.Match[str]) -> str:
        raw_target = match.group(1).strip().replace("\\", "/")
        label = (match.group(2) or "").strip()
        target_path, separator, anchor = raw_target.partition("#")
        if target_path and not PurePosixPath(target_path).suffix:
            target_path += ".md"
        if target_path:
            href = posixpath.relpath(target_path, current_dir or ".")
        else:
            href = ""
        if separator:
            href += f"#{anchor}"
        if not label:
            label = PurePosixPath(target_path).stem or anchor
        return f"[{label}]({href})"

    return WIKILINK_RE.sub(replace, markdown)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _display_text(value: Any) -> str:
    if isinstance(value, list):
        return " · ".join(
            str(item).strip()
            for item in value
            if item is not None and str(item).strip()
        )
    return str(value or "").strip()


def _date_only(value: Any) -> str:
    """Return the calendar date from an ISO-like value without changing timezone."""
    text = _display_text(value)
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:$|[T ])", text)
    return match.group(1) if match else ""


def _signal_ui_item(root: Path, signal_id: str) -> dict[str, Any] | None:
    database = _database_path(root)
    if not database.is_file():
        return None
    with closing(_read_only_connection(root)) as connection:
        signal_row = connection.execute(
            "SELECT payload_json FROM wiki_records WHERE collection='signals' AND record_id=?",
            (signal_id,),
        ).fetchone()
        if signal_row is None:
            return None
        signal = json.loads(signal_row[0])
        insight_id = str(signal.get("insight_id") or "").strip()
        insight_row = connection.execute(
            "SELECT payload_json FROM wiki_records WHERE collection='insights' AND record_id=?",
            (insight_id,),
        ).fetchone()
    insight = json.loads(insight_row[0]) if insight_row else {}
    company_names = [
        COMPANY_DISPLAY_NAMES.get(
            str(company_id),
            str(company_id).removeprefix("COM-").replace("-", " "),
        )
        for company_id in signal.get("company_ids", [])
        if str(company_id).strip()
    ]
    region = next(
        (
            _display_text(record.get(field))
            for record in (signal, insight)
            for field in ("country_region", "region", "regions", "countries")
            if _display_text(record.get(field))
        ),
        "",
    )
    return {
        "title": _display_text(insight.get("title")),
        "sentence": _display_text(signal.get("sentence")),
        "company": " · ".join(company_names),
        "business_axis": _display_text(signal.get("business_axis")),
        "signal_type": _display_text(signal.get("signal_type")),
        "signal_role": _display_text(signal.get("signal_role")),
        "region": region,
        "business_impact": {
            "score": (signal.get("business_impact") or {}).get("score"),
            "rationale": _display_text(
                (signal.get("business_impact") or {}).get("rationale")
            ),
        },
        "urgency": {
            "score": (signal.get("urgency") or {}).get("score"),
            "rationale": _display_text((signal.get("urgency") or {}).get("rationale")),
        },
        "assessed_at": _display_text(signal.get("assessed_at")),
        # Detection means first registration in this system. Reassessment must
        # not make an older Signal look newly detected.
        "detected_at": _date_only(
            signal.get("created_at") or signal.get("assessed_at")
        ),
    }


def _home_markdown(data: dict[str, Any]) -> str:
    market = _market_module()
    settings = data["settings"]
    signals = sorted(
        data["signals"],
        key=lambda item: (
            int((item.get("business_impact") or {}).get("score") or 0)
            + int((item.get("urgency") or {}).get("score") or 0),
            str(item.get("assessed_at") or ""),
        ),
        reverse=True,
    )
    lines = [
        market.GENERATED_MARKER,
        "",
        "# 포스코그룹 마켓센싱",
        "",
        "철강·리튬·에너지 사업의 의사결정에 영향을 줄 외부 변화를 선별해 "
        "한 문장부터 원문까지 단계적으로 보여줍니다.",
        "",
        "## 지금 볼 시그널",
        "",
        "| 관심도 | 회사·사업축 | 핵심 변화 | 평가일 |",
        "| --- | --- | --- | --- |",
    ]
    for signal in signals[:5]:
        companies = ", ".join(
            market.subject_display_name(str(company_id), settings)
            for company_id in signal.get("company_ids", [])
        ) or "-"
        impact = (signal.get("business_impact") or {}).get("score", "-")
        urgency = (signal.get("urgency") or {}).get("score", "-")
        signal_path = Path("signals") / f"{signal.get('signal_id')}.md"
        lines.append(
            f"| 영향 **{impact}/{market.SIGNAL_SCORE_MAX}** · 긴급 **{urgency}/{market.SIGNAL_SCORE_MAX}** "
            f"| {market.markdown_cell(companies)}, {market.markdown_cell(signal.get('business_axis') or '-')} "
            f"| {market.wikilink(signal_path, str(signal.get('sentence') or '마켓 시그널'))} "
            f"| {market.markdown_cell(signal.get('assessed_at') or '-')} |"
        )
    if not signals:
        lines.append("| - | - | 현재 등록된 시그널이 없습니다. | - |")
    lines.extend(
        [
            "",
            "[[signals/index|전체 마켓 시그널 보기 →]]",
            "",
            '!!! info "판단 경계"',
            "",
            "    점수와 영향 경로는 공개 정보에 근거한 분석입니다. 회사 내부의 "
            "매출·원가·계약 정보가 확인되면 평가가 달라질 수 있습니다.",
            "",
            "## 운영 현황",
            "",
            '??? note "근거 저장 현황"',
            "",
            f"    **{len(signals)}개 시그널** · "
            f"**{len(data['sources'])}개 원문** · **{len(data['claims'])}개 검증 항목** · "
            f"[[REVIEW|사람 검토 대기]] **{len(data['pending_reviews'])}건**",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _review_markdown(data: dict[str, Any]) -> str:
    market = _market_module()
    reviews = data["pending_reviews"]
    lines = [
        market.GENERATED_MARKER,
        "",
        "# 검토 대기",
        "",
        f"미해결 검토: **{len(reviews)}건**",
        "",
    ]
    for review in reviews:
        lines.extend(
            [
                f"## {market.markdown_cell(review.get('review_id') or '검토 항목')}",
                "",
                f"- 유형: `{market.markdown_cell(review.get('type') or '-')}`",
                f"- 주체: {market.markdown_cell(review.get('subject_id') or '-')}",
                f"- 속성: `{market.markdown_cell(review.get('predicate') or '-')}`",
                "- 허용 결정: "
                + ", ".join(
                    f"`{market.markdown_cell(item)}`"
                    for item in review.get("allowed_decisions", [])
                ),
                "",
            ]
        )
    if not reviews:
        lines.append("- 검토 대기 항목이 없습니다.")
    return "\n".join(lines).rstrip() + "\n"


def _source_markdown(root: Path, source: dict[str, Any]) -> str:
    market = _market_module()
    source_id = str(source.get("source_id") or "")
    database = _database_path(root)
    content: bytes | str | None = None
    if database.is_file():
        with closing(_read_only_connection(root)) as connection:
            row = connection.execute(
                "SELECT content FROM wiki_source_contents WHERE source_id=?",
                (source_id,),
            ).fetchone()
            content = row["content"] if row else None
    if isinstance(content, bytes):
        raw_text = content.decode("utf-8", errors="replace")
    else:
        raw_text = str(content or "")
    lines = [
        market.GENERATED_MARKER,
        "",
        f"# {market.markdown_cell(source.get('title') or source_id or '보관 원문')}",
        "",
        f"- 발행자: {market.markdown_cell(source.get('publisher') or '-')}",
        f"- 발표일: {market.markdown_cell(source.get('published_at') or '-')}",
        f"- 수집일: {market.markdown_cell(source.get('collected_at') or '-')}",
    ]
    if source.get("url"):
        lines.append(f"- [공개 원문 열기]({source['url']})")
    lines.extend(["", "## 보관 원문", ""])
    # Archived source text is untrusted evidence, not page Markdown. An indented
    # code block preserves it verbatim and prevents accidental links/HTML from
    # becoming active in the reader surface.
    lines.extend(f"    {line}" for line in raw_text.splitlines())
    if not raw_text:
        lines.append("    보관된 원문 본문이 없습니다.")
    return "\n".join(lines).rstrip() + "\n"


def _recent_updates_markdown(data: dict[str, Any]) -> str:
    market = _market_module()
    settings = data["settings"]
    sources_by_id = _records_by_id(data["sources"], "source_id")
    signals = sorted(
        data["signals"], key=lambda item: str(item.get("assessed_at") or ""), reverse=True
    )
    lines = [
        market.GENERATED_MARKER,
        "",
        "# 최근 변화",
        "",
        "발행된 Signal을 평가일과 정보 발표일 기준으로 보여줍니다.",
        "",
        "| 평가일 | 정보 발표일 | 회사·사업축 | 변화 | 영향 | 긴급 |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for signal in signals:
        source_dates = sorted(
            str(sources_by_id.get(str(source_id), {}).get("published_at") or "")
            for source_id in signal.get("source_ids", [])
            if sources_by_id.get(str(source_id), {}).get("published_at")
        )
        companies = ", ".join(
            market.subject_display_name(str(company_id), settings)
            for company_id in signal.get("company_ids", [])
        ) or "-"
        signal_path = Path("signals") / f"{signal.get('signal_id')}.md"
        lines.append(
            f"| {market.markdown_cell(signal.get('assessed_at') or '-')} "
            f"| {market.markdown_cell(source_dates[-1] if source_dates else '게시일 미상')} "
            f"| {market.markdown_cell(companies)}, {market.markdown_cell(signal.get('business_axis') or '-')} "
            f"| {market.wikilink(signal_path, str(signal.get('sentence') or '마켓 시그널'))} "
            f"| **{market.markdown_cell((signal.get('business_impact') or {}).get('score', '-'))}/10** "
            f"| **{market.markdown_cell((signal.get('urgency') or {}).get('score', '-'))}/10** |"
        )
    if not signals:
        lines.append("| - | - | - | 아직 발행된 시그널이 없습니다. | - | - |")
    return "\n".join(lines).rstrip() + "\n"


def _research_markdown() -> str:
    return "\n".join(
        [
            "# AI 조사",
            "",
            "조사 범위와 실행 Provider를 정한 뒤 Deep Agent가 DuckDuckGo로 공개 원문을 찾아 분석합니다.",
            "",
            "화면이 준비되지 않으면 로컬 조사 서버가 실행 중인지 확인해 주세요.",
        ]
    ).rstrip() + "\n"


def _signal_ui_payload(
    root: Path, src_path: str, source_markdown: str
) -> dict[str, Any] | None:
    normalized_path = src_path.replace("\\", "/")
    if normalized_path in {"signals/index.md", "recent-updates.md"}:
        signal_ids = dict.fromkeys(
            match.group("signal_id")
            for match in SIGNAL_WIKILINK_RE.finditer(source_markdown)
        )
        items = [
            item
            for signal_id in signal_ids
            if (item := _signal_ui_item(root, signal_id)) is not None
        ]
        return {"kind": "index", "items": items}

    match = re.fullmatch(r"signals/(?P<signal_id>SIG-[A-Z0-9]+)\.md", normalized_path)
    if not match:
        return None
    item = _signal_ui_item(root, match.group("signal_id"))
    return {"kind": "detail", "item": item} if item else None


def _signal_ui_data_script(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    serialized = (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    kind = payload["kind"]
    return (
        # Material instant navigation executes inserted script nodes even when their
        # type is application/json. A template preserves inert JSON across both full
        # loads and instant navigation without producing a console SyntaxError.
        f'<template data-signal-ui="{kind}">'
        f"{serialized}</template>"
    )


def on_files(files: Any, config: Any) -> Any:
    """Expose SQLite records as in-memory MkDocs pages.

    The database remains the only persisted data source; no Markdown projection
    is written back into the repository.
    """
    root = _wiki_root(config)
    data = _projection_data(root)
    market = _market_module()
    sources_by_id = _records_by_id(data["sources"], "source_id")
    claims_by_id = _records_by_id(data["claims"], "claim_id")
    signals_by_id = _records_by_id(data["signals"], "signal_id")
    insights_by_id = _records_by_id(data["insights"], "insight_id")

    pages: dict[str, str] = {
        "index.md": _home_markdown(data),
        "REVIEW.md": _review_markdown(data),
        "recent-updates.md": _recent_updates_markdown(data),
        "research/index.md": _research_markdown(),
        "signals/index.md": "\n".join(
            market.signal_index_lines(data["signals"], insights_by_id, data["settings"])
        ).rstrip()
        + "\n",
    }

    for signal_id, signal in signals_by_id.items():
        insight = insights_by_id.get(str(signal.get("insight_id") or ""))
        if insight is None:
            continue
        pages[f"signals/{signal_id}.md"] = (
            "\n".join(
                market.signal_page_lines(signal, insight, claims_by_id, sources_by_id)
            ).rstrip()
            + "\n"
        )

    for source_id, source in sources_by_id.items():
        pages[f"sources/{source_id}.md"] = _source_markdown(root, source)

    report_links: list[tuple[str, str]] = []
    for artifact in data["artifacts"]:
        artifact_id = str(artifact.get("artifact_id") or "").replace("\\", "/")
        markdown = str(artifact.get("markdown_text") or "")
        if (
            not artifact_id.endswith(".md")
            or artifact_id.startswith("reports/audits/")
            or not markdown
        ):
            continue
        pages[artifact_id] = markdown.rstrip() + "\n"
        report_links.append((str(artifact.get("title") or Path(artifact_id).stem), artifact_id))
    report_lines = [
        market.GENERATED_MARKER,
        "",
        "# 동향 보고서",
        "",
        "SQLite에 보관된 공유용 보고서입니다.",
        "",
    ]
    report_lines.extend(
        f"- [{market.markdown_cell(title)}]({posixpath.relpath(path, 'reports')})"
        for title, path in report_links
    )
    if not report_links:
        report_lines.append("- 아직 발행된 상세 보고서가 없습니다.")
    pages["reports/index.md"] = "\n".join(report_lines).rstrip() + "\n"

    existing = {file.src_uri for file in files}
    for folder_name in ("assets", "javascripts", "stylesheets"):
        folder = root / folder_name
        if not folder.is_dir():
            continue
        for asset_path in folder.rglob("*"):
            if not asset_path.is_file():
                continue
            src_uri = asset_path.relative_to(root).as_posix()
            if src_uri in existing:
                continue
            files.append(
                File.generated(config, src_uri, abs_src_path=str(asset_path.resolve()))
            )
            existing.add(src_uri)
    for src_uri, content in pages.items():
        if src_uri in existing:
            continue
        files.append(File.generated(config, src_uri, content=content))
    return files


def on_page_markdown(
    markdown: str,
    page: Any,
    config: Any,
    files: Any,
) -> str:
    """Render links and attach Signal UI data without changing source Markdown."""
    rendered = convert_wikilinks(markdown, page.file.src_path)
    if page.file.src_path.replace("\\", "/") == "research/index.md":
        loading = (
            '<div data-research-agent-root aria-label="AI 조사 관리">'
            '<section class="research-panel research-loading-shell" aria-live="polite">'
            '<strong class="research-loading-title">조사 관리 화면 준비 중</strong>'
            '<p>조사 주제·회사·실행 주기 설정을 불러오고 있습니다.</p>'
            '</section></div>'
        )
        return loading + "\n\n" + rendered
    payload = _signal_ui_payload(
        _wiki_root(config), page.file.src_path, markdown
    )
    if payload is None:
        return rendered
    return f"{_signal_ui_data_script(payload)}\n\n{rendered}"


def _page_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return (
                line[2:]
                .strip()
                .removesuffix(" 기술 현황")
                .removesuffix(" 기업 현황")
            )
    return path.stem


def _report_nav_title(path: Path) -> str:
    title = _page_title(path)
    match = HALF_YEAR_REPORT_TITLE_RE.fullmatch(title)
    if match:
        return f"{match.group('period')} 동향"
    return title


def _report_date(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, separator, value = line.partition(":")
            if separator and key.strip() == "date":
                return value.strip().strip("\"'")
    return ""


def _report_pages(root: Path) -> list[dict[str, str]]:
    paths = sorted(
        root.glob("reports/briefs/*.md"),
        key=lambda path: (
            _report_date(path),
            _page_title(path).casefold(),
        ),
        reverse=True,
    )
    return [
        {_report_nav_title(path): path.relative_to(root).as_posix()}
        for path in paths
        if path.is_file()
    ]


def _pages(root: Path, pattern: str) -> list[dict[str, str]]:
    paths = sorted(root.glob(pattern), key=lambda path: _page_title(path).casefold())
    if pattern == "companies/*.md":
        paths.sort(
            key=lambda path: (
                not path.stem.endswith("POSCO"),
                _page_title(path).casefold(),
            )
        )
    return [
        {_page_title(path): path.relative_to(root).as_posix()}
        for path in paths
        if path.is_file()
    ]


def on_config(config: Any) -> Any:
    """Expose only the Market Signal collection in the reader navigation."""
    root = _wiki_root(config)
    data = _projection_data(root)
    insights_by_id = _records_by_id(data["insights"], "insight_id")

    signals = []
    for signal in data["signals"]:
        signal_id = str(signal.get("signal_id") or "").strip()
        if not signal_id:
            continue
        insight = insights_by_id.get(str(signal.get("insight_id") or ""), {})
        title = _display_text(insight.get("title") or signal.get("sentence")) or signal_id
        signals.append({title: f"signals/{signal_id}.md"})
    config["nav"] = [
        {"마켓 시그널": [{"전체 시그널": "signals/index.md"}, *signals]},
        {"AI 조사": "research/index.md"},
    ]
    return config
