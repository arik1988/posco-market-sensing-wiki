from __future__ import annotations

import base64
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

try:
    from tools.research_agent.cli_tools import MarketSensingCli
    from tools.research_agent.codex_model import CodexOAuthChatModel, _decode_arguments
    from tools.research_agent.service import ResearchRequest
    from tools.research_agent.settings import (
        AgentSettings,
        ProviderId,
        provider_readiness,
    )
    from tools.research_agent.web import PublicWeb

    RESEARCH_AGENT_DEPS = True
except ModuleNotFoundError as exc:
    if exc.name not in {
        "deepagents",
        "langchain",
        "langchain_core",
        "langchain_openai",
        "langgraph",
        "openai_codex",
    }:
        raise
    RESEARCH_AGENT_DEPS = False


@unittest.skipUnless(RESEARCH_AGENT_DEPS, "research-agent dependencies are isolated")
class ResearchAgentSettingsTests(unittest.TestCase):
    def test_pgpt_uses_company_composite_bearer_without_leaking_secrets(self) -> None:
        values = {
            "PGPT_API_KEY": "private-api-key",
            "PGPT_EMPLOYEE_NO": "E12345",
            "PGPT_MODEL": "company-model",
        }
        with patch.dict(os.environ, values, clear=False):
            settings = AgentSettings.from_env(ProviderId.PGPT)

        decoded = json.loads(base64.b64decode(settings.pgpt_token()))
        self.assertEqual(
            decoded,
            {"apiKey": "private-api-key", "companyCode": "30", "systemCode": "E12345"},
        )
        self.assertNotIn("private-api-key", repr(settings))
        self.assertNotIn("E12345", repr(settings))

    def test_pgpt_rejects_unapproved_credential_destination(self) -> None:
        values = {
            "PGPT_API_KEY": "private-api-key",
            "PGPT_EMPLOYEE_NO": "E12345",
            "PGPT_MODEL": "company-model",
            "PGPT_BASE_URL": "https://example.com/v1",
        }
        with patch.dict(os.environ, values, clear=False):
            with self.assertRaisesRegex(ValueError, "approved P-GPT endpoint"):
                AgentSettings.from_env(ProviderId.PGPT)

    def test_provider_readiness_never_returns_credentials(self) -> None:
        values = {
            "PGPT_API_KEY": "private-api-key",
            "PGPT_EMPLOYEE_NO": "E12345",
            "PGPT_MODEL": "company-model",
        }
        with patch.dict(os.environ, values, clear=False):
            payload = provider_readiness()
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("private-api-key", rendered)
        self.assertNotIn("E12345", rendered)
        self.assertTrue(payload[0]["configured"])
        self.assertEqual(
            payload[1]["models"],
            ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
        )
        self.assertEqual(payload[1]["efforts"], ["light", "medium", "high"])

    def test_codex_request_options_override_environment_and_map_light_to_low(self) -> None:
        with patch.dict(
            os.environ,
            {"MARKET_AGENT_CODEX_MODEL": "gpt-5.6-terra", "MARKET_AGENT_CODEX_EFFORT": "high"},
            clear=False,
        ):
            settings = AgentSettings.from_env(
                ProviderId.CODEX,
                codex_model="gpt-5.6-luna",
                codex_effort="light",
            )
        self.assertEqual(settings.codex_model, "gpt-5.6-luna")
        self.assertEqual(settings.codex_effort, "low")


@unittest.skipUnless(RESEARCH_AGENT_DEPS, "research-agent dependencies are isolated")
class ResearchRequestTests(unittest.TestCase):
    def test_request_defaults_to_full_sqlite_publication(self) -> None:
        request = ResearchRequest.from_dict(
            {
                "topic": "철강 수입규제 변화",
                "topic_company": "POSCO",
                "companies": ["POSCO"],
                "business_axes": ["철강"],
                "date_from": "2026-08-01",
                "date_to": "2026-08-29",
                "provider": "codex",
            }
        )
        self.assertTrue(request.publish)
        self.assertEqual(request.provider, ProviderId.CODEX)
        self.assertEqual(request.business_axes, ("철강",))
        self.assertEqual(request.company_axes, (("POSCO", "철강"),))
        self.assertEqual(request.topic_company, "POSCO")
        self.assertEqual(request.codex_model, "gpt-5.6-luna")
        self.assertEqual(request.codex_effort, "medium")

    def test_request_preserves_selected_codex_model_and_effort(self) -> None:
        request = ResearchRequest.from_dict(
            {
                "topic": "철강 수입규제 변화",
                "topic_company": "POSCO",
                "companies": ["POSCO"],
                "date_from": "2026-08-01",
                "date_to": "2026-08-29",
                "provider": "codex",
                "codex_model": "gpt-5.6-sol",
                "codex_effort": "high",
            }
        )
        self.assertEqual(request.codex_model, "gpt-5.6-sol")
        self.assertEqual(request.codex_effort, "high")

    def test_request_rejects_unlisted_codex_options(self) -> None:
        base = {
            "topic": "철강 수입규제 변화",
            "topic_company": "POSCO",
            "companies": ["POSCO"],
            "date_from": "2026-08-01",
            "date_to": "2026-08-29",
            "provider": "codex",
        }
        with self.assertRaisesRegex(ValueError, "GPT-5.6-Sol"):
            ResearchRequest.from_dict({**base, "codex_model": "gpt-5.5"})
        with self.assertRaisesRegex(ValueError, "Light"):
            ResearchRequest.from_dict({**base, "codex_effort": "xhigh"})

    def test_request_preserves_user_edited_company_axis_pairs(self) -> None:
        request = ResearchRequest.from_dict(
            {
                "topic": "신규 공급망 변화",
                "topic_company": "직접 입력 회사",
                "company_axes": [
                    {"company": "직접 입력 회사", "business_axis": "맞춤 원료 조달"},
                    {"company": "POSCO", "business_axis": "저탄소 철강"},
                ],
                "date_from": "2026-08-01",
                "date_to": "2026-08-29",
                "provider": "codex",
            }
        )

        self.assertEqual(
            request.company_axes,
            (("직접 입력 회사", "맞춤 원료 조달"), ("POSCO", "저탄소 철강")),
        )
        self.assertEqual(request.companies, ("직접 입력 회사", "POSCO"))
        self.assertEqual(request.business_axes, ("맞춤 원료 조달", "저탄소 철강"))
        self.assertEqual(request.topic_company, "직접 입력 회사")

    def test_request_rejects_topic_company_outside_selected_scope(self) -> None:
        with self.assertRaisesRegex(ValueError, "아래 회사·사업축 범위"):
            ResearchRequest.from_dict(
                {
                    "topic": "철강 수입규제 변화",
                    "topic_company": "POSCO Holdings",
                    "company_axes": [{"company": "POSCO", "business_axis": "철강"}],
                    "date_from": "2026-08-01",
                    "date_to": "2026-08-29",
                    "provider": "codex",
                }
            )

    def test_request_rejects_inverted_or_unbounded_period(self) -> None:
        base = {
            "topic": "리튬 가격 변화",
            "date_from": "2026-08-29",
            "date_to": "2026-08-01",
            "provider": "pgpt",
        }
        with self.assertRaisesRegex(ValueError, "최대 366일"):
            ResearchRequest.from_dict(base)

    def test_request_rejects_empty_or_unknown_company_scope(self) -> None:
        base = {
            "topic": "리튬 가격 변화",
            "date_from": "2026-08-01",
            "date_to": "2026-08-29",
            "provider": "pgpt",
        }
        with self.assertRaisesRegex(ValueError, "하나 이상"):
            ResearchRequest.from_dict(base)
        with self.assertRaisesRegex(ValueError, "설정에 없는 회사"):
            ResearchRequest.from_dict({**base, "companies": ["Unknown Corp"]})


@unittest.skipUnless(RESEARCH_AGENT_DEPS, "research-agent dependencies are isolated")
class CodexToolEnvelopeTests(unittest.TestCase):
    def test_bound_models_share_one_app_server_runtime(self) -> None:
        model = CodexOAuthChatModel()
        bound = model.bind_tools([])
        self.assertIs(model.runtime, bound.runtime)

    def test_separable_argument_objects_are_merged(self) -> None:
        self.assertEqual(
            _decode_arguments('{"query":"철강 2026"}{"limit":8}'),
            {"query": "철강 2026", "limit": 8},
        )

    def test_duplicate_or_trailing_arguments_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            _decode_arguments('{"query":"a"}{"query":"b"}')
        with self.assertRaisesRegex(ValueError, "malformed"):
            _decode_arguments('{"query":"a"} trailing')


@unittest.skipUnless(RESEARCH_AGENT_DEPS, "research-agent dependencies are isolated")
class ResearchAgentUiContractTests(unittest.TestCase):
    def test_mkdocs_loads_research_tab_with_two_explicit_providers(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = (root / "tools" / "project" / "mkdocs.yml").read_text(encoding="utf-8")
        script = (
            root / "market-sensing-wiki" / "javascripts" / "research-agent.js"
        ).read_text(encoding="utf-8")
        loader = (
            root
            / "market-sensing-wiki"
            / "javascripts"
            / "research-control-loader.js"
        ).read_text(encoding="utf-8")
        styles = (root / "market-sensing-wiki" / "stylesheets" / "extra.css").read_text(
            encoding="utf-8"
        )
        hooks = (root / "tools" / "project" / "mkdocs_hooks.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "javascripts/research-control-loader.js?v=20260829-luna-default",
            config,
        )
        self.assertIn("research-agent.js?ui=20260829-luna-default", loader)
        self.assertIn("window.__poscoResearchAgentBoot = boot", script)
        self.assertIn("boot();", script)
        self.assertIn('script.addEventListener("load"', loader)
        self.assertIn("window.__poscoResearchAgentBoot();", loader)
        self.assertIn('providerCard("pgpt", "P-GPT", "실제 운영"', script)
        self.assertIn('providerCard("codex", "Codex OAuth", "개발 검증"', script)
        self.assertIn('option("gpt-5.6-sol", "GPT-5.6-Sol")', script)
        self.assertIn('option("gpt-5.6-terra", "GPT-5.6-Terra")', script)
        self.assertIn('option("gpt-5.6-luna", "GPT-5.6-Luna")', script)
        self.assertIn('codexModel.value = "gpt-5.6-luna"', script)
        self.assertIn('option("light", "Light")', script)
        self.assertIn("codex_model: controls.codexModel.value", script)
        self.assertIn("codex_effort: controls.codexEffort.value", script)
        self.assertIn(".research-codex-options", styles)
        self.assertIn("http://127.0.0.1:8201", script)
        self.assertIn("반복 조사 저장", script)
        self.assertIn("/api/research/schedules", script)
        self.assertIn("조사 주제 직접 입력", script)
        self.assertIn("대상 회사 직접 입력", script)
        self.assertIn("topic_company: controls.topicCompany.value.trim()", script)
        self.assertIn("+ 회사·조사 주제 추가", script)
        self.assertIn("company_axes: companyAxes", script)
        self.assertIn(".research-company-edit-grid", styles)
        self.assertIn(".research-topic-scope-grid", styles)
        self.assertIn(".research-provider-grid", styles)
        self.assertIn(".research-schedule-fields", styles)
        self.assertIn("조사 관리 화면 준비 중", hooks)


@unittest.skipUnless(RESEARCH_AGENT_DEPS, "research-agent dependencies are isolated")
class ResearchAgentWebTests(unittest.IsolatedAsyncioTestCase):
    async def test_duckduckgo_search_normalizes_redirects_and_deduplicates(
        self,
    ) -> None:
        html = """
        <a class="result-link" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fnews">첫 결과</a>
        <td class="result-snippet">첫 번째 공개 원문</td>
        <a class="result__a" href="https://example.com/news">중복 결과</a>
        <div class="result__snippet">중복</div>
        <a class="result__a" href="https://second.example/report">두 번째 결과</a>
        <div class="result__snippet">두 번째 공개 원문</div>
        """

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "lite.duckduckgo.com")
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})

        web = PublicWeb()
        await web._client.aclose()
        web._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await web.search("철강 관세", 5)
        finally:
            await web.aclose()
        self.assertEqual(
            [item["url"] for item in result["results"]],
            ["https://example.com/news", "https://second.example/report"],
        )

    async def test_read_only_cli_rejects_publication_commands(self) -> None:
        cli = MarketSensingCli(os_path(), publish=False)
        result = await cli.run("add-source")
        self.assertFalse(result["ok"])

    async def test_cli_file_options_only_accept_mapped_temporary_files(self) -> None:
        cli = MarketSensingCli(os_path(), publish=True)
        result = await cli.run(
            "add-source", ["--content-file", "C:\\private\\secret.txt"]
        )
        self.assertFalse(result["ok"])
        self.assertIn("@파일명", str(result["error"]))


class ResearchModelSelectionContractTests(unittest.TestCase):
    def test_request_and_runtime_preserve_supported_selection(self) -> None:
        from tools.research_agent.service import ResearchRequest
        from tools.research_agent.settings import AgentSettings

        request = ResearchRequest.from_dict(
            {
                "topic": "철강 수입규제 변화",
                "topic_company": "POSCO",
                "companies": ["POSCO"],
                "date_from": "2026-08-01",
                "date_to": "2026-08-29",
                "provider": "codex",
                "codex_model": "gpt-5.6-luna",
                "codex_effort": "light",
            }
        )
        settings = AgentSettings.from_env(
            request.provider,
            codex_model=request.codex_model,
            codex_effort=request.codex_effort,
        )
        self.assertEqual(request.codex_model, "gpt-5.6-luna")
        self.assertEqual(request.codex_effort, "light")
        self.assertEqual(settings.codex_model, "gpt-5.6-luna")
        self.assertEqual(settings.codex_effort, "low")

    def test_request_rejects_unlisted_model_and_effort(self) -> None:
        from tools.research_agent.service import ResearchRequest

        base = {
            "topic": "철강 수입규제 변화",
            "topic_company": "POSCO",
            "companies": ["POSCO"],
            "date_from": "2026-08-01",
            "date_to": "2026-08-29",
            "provider": "codex",
        }
        with self.assertRaisesRegex(ValueError, "GPT-5.6-Sol"):
            ResearchRequest.from_dict({**base, "codex_model": "gpt-5.5"})
        with self.assertRaisesRegex(ValueError, "Light"):
            ResearchRequest.from_dict({**base, "codex_effort": "xhigh"})


def os_path():
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
