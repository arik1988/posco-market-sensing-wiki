"""Self-contained HTML renderer for market-sensing-intelligence Markdown reports."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from sqlite_store import list_records


SOURCE_ID_RE = re.compile(r"\bSRC-\d{8}-[A-F0-9]{8,64}\b")
WIKILINK_RE = re.compile(r"\[\[([^]|]+)(?:\|([^]]+))?\]\]")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def safe_href(value: str) -> str | None:
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme and parts.scheme.lower() not in {"http", "https"}:
        return None
    if value.startswith(("//", "\\\\")):
        return None
    return value


def inline_markup(
    text: str, citation_numbers: dict[str, int] | None = None
) -> str:
    placeholders: list[str] = []

    def hold(value: str) -> str:
        token = f"\x00{len(placeholders)}\x00"
        placeholders.append(value)
        return token

    def replace_link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1), quote=False)
        href = safe_href(match.group(2))
        if href is None:
            return hold(label)
        source_match = SOURCE_ID_RE.search(href)
        if source_match and "/sources/" in href.replace("\\", "/"):
            source_id = source_match.group(0)
            anchor = (
                f"source-{citation_numbers[source_id]}"
                if citation_numbers and source_id in citation_numbers
                else f"src-{source_id}"
            )
            citation_label = (
                f"[{citation_numbers[source_id]}]"
                if citation_numbers and source_id in citation_numbers
                else label
            )
            return hold(
                f'<a class="citation" href="#{anchor}" '
                f'title="{html.escape(match.group(1), quote=True)}">'
                f"{citation_label}</a>"
            )
        escaped_href = html.escape(href, quote=True)
        external = urlsplit(href).scheme in {"http", "https"}
        attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
        return hold(f'<a href="{escaped_href}"{attrs}>{label}</a>')

    def replace_code(match: re.Match[str]) -> str:
        return hold(f"<code>{html.escape(match.group(1), quote=False)}</code>")

    def replace_wikilink(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        label = (match.group(2) or Path(target).name).strip()
        source_match = SOURCE_ID_RE.search(Path(target).name)
        if source_match:
            source_id = source_match.group(0)
            anchor = (
                f"source-{citation_numbers[source_id]}"
                if citation_numbers and source_id in citation_numbers
                else f"src-{source_id}"
            )
            citation_label = (
                f"[{citation_numbers[source_id]}]"
                if citation_numbers and source_id in citation_numbers
                else html.escape(label, quote=False)
            )
            return hold(
                f'<a class="citation" href="#{anchor}" '
                f'title="{html.escape(label, quote=True)}">{citation_label}</a>'
            )
        return hold(html.escape(label, quote=False))

    working = WIKILINK_RE.sub(replace_wikilink, text)
    working = MARKDOWN_LINK_RE.sub(replace_link, working)
    working = INLINE_CODE_RE.sub(replace_code, working)
    working = html.escape(working, quote=False)
    def replace_source_id(match: re.Match[str]) -> str:
        source_id = match.group(0)
        if citation_numbers and source_id in citation_numbers:
            number = citation_numbers[source_id]
            return f'<a class="citation" href="#source-{number}">[{number}]</a>'
        return f'<a class="citation" href="#src-{source_id}">{source_id}</a>'

    working = SOURCE_ID_RE.sub(replace_source_id, working)
    working = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", working)
    working = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", working)
    for index, value in enumerate(placeholders):
        working = working.replace(html.escape(f"\x00{index}\x00"), value)
    return working


def parse_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, markdown
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, "\n".join(lines[end + 1 :])


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def heading_anchor(text: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", "-", text.casefold()).strip("-")


def markdown_to_html(
    markdown: str, citation_numbers: dict[str, int] | None = None
) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    in_code = False
    code_lines: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            output.append(
                "<p>"
                + inline_markup(" ".join(paragraph), citation_numbers)
                + "</p>"
            )
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                output.append(
                    "<pre><code>"
                    + html.escape("\n".join(code_lines), quote=False)
                    + "</code></pre>"
                )
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue

        if (
            stripped.startswith("|")
            and index + 1 < len(lines)
            and is_table_separator(lines[index + 1])
        ):
            flush_paragraph()
            close_list()
            headers = split_table_row(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(split_table_row(lines[index]))
                index += 1
            output.append('<div class="table-wrap"><table><thead><tr>')
            output.extend(
                f"<th>{inline_markup(cell, citation_numbers)}</th>"
                for cell in headers
            )
            output.append("</tr></thead><tbody>")
            for row in rows:
                output.append("<tr>")
                padded = row + [""] * max(0, len(headers) - len(row))
                output.extend(
                    f"<td>{inline_markup(cell, citation_numbers)}</td>"
                    for cell in padded[: len(headers)]
                )
                output.append("</tr>")
            output.append("</tbody></table></div>")
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            text = heading.group(2)
            anchor = heading_anchor(text)
            output.append(
                f'<h{level} id="{html.escape(anchor, quote=True)}">'
                f"{inline_markup(text, citation_numbers)}</h{level}>"
            )
            index += 1
            continue

        unordered = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if unordered or ordered:
            flush_paragraph()
            desired = "ul" if unordered else "ol"
            if list_type != desired:
                close_list()
                output.append(f"<{desired}>")
                list_type = desired
            match = unordered or ordered
            assert match is not None
            output.append(
                f"<li>{inline_markup(match.group(1), citation_numbers)}</li>"
            )
            index += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            close_list()
            output.append(
                f"<blockquote>{inline_markup(stripped.lstrip('>').strip(), citation_numbers)}</blockquote>"
            )
            index += 1
            continue

        if not stripped:
            flush_paragraph()
            close_list()
        else:
            close_list()
            paragraph.append(stripped)
        index += 1

    if in_code:
        output.append(
            "<pre><code>"
            + html.escape("\n".join(code_lines), quote=False)
            + "</code></pre>"
        )
    flush_paragraph()
    close_list()
    return "\n".join(output)


def load_source_records(root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for _, record in list_records(root, "sources"):
        source_id = record.get("source_id")
        if isinstance(source_id, str):
            records[source_id] = record
    return records


def source_reference_html(
    source_ids: list[str],
    records: dict[str, dict[str, Any]],
    root: Path,
    output_path: Path,
    *,
    include_raw_links: bool = True,
) -> str:
    if not source_ids:
        return (
            '<section class="sources-section"><h2>출처</h2>'
            '<p class="empty-note">보고서에 연결된 출처가 없습니다.</p></section>'
        )
    cards: list[str] = []
    for number, source_id in enumerate(source_ids, 1):
        record = records.get(source_id)
        if record is None:
            cards.append(
                f'<article class="source-card missing" id="source-{number}">'
                f'<span class="source-number">{number:02d}</span>'
                f"<div><h3>{html.escape(source_id)}</h3>"
                "<p>출처 레코드를 찾을 수 없습니다.</p></div></article>"
            )
            continue
        title = html.escape(str(record.get("title") or source_id), quote=False)
        publisher = html.escape(str(record.get("publisher") or "Unknown"), quote=False)
        published = html.escape(
            str(record.get("published_at") or "게시일 미상"), quote=False
        )
        source_type = html.escape(
            str(record.get("source_type") or "other"), quote=False
        )
        reliability = html.escape(
            str(record.get("reliability") or "unknown"), quote=False
        )
        links: list[str] = []
        url = record.get("url")
        if isinstance(url, str) and safe_href(url):
            links.append(
                f'<a href="{html.escape(url, quote=True)}" target="_blank" '
                'rel="noopener noreferrer">원문 웹페이지</a>'
            )
        if include_raw_links and record.get("raw_ref"):
            links.append('<span title="SQLite에 보관됨">보관 원문 · DB</span>')
        card_links = " · ".join(links) if links else "연결 가능한 URL 없음"
        cards.append(
            f'<article class="source-card" id="source-{number}">'
            f'<span class="source-number">{number:02d}</span><div>'
            f"<h3>{title}</h3>"
            f'<p class="source-meta">{publisher} · {published} · {source_type} · '
            f"신뢰도 {reliability}</p>"
            f'<p class="source-links">{card_links}</p>'
            "</div></article>"
        )
    return (
        '<section class="sources-section"><h2>출처</h2>'
        '<p class="section-lead">본문에 인용된 자료의 발행 정보와 원문 연결입니다.</p>'
        '<div class="source-list">'
        + "".join(cards)
        + "</div></section>"
    )


REPORT_CSS = """
:root {
  --ink: #17202b;
  --muted: #647181;
  --line: #d9e0e6;
  --paper: #ffffff;
  --canvas: #f4f6f8;
  --navy: #122232;
  --navy-2: #1b3449;
  --blue: #05507D;
  --green: #2F7D68;
  --amber: #b97717;
  --red: #b33a3a;
}
* { box-sizing: border-box; }
html { background: var(--canvas); color: var(--ink); scroll-behavior: smooth; }
body {
  margin: 0;
  font-family: "Segoe UI", "Noto Sans KR", Arial, sans-serif;
  font-size: 15px;
  line-height: 1.65;
}
.report-shell {
  width: min(1120px, calc(100% - 32px));
  margin: 24px auto 48px;
  background: var(--paper);
  box-shadow: 0 12px 36px rgba(24, 39, 54, .12);
}
.report-header {
  padding: 38px 48px 34px;
  color: #f8fbfd;
  background: linear-gradient(135deg, var(--navy), var(--navy-2));
  border-bottom: 5px solid var(--blue);
}
.eyebrow {
  margin: 0 0 10px;
  color: #9ecde7;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.report-header h1 {
  margin: 0;
  max-width: 850px;
  color: #fff;
  font-size: clamp(30px, 4.6vw, 48px);
  line-height: 1.14;
  letter-spacing: -.035em;
}
.metadata {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 24px;
}
.meta-chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border: 1px solid rgba(255,255,255,.22);
  border-radius: 4px;
  color: #eaf4fa;
  background: rgba(255,255,255,.07);
  font-size: 14px;
}
.report-body { padding: 38px 48px 48px; }
.report-content > h1:first-child { display: none; }
h2 {
  margin: 38px 0 14px;
  padding-top: 10px;
  border-top: 2px solid var(--ink);
  color: var(--ink);
  font-size: 23px;
  line-height: 1.25;
}
h3 { margin: 26px 0 10px; color: #27394a; font-size: 18px; }
h4 { margin: 22px 0 8px; color: #405466; font-size: 15px; }
p { margin: 10px 0 16px; }
ul, ol { margin: 10px 0 20px; padding-left: 24px; }
li { margin: 5px 0; }
a { color: #16658f; text-decoration-thickness: 1px; text-underline-offset: 2px; }
code {
  padding: 2px 5px;
  border: 1px solid #d9e1e7;
  border-radius: 3px;
  background: #f3f6f8;
  font-family: Consolas, "Cascadia Mono", monospace;
  font-size: 14px;
}
pre {
  overflow-x: auto;
  padding: 16px;
  border-radius: 4px;
  color: #ecf4f8;
  background: #172633;
}
pre code { padding: 0; border: 0; color: inherit; background: transparent; }
blockquote {
  margin: 18px 0;
  padding: 13px 16px;
  border-left: 4px solid var(--blue);
  color: #35495a;
  background: #f3f7fa;
}
.table-wrap {
  overflow-x: auto;
  margin: 18px 0 26px;
  border: 1px solid var(--line);
}
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th {
  padding: 10px 12px;
  color: #f8fbfd;
  background: #263b4d;
  text-align: left;
  vertical-align: bottom;
}
td {
  padding: 10px 12px;
  border-top: 1px solid var(--line);
  vertical-align: top;
}
tbody tr:nth-child(even) { background: #f7f9fb; }
.citation {
  display: inline;
  color: #14668f;
  font-size: 14px;
  font-weight: 650;
}
.sources-section {
  margin-top: 46px;
  padding-top: 8px;
  border-top: 3px solid var(--ink);
}
.section-lead, .empty-note { color: var(--muted); }
.sources-section .section-lead { margin-bottom: 12px; }
.source-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.source-card {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-left: 3px solid var(--green);
  background: #ffffff;
  break-inside: avoid;
}
.source-card > div { min-width: 0; }
.source-card.missing { border-left-color: var(--red); }
.source-card:target {
  border-color: var(--blue);
  border-left-color: var(--blue);
  background: #f0f7fb;
  box-shadow: 0 0 0 3px rgba(5,80,125,.14);
}
.source-number {
  color: var(--muted);
  font-family: Consolas, monospace;
  font-size: 14px;
}
.source-card h3 {
  margin: 0 0 3px;
  font-size: 15px;
  line-height: 1.35;
}
.source-meta, .source-links {
  margin: 2px 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.4;
}
.report-footer {
  padding: 16px 48px;
  color: #d6e1e8;
  background: var(--navy);
  font-size: 14px;
}
@media (max-width: 720px) {
  .report-shell { width: 100%; margin: 0; box-shadow: none; }
  .report-header, .report-body { padding-left: 22px; padding-right: 22px; }
  .report-header { padding-top: 28px; }
  .source-list { grid-template-columns: 1fr; }
  table { font-size: 14px; }
}
@media print {
  @page { size: A4; margin: 13mm; }
  html, body { background: #fff; }
  body { font-size: 10.5pt; }
  .report-shell { width: 100%; margin: 0; box-shadow: none; }
  .report-header { padding: 22px 28px; background: #172b3d !important; }
  .report-header h1 { font-size: 26pt; }
  .report-body { padding: 22px 28px; }
  .report-footer { padding: 10px 28px; }
  a { color: inherit; }
  h2, h3, .source-card, table { break-inside: avoid; }
}
"""


def render_report_html(
    root: Path,
    markdown_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    root = root.resolve()
    markdown_path = markdown_path.resolve()
    output_path = output_path.resolve()
    markdown = markdown_path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(markdown)
    body = re.sub(r"<!--.*?-->\s*", "", body, flags=re.DOTALL)
    first_heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = metadata.get("title") or (
        first_heading.group(1) if first_heading else markdown_path.stem
    )
    source_ids = list(dict.fromkeys(SOURCE_ID_RE.findall(body)))
    citation_numbers = {
        source_id: index for index, source_id in enumerate(source_ids, 1)
    }
    records = load_source_records(root)
    source_html = source_reference_html(
        source_ids,
        records,
        root,
        output_path,
        include_raw_links=True,
    )
    meta_values = [
        ("보고일", metadata.get("date")),
        ("기준일", metadata.get("since")),
        ("인용 출처", f"{len(source_ids)}개"),
    ]
    chips = "".join(
        f'<span class="meta-chip">{html.escape(label)} · '
        f"{html.escape(str(value))}</span>"
        for label, value in meta_values
        if value
    )
    document = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title, quote=False)}</title>
  <style>{REPORT_CSS}</style>
</head>
<body>
  <main class="report-shell">
    <header class="report-header">
      <p class="eyebrow">Steel Technology Intelligence</p>
      <h1>{html.escape(title, quote=False)}</h1>
      <div class="metadata">{chips}</div>
    </header>
    <div class="report-body">
      <article class="report-content">
{markdown_to_html(body, citation_numbers)}
      </article>
      {source_html}
    </div>
    <footer class="report-footer">
      Markdown 원본: {html.escape(markdown_path.name)} · 생성일: {html.escape(metadata.get("date") or "")}
    </footer>
  </main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8", newline="\n")
    return {
        "output": str(output_path),
        "source_count": len(source_ids),
        "missing_source_ids": [
            source_id for source_id in source_ids if source_id not in records
        ],
    }
