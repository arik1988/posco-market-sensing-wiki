from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    PROJECT_ROOT
    / "skills"
    / "market-sensing-intelligence"
    / "scripts"
    / "market_sensing.py"
)
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("market_sensing", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {MODULE_PATH}")
market_sensing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(market_sensing)


RECOMMENDATION_REWRITES = {
    "WRN-LITHIUM-HYDROXIDE-MIX": (
        "제품 믹스 판단의 출발점은 총 리튬 수요가 아니라 고객·지역·차종별 배터리 "
        "화학계입니다. 확정계약, 고객 양산일정과 현지 조달요건을 가중해 탄산리튬과 "
        "수산화리튬 수요를 방어·기준·상방으로 나누고, 각 경우의 설비 가동률과 가격 "
        "프리미엄을 함께 봐야 합니다. 설비별 전환 가능량·기간·변동비·품질인증·장기계약 "
        "제약을 확인한 뒤 신규 증설의 게이트를 수산화리튬 확정 수요와 최소 가동률로 "
        "바꾸는 것이 핵심입니다. 기존 계획과 새 제품 믹스 계획의 EBITDA·현금흐름 차이가 "
        "확인돼야 증설·전환·유지 중 하나를 선택할 수 있습니다."
    ),
    "WRN-RARE-EARTH-CONTROL-OPTION": (
        "11월 공고 전에는 확정매입보다 철회 가능한 구매권·소수지분·단계투자를 우선하는 "
        "것이 타당합니다. 그 판단은 4월 유지품목과 10월 중단품목을 고객 제품별로 나눈 "
        "재고·대체 가능성, 후보사업의 고객 최소구매·가격공식·정책금융·허용국가·지배구조 "
        "제한을 같은 기준으로 비교한 뒤 내려야 합니다. 통제 재개와 고객계약이 함께 "
        "확인될 때만 확정투자로 넘어가고, 둘 중 하나가 약하면 옵션과 조달계약을 유지합니다. "
        "공고 후에는 이미 합의한 전환 규칙과 승인절차로 품목별 투자·조달안을 즉시 다시 "
        "판단할 수 있어야 합니다."
    ),
    "WRN-STRATEGIC-MINERALS-MARKET-DESIGN": (
        "전략광물 진입의 순서는 광종 선택보다 수요·정책·철회조건의 결합이 먼저입니다. "
        "후보광종별 장기 수요와 최소구매 의향을 확인하고, G7·EU·호주 지원이 발표인지 "
        "실제 조건서·계약 단계인지 구분해 적격비용·판매처·지배구조 제한을 비교해야 합니다. "
        "구매권·소수지분·단계투자의 철회비용까지 넣은 하방 NPV와 최소구매 커버리지가 내부 "
        "기준을 넘을 때만 확정투자로 전환합니다. 첫 계약을 뒤따라가는 방식보다 공통 계약 "
        "템플릿을 먼저 준비해 고객과 정부를 동시에 협상하는 편이 선택권을 지키는 데 "
        "유리합니다."
    ),
}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path}")
    return value


def unique_text(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def evidence_source_ids(trend: dict[str, Any], warning: dict[str, Any]) -> list[str]:
    timeline_sources = [
        source_id
        for item in warning.get("timeline", [])
        for source_id in item.get("source_ids", [])
    ]
    company_sources = (warning.get("company_lens") or {}).get("evidence_source_ids", [])
    return unique_text(
        list(trend.get("supporting_source_ids", []))
        + list(trend.get("counter_source_ids", []))
        + timeline_sources
        + list(company_sources)
    )


def key_numbers(
    trend: dict[str, Any], warning: dict[str, Any]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for indicator in trend.get("indicators", []):
        if not isinstance(indicator, dict):
            continue
        current = str(indicator.get("current") or "").strip()
        unit = str(indicator.get("unit") or "").strip()
        value = " ".join(part for part in (current, unit) if part)
        source_ids = unique_text(list(indicator.get("source_ids", [])))
        if value and source_ids:
            items.append(
                {
                    "value": value,
                    "label": str(indicator.get("label") or "핵심 지표"),
                    "meaning": str(
                        indicator.get("interpretation") or "현재 판단의 기준값"
                    ),
                    "source_ids": source_ids,
                }
            )
        if len(items) == 3:
            return items

    for timeline_item in reversed(list(warning.get("timeline", []))):
        if not isinstance(timeline_item, dict):
            continue
        source_ids = unique_text(list(timeline_item.get("source_ids", [])))
        date_label = str(timeline_item.get("date_label") or "").strip()
        if not date_label or not source_ids:
            continue
        items.append(
            {
                "value": date_label,
                "label": "공식 확인선" if not items else "변화 시점",
                "meaning": str(timeline_item.get("label") or "결론을 갱신할 시점"),
                "source_ids": source_ids,
            }
        )
        if len(items) == 3:
            break
    if not items:
        raise ValueError(f"{warning.get('warning_id')}: no source-backed key number")
    return items


def three_rows(values: list[str], fallback: str) -> list[str]:
    rows = unique_text(values)
    while len(rows) < 3:
        rows.append(fallback)
    return rows[:3]


def build_editorial_plan(
    trend: dict[str, Any], thesis: dict[str, Any], warning: dict[str, Any]
) -> dict[str, Any]:
    sources = evidence_source_ids(trend, warning)
    if not sources:
        raise ValueError(f"{warning.get('warning_id')}: no evidence sources")

    actions = three_rows(
        [str(item) for item in warning.get("actions", [])],
        str(warning.get("next_milestone") or "다음 공식 분기점을 확인합니다."),
    )
    escalation = three_rows(
        [str(item) for item in warning.get("escalation_rules", [])],
        str(warning.get("next_milestone") or "다음 공식 분기점을 확인합니다."),
    )
    deescalation = three_rows(
        [str(item) for item in warning.get("deescalation_rules", [])],
        "반증 조건이 확인되면 이슈 강도를 낮춥니다.",
    )
    owner = str(warning.get("owner") or "담당 조직")

    return {
        "reader_question": str(warning.get("decision_question") or ""),
        "provisional_conclusion": str(
            thesis.get("statement") or warning.get("executive_summary") or ""
        ),
        "key_numbers": key_numbers(trend, warning),
        "visuals": [
            {
                "type": "causal_map",
                "status": "adopted",
                "title": str(
                    (warning.get("causal_map") or {}).get("title")
                    or "외부 변화가 회사 결정으로 전달되는 경로"
                ),
                "source_ids": sources,
            },
            {
                "type": "decision_sequence",
                "status": "adopted",
                "title": "결정을 미루지 않기 위해 먼저 완성할 세 가지 산출물",
                "columns": ["순서·책임", "이번에 만들 것", "완료 후 판단"],
                "rows": [
                    ["1 · " + owner, actions[0], "두 번째 검증으로 이동"],
                    ["2 · " + owner, actions[1], "대안의 경제성과 실행 가능성 비교"],
                    ["3 · " + owner, actions[2], "투자·계약·보류 중 하나를 선택"],
                ],
                "caption": "문단에 흩어진 행동을 실행 순서와 완료 후 판단으로 재구성했습니다.",
                "source_ids": sources,
            },
            {
                "type": "monitoring_dashboard",
                "status": "adopted",
                "title": "세 확인선이 현재 결론을 강화하거나 낮춘다",
                "columns": ["관찰 지표·책임", "강화 신호", "완화 신호"],
                "rows": [
                    ["1 · " + owner, escalation[0], deescalation[0]],
                    ["2 · " + owner, escalation[1], deescalation[1]],
                    ["3 · " + owner, escalation[2], deescalation[2]],
                ],
                "caption": "공식 발표와 내부 확인값이 바뀌면 같은 표에서 이슈 강도를 다시 판단합니다.",
                "source_ids": sources,
            },
            {
                "type": "break_even",
                "status": "deferred",
                "title": "회사 순영향액과 손익분기점",
                "reason": "공개자료만으로 회사별 물량·가격·원가·계약 전가율을 확정할 수 없어 장식용 숫자를 만들지 않았습니다.",
                "required_inputs": [
                    "회사별 실제 노출 물량과 계약 갱신시점",
                    "가격·원가·물류·관세의 내부 기준값",
                    "고객 전가율과 대응 투자·운영비",
                ],
            },
        ],
    }


def watch_manifest(store: Path, warning_path: Path) -> dict[str, Any]:
    warning = read_json(warning_path)
    rewrite = RECOMMENDATION_REWRITES.get(str(warning.get("warning_id")))
    if rewrite:
        recommendation = next(
            item
            for item in warning.get("report_sections", [])
            if item.get("role") == "recommendation"
        )
        recommendation["body"] = rewrite
    thesis = read_json(store / ".system" / "theses" / f"{warning['thesis_id']}.json")
    trend_ids = list(thesis.get("trend_ids", []))
    if len(trend_ids) != 1:
        raise ValueError(f"{warning['warning_id']}: expected one trend")
    trend = read_json(store / ".system" / "trends" / f"{trend_ids[0]}.json")
    return {
        "schema_version": market_sensing.STRATEGIC_WATCH_SCHEMA_VERSION,
        "trend": trend,
        "thesis": thesis,
        "warning": warning,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill source-grounded reader editorial plans for strategic issues."
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    store = args.root.resolve()
    changed: list[str] = []
    skipped: list[str] = []
    for warning_path in sorted((store / ".system" / "warnings").glob("WRN-*.json")):
        manifest = watch_manifest(store, warning_path)
        warning = manifest["warning"]
        if isinstance(warning.get("editorial_plan"), dict) and not args.force:
            skipped.append(str(warning["warning_id"]))
            continue
        warning["editorial_plan"] = build_editorial_plan(
            manifest["trend"], manifest["thesis"], warning
        )
        market_sensing.validate_strategic_watch_manifest(store, manifest)
        changed.append(str(warning["warning_id"]))
        if args.apply:
            with tempfile.TemporaryDirectory() as temporary_directory:
                manifest_path = Path(temporary_directory) / warning_path.name
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                market_sensing.upsert_strategic_watch(
                    argparse.Namespace(
                        root=str(store),
                        watch_file=str(manifest_path),
                    )
                )

    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "updated": changed,
                "skipped": skipped,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
