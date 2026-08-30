import json
import sqlite3
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "market-sensing-intelligence"
    / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))
PROJECT_TOOLS = Path(__file__).resolve().parents[1] / "tools" / "project"
sys.path.insert(0, str(PROJECT_TOOLS))

import market_sensing  # noqa: E402
import mkdocs_hooks  # noqa: E402
import signal_analytics  # noqa: E402
import sqlite_store  # noqa: E402


def valid_structured_analysis():
    def table(key, label, columns, rows):
        return {
            "key": key,
            "label": label,
            "display": "table",
            "columns": [{"key": item, "label": item} for item in columns],
            "rows": [dict(zip(columns, row)) for row in rows],
        }

    return {
        "schema_version": 3,
        "sections": [
            {
                "key": "scenarios",
                "title": "시나리오",
                "items": [
                    {"key": "decision_question", "label": "판단 질문", "display": "text", "value": "판단할 수 있는가?"},
                    {"key": "provisional_conclusion", "label": "잠정 결론", "display": "text", "value": "조건 확인이 필요합니다."},
                    table("scenarios", "시나리오", ["case", "condition", "meaning", "action"], [
                        ["방어", "조건 A", "의미 A", "대응 A"],
                        ["기준", "조건 B", "의미 B", "대응 B"],
                        ["압박", "조건 C", "의미 C", "대응 C"],
                    ]),
                ],
            },
            {
                "key": "business_impact",
                "title": "사업 영향",
                "items": [
                    {"key": "impact_path", "label": "사업 영향 경로", "display": "flow", "steps": ["규정", "계약", "판매"]},
                    table("opportunity", "기회", ["condition", "effect", "action"], [["조건", "효과", "행동"]]),
                    table("risk", "위험", ["condition", "effect", "action"], [["조건", "효과", "행동"]]),
                    {"key": "opportunity_cost", "label": "기회비용", "display": "text", "value": "대응 지연 비용입니다."},
                    {"key": "secondary_effects", "label": "2차 영향", "display": "list", "items": ["계약", "운영"]},
                    table("response_options", "대응 선택지", ["option", "benefit", "cost_or_risk", "activation_condition"], [
                        ["선택 A", "효과 A", "비용 A", "조건 A"], ["선택 B", "효과 B", "비용 B", "조건 B"]]),
                    table("quantification_decision", "정량화 판단", ["status", "basis", "next_input"], [["not_applicable", "주제가 정량 영향과 본질적으로 맞지 않음", "재검토 조건"]]),
                ],
            },
            {
                "key": "key_drivers",
                "title": "키 드라이버",
                "items": [
                    table("monitoring_indicators", "관찰 지표", ["indicator", "current_state", "threshold", "decision_effect", "owner", "cadence"], [
                        ["가격", "미확인", "기준 초과", "가격 재검토", "영업", "주간"],
                        ["물량", "미확인", "기준 미달", "물량 재검토", "판매", "월간"],
                        ["계약", "미확인", "만기 도래", "계약 재검토", "법무", "월간"],
                    ]),
                    table("escalation_triggers", "상향 트리거", ["condition", "current_status", "decision_effect"], [["조건 A", "미충족", "상향"], ["조건 B", "미충족", "상향"]]),
                    table("deescalation_triggers", "하향 트리거", ["condition", "current_status", "decision_effect"], [["조건 C", "미충족", "하향"], ["조건 D", "미충족", "하향"]]),
                    table("timing", "시점", ["event", "date_or_condition", "status"], [["발표", "2026-08-01", "확인"], ["시행", "미확인", "미확인"], ["다음 검토", "2026-09-01", "예정"]]),
                    {"key": "sensitivity_drivers", "label": "민감도", "display": "list", "items": ["가격", "물량", "계약"]},
                    {"key": "execution_sequence", "label": "실행 순서", "display": "flow", "steps": ["확인", "비교", "결정"]},
                ],
            },
            {
                "key": "evidence",
                "title": "근거와 시점",
                "items": [
                    {"key": "verified_change", "label": "확인된 변화", "display": "text", "value": "검증요건이 추가됐습니다."},
                ],
            },
            {
                "key": "falsification_actions",
                "title": "반증과 다음 행동",
                "items": [
                    {"key": "baseline_assumption", "label": "기존 전제", "display": "text", "value": "가격이 판단을 좌우합니다."},
                    {"key": "decision_change", "label": "바꿀 결정", "display": "text", "value": "검증정보를 함께 봅니다."},
                    {"key": "falsification_condition", "label": "반증 조건", "display": "text", "value": "기존 계약이 모두 요건을 충족합니다."},
                    {"key": "decision_outputs", "label": "다음 산출물", "display": "list", "items": ["계약 매트릭스"]},
                    {"key": "internal_data", "label": "필요 내부 데이터", "display": "list", "items": ["계약 원가"]},
                    {"key": "owner", "label": "담당", "display": "text", "value": "영업·법무"},
                    {"key": "detection_trigger", "label": "재탐지 조건", "display": "text", "value": "계약 조건 변경"},
                    {"key": "limitations", "label": "판단의 한계", "display": "text", "value": "내부 계약은 공개되지 않았습니다."},
                ],
            }
        ],
    }


def valid_editorial_analysis():
    return (
        "## 비용 조건 변화에 따른 계약 판단 전환\n"
        + "확인된 변화와 시점을 구분해 설명합니다. " * 25
        + "\n## 가격과 계약이 마진으로 이어지는 사업 영향\n"
        + "가격과 계약을 거쳐 사업 영향 경로가 판매 마진에 전달됩니다. " * 20
        + "\n## 세 갈래 조건부 시나리오와 대응 순서\n\n"
        + "| 시나리오 | 관찰 조건 | 사업 의미 | 우선 대응 |\n"
        + "| --- | --- | --- | --- |\n"
        + "| 방어 | 조건 A | 의미 A | 대응 A |\n"
        + "| 기준 | 조건 B | 의미 B | 대응 B |\n"
        + "| 압박 | 조건 C | 의미 C | 대응 C |\n\n"
        + "각 조건과 대응을 구분합니다. " * 15
        + "\n## 가격·물량·계약 만기에 따른 대응 시점\n"
        + "### 이번 주 확인할 지표\n"
        + "- 가격 — 마진 판단 변경\n- 물량 — 판매 판단 변경\n"
        + "- 계약 만기 — 대응시점 변경\n"
        + "판단을 바꾸는 관찰 지표를 설명합니다. " * 15
        + "\n## 고객별 민감도에 따른 실행 순서\n"
        + "### 의사결정에 필요한 다음 산출물\n"
        + "1. 고객별 민감도\n2. 선택지 비교표\n3. 대응 조건표\n"
        + "실행 가능한 다음 산출물을 정의합니다. " * 15
        + '\n!!! warning "판단의 한계"\n\n'
        + "    내부 원가와 계약정보가 필요합니다. 공개정보의 한계를 한 번 명시합니다."
    )


class SQLiteMarketSensingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "market-sensing-wiki"
        market_sensing.scaffold(self.root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_stable_node_id_accepts_numeric_version_parts(self):
        first = market_sensing._stable_node_id("CLMV", "CLM-TEST", 1, "SRC-TEST")
        second = market_sensing._stable_node_id("CLMV", "CLM-TEST", "1", "SRC-TEST")
        self.assertEqual(first, second)
        self.assertRegex(first, r"^CLMV-[A-F0-9]{12}$")

    def test_score_rationale_requires_fact_path_score_and_boundary(self):
        valid = (
            "분기 쿼터 4만 톤이 소진돼 초과 물량에 추가 관세가 적용될 수 있습니다. "
            "선적 시점과 관세 부담 주체가 시장 접근성과 계약 마진을 함께 바꾸므로 "
            "경영 판단이 필요한 7점으로 평가했습니다. 회사의 실제 사용량과 관세 "
            "전가 조건이 확인되지 않아 8점 이상으로 높이지 않았습니다."
        )
        self.assertEqual(
            market_sensing.validate_score_rationale("business_impact", 7, valid),
            valid,
        )
        with self.assertRaisesRegex(ValueError, "between 120 and 600"):
            market_sensing.validate_score_rationale(
                "business_impact", 7, "시장 접근성과 계약 마진이 달라집니다."
            )
        with self.assertRaisesRegex(ValueError, "why it is 7점"):
            market_sensing.validate_score_rationale(
                "business_impact", 7, valid.replace("7점", "해당 점수")
            )
        with self.assertRaisesRegex(ValueError, "adjacent-score boundary"):
            market_sensing.validate_score_rationale(
                "business_impact",
                7,
                valid.replace("8점 이상으로 높이지 않았습니다", "추가 확인이 필요합니다"),
            )

    def test_quantification_decision_requires_model_or_narrow_json_exception(self):
        estimate = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "research"
                / "impact-estimates"
                / "senex-gas-reservation.json"
            ).read_text(encoding="utf-8")
        )
        modeled = market_sensing.modeled_quantification_decision(estimate)
        self.assertEqual(
            "modeled",
            market_sensing.validate_quantification_decision(
                modeled, estimate
            )["status"],
        )
        not_applicable = {
            "schema_version": 1,
            "status": "not_applicable",
            "assessed_at": "2026-08-29",
            "basis": (
                "이 Signal은 금액이나 운영량 민감도가 아니라 정성적 분류체계 변경만을 "
                "다루므로 독립 계산 결과가 의사결정을 개선하지 않습니다."
            ),
            "reason_code": "subject_not_quantifiable",
            "required_inputs": ["정량 영향 경로가 생기는 후속 운영 사건"],
            "reconsider_when": "후속 사건에서 가격·물량·비용 또는 일정 노출이 확인될 때",
            "related_signal_ids": [],
        }
        self.assertEqual(
            "not_applicable",
            market_sensing.validate_quantification_decision(not_applicable)["status"],
        )
        with self.assertRaisesRegex(ValueError, "modeled or not_applicable"):
            market_sensing.validate_quantification_decision(
                {**not_applicable, "status": "deferred"}
            )
        with self.assertRaisesRegex(ValueError, "cannot have impact_estimate"):
            market_sensing.validate_quantification_decision(
                not_applicable, estimate
            )

    def test_structured_quantification_status_rejects_internal_waiting(self):
        structured = valid_structured_analysis()
        for section in structured["sections"]:
            for item in section["items"]:
                if item["key"] == "quantification_decision":
                    item["rows"][0]["status"] = "내부 입력 대기"
        with self.assertRaisesRegex(ValueError, "modeled or not_applicable"):
            market_sensing.validate_structured_analysis(structured)

    def scout_args(self, run_id="weekly-scout", **overrides):
        values = {
            "root": str(self.root),
            "run_id": run_id,
            "date_from": "2026-08-23",
            "date_to": "2026-08-29",
            "target_count": None,
            "company_id": None,
            "business_axis": None,
            "user_scope": None,
            "coverage_file": None,
            "complete": False,
        }
        values.update(overrides)
        return Namespace(**values)

    def valid_no_change_coverage(self, run):
        # Legacy candidate-density fixtures exercise the v4 compatibility path.
        # New runs use v5 and must satisfy the published-Signal gate tested below.
        run["research_contract"]["version"] = 4
        coverage = market_sensing.initial_research_coverage(
            run["research_contract"]["required_company_axes"]
        )
        for cell in coverage["cells_checked"]:
            cell.update(
                {
                    "status": "no_change",
                    "channels": ["government_action", "physical_action"],
                    "search_strategies": [
                        {
                            "strategy": strategy,
                            "channel": channel,
                            "query": f"{strategy} 2026-08 external market change",
                            "executed_at": "2026-08-29T12:00:00+09:00",
                            "change_types": [change_type],
                            "new_candidates": 0,
                            "new_high_impact_candidates": 0,
                        }
                        for strategy, channel, change_type in (
                            ("official_regulatory", "government_action", "정책·규제"),
                            ("physical_project", "physical_action", "공급망·물류"),
                            ("local_implementation", "government_action", "고객·계약"),
                        )
                    ],
                    "limitations": [
                        "조사 기간 안에 영향 경로가 확인되는 새로운 외부 변화를 찾지 못했습니다."
                    ],
                    "next_trigger": "다음 공식 정책 또는 프로젝트 이행 발표 시 재탐색",
                }
            )
        period_days = (
            date.fromisoformat(run["date_to"]) - date.fromisoformat(run["date_from"])
        ).days + 1
        for index in range(period_days * 3):
            cell = coverage["cells_checked"][index % len(coverage["cells_checked"])]
            candidate_id = f"CAN-DENSITY-{index + 1:03d}"
            cell["candidate_ids"].append(candidate_id)
            coverage["candidates"].append(
                {
                    "candidate_id": candidate_id,
                    "candidate_date": (
                        date.fromisoformat(run["date_from"])
                        + timedelta(days=index // 3)
                    ).isoformat(),
                    "detected_at": "2026-08-29",
                    "company_id": cell["company_id"],
                    "business_axis": cell["business_axis"],
                    "change_type": market_sensing.SIGNAL_TYPES[
                        index % len(market_sensing.SIGNAL_TYPES)
                    ],
                    "title": f"기간 내 외부 변화 평가 후보 {index + 1}",
                    "source_url": f"https://example.com/candidates/{index + 1}",
                    "disposition": "watchlist",
                    "reason": "사업 영향 경로를 추가 확인하기 위해 관찰 후보로 보존합니다.",
                }
            )
        coverage["no_signal_reasons_by_company"] = {
            company_id: {
                "reason": "독립 채널을 교차 점검했지만 기간 내 발행 기준을 충족한 변화가 없었습니다.",
                "next_trigger": "다음 공식 정책 또는 프로젝트 이행 발표 시 재탐색",
            }
            for company_id in {
                cell["company_id"]
                for cell in run["research_contract"]["required_company_axes"]
            }
        }
        return coverage

    def test_priority_company_defaults_cover_all_configured_family_companies(self):
        expected = {
            "POSCO": ("COM-POSCO", ("철강",)),
            "POSCO Holdings": ("COM-POSCO-HOLDINGS", ("리튬", "전략광물")),
            "POSCO International": (
                "COM-POSCO-INTERNATIONAL",
                ("에너지", "식량·팜"),
            ),
            "POSCO E&C": ("COM-POSCO-ENC", ("건설·인프라",)),
            "POSCO Future M": ("COM-POSCO-FUTURE-M", ("이차전지소재",)),
            "POSCO Flow": ("COM-POSCO-FLOW", ("철강·원료 물류",)),
            "POSCO Mobility Solution": (
                "COM-POSCO-MOBILITY-SOLUTION",
                ("구동모터코아·강건재가공",),
            ),
            "POSCO Steeleon": ("COM-POSCO-STEELEON", ("도금·컬러강판",)),
        }

        self.assertEqual(list(expected), market_sensing.default_watchlist()["companies"])
        for company_name, (company_id, business_axes) in expected.items():
            self.assertEqual(
                business_axes,
                market_sensing.MARKET_SENSING_COMPANY_AXES[company_id],
            )
            self.assertEqual(business_axes[0], market_sensing.MARKET_SENSING_AXES[company_id])
            for business_axis in business_axes:
                self.assertTrue(
                    market_sensing.company_supports_business_axis(
                        company_id, business_axis
                    )
                )
            self.assertIn(company_id, market_sensing.TARGET_COMPANY_SOURCE_TERMS)
            self.assertEqual(company_name, mkdocs_hooks.COMPANY_DISPLAY_NAMES[company_id])
            self.assertIn(f"- {company_name}", market_sensing.WIKI_SETTINGS_TEMPLATE)

        self.assertFalse(
            market_sensing.company_supports_business_axis(
                "COM-POSCO-INTERNATIONAL", "철강"
            )
        )

        self.assertIn("최근 1주일치 조사해", (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn(
            "회사 × 사업축 × 영향 경로",
            (
                Path(__file__).resolve().parents[1]
                / "skills"
                / "market-sensing-intelligence"
                / "references"
                / "adaptive-research.md"
            ).read_text(encoding="utf-8"),
        )

    def test_scout_freezes_every_priority_company_axis_before_search(self):
        result = market_sensing.scout_run(self.scout_args())
        _, run = market_sensing.run_record_by_id(self.root, "weekly-scout")

        required = {
            (item["company_id"], item["business_axis"])
            for item in run["research_contract"]["required_company_axes"]
        }
        checked = {
            (item["company_id"], item["business_axis"])
            for item in run["coverage"]["cells_checked"]
        }
        self.assertEqual(10, result["required_cells"])
        self.assertEqual(5, run["research_contract"]["version"])
        self.assertEqual(
            3, run["research_contract"]["minimum_published_signals_per_day"]
        )
        self.assertNotIn("minimum_candidates_per_day", run["research_contract"])
        self.assertEqual(required, checked)
        self.assertEqual({"pending"}, {item["status"] for item in run["coverage"]["cells_checked"]})

    def test_scout_completion_rejects_missing_or_thin_coverage(self):
        market_sensing.scout_run(self.scout_args())
        with self.assertRaisesRegex(ValueError, "coverage gate failed"):
            market_sensing.scout_run(
                self.scout_args(date_from=None, date_to=None, complete=True)
            )
        _, run = market_sensing.run_record_by_id(self.root, "weekly-scout")
        self.assertEqual("in_progress", run["status"])

    def test_explicit_target_count_uses_limited_mode_without_full_coverage_gate(self):
        initialized = market_sensing.scout_run(
            self.scout_args(run_id="three-signals", target_count=3)
        )
        _, run = market_sensing.run_record_by_id(self.root, "three-signals")

        self.assertEqual("count_limited", initialized["research_mode"])
        self.assertEqual(3, run["research_contract"]["target_count"])
        self.assertEqual([], run["coverage"]["cells_checked"])

        signals = [
            {
                "run_id": "three-signals",
                "signal_id": f"SIG-LIMITED-{index}",
                "status": "active",
                "source_ids": ["SRC-SINGLE"],
            }
            for index in range(1, 4)
        ]
        run["signal_ids"] = [item["signal_id"] for item in signals]
        run_path, _ = market_sensing.run_record_by_id(self.root, "three-signals")
        market_sensing.write_json(run_path, run)
        self.assertEqual([], market_sensing.evaluate_research_coverage(run, signals))
        with patch.object(
            market_sensing,
            "signal_records",
            return_value=[(self.root / f"{item['signal_id']}.json", item) for item in signals],
        ):
            completed = market_sensing.scout_run(
                self.scout_args(
                    run_id="three-signals",
                    date_from=None,
                    date_to=None,
                    target_count=3,
                    complete=True,
                )
            )
        self.assertEqual("scout_completed", completed["action"])

    def test_explicit_target_count_does_not_complete_below_requested_count(self):
        market_sensing.scout_run(
            self.scout_args(run_id="three-signals", target_count=3)
        )
        _, run = market_sensing.run_record_by_id(self.root, "three-signals")
        run["signal_ids"] = ["SIG-ONE", "SIG-TWO"]
        findings = market_sensing.evaluate_research_coverage(
            run,
            [
                {"signal_id": "SIG-ONE", "status": "active"},
                {"signal_id": "SIG-TWO", "status": "active"},
            ],
        )
        self.assertTrue(any("2/3 requested Signals" in item for item in findings))

    def test_explicit_company_scope_overrides_default_all_company_coverage(self):
        initialized = market_sensing.scout_run(
            self.scout_args(
                run_id="holdings-only",
                company_id=["COM-POSCO-HOLDINGS"],
                user_scope="포스코홀딩스만 찾아봐",
            )
        )
        _, run = market_sensing.run_record_by_id(self.root, "holdings-only")
        required = run["research_contract"]["required_company_axes"]

        self.assertEqual("user_scoped", initialized["research_mode"])
        self.assertEqual("포스코홀딩스만 찾아봐", run["research_contract"]["user_directive"])
        self.assertEqual(
            {("COM-POSCO-HOLDINGS", "리튬"), ("COM-POSCO-HOLDINGS", "전략광물")},
            {(item["company_id"], item["business_axis"]) for item in required},
        )
        self.assertEqual(2, len(run["coverage"]["cells_checked"]))

    def test_v5_scout_does_not_complete_with_candidates_but_no_published_signals(self):
        market_sensing.scout_run(self.scout_args())
        _, run = market_sensing.run_record_by_id(self.root, "weekly-scout")
        coverage_path = Path(self.temp_dir.name) / "coverage.json"
        coverage_path.write_text(
            json.dumps(self.valid_no_change_coverage(run), ensure_ascii=False),
            encoding="utf-8",
        )

        # Explicitly document why this fixture has no publishable Signals. The
        # portfolio gate should not be bypassed by search-ledger boilerplate.
        run["signal_contract"]["documented_axis_gaps"] = [
            {
                "axis": item["business_axis"],
                "actual_signals": 0,
                "reason": "독립 채널에서 회사 영향 경로가 확인되는 외부 변화를 찾지 못했습니다.",
                "next_trigger": "다음 공식 정책 또는 고객 계약 변화 시 재탐색",
            }
            for item in run["research_contract"]["required_company_axes"]
        ]
        run["research_contract"]["version"] = 5
        run["research_contract"].pop("minimum_candidates_per_day", None)
        run["research_contract"]["minimum_published_signals_per_day"] = 3
        run_path, _ = market_sensing.run_record_by_id(self.root, "weekly-scout")
        market_sensing.write_json(run_path, run)
        with self.assertRaisesRegex(ValueError, "daily published Signal availability"):
            market_sensing.scout_run(
                self.scout_args(
                    date_from=None,
                    date_to=None,
                    coverage_file=str(coverage_path),
                    complete=True,
                )
            )
        _, completed = market_sensing.run_record_by_id(self.root, "weekly-scout")
        self.assertEqual("in_progress", completed["status"])

    def test_v5_requires_three_distinct_active_published_signals_per_day(self):
        market_sensing.scout_run(
            self.scout_args(
                run_id="published-daily",
                date_from="2026-08-29",
                date_to="2026-08-29",
                company_id=["COM-POSCO"],
            )
        )
        _, run = market_sensing.run_record_by_id(self.root, "published-daily")
        coverage = self.valid_no_change_coverage(run)
        run["research_contract"]["version"] = 5
        run["research_contract"].pop("minimum_candidates_per_day", None)
        run["research_contract"]["minimum_published_signals_per_day"] = 3
        signals = []
        for index, candidate in enumerate(coverage["candidates"], start=1):
            signal_id = f"SIG-PUBLISHED-{index}"
            candidate.update(
                {"disposition": "published_signal", "signal_id": signal_id}
            )
            candidate.pop("reason", None)
            signals.append(
                {
                    "signal_id": signal_id,
                    "status": "active",
                    "company_ids": [candidate["company_id"]],
                    "business_axis": candidate["business_axis"],
                }
            )
        run["coverage"] = coverage

        self.assertEqual([], market_sensing.evaluate_research_coverage(run, signals))

        coverage["candidates"][-1]["disposition"] = "watchlist"
        coverage["candidates"][-1].pop("signal_id")
        coverage["candidates"][-1]["reason"] = (
            "회사 영향 경로와 원문을 추가 확인하기 위해 관찰 후보로 유지합니다."
        )
        findings = market_sensing.evaluate_research_coverage(run, signals)
        self.assertTrue(
            any("daily published Signal availability is 2/3" in item for item in findings)
        )

    def test_v5_does_not_count_one_signal_on_multiple_calendar_days(self):
        market_sensing.scout_run(
            self.scout_args(run_id="reused-daily-signal", company_id=["COM-POSCO"])
        )
        _, run = market_sensing.run_record_by_id(self.root, "reused-daily-signal")
        coverage = self.valid_no_change_coverage(run)
        run["research_contract"]["version"] = 5
        run["research_contract"]["minimum_published_signals_per_day"] = 3
        reused = coverage["candidates"][0]
        duplicate = dict(reused)
        duplicate.update(
            {
                "candidate_id": "CAN-REUSED-OTHER-DAY",
                "candidate_date": "2026-08-24",
                "source_url": "https://example.com/reused/other-day",
                "disposition": "published_signal",
                "signal_id": "SIG-REUSED",
            }
        )
        reused.update({"disposition": "published_signal", "signal_id": "SIG-REUSED"})
        reused.pop("reason", None)
        coverage["candidates"].append(duplicate)
        run["coverage"] = coverage
        findings = market_sensing.evaluate_research_coverage(
            run,
            [
                {
                    "signal_id": "SIG-REUSED",
                    "status": "active",
                    "company_ids": [reused["company_id"]],
                    "business_axis": reused["business_axis"],
                }
            ],
        )

        self.assertTrue(any("cannot satisfy another calendar day" in item for item in findings))

    def test_v2_scout_rejects_templated_zero_yield_strategies(self):
        market_sensing.scout_run(self.scout_args(run_id="shallow-monthly"))
        _, run = market_sensing.run_record_by_id(self.root, "shallow-monthly")
        coverage = self.valid_no_change_coverage(run)
        for cell in coverage["cells_checked"]:
            for strategy in cell["search_strategies"]:
                strategy.pop("query")
                strategy.pop("executed_at")
                strategy.pop("change_types")
        run["coverage"] = coverage
        findings = market_sensing.evaluate_research_coverage(run, [])
        self.assertTrue(any("concrete executed query" in item for item in findings))

    def test_v3_scout_requires_three_evaluated_candidates_per_day(self):
        market_sensing.scout_run(self.scout_args(run_id="daily-density"))
        _, run = market_sensing.run_record_by_id(self.root, "daily-density")
        coverage = self.valid_no_change_coverage(run)
        coverage["candidates"] = coverage["candidates"][:-1]
        removed_id = "CAN-DENSITY-021"
        for cell in coverage["cells_checked"]:
            cell["candidate_ids"] = [
                candidate_id
                for candidate_id in cell["candidate_ids"]
                if candidate_id != removed_id
            ]
        run["coverage"] = coverage
        findings = market_sensing.evaluate_research_coverage(run, [])
        self.assertTrue(any("daily detection density is 2/3" in item for item in findings))

    def test_v3_scout_rejects_one_thin_day_even_when_total_is_above_minimum(self):
        market_sensing.scout_run(self.scout_args(run_id="uneven-daily-density"))
        _, run = market_sensing.run_record_by_id(self.root, "uneven-daily-density")
        coverage = self.valid_no_change_coverage(run)
        coverage["candidates"][-1]["candidate_date"] = run["date_from"]
        run["coverage"] = coverage

        findings = market_sensing.evaluate_research_coverage(run, [])

        self.assertTrue(
            any("2026-08-29: daily detection density is 2/3" in item for item in findings)
        )

    def test_v3_scout_rejects_duplicate_observed_changes_under_new_ids(self):
        market_sensing.scout_run(self.scout_args(run_id="duplicate-density"))
        _, run = market_sensing.run_record_by_id(self.root, "duplicate-density")
        coverage = self.valid_no_change_coverage(run)
        coverage["candidates"][1]["source_url"] = coverage["candidates"][0]["source_url"]
        coverage["candidates"][1]["title"] = coverage["candidates"][0]["title"]
        coverage["candidates"][1]["company_id"] = coverage["candidates"][0]["company_id"]
        coverage["candidates"][1]["business_axis"] = coverage["candidates"][0]["business_axis"]
        run["coverage"] = coverage

        findings = market_sensing.evaluate_research_coverage(run, [])

        self.assertTrue(any("duplicates observed change" in item for item in findings))

    def test_v3_published_candidate_requires_matching_active_signal(self):
        market_sensing.scout_run(self.scout_args(run_id="missing-published-signal"))
        _, run = market_sensing.run_record_by_id(self.root, "missing-published-signal")
        coverage = self.valid_no_change_coverage(run)
        candidate = coverage["candidates"][0]
        candidate.update({"disposition": "published_signal", "signal_id": "SIG-NOT-FOUND"})
        candidate.pop("reason")
        run["coverage"] = coverage

        findings = market_sensing.evaluate_research_coverage(run, [])

        self.assertTrue(any("must reference an active Signal" in item for item in findings))

    def test_v3_invalid_candidate_date_is_reported_without_crashing(self):
        market_sensing.scout_run(self.scout_args(run_id="invalid-candidate-date"))
        _, run = market_sensing.run_record_by_id(self.root, "invalid-candidate-date")
        coverage = self.valid_no_change_coverage(run)
        coverage["candidates"][0]["candidate_date"] = "not-a-date"
        run["coverage"] = coverage

        findings = market_sensing.evaluate_research_coverage(run, [])

        self.assertTrue(any("candidate_date must be inside" in item for item in findings))

    def test_v4_backfill_counts_candidate_date_without_backdating_detection(self):
        market_sensing.scout_run(self.scout_args(run_id="honest-backfill"))
        _, run = market_sensing.run_record_by_id(self.root, "honest-backfill")
        coverage = self.valid_no_change_coverage(run)
        for candidate in coverage["candidates"]:
            candidate["detected_at"] = "2026-09-01"
        run["coverage"] = coverage

        findings = market_sensing.evaluate_research_coverage(run, [])

        self.assertFalse(any("daily detection density" in item for item in findings))
        self.assertFalse(any("detected_at must be inside" in item for item in findings))

    def test_audit_flags_completed_research_run_with_a_missing_cell(self):
        market_sensing.scout_run(self.scout_args())
        path, run = market_sensing.run_record_by_id(self.root, "weekly-scout")
        run["coverage"] = self.valid_no_change_coverage(run)
        run["coverage"]["cells_checked"].pop()
        run["status"] = "completed"
        run["completed_at"] = "2026-08-29T12:00:00+09:00"
        market_sensing.write_json(path, run)

        audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        self.assertGreater(audit["counts"]["research_coverage"], 0)

    def test_signal_analysis_rejects_unheaded_lead_paragraph(self):
        with self.assertRaisesRegex(ValueError, "must start with a conclusion-led ##"):
            market_sensing.validate_signal_analysis(
                "시장이 닫힌 것은 아니지만 주문별 배분 기준이 바뀌었습니다."
            )

    def test_signal_analysis_rejects_repeated_signal_title_as_h1(self):
        with self.assertRaisesRegex(ValueError, "must start with a conclusion-led ##"):
            market_sensing.validate_signal_analysis(
                "# 외부 변화 제목\n\n## 판매 기준이 바뀌었다\n\n본문입니다."
            )

    def test_signal_analysis_rejects_h3_before_first_report_chapter(self):
        malformed = valid_editorial_analysis().replace(
            "## 비용 조건 변화에 따른 계약 판단 전환",
            "### 비용 조건 변화에 따른 계약 판단 전환",
            1,
        )
        with self.assertRaisesRegex(ValueError, "must start with a conclusion-led ##"):
            market_sensing.validate_signal_analysis(malformed)

    def test_signal_analysis_rejects_generic_or_decimal_chapters(self):
        generic = valid_editorial_analysis().replace(
            "## 비용 조건 변화에 따른 계약 판단 전환", "## 공개 근거 확인", 1
        )
        with self.assertRaisesRegex(ValueError, "report-specific conclusions"):
            market_sensing.validate_signal_analysis(generic)
        numbered = valid_editorial_analysis().replace(
            "## 가격과 계약이 마진으로 이어지는 사업 영향",
            "## 0.1 가격과 계약이 마진으로 이어지는 사업 영향",
            1,
        )
        with self.assertRaisesRegex(ValueError, "decimal section numbers"):
            market_sensing.validate_signal_analysis(numbered)

    def test_signal_analysis_rejects_polite_sentence_headings(self):
        malformed = valid_editorial_analysis().replace(
            "## 비용 조건 변화에 따른 계약 판단 전환",
            "## 비용 조건 변화가 계약 판단을 바꿉니다",
            1,
        )
        with self.assertRaisesRegex(ValueError, "polite sentence endings"):
            market_sensing.validate_signal_analysis(malformed)

    def test_rewrite_analysis_headings_changes_only_exact_heading_labels(self):
        original = valid_editorial_analysis()
        rewritten = market_sensing.rewrite_analysis_headings(
            original,
            {
                "비용 조건 변화에 따른 계약 판단 전환": "비용 조건 변화와 계약 판단",
                "이번 주 확인할 지표": "이번 주 핵심 확인할 지표",
            },
        )
        self.assertIn("## 비용 조건 변화와 계약 판단", rewritten)
        self.assertIn("### 이번 주 핵심 확인할 지표", rewritten)
        self.assertIn("확인된 변화와 시점을 구분해 설명합니다.", rewritten)
        self.assertNotIn("## 비용 조건 변화에 따른 계약 판단 전환", rewritten)

    def test_signal_analysis_rejects_repeated_uncertainty_disclaimers(self):
        malformed = valid_editorial_analysis() + (
            "\n확인되지 않은 값입니다. 공개되지 않은 값입니다. "
            "연결이익의 확정은 아닙니다."
        )
        with self.assertRaisesRegex(ValueError, "repeats uncertainty"):
            market_sensing.validate_signal_analysis(malformed)

    def test_scaffold_creates_one_database_and_no_data_markdown(self):
        self.assertTrue(sqlite_store.database_path(self.root).is_file())
        self.assertEqual([], list(self.root.rglob("*.md")))
        self.assertEqual([], list(self.root.rglob("*.json")))

    def test_json_compatibility_addresses_persist_only_in_sqlite(self):
        logical_path = self.root / ".system" / "claims" / "CLM-TEST.json"
        record = {"claim_id": "CLM-TEST", "schema_version": 1, "value": "검증"}
        market_sensing.write_json(logical_path, record)
        self.assertFalse(logical_path.exists())
        self.assertEqual(record, market_sensing.read_json(logical_path))
        loaded = market_sensing.load_json_objects(logical_path.parent)
        self.assertEqual("CLM-TEST", loaded[0][0].stem)
        self.assertEqual(record, loaded[0][1])

    def test_source_content_is_blob_and_hash_is_preserved(self):
        logical_path = self.root / ".system" / "source-records" / "SRC-TEST.json"
        record = {"source_id": "SRC-TEST", "schema_version": 1}
        market_sensing.write_json(logical_path, record)
        sqlite_store.put_source_content(self.root, "SRC-TEST", "원문\n내용".encode())
        self.assertEqual("원문\n내용".encode(), sqlite_store.get_source_content(self.root, "SRC-TEST"))
        connection = sqlite3.connect(sqlite_store.database_path(self.root))
        try:
            row = connection.execute(
                "SELECT raw_sha256, length(content) FROM wiki_source_contents WHERE source_id=?",
                ("SRC-TEST",),
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(32 * 2, len(row[0]))
        self.assertEqual(len("원문\n내용".encode()), row[1])

    def test_signal_analytics_contract_normalizes_evidence_and_versions(self):
        risk_factor = signal_analytics.validate_risk_factor(
            {
                "risk_factor_id": "RF-EU-LOW-CARBON-PROCUREMENT",
                "name": "EU 저탄소 조달기준",
                "definition": "EU 철강 조달에서 저탄소 기준이 시장 접근을 바꾸는 위험요인",
                "category": "POLICY_REGULATION",
            }
        )
        sqlite_store.put_risk_factor(self.root, risk_factor)
        source = {
            "schema_version": 2,
            "source_id": "SRC-EU-001",
            "source_type": "official",
            "source_modality": "DOCUMENT",
            "collected_at": "2026-08-29",
        }
        market_sensing.write_json(
            self.root / ".system" / "source-records" / "SRC-EU-001.json", source
        )
        sqlite_store.put_source_asset(self.root, source)
        event = signal_analytics.event_version(
            {
                "event_id": "EVT-EU-PROCUREMENT",
                "version_no": 1,
                "event_type": "policy_change",
                "actor_ref": "EU",
                "target_ref": "steel-procurement",
                "observed_at": "2026-08-29",
                "after_value": "low-carbon-standard",
                "source_ids": ["SRC-EU-001"],
                "modality": "DOCUMENT",
                "risk_factor_ids": [risk_factor["risk_factor_id"]],
            }
        )
        market_sensing.write_json(
            self.root / ".system" / "events" / f"{event['event_version_id']}.json",
            event,
        )
        sqlite_store.put_event_version(self.root, event)
        sqlite_store.put_risk_factor_links(
            self.root,
            subject_kind="event",
            subject_version_id=event["event_version_id"],
            risk_factor_ids=event["risk_factor_ids"],
        )
        first, impacts, scenarios = signal_analytics.build_signal_bundle(
            canonical_key="eu.steel.low-carbon-procurement",
            title="EU 철강 수입축소와 저탄소 조달기준 결합",
            sentence="EU 시장 접근 조건이 수입량과 저탄소 조달기준의 결합으로 바뀝니다.",
            signal_type="정책·규제",
            signal_role="core_market_signal",
            signal_origin="external_change",
            assessed_at="2026-08-29",
            risk_factor_ids=[risk_factor["risk_factor_id"]],
            evidence_refs=[{
                "kind": "event",
                "version_id": event["event_version_id"],
                "modality": "DOCUMENT",
                "relation": "support",
                "source_ids": ["SRC-EU-001"],
            }],
            company_ids=["COM-POSCO"],
            business_axis="철강",
            business_impact={"score": 7, "rationale": "시장 접근 조건이 바뀝니다."},
            urgency={"score": 6, "rationale": "조달기준 확정 전 확인이 필요합니다."},
            assessment_confidence="high",
            structured_analysis=valid_structured_analysis(),
            created_at="2026-08-29T12:00:00+09:00",
            stable_signal_id="SIG-ABCDEF123456",
        )
        market_sensing.write_json(
            self.root / ".system" / "signal-versions" / f"{first['signal_version_id']}.json",
            first,
        )
        for impact in impacts:
            market_sensing.write_json(
                self.root / ".system" / "company-impacts" / f"{impact['company_impact_version_id']}.json",
                impact,
            )
        for scenario in scenarios:
            market_sensing.write_json(
                self.root / ".system" / "scenarios" / f"{scenario['scenario_version_id']}.json",
                scenario,
            )
        sqlite_store.put_signal_analytics_bundle(self.root, first, impacts, scenarios)
        current_signal = {
            **first,
            "schema_version": 4,
            "insight_id": "INS-EU-001",
            "company_ids": ["COM-POSCO"],
            "business_axis": "철강",
            "business_impact": {"score": 7, "rationale": "시장 접근 조건이 바뀝니다."},
            "urgency": {"score": 6, "rationale": "조달기준 확정 전 확인이 필요합니다."},
            "assessment_confidence": "high",
            "claim_ids": [],
            "source_ids": ["SRC-EU-001"],
            "status": "active",
            "updated_at": first["created_at"],
        }
        insight = {
            "schema_version": 3,
            "insight_id": "INS-EU-001",
            "title": first["title"],
            "analysis_structured": valid_structured_analysis(),
            "analysis_markdown": valid_editorial_analysis(),
            "claim_ids": [],
            "source_ids": ["SRC-EU-001"],
        }
        market_sensing.write_json(
            self.root / ".system" / "signals" / f"{first['signal_id']}.json",
            current_signal,
        )
        market_sensing.write_json(
            self.root / ".system" / "insights" / "INS-EU-001.json", insight
        )
        second = market_sensing.refresh_signal_analytics_version(
            self.root, current_signal, insight
        )
        self.assertEqual("SIG-ABCDEF123456", first["signal_id"])
        self.assertEqual(first["signal_id"], second["signal_id"])
        self.assertNotEqual(first["signal_version_id"], second["signal_version_id"])
        self.assertEqual(2, second["version_no"])
        integrity = sqlite_store.integrity(self.root)
        self.assertEqual(1, integrity["analytics_counts"]["wiki_source_assets"])
        self.assertEqual(1, integrity["analytics_counts"]["wiki_event_versions"])
        self.assertEqual(2, integrity["analytics_counts"]["wiki_signal_versions"])
        self.assertEqual(6, integrity["analytics_counts"]["wiki_scenario_versions"])

    def test_settings_and_operation_log_do_not_create_files(self):
        settings_path = self.root / "config" / "watchlist.json"
        market_sensing.write_json(settings_path, {"schema_version": 1, "companies": ["POSCO"]})
        market_sensing.append_log(self.root, "test", "detail")
        self.assertFalse(settings_path.exists())
        self.assertFalse((self.root / "log.md").exists())
        self.assertEqual(["POSCO"], market_sensing.read_json(settings_path)["companies"])

    def test_audit_report_is_stored_as_artifact(self):
        result = market_sensing.audit_store(Namespace(root=str(self.root), stale_days=180))
        self.assertEqual("audit:" + market_sensing.today(), result["report_artifact_id"])
        artifact = sqlite_store.get_artifact(self.root, result["report_artifact_id"])
        self.assertIn("## Summary", artifact["markdown_text"])
        self.assertFalse((self.root / "reports").exists())

    def test_search_reads_sqlite_records_without_markdown_projection(self):
        market_sensing.write_json(
            self.root / ".system" / "insights" / "INS-TEST.json",
            {
                "insight_id": "INS-TEST",
                "title": "LFP 비중 확대",
                "summary": "수산화리튬 제품 믹스를 다시 판단합니다.",
                "analysis_markdown": "## 결론\n\n탄산리튬 계약을 확인합니다.",
            },
        )
        result = market_sensing.search_store(
            Namespace(root=str(self.root), query="LFP 수산화리튬", limit=5)
        )
        self.assertEqual("INS-TEST", result["notes"][0]["artifact_id"])
        self.assertEqual([], list(self.root.rglob("*.md")))

    def test_structured_analysis_is_nested_json_in_sqlite_payload(self):
        structured = market_sensing.validate_structured_analysis(
            valid_structured_analysis()
        )
        market_sensing.write_json(
            self.root / ".system" / "insights" / "INS-STRUCTURED.json",
            {
                "schema_version": market_sensing.INSIGHT_SCHEMA_VERSION,
                "insight_id": "INS-STRUCTURED",
                "analysis_markdown": "읽기용 산문",
                "analysis_structured": structured,
            },
        )
        connection = sqlite3.connect(sqlite_store.database_path(self.root))
        try:
            row = connection.execute(
                """
                SELECT
                    json_extract(payload_json, '$.analysis_markdown'),
                    json_extract(payload_json, '$.analysis_structured.schema_version'),
                    json_extract(payload_json, '$.analysis_structured.sections[0].items[0].label')
                FROM wiki_records
                WHERE collection='insights' AND record_id='INS-STRUCTURED'
                """
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(("읽기용 산문", 3, "판단 질문"), row)

    def test_set_structured_analysis_rejects_legacy_signal_contract(self):
        market_sensing.write_json(
            self.root / ".system" / "signals" / "SIG-TEST.json",
            {"signal_id": "SIG-TEST", "insight_id": "INS-TEST"},
        )
        market_sensing.write_json(
            self.root / ".system" / "insights" / "INS-TEST.json",
            {
                "schema_version": market_sensing.LEGACY_INSIGHT_SCHEMA_VERSION,
                "insight_id": "INS-TEST",
                "analysis_markdown": "읽기용 산문은 유지합니다.",
                "claim_ids": [],
                "source_ids": [],
            },
        )
        structured_path = Path(self.temp_dir.name) / "structured-analysis.json"
        structured_path.write_text(
            json.dumps(valid_structured_analysis(), ensure_ascii=False),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "canonical_key is required"):
            market_sensing.set_structured_analysis(
                Namespace(
                    root=str(self.root),
                    signal_id="SIG-TEST",
                    structured_analysis_file=str(structured_path),
                )
            )
        insight = market_sensing.read_json(
            self.root / ".system" / "insights" / "INS-TEST.json"
        )
        self.assertEqual(market_sensing.LEGACY_INSIGHT_SCHEMA_VERSION, insight["schema_version"])
        self.assertEqual("읽기용 산문은 유지합니다.", insight["analysis_markdown"])
        self.assertNotIn("analysis_structured", insight)

    def test_set_signal_analysis_rejects_claims_without_canonical_versions(self):
        for source_id in ("SRC-OLD", "SRC-NEW"):
            market_sensing.write_json(
                self.root / ".system" / "source-records" / f"{source_id}.json",
                {"schema_version": 1, "source_id": source_id},
            )
        for claim_id, source_id in (("CLM-OLD", "SRC-OLD"), ("CLM-NEW", "SRC-NEW")):
            market_sensing.write_json(
                self.root / ".system" / "claims" / f"{claim_id}.json",
                {
                    "schema_version": 1,
                    "claim_id": claim_id,
                    "source_ids": [source_id],
                },
            )
        market_sensing.write_json(
            self.root / ".system" / "signals" / "SIG-TEST.json",
            {
                "signal_id": "SIG-TEST",
                "insight_id": "INS-TEST",
                "claim_ids": ["CLM-OLD"],
                "source_ids": ["SRC-OLD"],
            },
        )
        market_sensing.write_json(
            self.root / ".system" / "insights" / "INS-TEST.json",
            {
                "schema_version": market_sensing.INSIGHT_SCHEMA_VERSION,
                "insight_id": "INS-TEST",
                "analysis_markdown": "기존 산문",
                "analysis_structured": valid_structured_analysis(),
                "claim_ids": ["CLM-OLD"],
                "source_ids": ["SRC-OLD"],
            },
        )
        analysis_path = Path(self.temp_dir.name) / "analysis.md"
        analysis_path.write_text(valid_editorial_analysis(), encoding="utf-8")
        structured_path = Path(self.temp_dir.name) / "structured.json"
        structured_path.write_text(
            json.dumps(valid_structured_analysis(), ensure_ascii=False),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "has no canonical claim_version_id"):
            market_sensing.set_signal_analysis(
                Namespace(
                    root=str(self.root),
                    signal_id="SIG-TEST",
                    analysis_file=str(analysis_path),
                    structured_analysis_file=str(structured_path),
                    claim_id=["CLM-NEW"],
                )
            )
        signal = market_sensing.read_json(
            self.root / ".system" / "signals" / "SIG-TEST.json"
        )
        insight = market_sensing.read_json(
            self.root / ".system" / "insights" / "INS-TEST.json"
        )
        self.assertEqual(["CLM-OLD"], signal["claim_ids"])
        self.assertEqual(["SRC-OLD"], insight["source_ids"])
        self.assertEqual("기존 산문", insight["analysis_markdown"])
        self.assertEqual(3, insight["analysis_structured"]["schema_version"])

    def test_sync_obsidian_is_a_no_file_operation(self):
        result = market_sensing.sync_obsidian(Namespace(root=str(self.root)))
        self.assertEqual("sqlite_canonical", result["action"])
        self.assertEqual(0, result["generated_files"])
        self.assertEqual([], list(self.root.rglob("*.md")))

    def test_integrity_closes_connections_on_windows(self):
        result = sqlite_store.integrity(self.root)
        self.assertEqual("ok", result["integrity_check"])
        database = sqlite_store.database_path(self.root)
        database.unlink()
        self.assertFalse(database.exists())

    def test_signal_projection_does_not_duplicate_embedded_impact_simulator(self):
        estimate = {
            "schema_version": 1,
            "title": "민감도",
            "description": "설명",
            "as_of": "2026-08-29",
            "confidence": "low",
            "notice": "예비 추정",
            "formula_display": "값",
            "variables": [],
            "outputs": [],
            "presets": [],
        }
        embedded = "```impact-simulator\n" + json.dumps(estimate) + "\n```"
        lines = market_sensing.signal_page_lines(
            {
                "signal_id": "SIG-TEST",
                "sentence": "사업 시사점입니다.",
                "business_axis": "철강",
                "signal_type": "수급·가격",
                "business_impact": {"score": 5, "rationale": "근거"},
                "urgency": {"score": 4, "rationale": "근거"},
            },
            {
                "title": "외부 변화",
                "summary": "요약",
                "analysis_markdown": embedded,
                "impact_estimate": estimate,
                "source_ids": [],
                "claim_ids": [],
            },
            {},
            {},
        )
        rendered = "\n".join(lines)
        self.assertEqual(1, rendered.count("```impact-simulator"))
        self.assertLess(rendered.index("1. 시나리오"), rendered.index("```impact-simulator"))

    def test_signal_projection_renders_structured_and_narrative_tabs(self):
        lines = market_sensing.signal_page_lines(
            {
                "signal_id": "SIG-TEST",
                "sentence": "사업 시사점입니다.",
                "business_axis": "에너지",
                "signal_type": "정책·규제",
                "business_impact": {"score": 7, "rationale": "근거"},
                "urgency": {"score": 8, "rationale": "근거"},
            },
            {
                "title": "EU 메탄 검증요건",
                "summary": "계약별 검증정보를 확인해야 합니다.",
                "analysis_markdown": "## 산문 결론\n\n계약 정보권이 판매선택권을 가릅니다.",
                "analysis_structured": valid_structured_analysis(),
                "source_ids": [],
                "claim_ids": [],
            },
            {},
            {},
        )
        rendered = "\n".join(lines)
        self.assertIn('=== "신호분석"', rendered)
        self.assertIn('=== "보고서"', rendered)
        self.assertIn("    **1. 시나리오**", rendered)
        self.assertIn("    **2. 사업 영향**", rendered)
        self.assertIn("    **3. 키 드라이버**", rendered)
        self.assertIn("    **4. 근거와 시점**", rendered)
        self.assertIn("    **5. 반증과 다음 행동**", rendered)
        self.assertIn("**시나리오**", rendered)
        self.assertNotIn("    ## 판단 요약", rendered)
        self.assertNotIn("    ## 왜 중요한가", rendered)
        self.assertNotIn("    ## 상세 분석", rendered)
        self.assertIn("    ## 산문 결론", rendered)
        self.assertLess(
            rendered.index('=== "신호분석"'),
            rendered.index("    **1. 시나리오**"),
        )

    def test_signal_evidence_shows_optional_claim_cross_validation(self):
        claims = {
            "CLM-SINGLE": {
                "predicate": "published_at",
                "value": "2026-08-29",
                "status": "active",
                "source_ids": ["SRC-ONE"],
            },
            "CLM-INDEPENDENT": {
                "predicate": "market_volume",
                "value": "시장 변화 → 계약 조건",
                "status": "active",
                "source_ids": ["SRC-ONE", "SRC-TWO"],
            },
            "CLM-CONFLICTED": {
                "predicate": "effective_date",
                "value": "시행일 해석 상충",
                "status": "disputed",
                "source_ids": ["SRC-TWO", "SRC-THREE"],
            },
        }
        sources = {
            source_id: {"title": source_id}
            for source_id in ("SRC-ONE", "SRC-TWO", "SRC-THREE")
        }
        lines = market_sensing.signal_page_lines(
            {
                "signal_id": "SIG-CROSS-VALIDATION",
                "sentence": "단독 속보도 지연 없이 일반 Signal로 발행합니다.",
                "business_axis": "철강",
                "signal_type": "정책·규제",
                "business_impact": {"score": 5, "rationale": "근거"},
                "urgency": {"score": 8, "rationale": "근거"},
            },
            {
                "title": "교차검증 표시 테스트",
                "summary": "요약",
                "analysis_markdown": "## 산문 결론\n\n단일 출처도 정상 발행합니다.",
                "analysis_structured": valid_structured_analysis(),
                "source_ids": list(sources),
                "claim_ids": list(claims),
            },
            claims,
            sources,
        )
        rendered = "\n".join(lines)
        structured, remainder = rendered.split('=== "보고서"', 1)
        self.assertIn("교차검증", structured)
        self.assertIn("단일 출처", structured)
        self.assertIn("독립 교차확인", structured)
        self.assertIn("출처 상충", structured)
        self.assertIn("단일 출처", remainder)
        self.assertNotIn("추가 검증 중", rendered)

    def test_legacy_narrative_signal_projects_decision_dashboard_from_typed_records(self):
        lines = market_sensing.signal_page_lines(
            {
                "signal_id": "SIG-LEGACY",
                "sentence": "제품·지역별 주문잔고와 가격 전가율로 계획을 다시 판단합니다.",
                "business_axis": "철강",
                "signal_type": "수급·가격",
                "created_at": "2026-08-19T16:18:06+09:00",
                "assessed_at": "2026-08-29",
                "assessment_confidence": "high",
                "business_impact": {"score": 7, "rationale": "판매가격에 직접 영향을 줍니다."},
                "urgency": {
                    "score": 6,
                    "rationale": "다음 분기 전에 다시 판단해야 합니다.",
                    "response_deadline": "2026-09-30",
                },
                "baseline_assumption": "세계 수요가 완만하게 회복됩니다.",
                "observed_break": "세계 수요 전망이 49 Mt 낮아졌습니다.",
                "decision_change": "제품·지역별 생산계획을 분리합니다.",
                "falsification_check": "주문잔고와 가격이 기존 계획을 충족하는지 확인합니다.",
            },
            {
                "title": "세계 철강 수요 회복 전망 하향",
                "summary": "세계 수요 전망과 중국 수요가 함께 낮아졌습니다.",
                "analysis_markdown": "## 산문 보고서\n\n산문 본문은 보고서 탭에만 표시됩니다.",
                "source_ids": ["SRC-ONE"],
                "claim_ids": ["CLM-IMPACT", "CLM-DRIVER", "CLM-NEXT"],
            },
            {
                "CLM-IMPACT": {
                    "predicate": "impact_path",
                    "value": "수요 하향 → 가격 압력 → 판매이익",
                    "status": "active",
                    "last_verified": "2026-08-29",
                    "source_ids": ["SRC-ONE"],
                },
                "CLM-DRIVER": {
                    "predicate": "global_demand_revision",
                    "value": "-49 Mt",
                    "status": "active",
                    "last_verified": "2026-04-14",
                    "source_ids": ["SRC-ONE"],
                },
                "CLM-NEXT": {
                    "predicate": "recommended_follow_up",
                    "value": "주문잔고와 계약가격을 대조합니다.",
                    "status": "active",
                    "last_verified": "2026-08-29",
                    "source_ids": ["SRC-ONE"],
                },
            },
            {
                "SRC-ONE": {
                    "title": "공식 수요 전망",
                    "publisher": "공식 기관",
                    "published_at": "2026-04-14",
                }
            },
        )
        rendered = "\n".join(lines)
        structured, narrative = rendered.split('=== "보고서"', 1)
        self.assertNotIn("구조화 데이터 준비 전", rendered)
        for section in (
            "1. 시나리오",
            "2. 사업 영향",
            "3. 키 드라이버",
            "4. 근거와 시점",
            "5. 반증과 다음 행동",
        ):
            self.assertIn(section, structured)
        self.assertIn("**7/10**", structured)
        self.assertIn("수요 하향 → 가격 압력 → 판매이익", structured)
        self.assertIn("-49 Mt", structured)
        self.assertNotIn("global demand revision", structured)
        self.assertIn("핵심 변수 1", structured)
        self.assertIn("확인된 근거 3건 · 원문 1건", structured)
        self.assertIn("단일 출처", structured)
        self.assertIn("주문잔고와 계약가격을 대조합니다.", structured)
        self.assertNotIn("산문 본문은 보고서 탭에만 표시됩니다.", structured)
        self.assertIn("산문 본문은 보고서 탭에만 표시됩니다.", narrative)

    def test_signal_score_rationales_stay_separate_in_ui_json_and_tooltips(self):
        market_sensing.write_json(
            self.root / ".system" / "signals" / "SIG-SCORES.json",
            {
                "signal_id": "SIG-SCORES",
                "insight_id": "INS-SCORES",
                "business_impact": {
                    "score": 9,
                    "rationale": "판매 가능 물량과 계약이익이 함께 바뀝니다.",
                },
                "urgency": {
                    "score": 7,
                    "rationale": "다음 계약 갱신 전에 조건을 확인해야 합니다.",
                },
            },
        )
        market_sensing.write_json(
            self.root / ".system" / "insights" / "INS-SCORES.json",
            {"insight_id": "INS-SCORES", "title": "평가 근거 분리 테스트"},
        )

        item = mkdocs_hooks._signal_ui_item(self.root, "SIG-SCORES")
        self.assertEqual(
            item["business_impact"],
            {
                "score": 9,
                "rationale": "판매 가능 물량과 계약이익이 함께 바뀝니다.",
            },
        )
        self.assertEqual(
            item["urgency"],
            {
                "score": 7,
                "rationale": "다음 계약 갱신 전에 조건을 확인해야 합니다.",
            },
        )

        project_root = Path(__file__).resolve().parents[1]
        script = (
            project_root / "market-sensing-wiki" / "javascripts" / "signal-list.js"
        ).read_text(encoding="utf-8")
        styles = (
            project_root / "market-sensing-wiki" / "stylesheets" / "extra.css"
        ).read_text(encoding="utf-8")
        self.assertIn("assessment?.score", script)
        self.assertIn("assessment?.rationale", script)
        self.assertIn('tooltip.setAttribute("role", "tooltip")', script)
        self.assertIn('group.setAttribute("aria-describedby", tooltip.id)', script)
        self.assertNotIn("signal-score-info", script)
        self.assertNotIn("signal-score-info", styles)
        self.assertIn('group.addEventListener("mouseenter"', script)
        self.assertIn('group.addEventListener("focus"', script)
        self.assertIn("position: fixed", styles)
        self.assertIn("z-index: 1000", styles)

    def test_signal_detail_header_uses_the_available_content_width(self):
        project_root = Path(__file__).resolve().parents[1]
        styles = (
            project_root / "market-sensing-wiki" / "stylesheets" / "extra.css"
        ).read_text(encoding="utf-8")

        self.assertIn(
            ".md-typeset .signal-detail-title,\n"
            ".md-typeset .signal-detail-lede.admonition,\n"
            ".md-typeset .signal-detail-evaluation {",
            styles,
        )
        self.assertIn("width: 100%;\n  max-width: none", styles)

    def test_research_only_phrase_still_requires_full_publication(self):
        project_root = Path(__file__).resolve().parents[1]
        instructions = (project_root / "AGENTS.md").read_text(encoding="utf-8")
        skill = (
            project_root / "skills" / "market-sensing-intelligence" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("`조사만`은 생략 조건이", instructions)
        self.assertIn("`조사만 해줘`도 같은 전체 파이프라인 요청", skill)

    def test_visual_enhancers_have_loading_and_retry_guards(self):
        project_root = Path(__file__).resolve().parents[1]
        impact_script = (
            project_root / "market-sensing-wiki" / "javascripts" / "impact-simulator.js"
        ).read_text(encoding="utf-8")
        mermaid_script = (
            project_root / "market-sensing-wiki" / "javascripts" / "mermaid-theme.js"
        ).read_text(encoding="utf-8")
        styles = (
            project_root / "market-sensing-wiki" / "stylesheets" / "extra.css"
        ).read_text(encoding="utf-8")
        self.assertIn("new MutationObserver(scheduleImpactEnhancement)", impact_script)
        self.assertIn("function quoteFlowchartNodeLabels", mermaid_script)
        self.assertIn(".impact-simulator-data::before", styles)

    def test_mkdocs_projection_reads_sqlite_without_touching_database_files(self):
        database = sqlite_store.database_path(self.root)
        before = (database.stat().st_size, database.stat().st_mtime_ns)
        projection = mkdocs_hooks._projection_data(self.root)
        after = (database.stat().st_size, database.stat().st_mtime_ns)
        self.assertEqual(before, after)
        self.assertEqual([], projection["signals"])
        database.unlink()
        self.assertFalse(database.exists())

    def test_mkdocs_projection_cache_ignores_reader_shm_timestamp_changes(self):
        database = sqlite_store.database_path(self.root)
        first = mkdocs_hooks._projection_data(self.root)
        Path(f"{database}-shm").touch()

        with patch.object(
            mkdocs_hooks,
            "_read_only_connection",
            side_effect=AssertionError("cached projection reopened SQLite"),
        ):
            second = mkdocs_hooks._projection_data(self.root)

        self.assertIs(first, second)

    def test_mkdocs_navigation_exposes_only_market_signals(self):
        database = self.root / "data" / "market_sensing.db"
        with patch.dict(
            "os.environ", {"MYPIN_DATABASE_PATH": str(database)}, clear=False
        ):
            market_sensing.write_json(
                self.root / ".system" / "signals" / "SIG-NAV.json",
                {
                    "signal_id": "SIG-NAV",
                    "insight_id": "INS-NAV",
                    "sentence": "사업 시사점",
                },
            )
            market_sensing.write_json(
                self.root / ".system" / "insights" / "INS-NAV.json",
                {"insight_id": "INS-NAV", "title": "외부 변화"},
            )

            config = {"docs_dir": str(self.root)}
            mkdocs_hooks.on_config(config)

        self.assertEqual(
            config["nav"],
            [
                {"마켓 시그널": [{"전체 시그널": "signals/index.md"}]},
                {"AI 조사": "research/index.md"},
            ],
        )
        navigation = json.loads(
            mkdocs_hooks._signal_navigation_json(mkdocs_hooks._projection_data(self.root))
        )
        self.assertEqual(
            navigation,
            {"items": [{"signal_id": "SIG-NAV", "title": "외부 변화"}]},
        )
        for hidden_label in (
            "홈",
            "최근 변화",
            "동향 보고서",
            "검토 대기",
        ):
            self.assertNotIn(hidden_label, repr(config["nav"]))

    def test_prune_to_signals_preserves_report_and_full_evidence_lineage(self):
        kept_source = {
            "source_id": "SRC-KEEP",
            "title": "보존 원문",
            "source_ids": [],
        }
        removed_source = {
            "source_id": "SRC-REMOVE",
            "title": "미연결 원문",
            "source_ids": [],
        }
        for source in (kept_source, removed_source):
            market_sensing.write_json(
                self.root
                / ".system"
                / "source-records"
                / f"{source['source_id']}.json",
                source,
            )
            sqlite_store.put_source_content(
                self.root,
                source["source_id"],
                f"{source['title']} 본문".encode(),
            )
        market_sensing.write_json(
            self.root / ".system" / "claims" / "CLM-KEEP.json",
            {
                "claim_id": "CLM-KEEP",
                "source_ids": ["SRC-KEEP"],
                "supersedes": ["CLM-HISTORY"],
            },
        )
        market_sensing.write_json(
            self.root / ".system" / "claims" / "CLM-HISTORY.json",
            {"claim_id": "CLM-HISTORY", "source_ids": ["SRC-KEEP"]},
        )
        market_sensing.write_json(
            self.root / ".system" / "claims" / "CLM-REMOVE.json",
            {"claim_id": "CLM-REMOVE", "source_ids": ["SRC-REMOVE"]},
        )
        market_sensing.write_json(
            self.root / ".system" / "insights" / "INS-KEEP.json",
            {
                "insight_id": "INS-KEEP",
                "title": "보존 시그널",
                "analysis_structured": valid_structured_analysis(),
                "analysis_markdown": "## 보고서 결론\n\n보고서 본문입니다.",
                "claim_ids": ["CLM-KEEP"],
                "source_ids": ["SRC-KEEP"],
            },
        )
        market_sensing.write_json(
            self.root / ".system" / "signals" / "SIG-KEEP.json",
            {
                "signal_id": "SIG-KEEP",
                "run_id": "RUN-KEEP",
                "insight_id": "INS-KEEP",
                "claim_ids": ["CLM-KEEP"],
                "source_ids": ["SRC-KEEP"],
            },
        )
        market_sensing.write_json(
            self.root / ".system" / "runs" / "RUN-KEEP.json",
            {"run_id": "RUN-KEEP", "signal_ids": ["SIG-KEEP"]},
        )
        for collection, record_id in (("runs", "RUN-REMOVE"),):
            market_sensing.write_json(
                self.root / ".system" / collection / f"{record_id}.json",
                {f"{collection[:-1]}_id": record_id},
            )
        sqlite_store.put_artifact(
            self.root,
            "report:remove",
            "report",
            "별도 보고서",
            markdown_text="# 별도 보고서",
        )
        sqlite_store.append_operation_log(
            self.root, "2026-08-29T00:00:00+09:00", "remove", "운영 기록"
        )

        preview = market_sensing.prune_to_signals(
            Namespace(root=str(self.root), dry_run=True, backup_path=None)
        )
        self.assertEqual(preview["preserved"]["signals"], 1)
        self.assertEqual(preview["removed"]["claims"], 1)
        self.assertTrue(market_sensing.read_json(
            self.root / ".system" / "claims" / "CLM-REMOVE.json"
        ))

        backup = Path(self.temp_dir.name) / "before-prune.db"
        result = market_sensing.prune_to_signals(
            Namespace(root=str(self.root), dry_run=False, backup_path=str(backup))
        )

        self.assertTrue(backup.is_file())
        self.assertEqual(result["integrity_check"], "ok")
        insight = market_sensing.read_json(
            self.root / ".system" / "insights" / "INS-KEEP.json"
        )
        self.assertIn("보고서 본문", insight["analysis_markdown"])
        self.assertEqual(3, insight["analysis_structured"]["schema_version"])
        self.assertTrue(market_sensing.read_json(
            self.root / ".system" / "claims" / "CLM-KEEP.json"
        ))
        self.assertEqual(
            ["SIG-KEEP"],
            market_sensing.read_json(
                self.root / ".system" / "runs" / "RUN-KEEP.json"
            )["signal_ids"],
        )
        with self.assertRaises(FileNotFoundError):
            market_sensing.read_json(
                self.root / ".system" / "claims" / "CLM-REMOVE.json"
            )
        self.assertIsNotNone(sqlite_store.get_source_content(self.root, "SRC-KEEP"))
        self.assertIsNone(sqlite_store.get_source_content(self.root, "SRC-REMOVE"))
        self.assertEqual([], sqlite_store.list_artifacts(self.root))
        integrity = sqlite_store.integrity(self.root)
        self.assertEqual(
            {"signals": 1, "insights": 1, "claims": 2, "sources": 1, "runs": 1},
            integrity["record_counts"],
        )
        connection = sqlite3.connect(sqlite_store.database_path(self.root))
        try:
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM wiki_operation_log"
                ).fetchone()[0],
            )
        finally:
            connection.close()

    def test_prune_to_signals_can_retain_an_explicit_development_fixture_set(self):
        for suffix in ("A", "B"):
            market_sensing.write_json(
                self.root / ".system" / "source-records" / f"SRC-{suffix}.json",
                {"source_id": f"SRC-{suffix}"},
            )
            market_sensing.write_json(
                self.root / ".system" / "claims" / f"CLM-{suffix}.json",
                {"claim_id": f"CLM-{suffix}", "source_ids": [f"SRC-{suffix}"]},
            )
            market_sensing.write_json(
                self.root / ".system" / "insights" / f"INS-{suffix}.json",
                {
                    "insight_id": f"INS-{suffix}",
                    "claim_ids": [f"CLM-{suffix}"],
                    "source_ids": [f"SRC-{suffix}"],
                },
            )
            market_sensing.write_json(
                self.root / ".system" / "signals" / f"SIG-{suffix}.json",
                {
                    "signal_id": f"SIG-{suffix}",
                    "insight_id": f"INS-{suffix}",
                    "claim_ids": [f"CLM-{suffix}"],
                    "source_ids": [f"SRC-{suffix}"],
                },
            )

        preview = market_sensing.prune_to_signals(
            Namespace(
                root=str(self.root),
                dry_run=True,
                backup_path=None,
                signal_id=["SIG-A"],
            )
        )
        self.assertEqual(1, preview["preserved"]["signals"])
        self.assertEqual(1, preview["removed"]["signals"])

        backup = Path(self.temp_dir.name) / "before-retain.db"
        result = market_sensing.prune_to_signals(
            Namespace(
                root=str(self.root),
                dry_run=False,
                backup_path=str(backup),
                signal_id=["SIG-A"],
            )
        )
        self.assertEqual("retained_selected_signal_lineage", result["action"])
        self.assertTrue(market_sensing.read_json(
            self.root / ".system" / "signals" / "SIG-A.json"
        ))
        with self.assertRaises(FileNotFoundError):
            market_sensing.read_json(
                self.root / ".system" / "signals" / "SIG-B.json"
            )
        integrity = sqlite_store.integrity(self.root)
        self.assertEqual(
            {"signals": 1, "insights": 1, "claims": 1, "sources": 1},
            integrity["record_counts"],
        )


if __name__ == "__main__":
    unittest.main()
