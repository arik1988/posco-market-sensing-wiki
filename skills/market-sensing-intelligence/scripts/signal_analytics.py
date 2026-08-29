"""Canonical Signal Analytics contracts shared by the Wiki snapshot and MyPIN."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any


SOURCE_MODALITIES = ("MARKET", "DOCUMENT", "PHYSICAL", "ATTENTION")
EVIDENCE_KINDS = ("claim", "event", "observation")
EVIDENCE_RELATIONS = ("support", "contradict", "context")
RISK_FACTOR_STATUSES = ("active", "retired")
CANONICAL_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*$")
RISK_FACTOR_ID_PATTERN = re.compile(r"^RF-[A-Z0-9][A-Z0-9-]{2,79}$")


def _digest(*parts: object, length: int = 16) -> str:
    raw = "\0".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length].upper()


def _timestamp(value: str | None = None) -> str:
    return value or datetime.now().astimezone().isoformat(timespec="seconds")


def require_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def validate_modality(value: object) -> str:
    modality = require_text(value, "source_modality").upper()
    if modality not in SOURCE_MODALITIES:
        raise ValueError(
            "source_modality must be MARKET, DOCUMENT, PHYSICAL, or ATTENTION"
        )
    return modality


def validate_risk_factor(value: dict[str, Any]) -> dict[str, Any]:
    risk_factor_id = require_text(value.get("risk_factor_id"), "risk_factor_id")
    if not RISK_FACTOR_ID_PATTERN.fullmatch(risk_factor_id):
        raise ValueError("risk_factor_id must use the RF-UPPER-KEBAB namespace")
    status = require_text(value.get("status", "active"), "status")
    if status not in RISK_FACTOR_STATUSES:
        raise ValueError("risk factor status must be active or retired")
    taxonomy_version = int(value.get("taxonomy_version", 1))
    if taxonomy_version < 1:
        raise ValueError("taxonomy_version must be at least 1")
    category = require_text(value.get("category"), "category")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", category):
        raise ValueError("risk factor category must be upper snake case")
    aliases = [require_text(item, "alias") for item in value.get("aliases", [])]
    if len(set(aliases)) != len(aliases):
        raise ValueError("risk factor aliases must be unique")
    now = _timestamp(value.get("created_at"))
    return {
        "schema_version": 1,
        "risk_factor_id": risk_factor_id,
        "taxonomy_version": taxonomy_version,
        "name": require_text(value.get("name"), "name"),
        "definition": require_text(value.get("definition"), "definition"),
        "category": category,
        "parent_risk_factor_id": value.get("parent_risk_factor_id"),
        "aliases": aliases,
        "status": status,
        "valid_from": value.get("valid_from"),
        "valid_to": value.get("valid_to"),
        "created_at": now,
        "updated_at": _timestamp(value.get("updated_at") or now),
    }


def observation_version(value: dict[str, Any]) -> dict[str, Any]:
    modality = validate_modality(value.get("modality"))
    if modality not in {"MARKET", "PHYSICAL", "ATTENTION"}:
        raise ValueError("observations must use MARKET, PHYSICAL, or ATTENTION modality")
    observation_id = require_text(value.get("observation_id"), "observation_id")
    version_no = int(value.get("version_no", 1))
    if version_no < 1:
        raise ValueError("observation version_no must be at least 1")
    risk_factor_ids = tuple(dict.fromkeys(value.get("risk_factor_ids", [])))
    if not risk_factor_ids:
        raise ValueError("observation requires at least one risk_factor_id")
    observed_at = require_text(value.get("observed_at"), "observed_at")
    series_key = require_text(value.get("series_key"), "series_key")
    return {
        "schema_version": 1,
        "observation_id": observation_id,
        "observation_version_id": f"OBSV-{_digest(observation_id, version_no, observed_at, value.get('value'))}",
        "version_no": version_no,
        "series_key": series_key,
        "metric_kind": require_text(value.get("metric_kind"), "metric_kind"),
        "value": value.get("value"),
        "unit": require_text(value.get("unit"), "unit"),
        "observed_at": observed_at,
        "source_id": require_text(value.get("source_id"), "source_id"),
        "modality": modality,
        "risk_factor_ids": list(risk_factor_ids),
        "verification_status": require_text(
            value.get("verification_status", "verified"), "verification_status"
        ),
        "created_at": _timestamp(value.get("created_at")),
    }


def event_version(value: dict[str, Any]) -> dict[str, Any]:
    modality = validate_modality(value.get("modality", "DOCUMENT"))
    event_id = require_text(value.get("event_id"), "event_id")
    version_no = int(value.get("version_no", 1))
    risk_factor_ids = tuple(dict.fromkeys(value.get("risk_factor_ids", [])))
    if not risk_factor_ids:
        raise ValueError("event requires at least one risk_factor_id")
    observed_at = require_text(value.get("observed_at"), "observed_at")
    return {
        "schema_version": 1,
        "event_id": event_id,
        "event_version_id": f"EVTV-{_digest(event_id, version_no, observed_at, value.get('after_value'))}",
        "version_no": version_no,
        "event_type": require_text(value.get("event_type"), "event_type"),
        "actor_ref": require_text(value.get("actor_ref"), "actor_ref"),
        "target_ref": require_text(value.get("target_ref"), "target_ref"),
        "observed_at": observed_at,
        "effective_at": value.get("effective_at"),
        "before_value": value.get("before_value"),
        "after_value": value.get("after_value"),
        "unit": value.get("unit"),
        "source_ids": list(dict.fromkeys(value.get("source_ids", []))),
        "modality": modality,
        "risk_factor_ids": list(risk_factor_ids),
        "status": require_text(value.get("status", "effective"), "status"),
        "created_at": _timestamp(value.get("created_at")),
    }


def _scenario_rows(structured_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    for section in structured_analysis.get("sections", []):
        if section.get("key") != "scenarios":
            continue
        for item in section.get("items", []):
            if item.get("key") == "scenarios" and item.get("display") == "table":
                return [dict(row) for row in item.get("rows", [])]
    raise ValueError("analysis_structured must contain the scenarios table")


def build_signal_bundle(
    *,
    canonical_key: str,
    title: str,
    sentence: str,
    signal_type: str,
    signal_role: str,
    signal_origin: str,
    assessed_at: str,
    risk_factor_ids: list[str],
    evidence_refs: list[dict[str, Any]],
    company_ids: list[str],
    business_axis: str,
    business_impact: dict[str, Any],
    urgency: dict[str, Any],
    assessment_confidence: str,
    structured_analysis: dict[str, Any],
    created_at: str,
    version_no: int = 1,
    stable_signal_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    canonical_key = require_text(canonical_key, "canonical_key")
    if not CANONICAL_KEY_PATTERN.fullmatch(canonical_key):
        raise ValueError("canonical_key must be stable lower-case dotted, kebab, or colon text")
    unique_risk_factors = list(dict.fromkeys(risk_factor_ids))
    if not unique_risk_factors:
        raise ValueError("Signal requires at least one risk_factor_id")
    if not evidence_refs:
        raise ValueError("Signal requires at least one Claim, Event, or Observation evidence ref")
    normalized_evidence = []
    for item in evidence_refs:
        kind = require_text(item.get("kind"), "evidence kind")
        if kind not in EVIDENCE_KINDS:
            raise ValueError("evidence kind must be claim, event, or observation")
        relation = require_text(item.get("relation", "support"), "evidence relation")
        if relation not in EVIDENCE_RELATIONS:
            raise ValueError("evidence relation must be support, contradict, or context")
        normalized_evidence.append(
            {
                "kind": kind,
                "version_id": require_text(item.get("version_id"), "evidence version_id"),
                "modality": validate_modality(item.get("modality")),
                "relation": relation,
                "source_ids": list(dict.fromkeys(item.get("source_ids", []))),
            }
        )
    if len({(v["kind"], v["version_id"], v["relation"]) for v in normalized_evidence}) != len(normalized_evidence):
        raise ValueError("Signal evidence refs must be unique")

    derived_signal_id = f"SIG-{_digest(canonical_key, length=12)}"
    signal_id = str(stable_signal_id or derived_signal_id).strip()
    if not re.fullmatch(r"SIG-[A-Z0-9]{12}", signal_id):
        raise ValueError("stable_signal_id must use the SIG-XXXXXXXXXXXX namespace")
    if version_no < 1:
        raise ValueError("Signal version_no must be at least 1")
    semantic_payload = {
        "canonical_key": canonical_key,
        "title": title,
        "sentence": sentence,
        "signal_type": signal_type,
        "signal_role": signal_role,
        "signal_origin": signal_origin,
        "assessed_at": assessed_at,
        "risk_factor_ids": unique_risk_factors,
        "evidence_refs": normalized_evidence,
    }
    signal_version_id = f"SIGV-{_digest(signal_id, version_no, json.dumps(semantic_payload, ensure_ascii=False, sort_keys=True))}"
    company_impacts = []
    for company_id in dict.fromkeys(company_ids):
        impact_id = f"CIV-{_digest(signal_version_id, company_id, business_axis)}"
        company_impacts.append(
            {
                "schema_version": 1,
                "company_impact_version_id": impact_id,
                "signal_version_id": signal_version_id,
                "version_no": 1,
                "company_id": company_id,
                "business_axis": business_axis,
                "business_impact": business_impact,
                "urgency": urgency,
                "assessment_confidence": assessment_confidence,
                "assessed_at": assessed_at,
                "created_at": created_at,
            }
        )
    impact_ids = [item["company_impact_version_id"] for item in company_impacts]
    scenarios = []
    for index, row in enumerate(_scenario_rows(structured_analysis), start=1):
        scenario_key = require_text(row.get("case"), "scenario case")
        scenarios.append(
            {
                "schema_version": 1,
                "scenario_version_id": f"SCNV-{_digest(signal_version_id, scenario_key, index)}",
                "signal_version_id": signal_version_id,
                "company_impact_version_ids": impact_ids,
                "scenario_key": scenario_key,
                "version_no": 1,
                "condition": require_text(row.get("condition"), "scenario condition"),
                "meaning": require_text(row.get("meaning"), "scenario meaning"),
                "action": require_text(row.get("action"), "scenario action"),
                "created_at": created_at,
            }
        )
    signal_version = {
        "schema_version": 1,
        "signal_id": signal_id,
        "signal_version_id": signal_version_id,
        "version_no": version_no,
        **semantic_payload,
        "company_impact_version_ids": impact_ids,
        "scenario_version_ids": [item["scenario_version_id"] for item in scenarios],
        "created_at": created_at,
    }
    return signal_version, company_impacts, scenarios


__all__ = [
    "SOURCE_MODALITIES",
    "build_signal_bundle",
    "event_version",
    "observation_version",
    "validate_modality",
    "validate_risk_factor",
]
