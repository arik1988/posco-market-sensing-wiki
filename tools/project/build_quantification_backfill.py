from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "market-sensing-wiki" / ".system"
OUTPUT = ROOT / "tools" / "project" / "manifests" / "quantification-backfill-20260819.json"


def load_records(folder: str, key: str) -> dict[str, dict]:
    records = {}
    for path in sorted((STORE / folder).glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        records[value[key]] = value
    return records


signals = load_records("signals", "signal_id")
insights = load_records("insights", "insight_id")
claims = load_records("claims", "claim_id")


def source_for(signal_id: str, predicate: str) -> list[str]:
    insight = insights[signals[signal_id]["insight_id"]]
    for claim_id in insight["claim_ids"]:
        claim = claims[claim_id]
        if claim["predicate"] == predicate:
            return list(claim["source_ids"])
    raise ValueError(f"{signal_id} has no linked claim for {predicate}")


def variable(
    id_: str,
    label: str,
    unit: str,
    minimum: float,
    maximum: float,
    step: float,
    default: float,
    basis: str,
    *,
    kind: str = "assumption",
    source_ids: list[str] | None = None,
) -> dict:
    return {
        "id": id_,
        "label": label,
        "unit": unit,
        "min": minimum,
        "max": maximum,
        "step": step,
        "default": default,
        "kind": kind,
        "basis": basis,
        "source_ids": source_ids or [],
    }


def multiply(*args: dict | float) -> dict:
    return {"op": "multiply", "args": list(args)}


def divide(left: dict, right: float) -> dict:
    return {"op": "divide", "args": [left, right]}


def modeled(
    signal_id: str,
    title: str,
    description: str,
    variables: list[dict],
    output_label: str,
    output_unit: str,
    formula_display: str,
    *,
    scale: float = 1,
) -> dict:
    defaults = {item["id"]: item["default"] for item in variables}
    defense = {
        item["id"]: item["min"] + (item["default"] - item["min"]) * 0.35
        for item in variables
    }
    pressure = {
        item["id"]: item["default"] + (item["max"] - item["default"]) * 0.65
        for item in variables
    }
    expression = multiply(*({"var": item["id"]} for item in variables))
    if scale != 1:
        expression = divide(expression, scale)
    assessed_at = signals[signal_id]["assessed_at"]
    estimate = {
        "schema_version": 1,
        "title": title,
        "description": description,
        "as_of": assessed_at,
        "confidence": "low",
        "notice": (
            "공개자료와 넓은 AI 가정을 결합한 방향·민감도용 예비 계산입니다. "
            "POSCO의 실제 물량·가격·원가·계약조건 또는 공식 전망이 아니며 관련 Signal과 "
            "동일한 충격은 중복 합산하지 않습니다."
        ),
        "formula_display": formula_display,
        "variables": variables,
        "outputs": [
            {
                "id": "net_impact",
                "label": output_label,
                "unit": output_unit,
                "decimals": 1,
                "primary": True,
                "expression": expression,
            }
        ],
        "presets": [
            {"id": "defense", "label": "방어", "values": defense},
            {"id": "base", "label": "기준", "values": defaults},
            {"id": "pressure", "label": "압박", "values": pressure},
        ],
    }
    return {
        "schema_version": 1,
        "decision": "modeled",
        "assessed_at": assessed_at,
        "impact_estimate": estimate,
    }


def omitted(
    signal_id: str,
    reason_code: str,
    rationale: str,
    required_inputs: list[str],
    reconsider_when: str,
) -> dict:
    return {
        "schema_version": 1,
        "decision": "omitted",
        "assessed_at": signals[signal_id]["assessed_at"],
        "omission": {
            "reason_code": reason_code,
            "rationale": rationale,
            "required_inputs": required_inputs,
            "reconsider_when": reconsider_when,
        },
    }


decisions: dict[str, dict] = {}


def add_exposure_model(
    signal_id: str,
    title: str,
    description: str,
    output_label: str,
    output_unit: str,
    formula_display: str,
    variables: list[dict],
    *,
    scale: float = 1,
) -> None:
    decisions[signal_id] = modeled(
        signal_id,
        title,
        description,
        variables,
        output_label,
        output_unit,
        formula_display,
        scale=scale,
    )


add_exposure_model(
    "SIG-C09FE799E568",
    "나트륨이온 ESS의 리튬 매출 노출 민감도",
    "60GWh 계약이 리튬이온 ESS 수요를 대체하는 비율에 따른 리튬 매출 노출입니다.",
    "리튬 매출 노출",
    "USD m",
    "계약용량 × GWh당 LCE × 대체율 × 리튬가격 ÷ 1,000,000",
    [
        variable("capacity", "계약용량", "GWh", 10, 100, 5, 60, "3년 누적 공급계약", kind="verified", source_ids=source_for("SIG-C09FE799E568", "sodium_storage_contract_gwh")),
        variable("lce_intensity", "GWh당 탄산리튬환산량", "t LCE/GWh", 400, 900, 25, 700, "배터리 화학·에너지밀도 차이를 포함한 넓은 대용 범위"),
        variable("displacement", "리튬이온 대체율", "fraction", 0.1, 1, 0.05, 0.6, "계약 물량 중 기존 리튬이온 ESS를 실제 대체하는 비율"),
        variable("lithium_price", "리튬 가격", "USD/t LCE", 8000, 30000, 1000, 12000, "제품·지역별 가격차를 포함한 예비 가격 범위"),
    ],
    scale=1_000_000,
)

add_exposure_model(
    "SIG-5C3D01947FFB", "EU 철강 쿼터 초과 관세 노출", "EU 판매량과 쿼터 초과비중·가격 전가율에 따른 총 관세 노출입니다.", "순 관세 노출", "USD m", "EU 판매량 × 판매단가 × 초과관세율 × 미전가율",
    [variable("eu_volume", "EU 연간 판매량", "Mt", 0.1, 3, 0.1, 1, "POSCO 내부 고객별 물량으로 교체할 가정"), variable("steel_price", "평균 판매단가", "USD/t", 450, 1200, 25, 700, "제품 믹스를 포함한 넓은 가격 가정"), variable("duty_rate", "초과 관세율", "fraction", 0, 0.5, 0.05, 0.5, "확정된 초과 관세율", kind="verified", source_ids=source_for("SIG-5C3D01947FFB", "effective_date")), variable("unpassed_share", "가격 미전가율", "fraction", 0, 1, 0.05, 0.5, "고객 계약별 관세 전가 실패 비율")],
)

add_exposure_model(
    "SIG-A07F1B887CA2", "세계 과잉설비의 철강 EBITDA 압박", "과잉설비가 가격·마진을 낮출 때 POSCO 노출 물량에 미치는 연간 EBITDA 민감도입니다.", "연간 EBITDA 압박", "USD m", "영향 물량 × 판매단가 × 마진 하락률 × 실현율",
    [variable("volume", "영향 물량", "Mt", 2, 30, 1, 10, "가격 경쟁에 노출된 제품군 물량 가정"), variable("price", "평균 판매단가", "USD/t", 450, 1200, 25, 700, "제품 믹스 대용 가격"), variable("margin_erosion", "마진 하락률", "fraction", 0, 0.12, 0.005, 0.03, "과잉설비가 실제 마진으로 전이되는 범위"), variable("realization", "손익 실현율", "fraction", 0.2, 1, 0.05, 0.7, "계약·제품믹스·원가 대응 후 실현 비율")],
)

add_exposure_model(
    "SIG-1BC42A78C68E", "EU 메탄 검증의 LNG 마진 노출", "검증자료 미비로 EU 판매선택권이 제한될 때의 연간 LNG 마진 노출입니다.", "연간 EBITDA 노출", "USD m", "EU 연계 물량 × 단위마진 × 판매제한 비율 × 미완화율",
    [variable("volume", "EU 연계 LNG 물량", "Mt/년", 0.1, 5, 0.1, 1, "계약별 생산지·도착지 물량으로 교체할 가정"), variable("margin", "LNG 단위마진", "USD/t", 10, 150, 5, 60, "트레이딩·터미널 비용 전 단위마진 가정"), variable("restricted", "판매제한 비율", "fraction", 0, 1, 0.05, 0.2, "MRV·검증자료 미비로 영향받는 계약 비중"), variable("unmitigated", "미완화율", "fraction", 0, 1, 0.05, 0.5, "대체 판매처·데이터 보완 후 남는 비율")],
)

add_exposure_model(
    "SIG-73C13A4E0FC9", "DRI 원료 프리미엄의 제조원가 민감도", "고품위 펠렛 조달 프리미엄과 대체원료 사용률에 따른 연간 제조원가 노출입니다.", "연간 원료비 증가", "USD m", "DRI 생산량 × 원료투입계수 × 펠렛 프리미엄 × 미대체율",
    [variable("dri_output", "DRI 생산량", "Mt/년", 0.2, 8, 0.2, 2, "상업 규모 전환 시나리오 가정"), variable("ore_intensity", "원료투입계수", "t/t DRI", 1.2, 1.8, 0.05, 1.4, "수율·환원조건을 포함한 예비 원료계수"), variable("pellet_premium", "고품위 펠렛 프리미엄", "USD/t", 0, 100, 5, 30, "일반 철광석 대비 조달 프리미엄 가정"), variable("unsubstituted", "펠렛 미대체율", "fraction", 0, 1, 0.05, 0.7, "HyREX 원료 유연성으로 대체하지 못하는 비율")],
)

add_exposure_model(
    "SIG-87F0A3C81E23", "EU CBAM 순탄소비용 민감도", "검증 배출량·인증서 가격·고객 전가율에 따른 EU 판매의 연간 순탄소비용입니다.", "연간 순탄소비용", "EUR m", "EU 판매량 × 제품 배출집약도 × 인증서 가격 × 미전가율",
    [variable("volume", "EU 판매량", "Mt/년", 0.1, 3, 0.1, 1, "제품·고객별 실제 수출물량으로 교체할 가정"), variable("emissions", "제품 배출집약도", "tCO2/t", 0.2, 3, 0.1, 2, "검증 배출량이 없을 때의 넓은 공정별 범위"), variable("certificate_price", "인증서 가격", "EUR/tCO2", 20, 200, 5, 80, "EU ETS 경매가격 연동 범위", kind="derived", source_ids=source_for("SIG-87F0A3C81E23", "certificate_price_basis_2026")), variable("unpassed", "가격 미전가율", "fraction", 0, 1, 0.05, 0.5, "고객 계약에서 회수하지 못하는 비율")],
)

decisions["SIG-EEE1E86FA129"] = omitted("SIG-EEE1E86FA129", "non_financial_decision_signal", "2038년 발전 비중은 확인됐지만 포스코인터내셔널에 귀속되는 발전량·LNG 조달지분·계약마진이 없어 그룹 금액으로 환산하면 장기 계획 수치를 실제 사업권으로 오인하게 됩니다.", ["포스코인터내셔널 귀속 발전용량과 이용률", "LNG 조달지분·가격식·단위마진"], "열병합 용량시장 낙찰 결과와 회사 귀속 물량이 확인되면 금액 모델을 다시 작성합니다.")
decisions["SIG-01BC189FE839"] = omitted("SIG-01BC189FE839", "double_counting_risk", "Atlas 첫 생산의 물량·가동률 충격은 이미 Atlas 확장시설과 시운전 Signal의 현금흐름·EBITDA 모델에 포함돼 있어 별도 금액을 더하면 같은 생산능력을 중복계상합니다.", ["공통 충격 식별자와 대표 Signal", "Orora 계약의 독립 증분물량·단위마진"], "Orora 계약의 기존 모델과 겹치지 않는 증분물량과 가격식이 확인되면 별도 계산합니다.")

add_exposure_model(
    "SIG-A4D20EDE549C", "Rio Tinto 증산의 리튬 매출 압박", "경쟁사 공급 증가가 가격에 전이될 때 POSCO 리튬 판매량에 미치는 연간 매출 민감도입니다.", "연간 매출 압박", "USD m", "POSCO 노출물량 × 리튬가격 × 가격하락률 × 실현율 ÷ 1,000",
    [variable("volume", "POSCO 노출물량", "kt LCE/년", 5, 100, 5, 30, "경쟁 공급과 같은 시장에서 판매되는 물량 가정"), variable("price", "리튬 가격", "USD/t LCE", 8000, 30000, 1000, 12000, "제품별 가격 범위"), variable("price_effect", "증산발 가격하락률", "fraction", 0, 0.3, 0.01, 0.05, "경쟁사 증산이 가격에 전이되는 비율"), variable("realization", "손익 실현율", "fraction", 0.2, 1, 0.05, 0.7, "계약 시차와 제품 믹스 반영 비율")], scale=1000,
)

add_exposure_model(
    "SIG-B8FE09C65A92", "호주 남부 가스 부족의 Senex 마진 기회", "남부 부족물량과 가격 프리미엄 중 Senex가 실제 공급할 수 있는 비중에 따른 EBITDA 민감도입니다.", "연간 EBITDA 기회", "AUD m", "남부 부족량 × 가격 프리미엄 × 공급가능 비율 × 마진 실현율",
    [variable("shortfall", "남부 부족량", "PJ", 0, 60, 1, 40, "ACCC의 2025년 3분기 남부 부족 전망", kind="verified", source_ids=source_for("SIG-B8FE09C65A92", "q3_2025_southern_shortfall")), variable("premium", "부족 프리미엄", "AUD/GJ", 0, 12, 0.5, 4, "기준 계약가격 대비 계절 프리미엄 가정"), variable("deliverable_share", "Senex 공급가능 비율", "fraction", 0, 0.5, 0.05, 0.15, "파이프라인·계약·가동률 제약 후 공급 비율"), variable("margin_capture", "마진 실현율", "fraction", 0.2, 1, 0.05, 0.7, "운송비·로열티·계약제약 반영 비율")],
)

add_exposure_model(
    "SIG-CC38306D8ADB", "호르무즈 차질의 LNG 조달비용 노출", "해협 운송 차질로 발생하는 가격·운임 상승 중 포스코인터내셔널이 부담하는 연간 비용입니다.", "연간 조달비용 증가", "USD m", "영향 물량 × 단위 가격·운임 상승 × 노출 비율 × 미전가율",
    [variable("volume", "영향 LNG 물량", "Mt/년", 0.1, 5, 0.1, 1, "호르무즈 경유·대체조달 대상 물량 가정"), variable("uplift", "가격·운임 상승", "USD/t", 0, 300, 10, 100, "현물가격과 우회 운임을 합친 예비 범위"), variable("exposure", "차질 노출 비율", "fraction", 0, 1, 0.05, 0.4, "목적지 전환·재고로 상쇄되지 않는 비율"), variable("unpassed", "미전가율", "fraction", 0, 1, 0.05, 0.5, "고객·발전 계약에 전가하지 못하는 비율")],
)

add_exposure_model(
    "SIG-3F2A4F44D389", "리튬 가격 반등의 EBITDA 민감도", "리튬 가격 변화가 POSCO 판매물량과 계약 시차를 거쳐 EBITDA에 미치는 범위입니다.", "연간 EBITDA 변화", "USD m", "판매물량 × 리튬가격 × 가격변화율 × 손익 실현율 ÷ 1,000",
    [variable("volume", "판매물량", "kt LCE/년", 5, 100, 5, 30, "내부 제품별 판매물량으로 교체할 가정"), variable("price", "기준 리튬 가격", "USD/t LCE", 8000, 30000, 1000, 12000, "제품별 가격차를 포함한 범위"), variable("price_change", "가격 변화율", "fraction", -0.3, 0.5, 0.05, 0.2, "반등 지속성과 재하락을 함께 포함한 범위"), variable("flow_through", "손익 실현율", "fraction", 0.1, 1, 0.05, 0.5, "계약 시차·원가·제품 믹스 반영 비율")], scale=1000,
)

add_exposure_model(
    "SIG-934ECBF9D82E", "2029년 남부 가스 부족의 Senex 마진 민감도", "구조적 부족이 시작될 때 Senex 공급가능 물량과 가격 프리미엄에 따른 EBITDA 범위입니다.", "연간 EBITDA 기회", "AUD m", "공급가능 물량 × 가격 프리미엄 × 부족기 판매비율 × 마진 실현율",
    [variable("deliverable", "공급가능 물량", "PJ/년", 5, 80, 5, 30, "Atlas·Roma North의 계약 후 잔여 공급능력 가정"), variable("premium", "남부 가격 프리미엄", "AUD/GJ", 0, 12, 0.5, 4, "구조적 부족기의 기준가격 대비 프리미엄"), variable("shortage_sales", "부족기 판매비율", "fraction", 0, 1, 0.05, 0.5, "프리미엄 시장에 판매 가능한 비율"), variable("margin_capture", "마진 실현율", "fraction", 0.2, 1, 0.05, 0.7, "운송·로열티·계약비용 반영 비율")],
)

add_exposure_model(
    "SIG-F0DF50590831", "LNG 공급 증가의 트레이딩 마진 민감도", "2026년 공급 증가로 아시아 LNG 가격이 낮아질 때 순매수·순매도 포지션에 따른 마진 변화입니다.", "연간 트레이딩 마진 변화", "USD m", "거래물량 × 단위가격 변화 × 순노출 비율 × 마진 실현율",
    [variable("volume", "영향 거래물량", "Mt/년", 0.1, 5, 0.1, 1, "포스코인터내셔널의 순노출 거래물량 가정"), variable("price_change", "단위가격 하락", "USD/t", -100, 200, 10, 60, "공급 증가가 현물가격에 전이되는 범위"), variable("net_exposure", "순매도 노출 비율", "fraction", -1, 1, 0.1, 0.3, "순매수는 음수, 순매도는 양수로 입력"), variable("margin_capture", "마진 실현율", "fraction", 0.1, 1, 0.05, 0.6, "헤지·장기계약·운송비 반영 비율")],
)

add_exposure_model(
    "SIG-F6C60D414787", "중국 블랙매스 수입 재개의 원료비 노출", "중국 수입 재개가 블랙매스 프리미엄을 높일 때 POSCO 재활용 원료 조달비에 미치는 범위입니다.", "연간 원료비 증가", "USD m", "조달물량 × 프리미엄 상승 × 중국 경쟁노출 × 미완화율 ÷ 1,000",
    [variable("volume", "블랙매스 조달물량", "kt/년", 1, 100, 1, 20, "재활용 사업의 내부 원료조달량으로 교체할 가정"), variable("premium", "프리미엄 상승", "USD/t", 0, 2000, 50, 500, "중국 수입수요 재개에 따른 가격 상승 범위"), variable("china_exposure", "중국 경쟁노출", "fraction", 0, 1, 0.05, 0.6, "중국 구매자와 경쟁하는 원료 비율"), variable("unmitigated", "미완화율", "fraction", 0, 1, 0.05, 0.7, "장기계약·자체 회수망으로 상쇄하지 못하는 비율")], scale=1000,
)

add_exposure_model(
    "SIG-F062894EEB9A", "LFP 확산의 수산화리튬 매출 노출", "배터리 수요 중 LFP 전환이 수산화리튬 판매량과 가격에 미치는 연간 매출 민감도입니다.", "연간 수산화리튬 매출 노출", "USD m", "노출물량 × 제품가격 × LFP 전환율 × 미전환율 ÷ 1,000",
    [variable("volume", "수산화리튬 노출물량", "kt/년", 5, 100, 5, 30, "제품별 판매계획으로 교체할 가정"), variable("price", "수산화리튬 가격", "USD/t", 8000, 30000, 1000, 12000, "계약·지역별 가격 범위"), variable("lfp_shift", "LFP 전환율", "fraction", 0, 0.6, 0.05, 0.2, "기존 고니켈 수요가 LFP로 이동하는 비율"), variable("unmitigated", "제품전환 미완화율", "fraction", 0, 1, 0.05, 0.7, "탄산리튬 전환·신규 고객으로 상쇄하지 못하는 비율")], scale=1000,
)

decisions["SIG-E12E73720ED1"] = omitted("SIG-E12E73720ED1", "no_grounded_exposure_basis", "첫 흑자 여부와 하반기 원가 개선 방향만 공개됐고 영업이익 금액·판매량·제품가격·현금원가가 없어 넓은 범위조차 실제 사업규모와 무관한 숫자가 될 위험이 큽니다.", ["분기 판매량과 평균 판매가격", "현금원가와 감가상각 포함 영업이익"], "분기 영업이익 금액 또는 판매량·가격·현금원가 조합이 공개되면 즉시 재계산합니다.")


def q3_energy_packet() -> dict:
    signal_id = "SIG-B3D99438BE40"
    assessed_at = signals[signal_id]["assessed_at"]
    variables = [
        variable("senex_profit", "Senex 분기 영업이익", "억원", 0, 800, 10, 267, "2025년 3분기 영업이익", kind="verified", source_ids=source_for(signal_id, "senex_q3_2025_operating_profit")),
        variable("myanmar_profit", "미얀마 분기 영업이익", "억원", 0, 1600, 25, 900, "2025년 3분기 영업이익", kind="verified", source_ids=source_for(signal_id, "myanmar_q3_2025_operating_profit")),
        variable("senex_change", "Senex 이익 변화율", "fraction", -0.5, 1, 0.05, 0.2, "판매량·단가 변화 시나리오"),
        variable("myanmar_change", "미얀마 이익 변화율", "fraction", -0.8, 0.5, 0.05, -0.2, "회수비용·판매량 변화 시나리오"),
    ]
    estimate = {
        "schema_version": 1, "title": "Senex·미얀마 영업이익 변화 브리지", "description": "두 자산의 분기 영업이익 변화가 에너지부문에 미치는 순증감입니다.", "as_of": assessed_at, "confidence": "low",
        "notice": "공개된 분기 영업이익과 AI 변화율 가정을 결합한 예비 계산이며 POSCO 실제 전망이 아닙니다.", "formula_display": "Senex 영업이익 × 변화율 + 미얀마 영업이익 × 변화율", "variables": variables,
        "outputs": [{"id": "net_impact", "label": "분기 영업이익 순증감", "unit": "억원", "decimals": 0, "primary": True, "expression": {"op": "add", "args": [multiply({"var": "senex_profit"}, {"var": "senex_change"}), multiply({"var": "myanmar_profit"}, {"var": "myanmar_change"})]}}],
        "presets": [
            {"id": "defense", "label": "방어", "values": {"senex_profit": 267, "myanmar_profit": 900, "senex_change": 0.4, "myanmar_change": -0.1}},
            {"id": "base", "label": "기준", "values": {"senex_profit": 267, "myanmar_profit": 900, "senex_change": 0.2, "myanmar_change": -0.2}},
            {"id": "pressure", "label": "압박", "values": {"senex_profit": 267, "myanmar_profit": 900, "senex_change": 0, "myanmar_change": -0.5}},
        ],
    }
    return {"schema_version": 1, "decision": "modeled", "assessed_at": assessed_at, "impact_estimate": estimate}


decisions["SIG-B3D99438BE40"] = q3_energy_packet()
decisions["SIG-067F405D30C8"] = omitted("SIG-067F405D30C8", "double_counting_risk", "그룹 성장계획의 Senex 증산 방향은 확인되지만 독립 증분물량이 없고, 동일 생산능력은 Atlas 확장·가스 부족 Signal의 기존 EBITDA 모델에 이미 반영돼 별도 금액을 더하면 중복계상됩니다.", ["2026년 Senex 독립 증분 판매물량", "기존 모델과 구분되는 계약단가·가동률"], "2026년 가이던스에서 독립 증분물량과 단가가 제시되면 대표 모델과의 중복을 제거해 계산합니다.")

add_exposure_model(
    "SIG-8BDE11D3224E", "GM LFP 전환의 수산화리튬 매출 노출", "북미 LFP 양산이 고니켈 양극재용 수산화리튬 수요를 대체할 때의 연간 매출 민감도입니다.", "연간 수산화리튬 매출 노출", "USD m", "노출물량 × 제품가격 × 실제 LFP 전환율 × 미완화율 ÷ 1,000",
    [variable("volume", "GM 연계 수산화리튬 노출물량", "kt/년", 1, 50, 1, 10, "GM·공급망 계약의 내부 물량으로 교체할 가정"), variable("price", "수산화리튬 가격", "USD/t", 8000, 30000, 1000, 12000, "북미 계약가격 대용 범위"), variable("conversion", "LFP 실제 전환율", "fraction", 0, 1, 0.05, 0.7, "2027년 양산계획이 실제 판매로 전환되는 비율"), variable("unmitigated", "제품전환 미완화율", "fraction", 0, 1, 0.05, 0.6, "탄산리튬·다른 고객으로 상쇄하지 못하는 비율")], scale=1000,
)

add_exposure_model(
    "SIG-0B6C56D8B4D8", "호주 남부 기존 가스전 감소의 Senex 마진 민감도", "남부 생산감소가 가격 프리미엄으로 전이될 때 Senex 물량의 연간 EBITDA 기회입니다.", "연간 EBITDA 기회", "AUD m", "Senex 공급물량 × 가격 프리미엄 × 생산감소 전이율 × 마진 실현율",
    [variable("deliverable", "Senex 공급물량", "PJ/년", 5, 80, 5, 30, "계약 후 가격노출이 남은 공급물량 가정"), variable("premium", "가격 프리미엄", "AUD/GJ", 0, 12, 0.5, 4, "남부 공급감소가 만드는 기준가격 대비 프리미엄"), variable("decline_pass", "생산감소 전이율", "fraction", 0, 1, 0.05, 0.46, "향후 5년 기존 가스전 생산감소 전망", kind="derived", source_ids=source_for("SIG-0B6C56D8B4D8", "southern_legacy_gas_production_change")), variable("margin_capture", "마진 실현율", "fraction", 0.2, 1, 0.05, 0.7, "운송·로열티·계약제약 반영 비율")],
)

add_exposure_model(
    "SIG-C5958F0A0B3B", "2026년 호주 가스 부족의 Senex EBITDA 민감도", "단기 부족량과 가격 프리미엄 중 Senex가 공급할 수 있는 비중에 따른 EBITDA 범위입니다.", "연간 EBITDA 기회", "AUD m", "부족량 × 가격 프리미엄 × 공급가능 비율 × 마진 실현율",
    [variable("shortfall", "단기 부족량", "PJ", 0, 15, 0.5, 2, "공급범위 하단의 2PJ 부족", kind="derived", source_ids=source_for("SIG-C5958F0A0B3B", "q4_2025_supply_range")), variable("premium", "가격 프리미엄", "AUD/GJ", 0, 12, 0.5, 4, "생산자 제시가격 대비 부족 프리미엄 가정"), variable("deliverable_share", "Senex 공급가능 비율", "fraction", 0, 1, 0.05, 0.4, "계약·파이프라인 제약 후 공급 비율"), variable("margin_capture", "마진 실현율", "fraction", 0.2, 1, 0.05, 0.7, "운송·로열티·계약비용 반영 비율")],
)

decisions["SIG-EFB4A11676A9"] = omitted("SIG-EFB4A11676A9", "double_counting_risk", "이 Signal은 EU 쿼터 축소와 저탄소 조달기준을 하나의 의사결정으로 묶지만 금액 충격은 개별 EU 쿼터·CBAM Signal 모델에 이미 포함됩니다. 합산 모델을 별도로 만들면 같은 판매물량과 탄소비용을 중복계상합니다.", ["Signal 간 공통 EU 판매물량 식별자", "쿼터·CBAM·저탄소 프리미엄의 상호배타적 계산식"], "공통 판매물량을 한 번만 사용하는 포트폴리오 계산기가 연결되면 통합 순마진 모델로 재검토합니다.")


missing_without_model = {
    signal_id
    for signal_id, signal in signals.items()
    if insights[signal["insight_id"]].get("impact_estimate") is None
}
if set(decisions) != missing_without_model:
    missing = sorted(missing_without_model - set(decisions))
    extra = sorted(set(decisions) - missing_without_model)
    raise ValueError(f"decision coverage mismatch; missing={missing}, extra={extra}")

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(
    json.dumps({"schema_version": 1, "decisions": decisions}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(OUTPUT)
