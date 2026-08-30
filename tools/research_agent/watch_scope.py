from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import market_sensing  # noqa: E402

from .service import COMPANY_AXES  # noqa: E402


MAX_COMPANY_AXES = 64
_PAIR_SEPARATOR = " | "
_SETTINGS_HEADINGS = {
    "focus": "분석 관점",
    "technologies": "우선 기술",
    "projects": "우선 프로젝트",
    "countries": "우선 국가",
    "priority_predicates": "중점 관찰 항목",
    "source_priority": "우선 출처 유형",
    "academic_scope": "학술 탐색 범위",
    "negative_signals": "리스크 신호",
    "report_sections": "보고서 중점",
}
_OPERATIONAL_LIMITS = {
    "search_overlap_days": (0, 365),
    "claim_stale_days": (1, 3650),
}


def _validate_pairs(raw_pairs: object, *, allow_empty: bool = False) -> list[dict[str, str]]:
    if not isinstance(raw_pairs, list):
        raise ValueError("company_axes는 회사와 사업축 객체의 배열이어야 합니다.")
    pairs: list[dict[str, str]] = []
    for item in raw_pairs:
        if not isinstance(item, dict):
            raise ValueError("각 관심 범위에 company와 business_axis를 입력해 주세요.")
        company = str(item.get("company") or "").strip()
        business_axis = str(item.get("business_axis") or "").strip()
        if not company or not business_axis:
            raise ValueError("회사와 사업축은 비워둘 수 없습니다.")
        if len(company) > 120 or len(business_axis) > 160:
            raise ValueError("회사명은 120자, 사업축은 160자 이하여야 합니다.")
        if any(value in company or value in business_axis for value in ("\r", "\n", "|")):
            raise ValueError("회사와 사업축에는 줄바꿈이나 | 문자를 사용할 수 없습니다.")
        pair = {"company": company, "business_axis": business_axis}
        if pair not in pairs:
            pairs.append(pair)
    if not pairs and not allow_empty:
        raise ValueError("관심 회사·사업축을 하나 이상 등록해 주세요.")
    if len(pairs) > MAX_COMPANY_AXES:
        raise ValueError(f"관심 회사·사업축은 최대 {MAX_COMPANY_AXES}개까지 등록할 수 있습니다.")
    return pairs


def _default_pairs(companies: list[str]) -> list[dict[str, str]]:
    return [
        {"company": company, "business_axis": COMPANY_AXES[company]}
        for company in companies
        if company in COMPANY_AXES
    ]


def get_watch_scope(wiki_root: Path) -> dict[str, Any]:
    settings = get_all_settings(wiki_root)
    raw_pairs = settings.get("company_axes")
    if isinstance(raw_pairs, list) and raw_pairs:
        pairs = (
            _validate_pairs(raw_pairs)
            if isinstance(raw_pairs[0], dict)
            else parse_company_axes(raw_pairs)
        )
    else:
        pairs = _default_pairs([str(item) for item in settings.get("companies", [])])
    return {
        "schema_version": 1,
        "company_axes": pairs,
        "companies": list(dict.fromkeys(pair["company"] for pair in pairs)),
        "count": len(pairs),
        "settings_updated_at": settings.get("settings_updated_at"),
    }


def get_all_settings(wiki_root: Path) -> dict[str, Any]:
    market_sensing.sync_settings_store(wiki_root)
    settings = dict(market_sensing.get_settings(wiki_root, "watchlist") or {})
    raw_pairs = settings.get("company_axes")
    pairs = parse_company_axes(raw_pairs) if isinstance(raw_pairs, list) else []
    if not pairs:
        pairs = _default_pairs([str(item) for item in settings.get("companies", [])])
    settings["company_axes"] = pairs
    settings["companies"] = list(dict.fromkeys(pair["company"] for pair in pairs))
    return settings


def patch_all_settings(wiki_root: Path, changes: dict[str, Any]) -> dict[str, Any]:
    if not changes:
        raise ValueError("변경할 설정을 하나 이상 입력해 주세요.")
    allowed = set(_SETTINGS_HEADINGS) | set(_OPERATIONAL_LIMITS) | {"company_axes"}
    unknown = sorted(set(changes) - allowed)
    if unknown:
        raise ValueError("지원하지 않는 설정입니다: " + ", ".join(unknown))
    settings_path = market_sensing.settings_path_for(wiki_root)
    if not settings_path.is_file():
        raise ValueError(f"설정 파일을 찾을 수 없습니다: {settings_path}")
    original_text = settings_path.read_text(encoding="utf-8")
    text = original_text

    if "company_axes" in changes:
        pairs = _validate_pairs(changes["company_axes"])
        companies = list(dict.fromkeys(pair["company"] for pair in pairs))
        text = _replace_markdown_section(text, "우선 기업", companies)
        text = _replace_markdown_section(
            text,
            "우선 회사·사업축",
            [f'{pair["company"]}{_PAIR_SEPARATOR}{pair["business_axis"]}' for pair in pairs],
            insert_after="우선 기업",
        )

    for key, heading in _SETTINGS_HEADINGS.items():
        if key not in changes:
            continue
        items = _validate_string_list(key, changes[key])
        text = _replace_markdown_section(text, heading, items)

    if any(key in changes for key in _OPERATIONAL_LIMITS):
        current = get_all_settings(wiki_root)
        values: dict[str, int] = {}
        for key, (minimum, maximum) in _OPERATIONAL_LIMITS.items():
            raw_value = changes.get(key, current.get(key))
            if isinstance(raw_value, bool) or not isinstance(raw_value, int):
                raise ValueError(f"{key}는 정수여야 합니다.")
            if not minimum <= raw_value <= maximum:
                raise ValueError(f"{key}는 {minimum}~{maximum} 범위여야 합니다.")
            values[key] = raw_value
        text = _replace_markdown_section(
            text,
            "운영 값",
            [
                f"검색 겹침 일수: {values['search_overlap_days']}",
                f"Claim 재검증 일수: {values['claim_stale_days']}",
            ],
            insert_after="보고서 중점",
        )

    market_sensing.atomic_write_text(settings_path, text)
    try:
        market_sensing.sync_settings_store(wiki_root)
    except Exception:
        market_sensing.atomic_write_text(settings_path, original_text)
        market_sensing.sync_settings_store(wiki_root)
        raise
    return get_all_settings(wiki_root)


def replace_watch_scope(wiki_root: Path, raw_pairs: object) -> dict[str, Any]:
    pairs = _validate_pairs(raw_pairs)
    patch_all_settings(wiki_root, {"company_axes": pairs})
    return get_watch_scope(wiki_root)


def add_watch_scope(wiki_root: Path, raw_pairs: object) -> dict[str, Any]:
    additions = _validate_pairs(raw_pairs)
    current = get_watch_scope(wiki_root)["company_axes"]
    return replace_watch_scope(wiki_root, [*current, *additions])


def remove_watch_scope(wiki_root: Path, raw_pairs: object) -> dict[str, Any]:
    removals = _validate_pairs(raw_pairs, allow_empty=True)
    current = get_watch_scope(wiki_root)["company_axes"]
    remaining = [pair for pair in current if pair not in removals]
    return replace_watch_scope(wiki_root, remaining)


def _replace_markdown_section(
    text: str,
    heading: str,
    items: list[str],
    *,
    insert_after: str | None = None,
) -> str:
    lines = text.splitlines()
    marker = f"## {heading}"
    try:
        start = lines.index(marker)
    except ValueError:
        if insert_after is None:
            raise ValueError(f"WIKI-SETTINGS.md에 '{heading}' 섹션이 없습니다.") from None
        after_marker = f"## {insert_after}"
        try:
            after_start = lines.index(after_marker)
        except ValueError:
            raise ValueError(f"WIKI-SETTINGS.md에 '{insert_after}' 섹션이 없습니다.") from None
        insert_at = next(
            (index for index in range(after_start + 1, len(lines)) if lines[index].startswith("## ")),
            len(lines),
        )
        block = [marker, "", *(f"- {item}" for item in items), ""]
        lines[insert_at:insert_at] = block
        return "\n".join(lines).rstrip() + "\n"

    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    lines[start + 1 : end] = ["", *(f"- {item}" for item in items), ""]
    return "\n".join(lines).rstrip() + "\n"


def parse_company_axes(values: object) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    pairs: list[dict[str, str]] = []
    for value in values:
        company, separator, business_axis = str(value).partition(_PAIR_SEPARATOR)
        if not separator:
            company, separator, business_axis = str(value).partition("|")
        if separator:
            pairs.append(
                {"company": company.strip(), "business_axis": business_axis.strip()}
            )
    return _validate_pairs(pairs, allow_empty=True)


def _validate_string_list(name: str, value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 200:
        raise ValueError(f"{name}은 최대 200개의 문자열 배열이어야 합니다.")
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text or len(text) > 2_000 or "\n" in text or "\r" in text:
            raise ValueError(f"{name} 항목은 1~2000자의 한 줄 문자열이어야 합니다.")
        if text not in result:
            result.append(text)
    return result
