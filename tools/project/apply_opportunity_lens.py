"""Backfill the balanced decision lens from reviewed scenario tables.

The script never edits Source, Claim, or archived raw evidence. Signal lenses are
derived from the first three-row scenario table already present in each governed
analysis. Strategic-issue lenses are curated because they combine several signals.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WIKI = PROJECT_ROOT / "market-sensing-wiki"
SIGNAL_SCHEMA_VERSION = 3
STRATEGIC_WATCH_SCHEMA_VERSION = 3

POSITIVE_TERMS = (
    "기회",
    "상방",
    "선점",
    "확대",
    "상승",
    "증가",
    "개선",
    "확보",
    "유지",
    "방어",
    "완화",
    "프리미엄",
    "가시성",
    "회복",
    "안정",
    "우위",
    "절감",
    "흑자",
)
NEGATIVE_TERMS = (
    "위험",
    "하방",
    "압박",
    "하락",
    "감소",
    "축소",
    "지연",
    "악화",
    "상실",
    "급등",
    "부족",
    "부담",
    "실패",
    "이탈",
    "손상",
    "불확실",
)

# Scenario labels describe the external market, so a superficially positive word
# can be adverse for POSCO (for example, pellet bottleneck relief can reduce the
# value of HyREX flexibility). These reviewed overrides preserve the company lens.
SIGNAL_ROW_OVERRIDES: dict[str, tuple[int, int]] = {
    "SIG-1BC42A78C68E": (1, 2),
    "SIG-4A25A18DCE47": (1, 0),
    "SIG-4FC6F602ABF5": (2, 1),
    "SIG-557B19547C16": (0, 2),
    "SIG-73C13A4E0FC9": (2, 0),
    "SIG-82BB8B02BF82": (2, 0),
    "SIG-87E7FDAE469F": (2, 0),
    "SIG-A4D20EDE549C": (2, 0),
    "SIG-C09FE799E568": (0, 2),
    "SIG-CC38306D8ADB": (2, 0),
    "SIG-E12E73720ED1": (0, 2),
    "SIG-F0DF50590831": (1, 2),
}

WARNING_LENSES: dict[str, dict[str, Any]] = {
    "WRN-ENERGY-EU-METHANE-COMPLIANCE": {
        "primary_direction": "mixed",
        "opportunity": {
            "condition": "생산지별 메탄 측정·보고·검증 자료와 계약상 감사권을 2027년 시행 전에 확보",
            "business_effect": "규제 적격 LNG를 유럽으로 전환 판매할 수 있는 선택권과 거래 가치를 경쟁사보다 먼저 확보",
            "action": "계약별 데이터 권리와 생산지 검증 수준을 등급화해 적격 물량을 장기 고객 협상에 우선 배치",
        },
        "risk": {
            "condition": "신규·갱신 계약에 검증요건이 엄격히 적용되지만 생산지 자료와 감사권이 계속 누락",
            "business_effect": "물리적으로 운송 가능한 LNG도 유럽 판매가 제한되고 할인 또는 대체조달 비용이 발생",
            "action": "증빙 공백 물량을 분리하고 계약 갱신 전에 데이터 조항·대체 생산지·판매처를 재협상",
        },
        "opportunity_cost": "규제 준비를 비용 대응으로만 보면 적격 물량의 희소가치와 유럽 판매선택권을 먼저 상품화할 시점을 놓칠 수 있습니다.",
        "decision_trigger": "계약별 검증자료와 감사권 확보율이 확인되면 적격 물량의 유럽 우선배치를 시작하고, 미확보 계약은 갱신 전에 대체안을 확정합니다.",
    },
    "WRN-LITHIUM-BLACK-MASS-FEEDSTOCK": {
        "primary_direction": "mixed",
        "opportunity": {
            "condition": "유럽 발생 원료에 대한 장기 소유권·최소물량·가격연동 조건을 중국행 물량 확대 전에 확보",
            "business_effect": "재활용 설비 가동률을 방어하면서 고품위 원료의 지역 간 가격차와 위탁처리 선택권을 활용",
            "action": "폐배터리 직접 회수 계약과 장기 원료계약을 처리능력 증설보다 먼저 확정",
        },
        "risk": {
            "condition": "중국의 실제 수입량과 가격 프리미엄이 늘지만 유럽 현지 원료계약이 단기 구매에 머묾",
            "business_effect": "원료 구매가격 상승과 가동률 하락이 겹쳐 재활용 회수마진과 투자 회수기간이 악화",
            "action": "중국행 통관량과 유럽 처리비를 월별 추적하고 최소물량 미달 시 증설 집행을 조정",
        },
        "opportunity_cost": "원료 이동을 위험으로만 보면 직접 회수망과 장기 소유권을 선점해 재활용 사업의 원료 기반을 넓힐 기회를 경쟁사에 내줄 수 있습니다.",
        "decision_trigger": "유럽산 블랙매스의 중국 통관량과 가격 프리미엄이 동시에 상승하면 장기 원료계약을 우선하고, 확보율이 낮으면 증설 속도를 낮춥니다.",
    },
    "WRN-LITHIUM-HYDROXIDE-MIX": {
        "primary_direction": "mixed",
        "opportunity": {
            "condition": "LFP 확대와 함께 탄산리튬 수요가 늘고 기존 설비·원료의 제품 전환 가능성이 확인",
            "business_effect": "총 리튬 수요 성장을 탄산·수산화 제품별 판매와 전환 서비스로 나눠 새로운 고객 수요를 확보",
            "action": "고객·지역·화학계별 장기수요를 다시 계산하고 전환투자와 계약 조건을 제품별로 설계",
        },
        "risk": {
            "condition": "북미까지 LFP 양산이 확대되지만 수산화리튬 중심 증설·판매계획이 그대로 유지",
            "business_effect": "수산화리튬 가동률과 가격 가산분이 낮아져 단일제품 증설의 회수기간이 길어짐",
            "action": "수산화리튬 증설의 단계 집행 기준과 탄산 전환 선택지를 경영안건으로 재심의",
        },
        "opportunity_cost": "제품 믹스 변화를 수요 하방으로만 보면 탄산리튬·LFP 고객 확대와 설비 전환능력을 새 수익원으로 만드는 기회를 놓칠 수 있습니다.",
        "decision_trigger": "고객별 LFP 양산 일정과 제품별 계약물량이 확인되면 전환투자를 시작하고, 수산화리튬 장기물량이 유지되면 기존 증설안을 보존합니다.",
    },
    "WRN-LITHIUM-SODIUM-ESS-SUBSTITUTION": {
        "primary_direction": "mixed",
        "opportunity": {
            "condition": "나트륨이온 납품이 고정형 ESS의 특정 용도·지역에 집중되고 리튬계 고성능 구간이 분리",
            "business_effect": "ESS를 단일 수요로 보지 않고 리튬이 우위를 유지하는 고객·성능 구간에 판매와 제품개발을 집중",
            "action": "응용처별 대체율과 성능 요구를 고객계약에 연결해 방어 가능한 리튬 수요를 선별",
        },
        "risk": {
            "condition": "60GWh 계약과 40GWh 증설이 일정대로 집행되고 해외 납품까지 확대",
            "business_effect": "ESS용 리튬 수요와 가격 상방이 줄어 증설·장기판매계약의 회수 가정이 약화",
            "action": "ESS 나트륨 전환율을 독립 변수로 반영해 증설과 장기계약 민감도를 재계산",
        },
        "opportunity_cost": "대체를 전체 리튬 수요 감소로만 읽으면 리튬이온이 우위를 유지하는 고성능 ESS 구간과 고객을 먼저 재정의할 기회를 잃을 수 있습니다.",
        "decision_trigger": "2026년 실제 납품량과 해외 고객 확대가 확인되면 ESS 대체율을 높이고, 특정 용도에 제한되면 리튬 우위 구간의 계약을 확대합니다.",
    },
    "WRN-STEEL-DRI-PELLET-BOTTLENECK": {
        "primary_direction": "opportunity",
        "opportunity": {
            "condition": "직접환원급 펠렛 부족과 가격 프리미엄이 지속되는 가운데 HyREX의 분광 사용 성능·품질·총원가가 상업 규모에서 입증",
            "business_effect": "원료 유연성이 저탄소 철강의 독립 경쟁우위가 되어 원료비 절감과 기술제휴·라이선스 선택권을 확대",
            "action": "광종별 실증 데이터를 공개 가능한 검증 패키지로 만들고 원료·기술을 묶은 제휴안을 설계",
        },
        "risk": {
            "condition": "고품위 펠렛 공급이 빠르게 늘거나 HyREX의 생산성·품질·총원가 검증이 지연",
            "business_effect": "원료 유연성의 차별가치가 줄고 실증·설비투자 회수와 기술제휴 일정이 늦어짐",
            "action": "수소·효율 중심 비교안을 병행하고 상업 검증 단계별 투자 중단 기준을 적용",
        },
        "opportunity_cost": "원료 병목을 조달 위험으로만 관리하면 분광 활용을 원가우위와 기술수출 자산으로 전환할 수 있는 선점 기회를 놓칠 수 있습니다.",
        "decision_trigger": "광종별 장기 연속운전에서 생산성·품질·총원가가 기준을 충족하면 제휴·라이선스 준비를 시작하고, 미달하면 실증 범위를 재설계합니다.",
    },
    "WRN-STEEL-EU-VOLUME-CARBON-MIX": {
        "primary_direction": "mixed",
        "opportunity": {
            "condition": "저탄소 조달기준이 실제 고객 구매와 가격 가산분으로 이어지고 검증 배출량이 경쟁재보다 우위",
            "business_effect": "희소한 수입쿼터를 고마진·저탄소 제품에 배분해 쿼터 1톤당 순이익과 장기계약 가치를 높임",
            "action": "고객별 순마진·탄소요건·구매의향을 결합한 쿼터 배분표로 물량을 선제 재배치",
        },
        "risk": {
            "condition": "쿼터는 조기 소진되지만 저탄소 기준 입법과 고객 가격 가산분이 지연",
            "business_effect": "수출 가능 물량과 단위이익이 함께 줄고 인증·탄소자료 비용만 먼저 발생",
            "action": "고객별 최소 수익성 기준을 적용하고 현지 생산·대체시장 전환 손익을 병행 비교",
        },
        "opportunity_cost": "쿼터 축소를 물량 방어로만 대응하면 저탄소 제품의 희소성과 고객별 가격 가산분을 이용해 수익구조를 바꿀 기회를 놓칠 수 있습니다.",
        "decision_trigger": "고객의 저탄소 구매의향과 가격 가산분이 인증비를 넘으면 우선배분을 시작하고, 입법 지연 시 순마진 중심 방어안으로 전환합니다.",
    },
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_cell(value: str) -> str:
    return re.sub(r"[*_`]", "", value).strip()


def scenario_rows(markdown: str) -> list[list[str]]:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if not (line.strip().startswith("|") and "시나리오" in line):
            continue
        rows: list[list[str]] = []
        for row_line in lines[index + 2 :]:
            if not row_line.strip().startswith("|"):
                break
            cells = [clean_cell(cell) for cell in row_line.strip().strip("|").split("|")]
            if len(cells) >= 4 and not all(re.fullmatch(r"[: -]+", cell or "-") for cell in cells):
                rows.append(cells[:4])
            if len(rows) == 3:
                return rows
    raise ValueError("analysis does not contain a three-row scenario table")


def term_score(row: list[str], terms: tuple[str, ...]) -> int:
    text = " ".join(row[:3])
    return sum(text.count(term) for term in terms)


def normalized_side(row: list[str]) -> dict[str, str]:
    return {
        "condition": f"관찰 기준은 ‘{row[1]}’입니다.",
        "business_effect": f"예상 사업 효과는 ‘{row[2]}’입니다.",
        "action": f"우선 행동은 ‘{row[3]}’입니다.",
    }


def signal_lens(signal_id: str, markdown: str) -> dict[str, Any]:
    rows = scenario_rows(markdown)
    override = SIGNAL_ROW_OVERRIDES.get(signal_id)
    if override:
        opportunity_row, risk_row = rows[override[0]], rows[override[1]]
    else:
        opportunity_row = max(rows, key=lambda row: term_score(row, POSITIVE_TERMS))
        risk_row = max(rows, key=lambda row: term_score(row, NEGATIVE_TERMS))
        if risk_row is opportunity_row:
            alternatives = [row for row in rows if row is not opportunity_row]
            risk_row = max(alternatives, key=lambda row: term_score(row, NEGATIVE_TERMS))
    opportunity = normalized_side(opportunity_row)
    risk = normalized_side(risk_row)
    return {
        "schema_version": 1,
        "primary_direction": "mixed",
        "opportunity": opportunity,
        "risk": risk,
        "opportunity_cost": (
            f"‘{opportunity_row[3]}’ 대응을 늦추면 ‘{opportunity_row[2]}’ 기회를 "
            f"놓치고, ‘{risk_row[2]}’ 상황이 현실화된 뒤에야 대응할 수 있습니다."
        ),
        "decision_trigger": (
            f"‘{opportunity_row[1]}’ 조건이 확인되면 기회 대응을 시작하고, "
            f"‘{risk_row[1]}’ 조건이 확인되면 방어 결정으로 전환합니다."
        ),
    }


def apply(wiki: Path) -> dict[str, int]:
    insights = {
        record["insight_id"]: record
        for path in sorted((wiki / ".system" / "insights").glob("*.json"))
        for record in [read_json(path)]
    }
    signal_count = 0
    for path in sorted((wiki / ".system" / "signals").glob("*.json")):
        signal = read_json(path)
        insight = insights[str(signal["insight_id"])]
        signal["schema_version"] = SIGNAL_SCHEMA_VERSION
        signal["decision_lens"] = signal_lens(
            str(signal["signal_id"]), str(insight["analysis_markdown"])
        )
        write_json(path, signal)
        signal_count += 1

    warning_count = 0
    for path in sorted((wiki / ".system" / "warnings").glob("*.json")):
        warning = read_json(path)
        warning_id = str(warning["warning_id"])
        if warning_id not in WARNING_LENSES:
            raise ValueError(f"missing curated warning lens: {warning_id}")
        warning["schema_version"] = STRATEGIC_WATCH_SCHEMA_VERSION
        warning["decision_lens"] = {
            "schema_version": 1,
            **WARNING_LENSES[warning_id],
        }
        write_json(path, warning)
        warning_count += 1

    for directory in ("trends", "theses"):
        for path in sorted((wiki / ".system" / directory).glob("*.json")):
            record = read_json(path)
            record["schema_version"] = STRATEGIC_WATCH_SCHEMA_VERSION
            write_json(path, record)

    return {"signals": signal_count, "strategic_issues": warning_count}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wiki", nargs="?", type=Path, default=DEFAULT_WIKI)
    args = parser.parse_args()
    result = apply(args.wiki.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
