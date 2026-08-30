from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlsplit


class ProviderId(StrEnum):
    PGPT = "pgpt"
    CODEX = "codex"


CODEX_MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
CODEX_EFFORTS = ("light", "medium", "high")
CODEX_EFFORT_RUNTIME = {"light": "low", "medium": "medium", "high": "high"}


@dataclass(frozen=True, slots=True)
class AgentSettings:
    provider: ProviderId
    pgpt_base_url: str
    pgpt_api_key: str | None = field(repr=False)
    pgpt_employee_no: str | None = field(repr=False)
    pgpt_company_code: str
    pgpt_model: str | None
    codex_model: str
    codex_effort: str

    @classmethod
    def from_env(
        cls,
        provider: str | ProviderId,
        *,
        codex_model: str | None = None,
        codex_effort: str | None = None,
    ) -> AgentSettings:
        selected = ProviderId(str(provider).strip().lower())
        selected_codex_model = (
            str(codex_model).strip()
            if codex_model is not None
            else os.environ.get("MARKET_AGENT_CODEX_MODEL", "gpt-5.6-luna").strip()
        ) or "gpt-5.6-luna"
        selected_codex_effort = (
            str(codex_effort).strip().lower()
            if codex_effort is not None
            else os.environ.get("MARKET_AGENT_CODEX_EFFORT", "medium").strip().lower()
        ) or "medium"
        selected_codex_effort = CODEX_EFFORT_RUNTIME.get(
            selected_codex_effort, selected_codex_effort
        )
        settings = cls(
            provider=selected,
            pgpt_base_url=(
                os.environ.get("PGPT_BASE_URL", "http://pgpt.posco.com/s0la01-gpt/v1")
                .strip()
                .rstrip("/")
            ),
            pgpt_api_key=os.environ.get("PGPT_API_KEY", "").strip() or None,
            pgpt_employee_no=os.environ.get("PGPT_EMPLOYEE_NO", "").strip() or None,
            pgpt_company_code=os.environ.get("PGPT_COMPANY_CODE", "30").strip() or "30",
            pgpt_model=(
                os.environ.get("PGPT_MODEL", "").strip()
                or os.environ.get("MYPIN_PGPT_RUNTIME_MODEL_ID", "").strip()
                or None
            ),
            codex_model=selected_codex_model,
            codex_effort=selected_codex_effort,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.provider is ProviderId.CODEX:
            if self.codex_model not in CODEX_MODELS:
                raise ValueError(
                    "Codex model must be gpt-5.6-sol, gpt-5.6-terra, or gpt-5.6-luna"
                )
            if self.codex_effort not in {"low", "medium", "high"}:
                raise ValueError(
                    "Codex effort must be light/low, medium, or high"
                )
        if self.provider is ProviderId.PGPT:
            missing = [
                name
                for name, value in (
                    ("PGPT_API_KEY", self.pgpt_api_key),
                    ("PGPT_EMPLOYEE_NO", self.pgpt_employee_no),
                    ("PGPT_MODEL", self.pgpt_model),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"P-GPT configuration is missing: {', '.join(missing)}"
                )
            parsed = urlsplit(self.pgpt_base_url)
            allowed = {
                item.strip().casefold()
                for item in os.environ.get(
                    "PGPT_ALLOWED_HOSTS", "pgpt.posco.com"
                ).split(",")
                if item.strip()
            }
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.hostname.casefold() not in allowed
            ):
                raise ValueError("PGPT_BASE_URL is not an approved P-GPT endpoint")

    def pgpt_token(self) -> str:
        if not self.pgpt_api_key or not self.pgpt_employee_no:
            raise ValueError("P-GPT credentials are not configured")
        envelope = {
            "apiKey": self.pgpt_api_key,
            "companyCode": self.pgpt_company_code,
            "systemCode": self.pgpt_employee_no,
        }
        raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
        return base64.b64encode(raw).decode("ascii")


def provider_readiness() -> list[dict[str, object]]:
    pgpt_values = (
        os.environ.get("PGPT_API_KEY", "").strip(),
        os.environ.get("PGPT_EMPLOYEE_NO", "").strip(),
        os.environ.get("PGPT_MODEL", "").strip()
        or os.environ.get("MYPIN_PGPT_RUNTIME_MODEL_ID", "").strip(),
    )
    return [
        {
            "id": ProviderId.PGPT,
            "label": "P-GPT",
            "purpose": "실제 운영",
            "configured": all(pgpt_values),
            "message": (
                "회사 P-GPT 설정이 준비되었습니다."
                if all(pgpt_values)
                else "PGPT_API_KEY, PGPT_EMPLOYEE_NO, PGPT_MODEL 설정이 필요합니다."
            ),
        },
        {
            "id": ProviderId.CODEX,
            "label": "Codex OAuth",
            "purpose": "개발 단계",
            "configured": True,
            "message": "실행 시 로컬 ChatGPT OAuth 로그인을 확인합니다.",
            "models": list(CODEX_MODELS),
            "efforts": list(CODEX_EFFORTS),
        },
    ]
