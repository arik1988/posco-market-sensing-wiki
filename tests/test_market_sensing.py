import json
import re
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "market-sensing-intelligence"
    / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))

import market_sensing  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_TOOLS = PROJECT_ROOT / "tools" / "project"
sys.path.insert(0, str(PROJECT_TOOLS))
import mkdocs_hooks  # noqa: E402
import apply_editorial_rewrite  # noqa: E402


class MarketSensingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "market-sensing-wiki"
        market_sensing.scaffold(self.root)
        market_sensing.write_json(
            self.root / ".system" / "runs" / "test-run.json",
            {"run_id": "test-run", "results": {"new_claims": 0, "new_signals": 0}},
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_project_instructions_require_end_to_end_signal_publication(self):
        agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        template = (
            PROJECT_ROOT
            / "skills"
            / "market-sensing-intelligence"
            / "references"
            / "signal-analysis-template.md"
        ).read_text(encoding="utf-8")
        scaffold_agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Source·Claim만 만들거나", agents)
        self.assertIn("add-signal", agents)
        self.assertIn("Codex 앱 브라우저", agents)
        self.assertIn("영향액을 숫자로 먼저", agents)
        self.assertIn("핵심 가정 3~8개", agents)
        self.assertIn("set-impact-estimate", agents)
        self.assertIn("상세 분석을 별도 보고서 링크 하나로 대신", template)
        for heading in (
            "의사결정급 Insight 계약",
            "판단 질문과 잠정 결론",
            "통념과 확인된 간극",
            "확인된 변화와 시점",
            "사업 시나리오",
            "지금 확인할 지표",
            "결론을 확정·폐기할 조건",
            "의사결정에 필요한 다음 산출물",
            "판단의 한계",
            "What-if와 자체 계산 계약",
            "여러 Signal을 현안으로 묶는 기준",
        ):
            self.assertIn(heading, template)
        for contract in (
            "판단을 바꾸는 간극",
            "확정·폐기할 반증 조건",
            "담당, 기한, 감지 트리거",
            "같은 의사결정 하나로 수렴",
            "회사 실제 원가·계약",
            "관측된 외부 변화",
            "사업 시사점",
            "정책·규제",
            "사업축 pill 1개",
        ):
            self.assertIn(contract, agents)
        self.assertIn("사업 시사점", scaffold_agents)
        self.assertIn("재무·실적", scaffold_agents)

    def source_args(self, content_file, title, url, force=False):
        return Namespace(
            root=str(self.root),
            content_file=str(content_file),
            title=title,
            url=url,
            publisher="Example Steel",
            published_at="2026-07-21",
            collected_at="2026-07-25",
            source_type="company_release",
            language="en",
            reliability="primary",
            academic=None,
            supporting_of=None,
            force=force,
        )

    def test_claim_stage_treats_completed_facility_with_production_start_as_operating(self):
        stage, _ = market_sensing.claim_stage(
            "2026년 6월 준공해 저탄소강 생산을 개시했다."
        )
        self.assertEqual(stage, "가동·현장 적용")

    def test_index_is_the_only_home_projection(self):
        self.assertTrue((self.root / "index.md").is_file())
        self.assertFalse((self.root / "HOME.md").exists())
        self.assertFalse(
            (self.root / "REVIEW.md").read_text(encoding="utf-8").endswith(
                "\n\n"
            )
        )
        report_index = (
            self.root / "reports" / "index.md"
        ).read_text(encoding="utf-8")
        self.assertIn('!!! abstract "현재 발행 상태"', report_index)
        self.assertIn("아직 발행된 동향 보고서가 없습니다.", report_index)
        self.assertIn("## 보고서에서 바로 확인할 내용", report_index)
        self.assertIn("## 읽는 순서", report_index)

        legacy_home = self.root / "HOME.md"
        legacy_home.write_text("legacy duplicate\n", encoding="utf-8")
        market_sensing.sync_obsidian_store(self.root)

        self.assertFalse(legacy_home.exists())
        self.assertIn(
            "# 포스코그룹 마켓센싱",
            (self.root / "index.md").read_text(encoding="utf-8"),
        )

    def claim_args(self, source_id, value):
        return Namespace(
            root=str(self.root),
            subject_id="PRJ-EXAMPLE-DRI",
            predicate="target_start_date",
            value=value,
            source_id=[source_id],
            confidence="medium",
            as_of="2026-07-25",
            reason="Official project update",
        )

    def valid_signal_analysis(self) -> str:
        return (
            "## 확인된 변화\n정책 시행으로 비용 조건이 바뀌었습니다. "
            + "확인된 사실과 시점을 구분합니다. " * 20
            + "\n## 사업 영향 경로\n가격과 계약을 거쳐 판매 마진에 전달됩니다. "
            + "전달 조건과 영향을 설명합니다. " * 20
            + "\n## 조건부 시나리오\n\n"
            + "| 시나리오 | 관찰 조건 | 사업 의미 | 우선 대응 |\n"
            + "| --- | --- | --- | --- |\n"
            + "| 방어 | 조건 A | 의미 A | 대응 A |\n"
            + "| 압박 | 조건 B | 의미 B | 대응 B |\n"
            + "| 재배치 | 조건 C | 의미 C | 대응 C |\n\n"
            + "각 조건과 대응을 구분합니다. " * 15
            + "\n## 지금 확인할 지표\n"
            + "- 가격 — 마진 판단 변경\n- 물량 — 판매 판단 변경\n"
            + "- 계약 만기 — 대응시점 변경\n"
            + "판단을 바꾸는 지표를 설명합니다. " * 15
            + "\n## 의사결정에 필요한 다음 산출물\n"
            + "1. 고객별 민감도\n2. 선택지 비교표\n3. 대응 조건표\n"
            + "실행 가능한 산출물을 정의합니다. " * 15
            + '\n!!! warning "판단의 한계"\n\n'
            + "    내부 원가와 계약정보가 필요합니다. "
            + "공개정보의 한계를 명시합니다. " * 15
        )

    def test_signal_graph_has_four_progressive_depths_and_reader_projection(self):
        content = self.root.parent / "signal-source.md"
        content.write_text(
            "A binding policy changes delivered cost from 2027.", encoding="utf-8"
        )
        source = market_sensing.add_source(
            self.source_args(content, "Binding policy", "https://example.com/policy")
        )
        claim = market_sensing.add_claim(
            self.claim_args(source["source_id"], "2027")
        )
        assessment_claim_ids = []
        for predicate, value in (
            ("business_axis", "철강"),
            ("business_impact_score_1_to_5", "5"),
            ("business_impact_rationale", "판매 마진에 직접 영향"),
            ("urgency_score_1_to_5", "4"),
            ("urgency_rationale", "시행 전 계약 확인 필요"),
            ("assessment_confidence", "medium"),
            ("assessed_at", "2026-08-18"),
            ("impact_path", "정책 변화에서 계약과 판매 마진으로 전달"),
            ("recommended_follow_up", "고객별 원가 민감도 작성"),
        ):
            created_claim = market_sensing.add_claim(
                Namespace(
                    root=str(self.root),
                    subject_id="COM-POSCO",
                    predicate=predicate,
                    value=value,
                    source_id=[source["source_id"]],
                    confidence="medium",
                    as_of="2026-08-18",
                    reason="Signal assessment contract test",
                )
            )
            assessment_claim_ids.append(created_claim["claim_id"])
        document = self.root / "reports" / "briefs" / "decision-note.md"
        document.write_text("# 의사결정 분석\n\n상세 영향 경로", encoding="utf-8")
        analysis = self.root.parent / "signal-analysis.md"
        analysis.write_text(
            self.valid_signal_analysis(),
            encoding="utf-8",
        )
        created = market_sensing.add_signal(
            Namespace(
                root=str(self.root),
                run_id="test-run",
                title="EU 철강 수입쿼터 축소",
                sentence="EU 조치로 고객별 계약 갱신일과 가격 전가 범위를 다시 확인해야 합니다.",
                signal_type="정책·규제",
                paragraph=(
                    "정부가 2027년부터 적용할 새 정책을 발표해 수입 철강의 도착원가가 "
                    "달라집니다. 포스코는 고객별 계약 갱신일과 가격 전가 가능 범위를 "
                    "확인해 판매 마진을 다시 계산해야 합니다."
                ),
                document_path="reports/briefs/decision-note.md",
                analysis_file=str(analysis),
                company_id=["COM-POSCO"],
                business_axis="철강",
                claim_id=[claim["claim_id"], *assessment_claim_ids],
                business_impact_score=5,
                business_impact_rationale="판매 마진에 직접 영향",
                urgency_score=4,
                urgency_rationale="시행 전 계약 확인 필요",
                response_deadline="2026-12-31",
                assessed_at="2026-08-18",
                assessment_confidence="medium",
            )
        )

        traces = [
            market_sensing.trace_signal(
                Namespace(
                    root=str(self.root), signal_id=created["signal_id"], depth=depth
                )
            )
            for depth in range(1, 5)
        ]
        self.assertNotIn("insight", traces[0])
        self.assertIn("insight", traces[1])
        self.assertNotIn("claims", traces[1])
        self.assertIn("document", traces[2])
        self.assertIn("claims", traces[2])
        self.assertNotIn("sources", traces[2])
        self.assertEqual(traces[3]["sources"][0]["url"], "https://example.com/policy")
        self.assertIn("binding policy", traces[3]["sources"][0]["archive_excerpt"].lower())
        self.assertIn("claims_to_sources", traces[3]["edges"])

        page = (self.root / "signals" / f"{created['signal_id']}.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## 왜 중요한가", page)
        self.assertIn("## 상세 분석", page)
        self.assertIn("## 원문", page)
        self.assertNotIn("전체 읽기", page)
        self.assertNotIn(created["signal_id"], page)
        self.assertNotIn(claim["claim_id"], page)
        self.assertNotIn("raw_path", page)
        run = market_sensing.run_record_by_id(self.root, "test-run")[1]
        self.assertEqual(run["results"]["new_signals"], 1)
        self.assertIn(created["signal_id"], run["signal_ids"])
        signal_record = market_sensing.read_json(
            self.root / ".system" / "signals" / f"{created['signal_id']}.json"
        )
        self.assertEqual(
            signal_record["schema_version"], market_sensing.SIGNAL_SCHEMA_VERSION
        )
        self.assertEqual(signal_record["signal_type"], "정책·규제")
        audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        for category in (
            "signal_schema",
            "signal_integrity",
            "signal_quality",
            "unpublished_claims",
            "unpublished_sources",
            "run_publication",
        ):
            self.assertEqual(audit["counts"][category], 0)

    def test_signal_rejects_invalid_score(self):
        document = self.root / "reports" / "briefs" / "decision-note.md"
        document.write_text("# 분석", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            market_sensing.add_signal(
                Namespace(
                    root=str(self.root), title="t", sentence="s", paragraph="p",
                    run_id="test-run",
                    signal_type="정책·규제",
                    document_path="reports/briefs/decision-note.md",
                    company_id=["COM-POSCO"], business_axis="철강",
                    claim_id=["missing"], business_impact_score=6,
                    business_impact_rationale="r", urgency_score=1,
                    urgency_rationale="r", response_deadline=None,
                    assessed_at="2026-08-18", assessment_confidence="medium",
                )
            )

    def test_signal_analysis_rejects_template_shaped_but_thin_content(self):
        thin = (
            "## 확인된 변화\n짧음\n## 사업 영향 경로\n짧음\n"
            "## 사업 시나리오\n시나리오\n## 지금 확인할 지표\n- 하나\n"
            "## 의사결정에 필요한 다음 산출물\n1. 하나\n"
            '!!! warning "판단의 한계"\n\n    짧음'
        )
        with self.assertRaisesRegex(ValueError, "at least 1200 characters"):
            market_sensing.validate_signal_analysis(thin)

    def test_signal_copy_rejects_opaque_translated_headline(self):
        with self.assertRaisesRegex(ValueError, "jargon"):
            market_sensing.validate_signal_copy(
                "Atlas first gas의 상업화 전환",
                "Atlas 가스전이 첫 생산을 시작해 증산 일정이 다음 단계로 넘어갔습니다.",
                "Atlas 가스전이 첫 생산을 시작했습니다. Senex는 생산량과 판매계약 반영 "
                "시점을 확인해 증산 물량이 실제 매출로 이어지는 시기를 판단해야 합니다.",
            )

    def test_signal_copy_accepts_plain_observed_change_title(self):
        market_sensing.validate_signal_copy(
            "Atlas 가스전 첫 생산 시작",
            "Atlas 가스전이 첫 생산을 시작해 Senex의 증산 계획이 실행 단계에 들어갔습니다.",
            "Atlas 가스전이 첫 생산을 시작했습니다. Senex는 생산량과 판매계약 반영 "
            "시점을 확인해 증산 물량이 실제 매출로 이어지는 시기를 판단해야 합니다.",
        )

    def test_signal_copy_rejects_headline_style_ellipsis(self):
        with self.assertRaisesRegex(ValueError, "headline-style ellipsis"):
            market_sensing.validate_signal_copy(
                "Atlas 가스전 첫 생산…Senex 증산 본격화",
                "Atlas 가스전이 첫 생산을 시작해 Senex의 증산 계획이 실행 단계에 들어갔습니다.",
                "Atlas 가스전이 첫 생산을 시작했습니다. Senex는 생산량과 판매계약 반영 "
                "시점을 확인해 증산 물량이 실제 매출로 이어지는 시기를 판단해야 합니다.",
            )

    def test_signal_copy_rejects_recommendation_in_observed_change_title(self):
        with self.assertRaisesRegex(ValueError, "not a business implication"):
            market_sensing.validate_signal_copy(
                "EU 철강 수입규제로 판매 경제성 재산정 필요",
                "EU 조치로 고객별 계약 갱신일과 가격 전가 범위를 다시 확인해야 합니다.",
                "EU가 철강 수입쿼터를 줄였습니다. 포스코는 고객별 계약 갱신일과 "
                "가격 전가 범위를 확인해 유럽 판매 판단을 다시 해야 합니다.",
            )

    def test_signal_copy_rejects_opaque_lead_even_with_plain_title(self):
        with self.assertRaisesRegex(ValueError, "lead contains"):
            market_sensing.validate_signal_copy(
                "Atlas 가스전 첫 생산 시작",
                "Atlas first gas가 확인돼 상업화 게이트를 통과했습니다.",
                "Atlas 가스전에서 첫 생산이 시작됐습니다. Senex는 실제 생산량과 "
                "판매계약 반영 시점을 확인해 매출 인식 시기를 판단해야 합니다.",
            )

    def test_signal_type_requires_the_governed_enum(self):
        self.assertEqual(
            market_sensing.SIGNAL_TYPES,
            (
                "정책·규제",
                "수급·가격",
                "경쟁사",
                "투자·프로젝트",
                "공급망·물류",
                "고객·계약",
                "기술·운영",
                "재무·실적",
            ),
        )
        self.assertEqual(market_sensing.validate_signal_type("수급·가격"), "수급·가격")
        with self.assertRaisesRegex(ValueError, "signal_type must be one of"):
            market_sensing.validate_signal_type("시장 동향")

    def test_signal_analysis_rejects_opaque_intro_without_reducing_depth(self):
        opaque = self.valid_signal_analysis().replace(
            "정책 시행으로 비용 조건이 바뀌었습니다.",
            "램프업 게이트와 트리거가 바뀌었습니다.",
            1,
        )
        with self.assertRaisesRegex(ValueError, "analysis lead contains"):
            market_sensing.validate_signal_analysis(opaque)

    def test_editorial_migration_applies_schema_v2_and_type_atomically(self):
        signal_id = "SIG-LEGACY"
        insight_id = "INS-LEGACY"
        signal_path = self.root / ".system" / "signals" / f"{signal_id}.json"
        insight_path = self.root / ".system" / "insights" / f"{insight_id}.json"
        original_signal = {
            "schema_version": 1,
            "signal_id": signal_id,
            "sentence": "기존 사업 판단 문장입니다.",
            "insight_id": insight_id,
            "company_ids": ["COM-POSCO"],
            "business_axis": "철강",
            "claim_ids": ["CLM-KEEP"],
            "source_ids": ["SRC-KEEP"],
        }
        original_insight = {
            "schema_version": 1,
            "insight_id": insight_id,
            "title": "기존 관측 변화 제목",
            "summary": "기존 요약입니다.",
            "analysis_markdown": self.valid_signal_analysis(),
            "claim_ids": ["CLM-KEEP"],
            "source_ids": ["SRC-KEEP"],
        }
        market_sensing.write_json(signal_path, original_signal)
        market_sensing.write_json(insight_path, original_insight)
        legacy_audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        legacy_report = (self.root / legacy_audit["report"]).read_text(encoding="utf-8")
        self.assertIn("schema_version must be 2", legacy_report)
        self.assertIn("signal_type must be one of", legacy_report)
        with self.assertRaisesRegex(ValueError, "complete current Signal set"):
            apply_editorial_rewrite.apply_proposals(
                [], self.root, self.root.parent / "partial-backup.json"
            )
        proposal_path = self.root.parent / "migration.json"
        market_sensing.write_json(
            proposal_path,
            {
                "items": [
                    {
                        "signal_id": signal_id,
                        "old_title": "기존 관측 변화 제목",
                        "title": "EU 철강 수입쿼터 축소",
                        "sentence": "EU 조치로 고객별 계약 갱신일과 가격 전가 범위를 다시 확인해야 합니다.",
                        "signal_type": "정책·규제",
                        "summary": (
                            "EU가 철강 수입쿼터를 줄였습니다. 포스코는 고객별 계약 갱신일과 "
                            "가격 전가 범위를 확인해 유럽 판매 판단을 다시 해야 합니다."
                        ),
                        "analysis_markdown": self.valid_signal_analysis(),
                    }
                ]
            },
        )
        proposals, errors = apply_editorial_rewrite.validate_proposals(
            [proposal_path], self.root
        )
        self.assertEqual(errors, [])
        backup = self.root.parent / "before-migration.json"
        apply_editorial_rewrite.apply_proposals(proposals, self.root, backup)

        migrated_signal = market_sensing.read_json(signal_path)
        migrated_insight = market_sensing.read_json(insight_path)
        self.assertEqual(migrated_signal["schema_version"], 2)
        self.assertEqual(migrated_signal["signal_type"], "정책·규제")
        self.assertEqual(migrated_signal["claim_ids"], ["CLM-KEEP"])
        self.assertEqual(migrated_insight["title"], "EU 철강 수입쿼터 축소")
        self.assertEqual(migrated_insight["source_ids"], ["SRC-KEEP"])

        before_signal = signal_path.read_text(encoding="utf-8")
        before_insight = insight_path.read_text(encoding="utf-8")
        retry_proposals = [
            {**proposal, "old_title": migrated_insight["title"]}
            for proposal in proposals
        ]
        call_count = 0
        original_write_json = market_sensing.write_json

        def fail_second_write(path, value):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise OSError("simulated migration write failure")
            return original_write_json(path, value)

        with mock.patch.object(
            apply_editorial_rewrite.market_sensing,
            "write_json",
            side_effect=fail_second_write,
        ):
            with self.assertRaisesRegex(OSError, "simulated"):
                apply_editorial_rewrite.apply_proposals(
                    retry_proposals, self.root, backup
                )
        self.assertEqual(signal_path.read_text(encoding="utf-8"), before_signal)
        self.assertEqual(insight_path.read_text(encoding="utf-8"), before_insight)

    def test_audit_reports_active_claims_not_published_as_signals(self):
        content = self.root.parent / "orphan-source.md"
        content.write_text("verified policy fact", encoding="utf-8")
        source = market_sensing.add_source(
            self.source_args(content, "Policy fact", "https://example.com/fact")
        )
        claim = market_sensing.add_claim(self.claim_args(source["source_id"], "2028"))
        run_path, run = market_sensing.run_record_by_id(self.root, "test-run")
        run["results"]["new_claims"] = 1
        market_sensing.write_json(run_path, run)
        audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        self.assertEqual(audit["counts"]["unpublished_claims"], 1)
        self.assertEqual(audit["counts"]["unpublished_sources"], 1)
        self.assertEqual(audit["counts"]["run_publication"], 1)
        report = (self.root / audit["report"]).read_text(encoding="utf-8")
        self.assertIn(claim["claim_id"], report)

    def test_markdown_settings_preserve_wrapped_list_items(self):
        settings_file = self.root.parent / "settings.md"
        settings_file.write_text(
            "## 보고서 중점\n\n- 첫 문장\n  다음 줄도 같은 설정\n- 둘째 항목\n",
            encoding="utf-8",
        )
        parsed = market_sensing.parse_markdown_settings(settings_file)
        self.assertEqual(
            parsed["report_sections"],
            ["첫 문장 다음 줄도 같은 설정", "둘째 항목"],
        )

    def test_mkdocs_wikilinks_are_page_relative(self):
        markdown = (
            "[[index|홈]] "
            "[[sources/SRC-EXAMPLE|근거]] "
            "[[#한눈에-보기|이 문서의 요약]]"
        )
        rendered = mkdocs_hooks.convert_wikilinks(
            markdown,
            r"companies\COM-Example-Steel.md",
        )
        self.assertEqual(
            rendered,
            "[홈](../index.md) "
            "[근거](../sources/SRC-EXAMPLE.md) "
            "[이 문서의 요약](#한눈에-보기)",
        )

    def test_company_source_reference_uses_compact_link_label(self):
        reference = market_sensing.source_reference(
            "SRC-EXAMPLE",
            {
                "SRC-EXAMPLE": {
                    "publisher": "Example Steel",
                    "published_at": "2026-07-21",
                }
            },
        )
        self.assertEqual(
            reference,
            "[[sources/SRC-EXAMPLE|:material-link-variant:]]",
        )

    def test_academic_source_metadata_is_searchable_and_rendered(self):
        content = self.root.parent / "conference-paper.md"
        content.write_text(
            "# Hydrogen reduction pilot results\n\nPilot campaign details.",
            encoding="utf-8",
        )
        args = self.source_args(
            content,
            "Hydrogen reduction pilot results",
            "https://doi.org/10.1234/example.2026.001",
        )
        args.source_type = "academic"
        args.publisher = "AIST"
        args.academic_kind = "conference_paper"
        args.author = ["A. Researcher", "B. Engineer"]
        args.venue = "AISTech 2026 Proceedings"
        args.doi = "https://doi.org/10.1234/example.2026.001"
        args.conference_name = "AISTech 2026"
        args.conference_date = "2026-05-04"
        args.conference_location = "Pittsburgh, USA"
        args.peer_review_status = "peer_reviewed"

        result = market_sensing.add_source(args)
        source_id = result["source_id"]
        record = market_sensing.source_record_by_id(self.root, source_id)[1]

        self.assertEqual(record["academic"]["kind"], "conference_paper")
        self.assertEqual(record["academic"]["doi"], "10.1234/example.2026.001")
        source_page = (self.root / "sources" / f"{source_id}.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## 학술 정보", source_page)
        self.assertIn("학회 논문", source_page)
        self.assertIn("AISTech 2026", source_page)
        self.assertIn("https://doi.org/10.1234/example.2026.001", source_page)

        search_result = market_sensing.search_store(
            Namespace(root=str(self.root), query="AISTech", limit=10)
        )
        self.assertEqual(search_result["sources"][0]["source_id"], source_id)
        self.assertEqual(
            search_result["sources"][0]["academic"]["kind"],
            "conference_paper",
        )

    def test_academic_source_requires_kind_and_valid_doi(self):
        content = self.root.parent / "paper.md"
        content.write_text("paper body", encoding="utf-8")
        args = self.source_args(content, "Paper", "https://example.com/paper")
        args.source_type = "academic"
        with self.assertRaisesRegex(ValueError, "require --academic-kind"):
            market_sensing.add_source(args)

        args.academic_kind = "journal_article"
        args.doi = "not-a-doi"
        with self.assertRaisesRegex(ValueError, "Invalid DOI"):
            market_sensing.add_source(args)

    def test_set_academic_metadata_enriches_existing_source(self):
        content = self.root.parent / "legacy-paper.md"
        content.write_text("legacy paper body", encoding="utf-8")
        args = self.source_args(
            content, "Legacy paper", "https://example.com/legacy-paper"
        )
        args.source_type = "academic"
        args.academic_kind = "journal_article"
        created = market_sensing.add_source(args)

        result = market_sensing.set_academic_metadata(
            Namespace(
                root=str(self.root),
                source_id=created["source_id"],
                academic=None,
                academic_kind="journal_article",
                author=["First Author", "Second Author"],
                venue="Journal of Green Iron",
                doi="https://doi.org/10.1234/green.iron",
                conference_name=None,
                conference_date=None,
                conference_location=None,
                peer_review_status="peer_reviewed",
                published_at="2024-02-03",
            )
        )

        self.assertEqual(result["academic"]["doi"], "10.1234/green.iron")
        self.assertEqual(
            result["academic"]["authors"], ["First Author", "Second Author"]
        )
        record = market_sensing.source_record_by_id(
            self.root, created["source_id"]
        )[1]
        self.assertEqual(record["published_at"], "2024-02-03")
        page = (
            self.root / "sources" / f"{created['source_id']}.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Journal of Green Iron", page)
        self.assertIn("First Author, Second Author", page)

    def test_audit_detects_invalid_academic_metadata(self):
        content = self.root.parent / "audit-paper.md"
        content.write_text("paper body", encoding="utf-8")
        args = self.source_args(content, "Paper", "https://example.com/paper")
        args.source_type = "academic"
        args.academic_kind = "journal_article"
        result = market_sensing.add_source(args)
        record_path, record = market_sensing.source_record_by_id(
            self.root, result["source_id"]
        )
        record["academic"]["kind"] = "conference"
        record["academic"]["doi"] = "bad-doi"
        market_sensing.write_json(record_path, record)

        audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        self.assertEqual(audit["counts"]["source_schema"], 2)
        report = (self.root / audit["report"]).read_text(encoding="utf-8")
        self.assertIn("invalid academic kind", report)
        self.assertIn("invalid DOI", report)

    def test_technology_navigation_is_collapsed_and_marks_current_page(self):
        settings = {
            "technologies": [
                "hydrogen direct reduced iron",
                "electric smelting furnace",
                "molten oxide electrolysis",
            ]
        }
        markdown = "\n".join(
            market_sensing.technology_navigation_lines(
                "electric smelting furnace",
                settings,
            )
        )

        self.assertIn(
            '??? info "관련 기술 바로가기 · 현재 위치: 환원·용융 경로"',
            markdown,
        )
        self.assertNotIn("???+ info", markdown)
        self.assertIn(
            "**전기용융로 (Electric Smelting Furnace) · 현재**",
            markdown,
        )
        self.assertIn(
            "[[technologies/TEC-hydrogen-direct-reduced-iron"
            "|수소 직접환원철 (Hydrogen DRI)]]",
            markdown,
        )
        self.assertIn("**전해 기반 경로**", markdown)

    def test_technology_dossier_renders_generic_deep_profile(self):
        claims_by_subject = {
            "TEC-molten-oxide-electrolysis": [
                {
                    "predicate": "technical_definition",
                    "value": "용융 산화물에서 철과 산소를 직접 생산",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": ["SRC-ACADEMIC"],
                },
                {
                    "predicate": "core_reaction",
                    "value": "Fe2O3 -> 2Fe + 1.5O2",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": ["SRC-ACADEMIC"],
                },
                {
                    "predicate": "energy_intensity_estimate",
                    "value": "성숙 설비 가정 2.89-4.45 kWh/kg Fe",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": ["SRC-ACADEMIC"],
                },
                {
                    "predicate": "unclassified_validation_note",
                    "value": "40 kt/y 모듈을 조합해 최대 800 kt/y까지 확대할 계획",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": ["SRC-ACADEMIC"],
                },
            ]
        }
        sources = {
            "SRC-ACADEMIC": {
                "source_id": "SRC-ACADEMIC",
                "title": "Academic MOE study",
                "publisher": "Example Journal",
                "published_at": "2026-07-07",
                "collected_at": "2026-07-25",
                "source_type": "academic",
                "url": "https://example.com/moe",
            }
        }

        markdown = "\n".join(
            market_sensing.technology_company_dossier_lines(
                "molten oxide electrolysis",
                {"companies": [], "technologies": ["molten oxide electrolysis"]},
                claims_by_subject,
                sources,
            )
        )

        self.assertIn("### 반응·셀·공정", markdown)
        self.assertIn("| **총괄 반응** | Fe2O3 -> 2Fe + 1.5O2", markdown)
        self.assertIn("### 에너지·환경·경제", markdown)
        self.assertIn("성숙 설비 가정 2.89-4.45 kWh/kg Fe", markdown)
        self.assertIn("### 최신 실증·검증 정보", markdown)
        self.assertIn("40 kt/y 모듈을 조합해 최대 800 kt/y", markdown)
        self.assertIn("## 12–36개월 기술 센싱 대시보드", markdown)
        self.assertIn("### 성숙도 승격 신호", markdown)
        self.assertIn("### 지연·실패 신호", markdown)
        self.assertIn("### POSCO 판단 질문", markdown)
        self.assertIn("| 학술 연구 |", markdown)
        self.assertNotIn("고온 용융염 전기분해가 아니라", markdown)

    def test_all_future_technology_pages_have_strategy_sensing_framework(self):
        self.assertEqual(
            set(market_sensing.TECHNOLOGY_DETAILS),
            set(market_sensing.TECHNOLOGY_SENSING_DASHBOARDS),
        )
        for technology, dashboard in market_sensing.TECHNOLOGY_SENSING_DASHBOARDS.items():
            with self.subTest(technology=technology):
                self.assertGreaterEqual(len(dashboard["leading_indicators"]), 3)
                self.assertGreaterEqual(len(dashboard["warning_signals"]), 2)
                self.assertGreaterEqual(len(dashboard["decision_questions"]), 3)

    def test_mkdocs_navigation_is_market_sensing_first(self):
        (self.root / "companies" / "COM-POSCO.md").write_text(
            "# POSCO 기술 현황\n",
            encoding="utf-8",
        )
        (self.root / "companies" / "COM-Zeta.md").write_text(
            "# Zeta Steel 기술 현황\n",
            encoding="utf-8",
        )
        (self.root / "technologies" / "TEC-hydrogen-dri.md").write_text(
            "# 수소 직접환원철 (Hydrogen DRI)\n",
            encoding="utf-8",
        )
        (self.root / "projects" / "PRJ-hydrogen-dri.md").write_text(
            "# 수소 직접환원철 프로젝트\n",
            encoding="utf-8",
        )
        config = {"docs_dir": str(self.root)}
        mkdocs_hooks.on_config(config)
        self.assertEqual(config["nav"][0], {"홈": "index.md"})
        self.assertEqual(
            config["nav"][1],
            {"마켓 시그널": [{"전체 시그널": "signals/index.md"}]},
        )
        self.assertEqual(config["nav"][2], {"최근 변화": "recent-updates.md"})
        self.assertNotIn("HOME.md", repr(config["nav"]))
        self.assertNotIn("기술별 현황", repr(config["nav"]))
        self.assertNotIn("사업영향", repr(config["nav"]))
        self.assertNotIn("기업별 현황", repr(config["nav"]))
        self.assertNotIn("프로젝트 변화", repr(config["nav"]))
        self.assertNotIn("프로젝트 진행", repr(config["nav"]))
        self.assertNotIn("projects/", repr(config["nav"]))
        self.assertNotIn("sources", str(config["nav"]))

    def test_mkdocs_navigation_exposes_trend_reports_but_not_audits(self):
        (self.root / "reports" / "index.md").write_text(
            "# 동향 보고서\n",
            encoding="utf-8",
        )
        (self.root / "reports" / "briefs" / "brief-2026-07-24.md").write_text(
            "# 일일 철강 기술 동향\n",
            encoding="utf-8",
        )
        (self.root / "reports" / "audits" / "audit-2026-07-25.md").write_text(
            "# Market Sensing Intelligence Audit\n",
            encoding="utf-8",
        )
        (
            self.root / "reports" / "academic-landscape-2026.md"
        ).write_text(
            "# 철강 신기술 논문·학회 근거 지형 2026\n",
            encoding="utf-8",
        )

        config = {"docs_dir": str(self.root)}
        mkdocs_hooks.on_config(config)

        trend_nav = next(
            item["동향 보고서"]
            for item in config["nav"]
            if "동향 보고서" in item
        )
        self.assertEqual(
            trend_nav[0],
            {"동향 보고서 안내": "reports/index.md"},
        )
        self.assertIn(
            {"일일 철강 기술 동향": "reports/briefs/brief-2026-07-24.md"},
            trend_nav,
        )
        self.assertIn(
            {
                "철강 신기술 논문·학회 근거 지형 2026":
                "reports/academic-landscape-2026.md"
            },
            trend_nav,
        )
        self.assertNotIn("audit-", repr(config["nav"]))

    def test_mkdocs_navigation_shortens_and_sorts_half_year_reports(self):
        older_report = (
            self.root / "reports" / "briefs" / "brief-2025-h2.md"
        )
        older_report.write_text(
            "---\n"
            "date: 2025-12-31\n"
            "---\n"
            "# 2025년 하반기 철강 신기술·프로젝트 동향\n",
            encoding="utf-8",
        )
        newer_report = (
            self.root / "reports" / "briefs" / "brief-2026-h1.md"
        )
        newer_report.write_text(
            "---\n"
            "date: 2026-07-25\n"
            "---\n"
            "# 2026년 상반기 철강 신기술·프로젝트 동향\n",
            encoding="utf-8",
        )

        config = {"docs_dir": str(self.root)}
        mkdocs_hooks.on_config(config)

        trend_nav = next(
            item["동향 보고서"]
            for item in config["nav"]
            if "동향 보고서" in item
        )
        self.assertEqual(
            trend_nav[-2:],
            [
                {"2026년 상반기 동향": "reports/briefs/brief-2026-h1.md"},
                {"2025년 하반기 동향": "reports/briefs/brief-2025-h2.md"},
            ],
        )

    def test_mermaid_contrast_fallback_is_loaded(self):
        config = (PROJECT_TOOLS / "mkdocs.yml").read_text(encoding="utf-8")
        theme = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "javascripts"
            / "mermaid-theme.js"
        ).read_text(encoding="utf-8")
        fallback = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "javascripts"
            / "mermaid-contrast.js"
        ).read_text(encoding="utf-8")

        self.assertIn("javascripts/mermaid-theme.js", config)
        self.assertIn("javascripts/mermaid-contrast.js", config)
        self.assertIn("pymdownx.superfences.fence_div_format", config)
        self.assertIn('primaryColor: "#edf2fb"', theme)
        self.assertIn('primaryBorderColor: "#3f66c9"', theme)
        self.assertIn('lineColor: "#6c737e"', theme)
        self.assertIn("startOnLoad: false", theme)
        self.assertIn("window.mermaid.run", theme)
        self.assertIn('document$.subscribe(() => scheduleMermaidRendering())', theme)
        self.assertIn('.mermaid:not([data-processed="true"])', theme)
        self.assertIn("MINIMUM_CONTRAST = 4.5", fallback)
        self.assertIn('style.setProperty("color"', fallback)
        self.assertIn('style.setProperty("fill"', fallback)

    def test_mermaid_fullscreen_viewer_is_loaded(self):
        config = (PROJECT_TOOLS / "mkdocs.yml").read_text(encoding="utf-8")
        viewer = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "javascripts"
            / "mermaid-viewer.js"
        ).read_text(encoding="utf-8")
        styles = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "stylesheets"
            / "extra.css"
        ).read_text(encoding="utf-8")

        self.assertIn("javascripts/mermaid-viewer.js", config)
        self.assertIn('button.setAttribute("title", "전체보기")', viewer)
        self.assertIn("mermaid-viewer-panel", viewer)
        self.assertIn('canvas.addEventListener("wheel"', viewer)
        self.assertIn('canvas.addEventListener("pointerdown"', viewer)
        self.assertIn('event.key === "Escape"', viewer)
        self.assertIn('data-action="zoom-out"', viewer)
        self.assertIn('data-action="zoom-in"', viewer)
        self.assertIn("const scaledWidth = size.width * scale", viewer)
        self.assertNotIn("scale(${scale})", viewer)
        self.assertIn("width: 27px", styles)
        self.assertIn("width: min(1480px, 80vw)", styles)
        self.assertIn("height: min(920px, 90vh)", styles)
        self.assertIn("border-color: #c9d5dc", styles)
        self.assertIn("backdrop-filter: blur(4px)", styles)

    def test_contextual_navigation_uses_instant_navigation_and_skips_redundant_motion(
        self,
    ):
        config = (PROJECT_TOOLS / "mkdocs.yml").read_text(encoding="utf-8")
        navigation = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "javascripts"
            / "contextual-navigation.js"
        ).read_text(encoding="utf-8")

        self.assertIn("javascripts/contextual-navigation.js", config)
        self.assertIn("site_url: https://market-sensing-ai-wiki.vercel.app", config)
        self.assertIn("- navigation.instant", config)
        self.assertIn("- navigation.instant.prefetch", config)
        self.assertNotIn("function suppressRedundantNavigation", navigation)
        self.assertNotIn("event.preventDefault()", navigation)
        self.assertIn(
            "scrollingElement.scrollHeight <= window.innerHeight + 1",
            navigation,
        )
        self.assertIn("if (!targetNeedsCentering()) return", navigation)

    def test_footnote_source_preview_is_loaded(self):
        config = (PROJECT_TOOLS / "mkdocs.yml").read_text(encoding="utf-8")
        tooltips = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "javascripts"
            / "footnote-tooltips.js"
        ).read_text(encoding="utf-8")
        styles = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "stylesheets"
            / "extra.css"
        ).read_text(encoding="utf-8")

        self.assertIn("javascripts/footnote-tooltips.js", config)
        self.assertIn('a.footnote-ref[href^=\'#fn\']', tooltips)
        self.assertIn('reference.setAttribute("aria-label"', tooltips)
        self.assertIn("function originalSourceLink", tooltips)
        self.assertIn('reference.setAttribute("href", originalLink.href)', tooltips)
        self.assertIn('reference.setAttribute("target", "_blank")', tooltips)
        self.assertIn('reference.setAttribute("rel", "noopener noreferrer")', tooltips)
        self.assertIn("footnote-source-tooltip", tooltips)
        self.assertIn("data-footnote-tooltip", styles)
        self.assertIn(".footnote-source-tooltip", styles)
        self.assertNotIn(
            ".md-typeset table a.footnote-ref[data-footnote-tooltip]",
            styles,
        )

    def test_financial_impact_simulator_uses_validated_portable_formula(self):
        config = (PROJECT_TOOLS / "mkdocs.yml").read_text(encoding="utf-8")
        simulator = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "javascripts"
            / "impact-simulator.js"
        ).read_text(encoding="utf-8")
        styles = (
            PROJECT_ROOT / "market-sensing-wiki" / "stylesheets" / "extra.css"
        ).read_text(encoding="utf-8")
        estimate_path = (
            PROJECT_ROOT
            / "research"
            / "impact-estimates"
            / "senex-gas-reservation.json"
        )
        estimate = json.loads(estimate_path.read_text(encoding="utf-8"))

        market_sensing.validate_impact_estimate(estimate)
        block = "\n".join(market_sensing.impact_estimate_block_lines(estimate))
        self.assertIn("```impact-simulator", block)
        self.assertIn("연간 EBITDA 영향", block)
        self.assertIn("javascripts/impact-simulator.js", config)
        self.assertIn("class: impact-simulator-data", config)
        self.assertIn("function evaluate(expression, values)", simulator)
        self.assertIn('case "multiply"', simulator)
        self.assertIn('range.type = "range"', simulator)
        self.assertIn("dominantVariable", simulator)
        self.assertIn("controlStrip.append(driver, toolbar)", simulator)
        self.assertIn('element("p", "impact-input-basis", variable.basis)', simulator)
        self.assertNotIn('assumption: "AI 가정"', simulator)
        self.assertIn('if (variable.kind === "assumption") return "";', simulator)
        self.assertIn(".impact-input-kind.is-assumption", styles)

    def test_financial_impact_simulator_rejects_executable_formula_strings(self):
        estimate = json.loads(
            (
                PROJECT_ROOT
                / "research"
                / "impact-estimates"
                / "senex-gas-reservation.json"
            ).read_text(encoding="utf-8")
        )
        estimate["outputs"][0]["expression"] = "window.alert('unsafe')"
        with self.assertRaisesRegex(ValueError, "number or expression object"):
            market_sensing.validate_impact_estimate(estimate)

    def test_vercel_redirects_cover_reader_facing_short_urls(self):
        config = json.loads(
            (PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8")
        )
        redirects = {
            item["source"]: item["destination"]
            for item in config["redirects"]
        }

        self.assertTrue(config["trailingSlash"])
        self.assertEqual(
            redirects["/academic-landscape-:slug"],
            "/reports/academic-landscape-:slug",
        )
        self.assertEqual(
            redirects["/brief-:slug"],
            "/reports/briefs/brief-:slug",
        )
        self.assertEqual(
            redirects["/briefs/:path*"],
            "/reports/briefs/:path*",
        )
        self.assertEqual(
            redirects["/reports/brief-:slug"],
            "/reports/briefs/brief-:slug",
        )
        self.assertEqual(
            redirects["/audit-:slug"],
            "/reports/audits/audit-:slug",
        )
        self.assertEqual(
            redirects["/audits/:path*"],
            "/reports/audits/:path*",
        )
        self.assertEqual(redirects["/TEC-:slug"], "/technologies/TEC-:slug")

    def test_mkdocs_headings_are_numbered_per_page(self):
        config = (PROJECT_TOOLS / "mkdocs.yml").read_text(encoding="utf-8")
        requirements = (
            PROJECT_TOOLS / "requirements-docs.txt"
        ).read_text(encoding="utf-8")
        styles = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "stylesheets"
            / "extra.css"
        ).read_text(encoding="utf-8")

        self.assertIn("mkdocs-enumerate-headings-plugin==0.7.0", requirements)
        self.assertIn("- enumerate-headings:", config)
        self.assertIn("start_level: 2", config)
        self.assertIn("increment_across_pages: false", config)
        self.assertIn("toc_depth: 3", config)
        self.assertIn("  projects/", config)
        self.assertIn(".enumerate-headings-plugin", styles)
        self.assertIn(".md-typeset h2,", styles)
        self.assertIn(".md-typeset h3 {", styles)
        self.assertIn("color: var(--md-primary-fg-color)", styles)

    def test_recent_updates_does_not_use_legacy_atomic_claim_table(self):
        styles = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "stylesheets"
            / "extra.css"
        ).read_text(encoding="utf-8")

        self.assertNotIn("data-recent-updates-changes", styles)
        self.assertFalse(hasattr(mkdocs_hooks, "on_page_content"))

    def test_home_matrix_gives_china_baowu_two_line_width(self):
        styles = (
            PROJECT_ROOT
            / "market-sensing-wiki"
            / "stylesheets"
            / "extra.css"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'table th a[href$="companies/COM-China-Baowu/"]',
            styles,
        )
        self.assertIn("display: inline-block", styles)
        self.assertIn("width: 6.25rem", styles)
        self.assertIn("word-break: keep-all", styles)

    def test_mkdocs_search_prioritizes_reader_pages(self):
        config = (PROJECT_TOOLS / "mkdocs.yml").read_text(encoding="utf-8")
        wiki_root = PROJECT_ROOT / "market-sensing-wiki"

        source_meta = (wiki_root / "sources" / ".meta.yml").read_text(
            encoding="utf-8"
        )
        company_meta = (wiki_root / "companies" / ".meta.yml").read_text(
            encoding="utf-8"
        )
        technology_meta = (
            wiki_root / "technologies" / ".meta.yml"
        ).read_text(encoding="utf-8")
        project_meta = (wiki_root / "projects" / ".meta.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("- material/meta", config)
        self.assertIn("exclude: true", source_meta)
        self.assertIn("boost: 1.2", company_meta)
        self.assertIn("boost: 1.2", technology_meta)
        self.assertIn("boost: 1.1", project_meta)

    def test_duplicate_conflict_review_audit_and_brief_flow(self):
        incoming = Path(self.temp_dir.name) / "incoming"
        incoming.mkdir()
        first = incoming / "first.md"
        first.write_text(
            "Example Steel announced that the hydrogen DRI project targets "
            "commercial operation in 2027. Capacity is 1 million tonnes per year.",
            encoding="utf-8",
        )

        created = market_sensing.add_source(
            self.source_args(
                first,
                "Example Steel hydrogen DRI project update",
                "https://example.com/news/update?utm_source=newsletter",
            )
        )
        self.assertEqual(created["action"], "created")
        first_source_id = created["source_id"]

        duplicate = market_sensing.add_source(
            self.source_args(
                first,
                "Syndicated Example Steel hydrogen DRI update",
                "https://media.example.org/reprint",
            )
        )
        self.assertEqual(duplicate["action"], "exact_duplicate")
        self.assertEqual(duplicate["source_id"], first_source_id)

        similar = incoming / "similar.md"
        similar.write_text(
            "Example Steel announced that the hydrogen DRI project now targets "
            "commercial operation in 2029. Capacity is 1 million tonnes per year.",
            encoding="utf-8",
        )
        duplicate_review = market_sensing.add_source(
            self.source_args(
                similar,
                "Example Steel hydrogen DRI project revised update",
                "https://industry.example.net/revised-update",
            )
        )
        self.assertEqual(duplicate_review["action"], "review_required")
        self.assertEqual(duplicate_review["type"], "duplicate_candidate")

        duplicate_resolved = market_sensing.resolve_review(
            Namespace(
                root=str(self.root),
                review_id=duplicate_review["review_id"],
                decision="accept-new",
                rationale="The revised date is material independent content.",
                related_source=None,
            )
        )
        self.assertEqual(duplicate_resolved["action"], "resolved")
        second = duplicate_resolved["result"]
        self.assertEqual(second["action"], "created")

        first_claim = market_sensing.add_claim(
            self.claim_args(first_source_id, "2027")
        )
        self.assertEqual(first_claim["action"], "created")
        project_page = (
            self.root / "projects" / "PRJ-EXAMPLE-DRI.md"
        )
        source_page = (
            self.root / "sources" / f"{first_source_id}.md"
        )
        self.assertTrue(project_page.exists())
        self.assertTrue(source_page.exists())
        project_page_text = project_page.read_text(encoding="utf-8")
        self.assertIn("## 확인된 핵심 정보", project_page_text)
        self.assertIn("| **목표 가동 시점** | 2027", project_page_text)
        self.assertIn("## 전체 확인 이력", project_page_text)
        self.assertIn("| 2026-07-21 | 발표·검증 |", project_page_text)
        self.assertIn("| 2027 | 목표 일정 | **목표 가동 시점**", project_page_text)
        self.assertIn(
            f"[[sources/{first_source_id}|보관 원문·메타데이터]]",
            project_page_text,
        )
        self.assertNotIn("Subject ID", project_page_text)
        self.assertNotIn("Claim ID", project_page_text)
        self.assertNotIn("### `target_start_date`", project_page_text)
        self.assertIn(
            "[[projects/PRJ-EXAMPLE-DRI|PRJ-EXAMPLE-DRI]]",
            source_page.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "## 보관 원문",
            source_page.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "> Example Steel announced that the hydrogen DRI project targets",
            source_page.read_text(encoding="utf-8"),
        )
        market_sensing.add_claim(
            Namespace(
                root=str(self.root),
                subject_id="COM-Example-Steel",
                predicate="hydrogen_dri_status",
                value="공식 프로젝트 발표 확인",
                source_id=[first_source_id],
                confidence="medium",
                as_of="2026-07-25",
                reason="Company technology coverage test",
            )
        )
        company_page = (
            self.root / "companies" / "COM-Example-Steel.md"
        ).read_text(encoding="utf-8")
        self.assertIn("# Example Steel 기술 현황", company_page)
        self.assertIn('!!! abstract "한눈에 보기"', company_page)
        self.assertIn("## 기술 포트폴리오", company_page)
        self.assertIn("## 기술별 근거와 확인 과제", company_page)
        self.assertIn("## 주요 프로젝트", company_page)
        self.assertIn(
            "[[projects/PRJ-EXAMPLE-DRI|PRJ-EXAMPLE-DRI]]",
            company_page,
        )
        self.assertIn("## 프로젝트별 상세", company_page)
        self.assertIn("**전체 공개 연혁**", company_page)
        self.assertIn("| **목표 가동 시점** | 2027", company_page)
        self.assertNotIn("공식 근거를 확인하지 못한 영역", company_page)
        self.assertNotIn(
            "용융산화물 전기분해 (Molten Oxide Electrolysis)",
            company_page,
        )
        self.assertIn("## AI 분석", company_page)
        self.assertIn("## 근거 자료", company_page)
        self.assertNotIn("Claim ID", company_page)
        self.assertNotIn(first_claim["claim_id"], company_page)
        index_page = (self.root / "index.md").read_text(encoding="utf-8")
        self.assertIn("# 포스코그룹 마켓센싱", index_page)
        recent_updates = (self.root / "recent-updates.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("# 최근 업데이트", recent_updates)
        self.assertIn("## 최근 조사 실행", recent_updates)
        self.assertIn("## 최근 공개 시그널", recent_updates)
        self.assertIn("아직 발행된 시그널이 없습니다.", recent_updates)
        self.assertNotIn("## 변경된 지식", recent_updates)
        self.assertNotIn("PRJ-EXAMPLE-DRI", recent_updates)
        self.assertNotIn(first_source_id, recent_updates)
        self.assertNotIn("target_start_date", recent_updates)
        self.assertIn("[[signals/index|전체 마켓 시그널 보기 →]]", index_page)
        self.assertNotIn("Claim ID", index_page)
        self.assertNotIn("target_start_date", index_page)
        self.assertNotIn("○ 미확인", index_page)
        self.assertNotIn("기업 기술 현황 HTML 열기", index_page)
        self.assertFalse((self.root / "reports" / "companies").exists())
        self.assertFalse((self.root / "기술별-기업현황.html").exists())
        self.assertFalse((self.root / "기업별-기술현황.html").exists())

        conflict = market_sensing.add_claim(
            self.claim_args(second["source_id"], "2029")
        )
        self.assertEqual(conflict["action"], "review_required")
        self.assertEqual(conflict["type"], "claim_conflict")

        resolved = market_sensing.resolve_review(
            Namespace(
                root=str(self.root),
                review_id=conflict["review_id"],
                decision="supersede",
                rationale="Newer official update replaces the earlier target.",
                related_source=None,
            )
        )
        self.assertEqual(resolved["action"], "resolved")
        self.assertIn(
            "- 검토 대기 항목이 없습니다.",
            (self.root / "REVIEW.md").read_text(encoding="utf-8"),
        )
        old_claim = json.loads(
            (
                self.root
                / ".system"
                / "claims"
                / f"{first_claim['claim_id']}.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(old_claim["status"], "superseded")

        log_before_search = (self.root / "log.md").read_text(encoding="utf-8")
        search_result = market_sensing.search_store(
            Namespace(root=str(self.root), query="hydrogen DRI 2029", limit=5)
        )
        self.assertEqual(search_result["action"], "search_results")
        self.assertTrue(search_result["verification_required"])
        self.assertEqual(search_result["claims"][0]["value"], "2029")
        self.assertEqual(search_result["claims"][0]["status"], "active")
        self.assertIn(
            second["source_id"],
            {item["source_id"] for item in search_result["sources"]},
        )
        self.assertIn(
            "projects/PRJ-EXAMPLE-DRI.md",
            {item["path"] for item in search_result["notes"]},
        )
        self.assertTrue(
            any(
                item["from"] == "projects/PRJ-EXAMPLE-DRI.md"
                and item["to"]
                == f"sources/{second['source_id']}.md"
                for item in search_result["followed_links"]
            )
        )
        self.assertEqual(
            (self.root / "log.md").read_text(encoding="utf-8"),
            log_before_search,
        )

        audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        self.assertEqual(audit["counts"]["source_integrity"], 0)
        self.assertEqual(audit["counts"]["claim_evidence"], 0)

        change_brief = market_sensing.brief(
            Namespace(root=str(self.root), since="2026-07-20", html=True)
        )
        self.assertGreaterEqual(change_brief["change_count"], 2)
        self.assertTrue((self.root / change_brief["report"]).exists())
        self.assertTrue((self.root / change_brief["html_report"]).exists())
        brief_markdown = (self.root / change_brief["report"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("# 포스코그룹 마켓센싱 브리프", brief_markdown)
        self.assertIn('!!! abstract "한눈에 보기"', brief_markdown)
        self.assertIn("## 확인된 변화", brief_markdown)
        self.assertNotIn("Claim ID", brief_markdown)
        self.assertNotIn("| Date | Claim |", brief_markdown)
        report_index = (self.root / "reports" / "index.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("**발행된 보고서 1건**", report_index)
        self.assertIn(
            f"포스코그룹 마켓센싱 브리프 · 2026-07-20–{market_sensing.today()}",
            report_index,
        )
        html_report = (self.root / change_brief["html_report"]).read_text(
            encoding="utf-8"
        )
        self.assertIn('<header class="report-header">', html_report)
        self.assertIn('id="source-1"', html_report)
        self.assertIn("https://example.com/news/update?utm_source=newsletter", html_report)
        self.assertTrue(html_report.endswith("</html>\n"))

        custom_markdown = self.root / "reports" / "briefs" / "custom-report.md"
        custom_markdown.write_text(
            "---\n"
            'title: "Custom sourced report"\n'
            "date: 2026-07-25\n"
            "---\n\n"
            "# Custom sourced report\n\n"
            f"Verified evidence: {first_source_id}\n\n"
            "<script>alert('unsafe')</script>\n\n"
            "[unsafe link](javascript:alert(1))\n",
            encoding="utf-8",
        )
        rendered = market_sensing.render_report(
            Namespace(
                root=str(self.root),
                input=str(custom_markdown),
                output=None,
            )
        )
        custom_html = (self.root / rendered["html_report"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("&lt;script&gt;", custom_html)
        self.assertNotIn("<script>alert", custom_html)
        self.assertNotIn('href="javascript:', custom_html)
        self.assertEqual(rendered["source_count"], 1)

        for page in [
            self.root / "REVIEW.md",
            self.root / "index.md",
            *sorted((self.root / "companies").glob("**/*.md")),
            *sorted((self.root / "technologies").glob("**/*.md")),
            *sorted((self.root / "projects").glob("**/*.md")),
            *sorted((self.root / "entities").glob("**/*.md")),
            *sorted((self.root / "sources").glob("**/*.md")),
        ]:
            text = page.read_text(encoding="utf-8")
            for target in re.findall(r"\[\[([^]|]+)(?:\|[^]]+)?\]\]", text):
                self.assertTrue(
                    (self.root / f"{target}.md").exists(),
                    f"Broken wikilink in {page}: {target}",
                )

    def test_audit_detects_raw_source_mutation(self):
        incoming = Path(self.temp_dir.name) / "source.md"
        incoming.write_text("Original immutable source.", encoding="utf-8")
        created = market_sensing.add_source(
            self.source_args(
                incoming,
                "Immutable source",
                "https://example.com/immutable",
            )
        )
        raw_path = self.root / created["raw_path"]
        raw_path.write_text("Modified source.", encoding="utf-8")

        audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        self.assertEqual(audit["counts"]["source_integrity"], 1)

    def test_audit_accepts_git_crlf_materialization_of_lf_source(self):
        incoming = Path(self.temp_dir.name) / "source-with-lines.md"
        incoming.write_bytes(b"Immutable first line.\nImmutable second line.\n")
        created = market_sensing.add_source(
            self.source_args(
                incoming,
                "Immutable source with line endings",
                "https://example.com/immutable-line-endings",
            )
        )
        raw_path = self.root / created["raw_path"]
        lf_bytes = raw_path.read_bytes().replace(b"\r\n", b"\n")
        raw_path.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))

        audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        self.assertEqual(audit["counts"]["source_integrity"], 0)

    def test_audit_does_not_flag_resolved_coexisting_claims(self):
        first_file = Path(self.temp_dir.name) / "first-scope.md"
        first_file.write_text(
            "The general EAF route needs carbon and oxygen control.",
            encoding="utf-8",
        )
        second_file = Path(self.temp_dir.name) / "project-scope.md"
        second_file.write_text(
            "A named project combines DRI and scrap in its EAF design.",
            encoding="utf-8",
        )
        first_source = market_sensing.add_source(
            self.source_args(
                first_file,
                "General EAF integration study",
                "https://example.com/general-eaf",
            )
        )
        second_source = market_sensing.add_source(
            self.source_args(
                second_file,
                "Project EAF integration design",
                "https://example.com/project-eaf",
            )
        )
        market_sensing.add_claim(
            self.claim_args(first_source["source_id"], "general operating constraint")
        )
        conflict = market_sensing.add_claim(
            self.claim_args(second_source["source_id"], "project-specific design")
        )
        self.assertEqual(conflict["action"], "review_required")
        market_sensing.resolve_review(
            Namespace(
                root=str(self.root),
                review_id=conflict["review_id"],
                decision="coexist",
                rationale="The claims describe different scopes.",
                related_source=None,
            )
        )

        audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        self.assertEqual(audit["counts"]["active_conflicts"], 0)

    def test_optional_source_images_are_projected_and_audited(self):
        incoming = Path(self.temp_dir.name) / "source.md"
        incoming.write_text(
            "Example Steel published a technical update with an equipment photo.",
            encoding="utf-8",
        )
        created = market_sensing.add_source(
            self.source_args(
                incoming,
                "Equipment photo source",
                "https://example.com/equipment-update",
            )
        )
        source_id = created["source_id"]
        market_sensing.add_claim(self.claim_args(source_id, "2028"))

        image_file = Path(self.temp_dir.name) / "facility.png"
        image_file.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a"
                "0000000d49484452000000010000000108060000001f15c489"
                "0000000d4944415408d763f8ffff3f0005fe02fea73581a8"
                "0000000049454e44ae426082"
            )
        )
        added = market_sensing.add_image(
            Namespace(
                root=str(self.root),
                source_id=source_id,
                image_file=str(image_file),
                image_url=None,
                origin_url="https://example.com/equipment-update",
                caption="Example Steel 실증 설비 전경",
                alt_text="원통형 반응기와 배관이 설치된 실증 설비",
                creator="Example Steel",
                kind="facility_photo",
                rights_status="permitted",
                rights_note="공식 미디어 자료의 내부 기술검토 사용 조건 확인",
                subject_id=["COM-EXAMPLE-STEEL", "PRJ-EXAMPLE-DRI"],
                display_width="detail",
                hero_priority=-100,
            )
        )
        self.assertEqual(added["action"], "image_added")
        local_image = self.root / added["local_path"]
        self.assertTrue(local_image.is_file())
        stored_source = json.loads(
            (
                self.root
                / ".system"
                / "source-records"
                / f"{source_id}.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            stored_source["images"][0]["subject_ids"],
            ["COM-EXAMPLE-STEEL", "PRJ-EXAMPLE-DRI"],
        )
        self.assertEqual(stored_source["images"][0]["display_width"], "detail")
        self.assertEqual(stored_source["images"][0]["hero_priority"], -100)

        link_only = market_sensing.add_image(
            Namespace(
                root=str(self.root),
                source_id=source_id,
                image_file=None,
                image_url="https://example.com/media/restricted.jpg",
                origin_url="https://example.com/equipment-update",
                caption="상세 장치 배치도",
                alt_text=None,
                creator=None,
                kind="equipment_drawing",
                rights_status="link_only",
                rights_note="복제 권한이 불명확해 원문 링크만 보존",
            )
        )
        self.assertIsNone(link_only["local_path"])

        source_page = (
            self.root / "sources" / f"{source_id}.md"
        ).read_text(encoding="utf-8")
        project_page = (
            self.root / "projects" / "PRJ-EXAMPLE-DRI.md"
        ).read_text(encoding="utf-8")
        for page in (source_page, project_page):
            self.assertIn("## 설비·공정 이미지", page)
            self.assertIn("Example Steel 실증 설비 전경", page)
            self.assertIn("실제 설비 사진", page)
        self.assertIn(
            "![상세 장치 배치도]"
            "(<https://example.com/media/restricted.jpg>)"
            "{ .steel-media-image .steel-media-detail }",
            source_page,
        )
        self.assertIn(
            "![원통형 반응기와 배관이 설치된 실증 설비]"
            f"(../{added['local_path']})"
            "{ .steel-media-image .steel-hero-image .steel-media-detail }",
            project_page,
        )
        self.assertIn(f"(../{added['local_path']})", source_page)

        record = json.loads(
            (
                self.root
                / ".system"
                / "source-records"
                / f"{source_id}.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(len(record["images"]), 2)
        self.assertEqual(record["images"][0]["content_sha256"], market_sensing.raw_sha256(
            local_image.read_bytes()
        ))
        clean_audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        self.assertEqual(clean_audit["counts"]["media_integrity"], 0)
        self.assertEqual(clean_audit["counts"]["media_schema"], 0)

        local_image.write_bytes(b"changed")
        changed_audit = market_sensing.audit_store(
            Namespace(root=str(self.root), stale_days=180)
        )
        self.assertEqual(changed_audit["counts"]["media_integrity"], 1)

    def test_link_only_image_can_be_rendered_as_remote_representative_image(self):
        source_id = "SRC-REMOTE-IMAGE"
        lines, excluded_media_ids = market_sensing.representative_image_lines(
            [source_id],
            {
                source_id: {
                    "images": [
                        {
                            "media_id": "MED-REMOTE",
                            "image_url": "https://example.com/media/cell-tap.jpg",
                            "origin_url": "https://example.com/official-release",
                            "caption": "공식 원문에 공개된 전해 셀 출선 장면",
                            "alt_text": "전해 셀에서 용융금속을 출선하는 장면",
                            "kind": "facility_photo",
                            "rights_status": "link_only",
                        }
                    ]
                }
            },
        )

        rendered = "\n".join(lines)
        self.assertIn(
            "![전해 셀에서 용융금속을 출선하는 장면]"
            "(<https://example.com/media/cell-tap.jpg>)"
            "{ .steel-media-image .steel-hero-image .steel-media-compact }",
            rendered,
        )
        self.assertIn("권리 `link_only`", rendered)
        self.assertIn("[원문 페이지](https://example.com/official-release)", rendered)
        self.assertEqual(excluded_media_ids, {"MED-REMOTE"})

    def test_link_only_gallery_embeds_remote_image_without_copying_it(self):
        source_id = "SRC-GALLERY-REMOTE"
        gallery = "\n".join(
            market_sensing.media_gallery_lines(
                [source_id],
                {
                    source_id: {
                        "images": [
                            {
                                "media_id": "MED-GALLERY-REMOTE",
                                "image_url": "https://example.com/media/process.png",
                                "origin_url": "https://example.com/official-release",
                                "caption": "공식 공정도",
                                "alt_text": "공식 공정 구성도",
                                "kind": "process_diagram",
                                "rights_status": "link_only",
                            }
                        ]
                    }
                },
            )
        )

        self.assertIn(
            "![공식 공정 구성도]"
            "(<https://example.com/media/process.png>)"
            "{ .steel-media-image .steel-media-detail }",
            gallery,
        )
        self.assertNotIn("이미지를 복제하지 않았습니다", gallery)

    def test_subject_scoped_media_is_not_reused_on_unrelated_pages(self):
        source_id = "SRC-SCOPED-MEDIA"
        sources = {
            source_id: {
                "images": [
                    {
                        "media_id": "MED-HYFOR",
                        "image_url": "https://example.com/hyfor.jpg",
                        "origin_url": "https://example.com/hyfor",
                        "caption": "HYFOR 실제 설비",
                        "alt_text": "HYFOR 실제 설비",
                        "kind": "facility_photo",
                        "rights_status": "link_only",
                        "subject_ids": [
                            "TEC-hydrogen-based-fine-ore-reduction",
                            "PRJ-HYFOR-DONAWITZ-PILOT",
                        ],
                    }
                ]
            }
        }

        allowed_hero, _ = market_sensing.representative_image_lines(
            [source_id],
            sources,
            subject_id="PRJ-HYFOR-DONAWITZ-PILOT",
        )
        unrelated_hero, _ = market_sensing.representative_image_lines(
            [source_id],
            sources,
            subject_id="PRJ-POSCO-HYREX-DEMO",
        )
        unrelated_gallery = market_sensing.media_gallery_lines(
            [source_id],
            sources,
            subject_id="PRJ-POSCO-HYREX-DEMO",
        )

        self.assertIn("HYFOR 실제 설비", "\n".join(allowed_hero))
        self.assertEqual(unrelated_hero, [])
        self.assertEqual(unrelated_gallery, [])

    def test_subject_scoped_media_is_found_outside_claim_source_list(self):
        sources = {
            "SRC-CLAIM": {"images": []},
            "SRC-RELATED-PROJECT": {
                "images": [
                    {
                        "media_id": "MED-TECH-HERO",
                        "local_path": "assets/media/tech-hero.png",
                        "caption": "기술 전용 AI 개념도",
                        "kind": "ai_reconstruction",
                        "rights_status": "ai_generated",
                        "hero_priority": -100,
                        "subject_ids": ["TEC-EXAMPLE"],
                    }
                ]
            },
        }

        hero, excluded_media_ids = market_sensing.representative_image_lines(
            ["SRC-CLAIM"],
            sources,
            subject_id="TEC-EXAMPLE",
        )
        unrelated_hero, _ = market_sensing.representative_image_lines(
            ["SRC-CLAIM"],
            sources,
            subject_id="TEC-OTHER",
        )

        self.assertIn("../assets/media/tech-hero.png", "\n".join(hero))
        self.assertEqual(excluded_media_ids, {"MED-TECH-HERO"})
        self.assertEqual(unrelated_hero, [])

    def test_representative_image_prefers_process_diagram_for_technology_page(self):
        source_id = "SRC-ESF-IMAGES"
        lines, excluded_media_ids = market_sensing.representative_image_lines(
            [source_id],
            {
                source_id: {
                    "images": [
                        {
                            "media_id": "MED-FACILITY",
                            "image_url": "https://example.com/esf-facility.jpg",
                            "origin_url": "https://example.com/esf",
                            "caption": "ESF 실증 설비",
                            "alt_text": "전기용융로 실증 설비",
                            "kind": "facility_photo",
                            "rights_status": "link_only",
                        },
                        {
                            "media_id": "MED-PROCESS",
                            "image_url": "https://example.com/esf-process.png",
                            "origin_url": "https://example.com/esf",
                            "caption": "ESF 공정 구성도",
                            "alt_text": "전기용융로 공정 구성도",
                            "kind": "process_diagram",
                            "rights_status": "link_only",
                        },
                    ]
                }
            },
            preferred_kinds=("process_diagram", "facility_photo"),
        )

        rendered = "\n".join(lines)
        self.assertIn("https://example.com/esf-process.png", rendered)
        self.assertNotIn("https://example.com/esf-facility.jpg", rendered)
        self.assertEqual(excluded_media_ids, {"MED-PROCESS"})

    def test_manual_hero_priority_can_place_ai_reconstruction_first(self):
        source_id = "SRC-ORDERED-HERO"
        lines, excluded_media_ids = market_sensing.representative_image_lines(
            [source_id],
            {
                source_id: {
                    "images": [
                        {
                            "media_id": "MED-OFFICIAL",
                            "image_url": "https://example.com/official-process.png",
                            "origin_url": "https://example.com/official",
                            "caption": "공식 공정 구성도",
                            "kind": "process_diagram",
                            "rights_status": "link_only",
                        },
                        {
                            "media_id": "MED-AI",
                            "local_path": "assets/media/ai.png",
                            "origin_url": "https://example.com/evidence",
                            "caption": "일관된 AI 개념도",
                            "kind": "ai_reconstruction",
                            "rights_status": "ai_generated",
                            "hero_priority": -100,
                            "display_width": "detail",
                        },
                    ]
                }
            },
        )

        rendered = "\n".join(lines)
        self.assertIn("../assets/media/ai.png", rendered)
        self.assertNotIn("official-process.png", rendered)
        self.assertIn(".steel-media-detail", rendered)
        self.assertEqual(excluded_media_ids, {"MED-AI"})

    def test_technology_dossier_links_related_project_status_schedule_and_capacity(self):
        source_id = "SRC-NEOSMELT"
        claims_by_subject = {
            "TEC-electric-smelting-furnace": [
                {
                    "predicate": "technical_definition",
                    "value": "환원철을 용융·정련해 용선을 생산하는 전기 용융 공정",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": [source_id],
                }
            ],
            "PRJ-NEOSMELT-KWINANA": [
                {
                    "predicate": "project_status",
                    "value": "최종 설계 및 투자결정 준비 중",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": [source_id],
                },
                {
                    "predicate": "capacity_tpy",
                    "value": "연간 30,000~40,000톤 용선",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": [source_id],
                },
                {
                    "predicate": "target_commissioning_date",
                    "value": "2028년 하반기",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": [source_id],
                },
                {
                    "predicate": "capture_capacity_tpd",
                    "value": "5 t-CO2/day",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": [source_id],
                },
            ],
        }
        sources = {
            source_id: {
                "source_id": source_id,
                "title": "NeoSmelt project update",
                "publisher": "BHP",
                "published_at": "2026-07-01",
                "collected_at": "2026-07-25",
                "source_type": "company_release",
                "url": "https://example.com/neosmelt",
            }
        }

        markdown = "\n".join(
            market_sensing.technology_company_dossier_lines(
                "electric smelting furnace",
                {"companies": [], "technologies": ["electric smelting furnace"]},
                claims_by_subject,
                sources,
            )
        )

        self.assertIn("## 관련 프로젝트", markdown)
        self.assertIn("PRJ-NEOSMELT-KWINANA", markdown)
        self.assertIn("최종 설계 및 투자결정 준비 중", markdown)
        self.assertIn("연간 30,000~40,000톤 용선", markdown)
        self.assertIn("2028년 하반기", markdown)
        self.assertIn("5 t-CO2/day", markdown)
        self.assertNotIn("<br>", markdown)

    def test_technology_maturity_label_is_conservative_about_targets(self):
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "연 30만 톤 통합 실증설비 부지를 준비 중"
            ),
            "건설·구축",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "2027년 가동 목표인 산업규모 실증설비 건설 중"
            ),
            "건설·구축",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "2030년까지 상용화 기술 개발 완료 목표"
            ),
            "연구",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "파일럿 설비 운전 확인; 상업 규모 운전은 미확인"
            ),
            "파일럿",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "900°C 학술 연구를 지원했다. 자체 파일럿 설비 운전은 확인되지 않는다."
            ),
            "외부 연구 지원",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "TRL 6 R&D 설비까지 확대했으나 산업 설비 가동은 미확인"
            ),
            "연구",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "대형 EAF 고급강 상업 생산"
            ),
            "상용",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "파일럿 건설은 기술 과제로 중단; R&D는 지속"
            ),
            "일부 프로젝트 중단",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "2026년 500 kg ESF로 중품위광 DRI 용융 시험"
            ),
            "소규모 시험",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "소결 Digital Twin과 복수 사업장의 WEF Global Lighthouse 확인"
            ),
            "가동·적용",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "복수 저탄소 경로를 개발·적용",
                "low-carbon ironmaking",
            ),
            "경로·프로젝트 확인",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "Boston Metal MOE에 전략 투자; 자체 상용 설비가 아닌 외부 기술 투자 단계"
            ),
            "외부 전략투자",
        )
        self.assertEqual(
            market_sensing.technology_maturity_label(
                "초기 천연가스 운전 후 수소를 단계 도입하는 조건부 계획"
            ),
            "조건부 계획",
        )

    def test_company_project_linking_ignores_generic_company_words(self):
        company_claims = [
            {
                "subject_id": "COM-Boston-Metal",
                "predicate": "molten_oxide_electrolysis_status",
                "value": "Boston Metal industrial cell operating",
                "status": "active",
                "source_ids": ["SRC-BOSTON"],
            }
        ]
        claims_by_subject = {
            "COM-Boston-Metal": company_claims,
            "PRJ-BOSTON-MOE": [
                {
                    "predicate": "project_status",
                    "value": "Boston Metal industrial cell operating",
                    "status": "active",
                    "source_ids": ["SRC-BOSTON"],
                }
            ],
            "PRJ-OTHER-SMELTER": [
                {
                    "predicate": "project_status",
                    "value": "Other company metal smelter construction",
                    "status": "active",
                    "source_ids": ["SRC-OTHER"],
                }
            ],
        }

        related = market_sensing.company_related_projects(
            "COM-Boston-Metal",
            "Boston Metal",
            company_claims,
            claims_by_subject,
        )

        self.assertEqual([project_id for project_id, _ in related], ["PRJ-BOSTON-MOE"])

    def test_company_dossier_requires_explicit_scope_for_related_project_media(self):
        company_claims = [
            {
                "subject_id": "COM-POSCO",
                "predicate": "partnership_status",
                "value": "POSCO partner projects",
                "status": "active",
                "last_verified": "2026-07-25",
                "source_ids": ["SRC-POSCO"],
            }
        ]
        claims_by_subject = {
            "COM-POSCO": company_claims,
            "PRJ-PARTNER-UNSCOPED": [
                {
                    "subject_id": "PRJ-PARTNER-UNSCOPED",
                    "predicate": "project_status",
                    "value": "POSCO partner pilot",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": ["SRC-PARTNER-UNSCOPED"],
                }
            ],
            "PRJ-POSCO-SCOPED": [
                {
                    "subject_id": "PRJ-POSCO-SCOPED",
                    "predicate": "project_status",
                    "value": "POSCO owned pilot",
                    "status": "active",
                    "last_verified": "2026-07-25",
                    "source_ids": ["SRC-POSCO-SCOPED"],
                }
            ],
        }
        sources = {
            "SRC-POSCO": {
                "title": "POSCO company status",
                "publisher": "POSCO",
                "url": "https://example.com/posco",
            },
            "SRC-PARTNER-UNSCOPED": {
                "title": "Partner pilot",
                "publisher": "Partner",
                "url": "https://example.com/partner",
                "images": [
                    {
                        "media_id": "MED-PARTNER",
                        "kind": "facility_photo",
                        "caption": "Partner-owned facility",
                        "alt_text": "Partner-owned facility",
                        "origin_url": "https://example.com/partner",
                        "rights_status": "link_only",
                        "rights_note": "Official partner image",
                        "image_url": "https://example.com/partner.jpg",
                    }
                ],
            },
            "SRC-POSCO-SCOPED": {
                "title": "POSCO pilot",
                "publisher": "POSCO",
                "url": "https://example.com/posco-pilot",
                "images": [
                    {
                        "media_id": "MED-POSCO",
                        "kind": "facility_photo",
                        "caption": "POSCO-owned facility",
                        "alt_text": "POSCO-owned facility",
                        "origin_url": "https://example.com/posco-pilot",
                        "rights_status": "link_only",
                        "rights_note": "Official POSCO image",
                        "image_url": "https://example.com/posco.jpg",
                        "subject_ids": ["COM-POSCO", "PRJ-POSCO-SCOPED"],
                    }
                ],
            },
        }

        markdown = "\n".join(
            market_sensing.company_dossier_lines(
                "COM-POSCO",
                "POSCO",
                company_claims,
                company_claims,
                [],
                {"companies": ["POSCO"], "technologies": []},
                sources,
                claims_by_subject,
            )
        )

        self.assertIn("POSCO-owned facility", markdown)
        self.assertNotIn("Partner-owned facility", markdown)

    def test_project_timeline_supports_month_dates_and_hides_bad_correction_values(self):
        source_id = "SRC-CORRECTION"
        claims = [
            {
                "predicate": "project_start_date",
                "value": "2024-02",
                "status": "active",
                "source_ids": [source_id],
            },
            {
                "predicate": "funding_amount",
                "value": "A million",
                "status": "superseded",
                "source_ids": [source_id],
                "history": [
                    {
                        "action": "status_changed",
                        "reason": "PowerShell 변수 확장으로 통화 기호와 금액이 누락된 입력 오류",
                    }
                ],
            },
        ]
        sources = {
            source_id: {
                "published_at": "2025-06-17",
                "collected_at": "2026-07-25",
            }
        }

        rows = market_sensing.project_timeline_rows(claims, sources)
        rendered = "\n".join(" | ".join(row) for row in rows)

        self.assertIn("2024-02", rendered)
        self.assertNotIn("A million", rendered)
        self.assertEqual(
            market_sensing.humanize_historical_claim_value(claims[1]),
            "입력 교정으로 대체됨 — 현재 유효 Claim과 원문 금액 참조",
        )

    def test_low_carbon_pathway_has_deep_structure_and_execution_timeline(self):
        detail = market_sensing.TECHNOLOGY_DETAILS["low-carbon ironmaking"]

        self.assertIn("다중 경로", detail["category"])
        self.assertIn("재생전력·전력망", detail["process_mermaid"])
        self.assertIn("PRJ-POSCO-GWANGYANG-EAF", detail["related_projects"])
        self.assertIn("PRJ-SSAB-LULEA-ELECTRIC-MILL", detail["related_projects"])
        self.assertIn("PRJ-TK-H2STEEL-DUISBURG", detail["related_projects"])
        self.assertGreaterEqual(len(detail["analysis_points"]), 6)
        self.assertGreaterEqual(len(detail["posco_implications"]), 3)
        self.assertEqual(
            market_sensing.PROJECT_TIMELINE_PREDICATES["tower_erection_date"],
            "실행 일정",
        )
        self.assertEqual(
            market_sensing.PREDICATE_LABELS["fid_conversion_rate_2026"],
            "FID 전환 비율",
        )

    def test_aqueous_electrolysis_has_deep_analysis_and_hides_event_photo(self):
        detail = market_sensing.TECHNOLOGY_DETAILS[
            "low-temperature aqueous iron electrolysis"
        ]

        self.assertIn("2단 전해채취 스택", detail["process_mermaid"])
        self.assertGreaterEqual(len(detail["analysis_points"]), 6)
        self.assertGreaterEqual(len(detail["posco_implications"]), 3)
        self.assertFalse(
            market_sensing.MEDIA_DISPLAY_OVERRIDES[
                "MED-098B84E432A7"
            ]["display_eligible"]
        )

    def test_markdown_settings_sync_and_drive_search_and_projection(self):
        settings_path = self.root.parent / "WIKI-SETTINGS.md"
        settings_path.write_text(
            "# LLM Wiki 관심사 설정\n\n"
            "## 분석 관점\n\n"
            "- 사업성 분석\n\n"
            "## 우선 기업\n\n"
            "- Example Steel\n\n"
            "## 중점 관찰 항목\n\n"
            "- capacity_tpy\n"
            "- target_start_date\n\n"
            "## 운영 값\n\n"
            "- 검색 겹침 일수: 7\n"
            "- Claim 재검증 일수: 45\n",
            encoding="utf-8",
        )
        synced = market_sensing.sync_settings(
            Namespace(root=str(self.root))
        )
        self.assertTrue(synced["changed"])
        watchlist = json.loads(
            (self.root / "config" / "watchlist.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(watchlist["companies"], ["Example Steel"])
        self.assertEqual(watchlist["focus"], ["사업성 분석"])
        self.assertEqual(watchlist["claim_stale_days"], 45)

        source_file = Path(self.temp_dir.name) / "settings-source.md"
        source_file.write_text(
            "Example Steel project capacity is 1 million tonnes and starts in 2029.",
            encoding="utf-8",
        )
        source = market_sensing.add_source(
            self.source_args(
                source_file,
                "Example Steel project facts",
                "https://example.com/settings-source",
            )
        )
        for predicate, value in (
            ("target_start_date", "2029"),
            ("capacity_tpy", "1000000"),
        ):
            market_sensing.add_claim(
                Namespace(
                    root=str(self.root),
                    subject_id="PRJ-EXAMPLE-DRI",
                    predicate=predicate,
                    value=value,
                    source_id=[source["source_id"]],
                    confidence="medium",
                    as_of="2026-07-25",
                    reason="Settings projection test",
                )
            )

        project_page = (
            self.root / "projects" / "PRJ-EXAMPLE-DRI.md"
        ).read_text(encoding="utf-8")
        self.assertLess(
            project_page.index("연간 생산능력"),
            project_page.index("목표 가동 시점"),
        )
        synced_settings = market_sensing.effective_settings(self.root)
        self.assertIn("사업성 분석", synced_settings["focus"])
        self.assertIn("Example Steel", synced_settings["companies"])
        index_text = (self.root / "index.md").read_text(encoding="utf-8")
        self.assertNotIn("priority_predicates", index_text)
        search = market_sensing.search_store(
            Namespace(
                root=str(self.root),
                query="PRJ-EXAMPLE-DRI",
                limit=5,
            )
        )
        self.assertEqual(search["claims"][0]["predicate"], "capacity_tpy")
        self.assertEqual(search["focus"], ["사업성 분석"])

        settings_path.write_text(
            settings_path.read_text(encoding="utf-8").replace(
                "- Example Steel", "- Updated Steel"
            ),
            encoding="utf-8",
        )
        market_sensing.search_store(
            Namespace(
                root=str(self.root),
                query="PRJ-EXAMPLE-DRI",
                limit=5,
            )
        )
        auto_synced = json.loads(
            (self.root / "config" / "watchlist.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(auto_synced["companies"], ["Updated Steel"])

if __name__ == "__main__":
    unittest.main()
