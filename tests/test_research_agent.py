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


@unittest.skipUnless(RESEARCH_AGENT_DEPS, "research-agent dependencies are isolated")
class ResearchRequestTests(unittest.TestCase):
    def test_request_defaults_to_full_sqlite_publication(self) -> None:
        request = ResearchRequest.from_dict(
            {
                "topic": "철강 수입규제 변화",
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
        styles = (root / "market-sensing-wiki" / "stylesheets" / "extra.css").read_text(
            encoding="utf-8"
        )
        hooks = (root / "tools" / "project" / "mkdocs_hooks.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("javascripts/research-control-loader.js", config)
        self.assertIn('providerCard("pgpt", "P-GPT", "실제 운영"', script)
        self.assertIn('providerCard("codex", "Codex OAuth", "개발 검증"', script)
        self.assertIn("http://127.0.0.1:8201", script)
        self.assertIn("반복 조사 저장", script)
        self.assertIn("/api/research/schedules", script)
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


def os_path():
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
