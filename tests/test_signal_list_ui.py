from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import market_sensing  # noqa: E402


def test_company_is_the_first_classification_pill() -> None:
    script = (
        PROJECT_ROOT / "market-sensing-wiki" / "javascripts" / "signal-list.js"
    ).read_text(encoding="utf-8")
    styles = (
        PROJECT_ROOT / "market-sensing-wiki" / "stylesheets" / "extra.css"
    ).read_text(encoding="utf-8")
    mkdocs_config = (PROJECT_ROOT / "tools" / "project" / "mkdocs.yml").read_text(
        encoding="utf-8"
    )

    assert '"회사, 사업축과 변화 유형"' in script
    assert script.index('"signal-pill signal-pill-company"') < script.index(
        '"signal-pill signal-pill-axis"'
    ) < script.index('"signal-pill signal-pill-type"')
    assert 'appendContextText(text, "회사"' not in script
    assert ".signal-pill-company" in styles
    assert "stylesheets/extra.css?v=20260830-lazy-signal-navigation" in mkdocs_config
    assert (
        "javascripts/signal-list.js?v=20260829-signal-combined-filter"
        in mkdocs_config
    )


def test_static_signal_fallback_keeps_all_classification_pills() -> None:
    signal = {
        "signal_id": "SIG-TEST",
        "insight_id": "INS-TEST",
        "company_ids": ["COM-POSCO-INTERNATIONAL"],
        "business_axis": "에너지",
        "signal_type": "경쟁사",
        "sentence": "사업 판단을 다시 확인해야 합니다.",
        "business_impact": {"score": 6},
        "urgency": {"score": 5},
        "assessed_at": "2026-08-29",
    }
    insight = {
        "title": "외부 변화",
        "summary": "요약",
        "analysis_markdown": "## 결론\n\n본문",
        "source_ids": [],
        "claim_ids": [],
    }
    settings = {"companies": ["POSCO INTERNATIONAL"]}

    pills = market_sensing.signal_classification_pills_markdown(signal, settings)
    assert pills.index("signal-pill-company") < pills.index(
        "signal-pill-axis"
    ) < pills.index("signal-pill-type")
    assert "POSCO International" in pills
    assert "에너지" in pills
    assert "경쟁사" in pills

    detail = "\n".join(
        market_sensing.signal_page_lines(signal, insight, {}, {}, settings)
    )
    assert detail.index("signal-pill-company") < detail.index("# 외부 변화")
    assert '.signal-static-pills aria-label="회사, 사업축과 변화 유형"' in detail
    assert "| 사업축 | 사업영향도" not in detail

    index = "\n".join(
        market_sensing.signal_index_lines([signal], {"INS-TEST": insight}, settings)
    )
    assert "회사·사업축·변화 유형" in index
    assert "signal-pill-company" in index


def test_combined_filter_keeps_sidebar_navigation_in_sync() -> None:
    script = (
        PROJECT_ROOT / "market-sensing-wiki" / "javascripts" / "signal-list.js"
    ).read_text(encoding="utf-8")

    assert "const updateSidebarSignalNavigation" in script
    assert '.md-sidebar--primary a[href*="signals/SIG-"]' in script
    assert "updateSidebarSignalNavigation(visible);" in script
    assert "updateSidebarSignalNavigation();" in script
    assert '"회사 필터"' in script
    assert '"사업축 필터"' in script
    assert "itemCompanies(item).includes(company)" in script
    assert "item.business_axis !== businessAxis" in script
    assert '["input", "change"]' in script
    assert 'const detectedAt = item.detected_at || "";' in script
    assert 'item.assessed_at || ""' not in script
    assert '"날짜 전체"' in script
    assert '"필터 초기화"' in script
