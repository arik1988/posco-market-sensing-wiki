import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools" / "project"))
sys.path.insert(
    0,
    str(REPO_ROOT / "skills" / "market-sensing-intelligence" / "scripts"),
)

import market_sensing  # noqa: E402
import publish_daily_signal_packets as publisher  # noqa: E402
from tests.test_sqlite_market_sensing import (  # noqa: E402
    valid_editorial_analysis,
    valid_structured_analysis,
)


class DailySignalPacketTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "market-sensing-wiki"
        market_sensing.scaffold(self.root)
        market_sensing.scout_run(
            Namespace(
                root=str(self.root),
                run_id="daily-v5",
                date_from="2026-08-29",
                date_to="2026-08-29",
                target_count=None,
                company_id=["COM-POSCO"],
                business_axis=["철강"],
                user_scope="날짜별 발행 Signal 검증",
                coverage_file=None,
                complete=False,
            )
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def packet(self):
        impact_rationale = (
            "공식 기관이 철강 수입 규칙 변경을 발표해 고객 계약과 통관비용이 달라질 수 "
            "있습니다. 가격 전가와 판매물량에 제한적 영향을 주므로 사업영향도는 3점으로 "
            "평가했습니다. 실제 적용 품목과 회사 물량이 확인되지 않아 4점 이상으로 높이지 "
            "않았습니다."
        )
        urgency_rationale = (
            "새 규칙의 발표일과 적용 준비기간이 확인됐습니다. 다음 계약 갱신 전 원산지와 "
            "가격 조항을 확인하면 되므로 긴급도는 3점으로 평가했습니다. 통관 보류나 즉시 "
            "시행이 확인되지 않아 4점 이상으로 높이지 않았습니다. 영업과 통상 담당은 다음 "
            "가격 제시 전에 적용 일정과 증빙 항목을 함께 점검해야 합니다."
        )
        decision = {
            "schema_version": 1,
            "status": "not_applicable",
            "assessed_at": "2026-08-29",
            "basis": (
                "이 Signal은 적용 품목이 확정되기 전의 규칙 분류 변경으로 독립적인 금액 "
                "모델보다 계약 적용 여부 확인이 먼저입니다."
            ),
            "reason_code": "subject_not_quantifiable",
            "required_inputs": ["적용 품목", "고객별 계약 물량"],
            "reconsider_when": "적용 품목과 실제 계약 물량이 확인될 때",
            "related_signal_ids": [],
        }
        structured = valid_structured_analysis()
        for section in structured["sections"]:
            for item in section["items"]:
                if item["key"] == "quantification_decision":
                    item["rows"][0].update(
                        {
                            "status": "not_applicable",
                            "basis": decision["basis"],
                            "next_input": decision["reconsider_when"],
                        }
                    )
        return {
            "candidate_date": "2026-08-29",
            "detected_at": "2026-08-29",
            "source": {
                "title": "철강 수입규칙 변경 공고",
                "url": "https://example.org/steel-rule",
                "publisher": "외부 규제기관",
                "published_at": "2026-08-29",
                "source_type": "government",
                "source_modality": "MARKET",
                "language": "ko",
                "reliability": "primary",
                "raw_markdown": "# 철강 수입규칙 변경\n\n공식 공고 본문을 확인했습니다.",
            },
            "claim": {
                "subject_id": "MKT-DAILY-TEST-20260829-A",
                "predicate": "observed_change",
                "value": "철강 수입규칙 변경이 공고됐다",
                "confidence": "high",
                "as_of": "2026-08-29",
            },
            "signal": {
                "canonical_key": "daily.test.20260829.a",
                "title": "철강 수입규칙 변경 공고",
                "sentence": "포스코는 적용 품목과 고객별 가격 전가 조항을 다시 확인해야 합니다.",
                "paragraph": (
                    "외부 규제기관이 철강 수입규칙 변경을 공고했습니다. 적용 품목에 포함되면 "
                    "통관비용과 고객 계약가격이 달라질 수 있습니다. 포스코는 다음 계약 갱신 전 "
                    "품목별 노출과 전가 조항을 확인해야 합니다."
                ),
                "company_id": "COM-POSCO",
                "business_axis": "철강",
                "signal_type": "정책·규제",
                "signal_role": "core_market_signal",
                "signal_origin": "policy_regulator",
                "business_impact_score": 3,
                "business_impact_rationale": impact_rationale,
                "urgency_score": 3,
                "urgency_rationale": urgency_rationale,
                "assessment_confidence": "high",
                "assessed_at": "2026-08-29",
                "impact_path": "수입규칙 변경 → 적용 품목 → 통관비용 → 계약가격",
                "recommended_follow_up": "적용 품목과 고객별 계약 전가 조항을 확인합니다.",
                "baseline_assumption": "기존 수입규칙이 다음 계약 갱신까지 유지됩니다.",
                "observed_break": "외부 규제기관이 변경 규칙을 공식 공고했습니다.",
                "decision_change": "품목별 통관비용과 판매가격을 다시 승인합니다.",
                "surprise_pattern": "market_access_rule",
                "surprise_score": 3,
                "falsification_check": "포스코 판매 품목이 모두 적용 대상에서 제외되는지 확인합니다.",
            },
            "analysis_markdown": valid_editorial_analysis(),
            "analysis_structured": structured,
            "quantification_decision": decision,
            "discovery": {
                "query": "2026-08-29 steel import rule official",
                "executed_at": "2026-08-29T12:00:00+09:00",
                "channel": "government_action",
                "change_types": ["정책·규제"],
            },
        }

    def test_packet_publishes_and_updates_daily_coverage(self):
        row = self.packet()
        publisher.preflight_rows([row])
        with tempfile.TemporaryDirectory() as temp_name:
            temp_dir = Path(temp_name)
            factor_id = publisher.ensure_risk_factor(str(self.root), row["signal"])
            source_id = publisher.add_packet_source(str(self.root), row, temp_dir)
            claim_ids = publisher.add_packet_claims(
                str(self.root), row, source_id, factor_id
            )
            result = publisher.add_packet_signal(
                str(self.root), "daily-v5", row, claim_ids, factor_id, temp_dir
            )
        publisher.update_coverage(str(self.root), "daily-v5", [(row, result)])

        _, run = market_sensing.run_record_by_id(self.root, "daily-v5")
        self.assertEqual(1, len(run["coverage"]["candidates"]))
        self.assertEqual("published_signal", run["coverage"]["candidates"][0]["disposition"])
        self.assertEqual(result["signal_id"], run["coverage"]["candidates"][0]["signal_id"])
        signal = next(
            value
            for _, value in market_sensing.signal_records(self.root)
            if value["signal_id"] == result["signal_id"]
        )
        findings = market_sensing.evaluate_research_coverage(
            run, [signal]
        )
        self.assertTrue(
            any("daily published Signal availability is 1/3" in item for item in findings)
        )

    def test_preflight_rejects_invalid_pattern_before_writes(self):
        row = self.packet()
        row["signal"]["surprise_pattern"] = "carrier_network_change"

        with self.assertRaisesRegex(ValueError, "packet row 1 failed preflight"):
            publisher.preflight_rows([row])

        self.assertEqual([], market_sensing.source_records(self.root))
        self.assertEqual([], market_sensing.claim_records(self.root))


if __name__ == "__main__":
    unittest.main()
