"""MkDocs integration for the generated Obsidian-compatible wiki."""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path, PurePosixPath
from typing import Any


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
}


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


def _signal_ui_item(root: Path, signal_id: str) -> dict[str, Any] | None:
    signal_path = root / ".system" / "signals" / f"{signal_id}.json"
    if not signal_path.is_file():
        return None

    signal = _read_json(signal_path)
    insight_id = str(signal.get("insight_id") or "").strip()
    insight_path = root / ".system" / "insights" / f"{insight_id}.json"
    insight = _read_json(insight_path) if insight_id and insight_path.is_file() else {}
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
        "business_impact": (signal.get("business_impact") or {}).get("score"),
        "urgency": (signal.get("urgency") or {}).get("score"),
        "assessed_at": _display_text(signal.get("assessed_at")),
    }


def _signal_ui_payload(
    root: Path, src_path: str, source_markdown: str
) -> dict[str, Any] | None:
    normalized_path = src_path.replace("\\", "/")
    if normalized_path == "signals/index.md":
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


def on_page_markdown(
    markdown: str,
    page: Any,
    config: Any,
    files: Any,
) -> str:
    """Render links and attach Signal UI data without changing source Markdown."""
    rendered = convert_wikilinks(markdown, page.file.src_path)
    payload = _signal_ui_payload(
        Path(config["docs_dir"]), page.file.src_path, markdown
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
    """Build concise navigation from the generated knowledge pages."""
    root = Path(config["docs_dir"])
    nav: list[dict[str, Any]] = [{"홈": "index.md"}]

    warnings = _pages(root, "strategic-warnings/WRN-*.md")
    warning_index = root / "strategic-warnings" / "index.md"
    if warning_index.is_file():
        nav.append(
            {"핵심 전략 이슈": [{"전체 이슈": "strategic-warnings/index.md"}, *warnings]}
        )

    signals = _pages(root, "signals/SIG-*.md")
    signal_index = root / "signals" / "index.md"
    if signal_index.is_file():
        nav.append({"마켓 시그널": [{"전체 시그널": "signals/index.md"}, *signals]})

    recent_updates = root / "recent-updates.md"
    if recent_updates.is_file():
        nav.append({"최근 변화": "recent-updates.md"})

    trend_reports: list[dict[str, str]] = []
    report_index = root / "reports" / "index.md"
    if report_index.is_file():
        trend_reports.append({"동향 보고서 안내": "reports/index.md"})
    academic_landscape = root / "reports" / "academic-landscape-2026.md"
    if academic_landscape.is_file():
        trend_reports.append(
            {
                _report_nav_title(academic_landscape):
                academic_landscape.relative_to(root).as_posix()
            }
        )
    trend_reports.extend(_report_pages(root))
    if trend_reports:
        nav.append({"동향 보고서": trend_reports})

    nav.extend(
        [
            {"검토 대기": "REVIEW.md"},
        ]
    )
    config["nav"] = nav
    return config
