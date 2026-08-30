#!/usr/bin/env python
"""Deterministic storage tools for the market-sensing-intelligence skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from report_html import render_report_html
from signal_analytics import (
    SOURCE_MODALITIES,
    build_signal_bundle,
    event_version,
    observation_version,
    validate_modality,
    validate_risk_factor,
)
from systematic_signal_analytics import (
    run_systematic_analysis,
    validate_systematic_analysis_result,
)
from sqlite_store import (
    append_operation_log,
    collection_for_directory,
    connection_scope as sqlite_connection_scope,
    database_path,
    delete_record,
    get_artifact,
    get_binary_asset,
    get_settings,
    get_source_content,
    infer_root_and_collection,
    initialize as initialize_sqlite,
    integrity as sqlite_integrity,
    list_artifacts,
    list_logical_json,
    online_backup,
    put_artifact,
    put_binary_asset,
    put_claim_version,
    put_event_version,
    put_observation_version,
    put_risk_factor,
    put_risk_factor_links,
    put_signal_analytics_bundle,
    put_systematic_analysis,
    put_source_asset,
    put_settings,
    put_source_content,
    read_logical_json,
    record_exists,
    transaction as sqlite_transaction,
    write_logical_json,
)


SOURCE_TYPES = {
    "company_release",
    "company_ir",
    "government",
    "permit",
    "patent",
    "academic",
    "equipment_supplier",
    "specialist_media",
    "general_media",
    "other",
}
SOURCE_RELIABILITY = {"primary", "high", "medium", "low"}
ACADEMIC_KINDS = {
    "journal_article",
    "conference_paper",
    "conference_presentation",
    "preprint",
    "thesis",
    "research_report",
}
PEER_REVIEW_STATUSES = {"peer_reviewed", "not_peer_reviewed", "unknown"}
CLAIM_STATUS = {"active", "superseded", "disputed", "cancelled", "stale"}
CLAIM_CONFIDENCE = {"high", "medium", "low"}
SOURCE_SCHEMA_VERSION = 2
CLAIM_SCHEMA_VERSION = 2
SIGNAL_SCHEMA_VERSION = 4
SIGNAL_SCORE_MAX = 10
SCORE_RATIONALE_MIN_LENGTH = 120
SCORE_RATIONALE_MAX_LENGTH = 600
SCORE_RATIONALE_BOUNDARY_PATTERN = re.compile(
    r"(?:이상|이하|상향|하향|높이|낮추|최상위|단계|수준)"
)
LEGACY_INSIGHT_SCHEMA_VERSION = 1
INSIGHT_SCHEMA_VERSION = 3
STRUCTURED_ANALYSIS_SCHEMA_VERSION = 3
LEGACY_STRUCTURED_ANALYSIS_SCHEMA_VERSION = 1
SUPPORTED_STRUCTURED_ANALYSIS_SCHEMA_VERSIONS = {1, 2, 3}
STRUCTURED_ANALYSIS_DISPLAY_TYPES = {"text", "list", "table", "flow"}
STRUCTURED_ANALYSIS_LEGACY_REQUIRED_KEYS = {
    "decision_question",
    "provisional_conclusion",
    "verified_change",
    "impact_path",
    "scenarios",
    "monitoring_indicators",
    "falsification_condition",
    "decision_outputs",
    "limitations",
}
STRUCTURED_ANALYSIS_REQUIRED_KEYS = {
    "decision_question",
    "provisional_conclusion",
    "verified_change",
    "impact_path",
    "scenarios",
    "monitoring_indicators",
    "falsification_condition",
    "decision_outputs",
    "limitations",
    "opportunity",
    "risk",
    "opportunity_cost",
    "quantification_decision",
    "escalation_triggers",
    "deescalation_triggers",
    "timing",
    "baseline_assumption",
    "decision_change",
    "internal_data",
    "owner",
    "detection_trigger",
}
STRUCTURED_ANALYSIS_MID_SCORE_REQUIRED_KEYS = {
    "secondary_effects",
    "response_options",
    "sensitivity_drivers",
    "execution_sequence",
}
STRUCTURED_ANALYSIS_HIGH_SCORE_REQUIRED_KEYS = {
    "delay_loss",
    "reversibility",
    "strongest_counterevidence",
    "decision_authority",
    "confirmed_deadline_or_condition",
}
STRUCTURED_ANALYSIS_REQUIRED_SECTION_KEYS = {
    "scenarios",
    "business_impact",
    "key_drivers",
    "evidence",
    "falsification_actions",
}
ASSUMPTION_CHALLENGE_SCHEMA_VERSION = 1
SIGNAL_TYPES = (
    "정책·규제",
    "수급·가격",
    "경쟁사",
    "투자·프로젝트",
    "공급망·물류",
    "고객·계약",
    "기술·운영",
    "재무·실적",
)
SIGNAL_ROLES = ("core_market_signal", "execution_context")
SIGNAL_ORIGINS = (
    "external_market",
    "policy_regulator",
    "competitor_counterparty",
    "company_execution",
)
SIGNAL_ROLE_ORIGINS = {
    "core_market_signal": {
        "external_market",
        "policy_regulator",
        "competitor_counterparty",
    },
    "execution_context": {"company_execution"},
}
RUN_SIGNAL_CONTRACT = {
    "version": 2,
    "minimum_core_market_ratio": 0.7,
    "single_asset_concentration_threshold": 0.5,
    "single_asset_minimum_signals": 3,
    "minimum_signals_per_axis": 3,
    "minimum_observation_band_ratio": 0.2,
    "minimum_management_band_ratio": 0.2,
    "maximum_executive_band_ratio": 0.5,
    "maximum_single_score_ratio": 0.5,
}
RUN_DISCOVERY_CONTRACT = {
    "version": 1,
    "required_for_roles": ["core_market_signal"],
}
RUN_RESEARCH_CONTRACT_VERSION = 5
RESEARCH_CELL_STATUSES = {"pending", "covered", "no_change", "blocked"}
RESEARCH_CANDIDATE_DISPOSITIONS = {"published_signal", "watchlist", "rejected"}
RESEARCH_EVIDENCE_CHANNELS = {
    "company_action",
    "government_action",
    "physical_action",
    "counterparty_action",
    "failure_signal",
    "follow_up_execution",
    "local_official",
}
SURPRISE_PATTERNS = {
    "substitute_demand",
    "market_access_rule",
    "input_bottleneck",
    "trade_flow_reversal",
    "policy_collision",
    "customer_behavior_gap",
    "cost_curve_break",
    "timing_gap",
}
TARGET_COMPANY_SOURCE_TERMS = {
    "COM-POSCO": ("posco", "포스코"),
    "COM-POSCO-HOLDINGS": ("posco holdings", "포스코홀딩스"),
    "COM-POSCO-INTERNATIONAL": (
        "posco international",
        "포스코인터내셔널",
        "senex",
    ),
    "COM-POSCO-ENC": ("posco e&c", "posco enc", "포스코이앤씨", "포스코건설"),
    "COM-POSCO-FUTURE-M": ("posco future m", "포스코퓨처엠", "포스코케미칼"),
    "COM-POSCO-FLOW": ("posco flow", "포스코플로우"),
    "COM-POSCO-MOBILITY-SOLUTION": (
        "posco mobility solution",
        "포스코모빌리티솔루션",
    ),
    "COM-POSCO-STEELEON": ("posco steeleon", "포스코스틸리온"),
}
COMPANY_OWNED_SOURCE_TYPES = {"company_release", "company_ir"}
MARKET_SENSING_COMPANY_AXES = {
    "COM-POSCO": ("철강",),
    "COM-POSCO-HOLDINGS": ("리튬", "전략광물"),
    "COM-POSCO-INTERNATIONAL": (
        "에너지",
        "식량·팜",
    ),
    "COM-POSCO-ENC": ("건설·인프라",),
    "COM-POSCO-FUTURE-M": ("이차전지소재",),
    "COM-POSCO-FLOW": ("철강·원료 물류",),
    "COM-POSCO-MOBILITY-SOLUTION": ("구동모터코아·강건재가공",),
    "COM-POSCO-STEELEON": ("도금·컬러강판",),
}
COMPANY_NAME_TO_ID = {
    "POSCO": "COM-POSCO",
    "POSCO Holdings": "COM-POSCO-HOLDINGS",
    "POSCO International": "COM-POSCO-INTERNATIONAL",
    "POSCO E&C": "COM-POSCO-ENC",
    "POSCO Future M": "COM-POSCO-FUTURE-M",
    "POSCO Flow": "COM-POSCO-FLOW",
    "POSCO Mobility Solution": "COM-POSCO-MOBILITY-SOLUTION",
    "POSCO Steeleon": "COM-POSCO-STEELEON",
}
MARKET_SENSING_AXES = {
    company_id: axes[0] for company_id, axes in MARKET_SENSING_COMPANY_AXES.items()
}
ALL_MARKET_SENSING_AXES = frozenset(
    axis for axes in MARKET_SENSING_COMPANY_AXES.values() for axis in axes
)


def company_supports_business_axis(company_id: str, business_axis: str) -> bool:
    return business_axis in MARKET_SENSING_COMPANY_AXES.get(company_id, ())
REQUIRED_SIGNAL_PREDICATES = {
    "business_axis",
    "business_impact_score_1_to_10",
    "business_impact_rationale",
    "urgency_score_1_to_10",
    "urgency_rationale",
    "assessment_confidence",
    "assessed_at",
    "impact_path",
    "recommended_follow_up",
}
GENERATED_MARKER = "<!-- AUTO-GENERATED BY market-sensing-intelligence. DO NOT EDIT. -->"
WIKILINK_PATTERN = re.compile(r"\[\[([^]|#]+)(?:#[^]|]+)?(?:\|[^]]+)?\]\]")
SUBJECT_FOLDERS = {
    "COM": "companies",
    "TEC": "technologies",
    "PRJ": "projects",
}
TECHNOLOGY_PREDICATES = {
    "hydrogen direct reduced iron": "hydrogen_dri_status",
    "electric smelting furnace": "electric_smelting_furnace_status",
    "molten oxide electrolysis": "molten_oxide_electrolysis_status",
    "blast furnace CCUS": "blast_furnace_ccus_status",
    "low-carbon ironmaking": "low_carbon_ironmaking_status",
    "smart steelworks": "smart_steelworks_status",
    "low-temperature aqueous iron electrolysis": "aqueous_iron_electrolysis_status",
    "high-grade EAF and scrap impurity removal": "high_grade_eaf_scrap_purification_status",
    "hydrogen-based fine-ore reduction": "fine_ore_hydrogen_reduction_status",
    "hydrogen plasma smelting reduction": "hydrogen_plasma_smelting_status",
    "microwave biomass ironmaking": "microwave_biomass_ironmaking_status",
    "zesty hydrogen flash reduction": "zesty_hydrogen_flash_reduction_status",
    "hisarna cyclone smelting reduction": "hisarna_cyclone_smelting_reduction_status",
}
TECHNOLOGY_DETAILS = {
    "hydrogen direct reduced iron": {
        "label": "수소 직접환원철 (Hydrogen DRI)",
        "category": "고체 철광석의 수소 가스 직접환원",
        "description": (
            "철광석을 녹이기 전에 수소 중심의 환원가스로 산소를 제거해 환원철을 만드는 "
            "경로입니다. 석탄 기반 고로를 대체할 잠재력이 있지만 저가 청정수소, 고품위 "
            "원료, 환원철 후단 용융 설비가 함께 필요합니다."
        ),
        "scope_note": (
            "이 문서는 펠릿·괴광을 충전하는 샤프트로 중심의 수소 DRI를 주축으로 "
            "다룹니다. 미분광 유동층 경로는 ‘무펠릿 미분광 수소환원’ 문서에서 "
            "별도로 비교합니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["DR급 펠릿·괴광"] --> B["샤프트 환원로 — 고체 상태"]\n'
            '    P["재생전력"] --> H["수전해 수소"]\n'
            '    H --> G["수소 가열·순환가스"]\n'
            '    G --> B\n'
            '    B --> W["수증기 제거·가스 재순환"]\n'
            '    W --> G\n'
            '    B --> D["DRI — 다공성 고체 철"]\n'
            '    D --> E["HDRI 직송 또는 HBI 브리켓"]\n'
            '    E --> F["EAF·전기용융 및 정련"]\n'
            '    F --> C["탄소·산소·슬래그 조정"]\n'
            '    classDef input fill:#F5F6F7,stroke:#9BA2AD,color:#20242C\n'
            '    classDef process fill:#EAF5EE,stroke:#24724A,color:#20242C\n'
            '    classDef output fill:#24724A,stroke:#195C39,color:#FFFFFF\n'
            '    classDef issue fill:#FFF4E5,stroke:#B26A00,color:#20242C\n'
            '    class A,P,H input\n'
            '    class B,G,W process\n'
            '    class D,E,F output\n'
            '    class C issue'
        ),
        "process_legend": (
            "**색상 범례 (AI 의미 그룹):** 회색=원료·에너지 · 녹색=환원·가스순환 · "
            "진한 녹색=제품·후단 · 황색=후단 보정 과제"
        ),
        "analysis_points": (
            "천연가스 기반 DRI 샤프트로와 수소가 포함된 환원가스 운전은 상업 규모 "
            "경험이 있지만, 이것이 곧 100% 재생수소의 장기 상업 운전 실적을 뜻하지는 "
            "않습니다. 수소 비율·열원·제품 탄소를 함께 확인해야 합니다.",
            "수소 환원은 탄소계 환원보다 최종 FeO→Fe 반응의 열수지가 불리해 가스 "
            "가열과 열통합이 중요합니다. 환원속도만 빠르다는 이유로 생산성이 자동으로 "
            "상승한다고 볼 수 없습니다.",
            "DR급 원료의 품위·강도·환원성·클러스터링 저항은 샤프트로 통기성과 EAF "
            "슬래그량을 동시에 좌우합니다. 저품위 광석을 쓰려면 선광·펠릿화 또는 "
            "전기용융로와의 조합을 별도로 평가해야 합니다.",
            "0%C DRI는 제선 단계의 직접배출을 줄이지만 EAF의 화학에너지·슬래그 포밍·"
            "FeO 환원·교반을 다른 방식으로 보충해야 하므로 철 생산과 제강을 하나의 "
            "시스템 경계에서 비교해야 합니다.",
        ),
        "posco_implications": (
            "POSCO HyREX는 미분광 유동층을 지향하므로 샤프트로 수소 DRI와 경쟁 관계인 "
            "동시에 벤치마크입니다. 비교 지표는 수소원단위뿐 아니라 펠릿화 에너지·"
            "원료 허용범위·스티킹 제어·후단 용융 부담까지 포함해야 합니다.",
            "광양 전기로와 향후 전기용융 기술을 고려하면, 외부 HBI 조달·자체 DRI·"
            "HyREX 환원물을 같은 금속원 포트폴리오에서 잔류원소·탄소·맥석·물류비로 "
            "비교할 필요가 있습니다.",
            "우선 모니터링 지표는 실제 수소 비율, 수소 kg/t-DRI, 가스 가열 전력, "
            "연속운전 시간, 금속화율, 제품 탄소, 클러스터링 지수, 펠릿 품위, "
            "HDRI 온도와 EAF kWh/t입니다.",
        ),
        "related_projects": (
            "PRJ-HYBRIT-LULEA-PILOT",
            "PRJ-HYBRIT-GALLIVARE-DEMO",
            "PRJ-STEGRA-BODEN",
            "PRJ-TATA-IJMUIDEN-DRP-EAF",
        ),
        "watch": (
            "실제 수소 사용 비율, 연간 DRI 생산량, 천연가스에서 수소로 전환하는 시점, "
            "수소·가열 전력 원단위, 금속화율·제품 탄소와 상용 연속운전 실적을 "
            "확인해야 합니다."
        ),
    },
    "electric smelting furnace": {
        "label": "전기용융로 (Electric Smelting Furnace)",
        "category": "DRI 용융·잔류산화물 환원·맥석 분리 제선",
        "description": (
            "직접환원철이나 저품위 원료에서 만든 환원물을 전기로 녹여 용선 또는 쇳물을 "
            "생산하는 경로입니다. 고품위 펠릿 의존도를 낮추고 기존 전로 공정과 연결할 "
            "수 있다는 점이 핵심입니다."
        ),
        "scope_note": (
            "이 문서의 ESF는 스크랩을 배치식으로 녹여 용강을 만드는 EAF가 아니라, "
            "DRI를 연속 투입해 잔류 FeO를 추가 환원하고 맥석을 슬래그로 분리하여 "
            "BOF·EAF 정련용 고탄소 용선을 만드는 제선 설비를 뜻합니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["DRI — 펠릿·괴광·미분·브리켓"] --> B["밀폐형 ESF — 연속 장입"]\n'
            '    P["전력"] --> E["전극·아크 및 저항가열"]\n'
            '    E --> B\n'
            '    C["소량 탄소·환원제"] --> B\n'
            '    F["CaO·MgO 등 플럭스"] --> B\n'
            '    B --> R["잔류 FeO 환원·금속 용융"]\n'
            '    R --> S["맥석·FeO·황을 담는 용융 슬래그"]\n'
            '    R --> H["고탄소 용선"]\n'
            '    S --> T["주기적 출재·시멘트 원료 검토"]\n'
            '    H --> O["BOF 또는 EAF 정련"]\n'
            '    O --> L["용강"]\n'
            '    B --> G["환원성 배가스·열 회수 검토"]\n'
            '    classDef input fill:#F5F6F7,stroke:#9BA2AD,color:#20242C\n'
            '    classDef process fill:#FFF1E8,stroke:#C95C27,color:#20242C\n'
            '    classDef output fill:#C95C27,stroke:#98431D,color:#FFFFFF\n'
            '    classDef issue fill:#FFF7D6,stroke:#A87600,color:#20242C\n'
            '    class A,P,C,F input\n'
            '    class B,E,R process\n'
            '    class H,O,L output\n'
            '    class S,T,G issue'
        ),
        "process_legend": (
            "**색상 범례 (AI 의미 그룹):** 회색=원료·에너지 · 주황=용융·환원 · "
            "진한 주황=금속 제품·정련 · 황색=슬래그·배가스 관리"
        ),
        "analysis_points": (
            "ESF의 원료 유연성은 맥석을 없애는 것이 아니라 슬래그로 받아내는 능력입니다. "
            "광석 품위가 낮을수록 슬래그량·플럭스·열부하·출재량이 증가하므로 허용 가능과 "
            "경제적이라는 판단을 분리해야 합니다.",
            "80–85% 금속화 DRI 수용 가능성은 샤프트로의 고금속화·스티킹 부담을 줄일 "
            "잠재력이 있지만, BHP의 공개 기술 시나리오입니다. 광종별 잔류 FeO 환원속도, "
            "탄소원단위와 철 회수율이 파일럿에서 함께 입증되어야 합니다.",
            "OSBF의 고저항·고출력 장점은 공급사 자료 비중이 크고 독립 검증이 부족합니다. "
            "아크 길이, 슬래그 전기전도도, 장입 속도, 열분포와 노체 형상이 서로 결합되므로 "
            "작은 로의 안정 운전을 그대로 대형화할 수 없습니다.",
            "저배출성은 ESF 단독이 아니라 환원가스의 수소·천연가스 비율, 전력 배출계수, "
            "탄소·플럭스, 철 수율, BOF 정련까지 포함한 DRI–ESF–BOF 시스템 경계에서 "
            "평가해야 합니다.",
        ),
        "posco_implications": (
            "HyREX의 유동층 환원물은 입도·금속화·잔류 FeO·맥석이 샤프트 DRI와 다를 수 "
            "있습니다. 1 t/h 파일럿의 첫 출선보다 광종별 장기 연속장입, Fe 수율, "
            "슬래그 염기도와 출재 안정성이 더 중요한 확대 지표입니다.",
            "ESF는 기존 BOF·연주·압연 자산을 유지할 수 있는 전환 경로이지만, 고로 한 기를 "
            "대체하려면 복수 모듈과 대규모 전력·전극·내화물 정비체계가 필요할 수 있습니다. "
            "배치도와 정비 중 우회 생산까지 포함한 통합 설계가 필요합니다.",
            "우선 모니터링 지표는 DRI 품위·입도·금속화율, 잔류 FeO, 탄소 kg/t, "
            "전력 kWh/t-hot metal, 슬래그 kg/t와 FeO, 철 회수율, 용선 C·Si·P·S, "
            "전극소모, 내화물 캠페인 수명, 연속운전 시간과 출선 간격입니다.",
        ),
        "related_projects": (
            "PRJ-NEOSMELT-KWINANA",
            "PRJ-HY4SMELT",
            "PRJ-METSO-PORI-DRI-SMELTING-PILOT",
        ),
        "watch": (
            "시험 규모와 상업 설비의 차이, 투입 원료 품위·금속화율, 탄소·전력원단위, "
            "철 회수율, 슬래그량·조성, 전극·내화물 수명과 후단 BOF·EAF 통합 여부를 "
            "확인해야 합니다."
        ),
    },
    "molten oxide electrolysis": {
        "label": "용융산화물 전기분해 (Molten Oxide Electrolysis)",
        "category": "고온 직접 전해 기반 1차 철 생산",
        "description": (
            "고온의 용융 산화철에 전기를 흘려 철과 산소를 직접 분리하는 전기화 제철 "
            "기술입니다. 탄소 환원제를 쓰지 않을 수 있지만 대형 셀의 수명·전력비·"
            "상용 규모 확대가 아직 핵심 과제입니다."
        ),
        "scope_note": (
            "이 문서는 1,600°C 안팎에서 액체 철을 직접 생산하는 산업화 경로와, "
            "더 낮은 온도에서 고체 철을 얻는 학술 변형을 구분해 다룹니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["철광석·플럭스"] --> B["용융 산화물 전해질"]\n'
            '    P["재생전력"] --> B\n'
            '    B --> C["음극 환원 — 액체 철"]\n'
            '    B --> D["불활성 양극 — 산소 발생"]\n'
            '    C --> E["출선·래들 정련"]\n'
            '    B --> F["맥석·전해질 관리"]\n'
            '    classDef input fill:#F5F6F7,stroke:#9BA2AD,color:#20242C\n'
            '    classDef process fill:#EDF2FB,stroke:#3F66C9,color:#20242C\n'
            '    classDef output fill:#3F66C9,stroke:#3158B8,color:#FFFFFF\n'
            '    classDef issue fill:#FFF4E5,stroke:#B26A00,color:#20242C\n'
            '    class A,P input\n'
            '    class B process\n'
            '    class C,D,E output\n'
            '    class F issue'
        ),
        "process_legend": (
            "**색상 범례 (AI 의미 그룹):** 회색=투입 · 옅은 코발트=전해 공정 · "
            "진한 코발트=제품·후단 · 황색=운영 쟁점"
        ),
        "analysis_points": (
            "2025년 다중 양극 셀의 톤 단위 출선은 단일 양극·kg급 시험보다 진전된 "
            "근거지만, 연속 캠페인 시간·전류효율·양극 마모율·연산 환산능력이 "
            "공개되지 않아 상용성 입증과는 구분해야 합니다.",
            "광석 품위 유연성은 펠릿·수소 인프라 의존을 줄일 잠재력이 있으나, "
            "맥석이 전해질 조성·점도·전도도·양극 부식과 부산물 처리에 미치는 "
            "영향까지 닫힌 물질수지로 검증되어야 합니다.",
            "경제성은 전력가격뿐 아니라 전류효율, 셀 가동률, 양극·내화물 수명, "
            "출선당 생산성에 민감합니다. 산소와 슬래그 판매수익은 대규모 시장에서 "
            "보수적으로 평가하는 편이 타당합니다.",
        ),
        "posco_implications": (
            "HyREX와 달리 수소 제조·저장·수송을 생략할 수 있어 장기 대안 포트폴리오의 "
            "옵션 가치가 있습니다. 대신 고온 전해 셀과 불활성 양극의 기술위험이 더 큽니다.",
            "POSCO 지원 서울대 연구는 900°C급 저온 MOE의 별도 연구축을 보여줍니다. "
            "Boston Metal의 액체 철 경로와 제품 형태·후단 공정이 다르므로 동일 성숙도 "
            "선상에서 직접 비교하면 안 됩니다.",
            "우선 모니터링 지표는 셀당 정격 전류와 생산량, 1회 연속운전 시간, "
            "전류효율, kWh/t-Fe, 양극 마모율, 맥석 허용범위, 제품 불순물, 첫 "
            "독립 실증부지와 라이선스 계약입니다.",
        ),
        "related_projects": ("PRJ-BOSTON-METAL-MOE-WOBURN",),
        "watch": (
            "투자·제휴 발표와 자체 설비 운영을 구분하고, 셀 규모, 연속 운전시간, "
            "제품 품질과 상용 설비 착공 여부를 확인해야 합니다."
        ),
    },
    "blast furnace CCUS": {
        "label": "고로 CCUS",
        "category": "기존 BF–BOF 자산의 잔존탄소 포집·순환·저장",
        "description": (
            "기존 고로에서 발생하는 이산화탄소를 분리·포집해 저장하거나 원료로 다시 "
            "사용하는 경로입니다. 기존 자산을 활용할 수 있지만 포집률, 에너지 사용, "
            "운송·저장 인프라와 비용이 사업성을 좌우합니다."
        ),
        "scope_note": (
            "이 문서는 고로가스에서 CO2를 분리하는 설비만이 아니라, 고로가스 재순환·"
            "산소송풍, 압축·액화·수송, 영구 저장 또는 제품 전환까지의 사슬을 다룹니다. "
            "CCU 제품화와 지중 CCS는 탄소의 체류기간과 회계 경계가 다르므로 분리해 봅니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["고로 — 철광석·코크스·열풍"] --> B["고로 상부가스 — CO·CO2·H2·N2"]\n'
            '    B --> C["제진·냉각·탈황 등 전처리"]\n'
            '    C --> D{"경로 선택"}\n'
            '    D --> E["후단 포집 — 아민·PSA/VPSA·물리흡수"]\n'
            '    D --> F["TGR-BF — CO2 분리 후 CO·H2 환원가스 재순환"]\n'
            '    F --> G["산소송풍·가스 가열·노내 열수지 제어"]\n'
            '    E --> H["고농도 CO2 — 탈수·압축 또는 액화"]\n'
            '    G --> H\n'
            '    H --> I{"탄소의 최종 행선지"}\n'
            '    I --> J["CCS — 파이프·선박 수송 후 지중 주입·MRV"]\n'
            '    I --> K["CCU — 메탄올·에탄올·합성메탄·공정용 CO2"]\n'
            '    K -. 제품 사용·연소 시 재배출 가능 .-> L["전과정 탄소회계"]\n'
            '    J --> L'
        ),
        "process_legend": (
            "**색상 범례 (AI 의미 그룹):** 회색=기존 고로·가스 · 파랑=분리·포집 · "
            "주황=가스 재순환·열수지 · 녹색=수송·저장 · 보라=제품화·탄소회계"
        ),
        "analysis_points": (
            "고로가스 포집률과 제철소 전체 감축률은 같은 수치가 아닙니다. 코크스오븐, "
            "소결, 열풍로, 발전 등 여러 배출원이 남고, 포집설비의 증기·전력 배출도 "
            "포함해야 하므로 제품 1톤 기준 순회피량을 별도로 계산해야 합니다.",
            "TGR-BF는 CO2를 제거한 CO·H2를 노 안으로 돌려 환원가스 이용률과 CO2 농도를 "
            "높일 수 있지만, 질소 희석을 줄이는 산소송풍과 가스 가열이 필요합니다. "
            "따라서 산소공장·압축기·열교환기까지 포함한 통합 설비입니다.",
            "아민식 후단 포집은 기존 가스계통에 추가하기 상대적으로 쉽지만 재생열이 "
            "핵심 부담입니다. PSA/VPSA·물리흡수는 가스 압력·조성에 민감해, 공정별 "
            "원가 비교는 동일한 CO2 순도·회수율·압축압력을 맞춘 뒤 해야 합니다.",
            "CCU는 포집량 전체를 영구 감축으로 계산할 수 없습니다. 에탄올·메탄올·"
            "합성메탄은 제품 사용 때 탄소가 다시 배출될 수 있으므로 화석 원료 대체량, "
            "추가 수소·전력, 제품 수명과 최종 처분을 포함해야 합니다.",
            "영구 저장형 CCS의 병목은 포집설비 밖에 있을 수 있습니다. 저장용량의 "
            "탐사·허가, 불순물 규격, 액화·선박 또는 파이프, 주입정, 장기 MRV와 "
            "누출 책임이 동시에 계약돼야 실제 포집량을 안정적으로 처리할 수 있습니다.",
        ),
        "posco_implications": (
            "HyREX 전환 이전의 잔존 BF 자산에는 포집이 브리지 옵션이 될 수 있지만, "
            "고로별 포집률보다 포항·광양 단지 전체의 CO2 발생원 지도와 공용 압축·"
            "액화·출하 허브 설계가 우선입니다.",
            "국내 저장지 제약을 고려하면 선박 수송을 포함한 해외 저장사슬의 인수 규격, "
            "장기 책임과 비용을 포집 기술과 함께 검증해야 합니다. CCU 파일럿은 저장 "
            "부족을 해소하는 보조 경로이지 자동으로 대규모 영구 감축을 보장하지 않습니다.",
            "우선 모니터링 지표는 원료가스 조성·압력, 포집률, CO2 순도, 재생열 GJ/t-CO2, "
            "전력 kWh/t-CO2, 압축·액화 에너지, 연간 이용률, 순회피량, 수송거리, "
            "저장계약 물량, MRV 기준과 톤당 총비용입니다.",
        ),
        "related_projects": (
            "PRJ-ULCOS-TGR-BF",
            "PRJ-TATA-JAMSHEDPUR-BF-CCU",
            "PRJ-STEELANOL-GHENT",
            "PRJ-CARBON2CHEM-DUISBURG",
            "PRJ-ARCELORMITTAL-GHENT-MHI-CO2-PILOT",
        ),
        "watch": (
            "고로 배출가스가 실제 포집 대상인지, CCU와 영구저장 CCS 중 어느 경로인지, "
            "포집량과 최종 저장처가 확정됐는지, 재생열·압축·수송을 포함한 순회피량과 "
            "톤당 비용이 공개됐는지 확인해야 합니다."
        ),
    },
    "low-carbon ironmaking": {
        "label": "저탄소 제철 종합 경로 (Low-carbon Ironmaking)",
        "category": "제철소·공급망 단위의 다중 경로 전환 체계",
        "description": (
            "스크랩 순환, 전기로, 직접환원, 수소, 전기용융, 전기분해, 바이오탄소와 "
            "CCUS를 지역·원료·기존 자산 조건에 맞춰 조합하는 전환 체계입니다. "
            "기술 하나의 성능이 아니라 원료에서 제품까지의 전체 배출과 실제 실행 "
            "단계를 함께 봐야 합니다."
        ),
        "scope_note": (
            "이 문서는 개별 반응기의 우열을 정하는 문서가 아닙니다. 1차 철과 스크랩, "
            "기존 고로 자산과 신규 설비, 전력·수소·CO2 인프라, 제품 인증을 하나의 "
            "전환 포트폴리오로 연결해 읽습니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    D["수요 절감·제품 수명 연장"] --> N["필요 조강 생산량"]\n'
            '    S["회수 스크랩"] --> Q["선별·불순물 관리"]\n'
            '    Q --> E["스크랩 중심 EAF"]\n'
            '    O["철광석·펠릿·미분광"] --> P{"1차 철 경로 선택"}\n'
            '    P --> B["기존 BF-BOF 효율화·H2 취입"]\n'
            '    B --> C["잔여 배출 CCUS"]\n'
            '    P --> R["가스/H2 DRI"]\n'
            '    R --> E\n'
            '    R --> M["ESF·용융로 + BOF/EAF"]\n'
            '    P --> X["수계·용융산화물 전기분해"]\n'
            '    X --> E\n'
            '    G["재생전력·전력망"] --> E\n'
            '    G --> H["저배출 수소"]\n'
            '    H --> R\n'
            '    T["CO2 운송·저장망"] --> C\n'
            '    E --> V["정련·압연·제품"]\n'
            '    M --> V\n'
            '    C --> V\n'
            '    V --> A["동일 경계 배출량·제품 속성 검증"]\n'
            '    N --> E\n'
            '    N --> P\n'
            '    classDef material fill:#F5F6F7,stroke:#8B95A5,color:#20242C\n'
            '    classDef bridge fill:#FFF2D9,stroke:#B97800,color:#20242C\n'
            '    classDef transform fill:#E7F3EE,stroke:#24724A,color:#20242C\n'
            '    classDef infra fill:#EAF0FB,stroke:#3F66C9,color:#20242C\n'
            '    classDef verify fill:#3F4F5F,stroke:#26323D,color:#FFFFFF\n'
            '    class D,S,Q,O,N material\n'
            '    class B,C bridge\n'
            '    class E,R,M,X,V transform\n'
            '    class G,H,T infra\n'
            '    class A verify'
        ),
        "process_legend": (
            "**색상 범례 (AI 재구성):** 회색=수요·원료 · 황색=기존 자산의 교량 경로 · "
            "녹색=공정 전환 · 청색=외부 인프라 · 진회색=동일 경계 검증"
        ),
        "analysis_points": (
            "스크랩 EAF는 가장 빠른 감축 수단이지만 세계 스크랩 총량은 축적된 철강재와 "
            "제품 수명에 묶여 있습니다. 기존 스크랩을 한 사업장이 더 사오는 것과 세계 "
            "순배출이 줄어드는 것은 같지 않으므로 스크랩 비율 보정과 추가 회수량을 함께 "
            "확인해야 합니다.",
            "천연가스 DRI를 ‘수소 전환 가능’으로 설계하는 것은 기술적 선택권을 남기지만, "
            "수소 공급망·개조 시점·보장된 전력원이 없으면 장기간 가스 운전으로 고착될 수 "
            "있습니다. capable, planned, FID, operating을 서로 다른 상태로 표시해야 합니다.",
            "고로 CCUS는 기존 자산을 활용하는 교량 경로가 될 수 있으나 코크스오븐·소결·"
            "자가발전 등 제철소의 분산 배출을 모두 포집하는 것은 아닙니다. 포집률보다 "
            "조강 1톤 기준 순회피량과 영구 저장량이 비교 지표에 더 가깝습니다.",
            "DRI-EAF와 DRI-ESF는 고품위 펠릿과 저품위 광석 대응력이 다릅니다. 설비 투자비 "
            "비교만으로는 부족하고 펠릿 프리미엄, 슬래그량, 전력·수소 원단위, 기존 BOF·"
            "연주 활용가치를 포함한 시스템 비용으로 비교해야 합니다.",
            "발표 용량은 운영 용량이 아닙니다. 2026년 IEA 집계에서 2020년 이후 발표된 "
            "근제로배출 철강 용량 105 Mt 중 FID 도달 비중은 5%였으므로, 공정 명칭보다 "
            "자금·인허가·FID·착공·시운전·램프업의 증거 사슬이 중요합니다.",
            "제품 배출량은 Scope 1만 표시하면 전기로의 전력과 DRI의 수소·펠릿 배출이 "
            "가려집니다. 최소한 Scope 1·2와 상류 Scope 3, 스크랩·부산물·인증서의 "
            "배분 규칙을 같은 경계로 맞춰야 기업 간 비교가 가능합니다.",
        ),
        "posco_implications": (
            "광양 250만 톤 전기로는 이미 준공·생산 단계인 교량 자산이고, HyREX 30만 톤 "
            "실증은 개발·부지 준비 단계입니다. 두 용량을 같은 ‘저탄소 생산능력’으로 "
            "합산하지 말고 제품군·원료·가동률별로 분리 관리해야 합니다.",
            "POSCO 경로의 핵심 비교축은 HyREX 반응기만이 아니라 광양 EAF의 스크랩·용선 "
            "혼합, 미분광 조달, 재생전력과 수소 공급, 필요 시 ESF/BOF 연계까지 이어지는 "
            "포트폴리오입니다. 각 자산의 수명과 다음 투자 결정 시점을 하나의 마스터 "
            "타임라인으로 묶는 것이 필요합니다.",
            "선행 모니터링 지표는 발표 용량이 아니라 FID 비율, 착공 진척, 실제 저배출 "
            "원료 투입량, 연속 운전시간, 제품별 Scope 1·2·상류 Scope 3, 스크랩 추가성, "
            "전력·수소 탄소집약도와 인증된 출하량입니다.",
        ),
        "related_projects": (
            "PRJ-POSCO-GWANGYANG-EAF",
            "PRJ-SSAB-LULEA-ELECTRIC-MILL",
            "PRJ-TK-H2STEEL-DUISBURG",
            "PRJ-ARCELORMITTAL-DUNKIRK-EAF",
            "PRJ-TATA-IJMUIDEN-DRP-EAF",
            "PRJ-JFE-KURASHIKI-LARGE-EAF",
            "PRJ-TATA-JAMSHEDPUR-EASYMELT",
        ),
        "watch": (
            "발표·MOU와 FID·착공·준공·램프업을 분리하고, 철광석 품위와 스크랩 추가성, "
            "실제 수소 비율, 전력 탄소집약도, CO2 영구저장량, 제품별 Scope 1·2·상류 "
            "Scope 3 및 제3자 검증 출하량을 같은 기준으로 확인해야 합니다."
        ),
    },
    "smart steelworks": {
        "label": "스마트 제철소 (Smart Steelworks)",
        "category": "제철 공정의 실시간 계측·모델·의사결정·제어 통합",
        "description": (
            "센서, 공정 모델, AI, 디지털 트윈과 자동운전을 이용해 품질·수율·에너지·"
            "안전성을 최적화하는 운영 기술입니다. 연구 과제와 실제 생산라인 배치를 "
            "구분해 봐야 합니다."
        ),
        "scope_note": (
            "이 문서는 단순 대시보드나 데이터 수집을 스마트 제철소로 간주하지 않습니다. "
            "물리 공정과 모델의 동기화, 예측의 검증, 운전 권한, DCS·PLC로의 되먹임, "
            "사람의 승인과 안전·보안 경계를 분리해 실제 자동화 수준을 판독합니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    P["물리 공정 — 원료·소결·고로·전로·연주·압연"]\n'
            '    P --> S["계측 — 온도·압력·성분·영상·진동·전력·위치"]\n'
            '    S --> C["문맥화 — 설비 ID·조업 이벤트·품질·정비 이력·시간 정렬"]\n'
            '    C --> M{"모델 계층"}\n'
            '    M --> PH["물리·열화학 모델"]\n'
            '    M --> ML["통계·기계학습·소프트센서"]\n'
            '    PH --> T["동기화된 디지털 트윈·상태 추정"]\n'
            '    ML --> T\n'
            '    T --> V["VVUQ·드리프트·신뢰도 감시"]\n'
            '    V --> D{"의사결정 권한"}\n'
            '    D --> A["조언 — 운전자에게 예측·권고"]\n'
            '    D --> H["사람 승인 — 승인 뒤 제어값 반영"]\n'
            '    D --> L["폐루프 — 허용범위 안에서 자동 최적화"]\n'
            '    A --> O["운전자·현장 전문가"]\n'
            '    H --> O\n'
            '    O --> X["DCS·PLC·액추에이터"]\n'
            '    L --> X\n'
            '    X --> P\n'
            '    G["OT 보안·인터록·수동 전환·롤백"] -. 전 계층 보호 .-> S\n'
            '    G -. 안전 한계 .-> D\n'
            '    G -. 실행 차단 .-> X\n'
            '    classDef physical fill:#F5F6F7,stroke:#6D7785,color:#20242C\n'
            '    classDef data fill:#EAF0FB,stroke:#3F66C9,color:#20242C\n'
            '    classDef model fill:#E7F3EE,stroke:#24724A,color:#20242C\n'
            '    classDef authority fill:#FFF2D9,stroke:#B97800,color:#20242C\n'
            '    classDef safety fill:#FBE9E9,stroke:#B74848,color:#20242C\n'
            '    class P,O,X physical\n'
            '    class S,C data\n'
            '    class M,PH,ML,T,V model\n'
            '    class D,A,H,L authority\n'
            '    class G safety'
        ),
        "process_legend": (
            "**색상 범례 (AI 재구성):** 회색=물리 공정·실행 · 청색=계측·데이터 · "
            "녹색=모델·검증 · 황색=사람과 자동화의 권한 · 적색=안전·OT 보안"
        ),
        "diagram_note": (
            "위 도식은 NIST의 디지털 트윈·human-in-the-loop·OT 보안 원칙과 철강사 "
            "공개 사례를 제철소 운전 계층으로 재구성한 것입니다. 특정 회사의 네트워크 "
            "토폴로지나 제어 로직, 실제 인터록 설계도는 아닙니다."
        ),
        "analysis_points": (
            "‘예측’, ‘권고’, ‘원터치’, ‘자동운전’은 같은 단계가 아닙니다. 모델이 값을 "
            "보여주는 단계, 운전자가 승인하는 단계, 제어기가 허용범위 안에서 스스로 "
            "조정하는 폐루프 단계를 구분해야 사고 책임과 성과를 비교할 수 있습니다.",
            "디지털 트윈은 3D 화면의 유무보다 물리 설비와의 동기화, 모델의 목적 적합성, "
            "검증·검정·불확도 정량화(VVUQ), 수명주기 데이터 연결이 핵심입니다. 화면이 "
            "정교해도 실제 센서 상태와 시간 정렬이 끊기면 운전용 트윈이 아닙니다.",
            "제철 공정은 측정이 늦거나 직접 측정할 수 없는 품질 변수가 많아 소프트센서가 "
            "중요합니다. 다만 원료 배합·노체 상태·계절·설비 보수 뒤 데이터 분포가 바뀌므로 "
            "드리프트 감지와 재검증 없이 과거 정확도를 현재 성능으로 간주하면 안 됩니다.",
            "물리 모델과 기계학습을 결합한 하이브리드 모델은 데이터가 드문 비정상 영역에서 "
            "물리 제약을 제공하고, 학습 모델은 계산속도와 잔차 보정을 담당할 수 있습니다. "
            "모델별 실패모드와 전환 조건까지 공개돼야 실시간 운전 신뢰도를 평가할 수 있습니다.",
            "단일 라인의 성과를 전 제철소 성과로 확대 해석하면 안 됩니다. 적용 설비 수, "
            "운전시간, 제품·원료 범위, 자동제어 사용률, 수동 복귀 횟수와 다른 사업장 "
            "재현성을 함께 확인해야 ‘확산’이 입증됩니다.",
            "생산량·수율·에너지 개선은 기준기간, 비교군, 원료·설비 보정, 통계적 불확도와 "
            "지속기간이 없으면 인과 효과를 분리하기 어렵습니다. 회사 발표 수치는 유용한 "
            "신호지만 독립 검증 성과와 구분해야 합니다.",
            "AI가 DCS·PLC 명령에 연결되는 순간 분석 시스템이 안전중요 OT의 일부가 됩니다. "
            "네트워크 분리, 최소권한, 모델·설정 변경관리, 명령 허용범위, 인터록, 수동 전환, "
            "롤백과 사고 로그가 모델 정확도만큼 중요합니다.",
            "스마트화의 경제성은 모델 개발비만이 아니라 센서 신뢰도, 데이터 정비, 엣지 "
            "컴퓨팅, 제어계 통합, 사이버보안, 교대조 교육과 모델 수명주기 운영비를 포함해 "
            "라인별 손실 회피·품질·에너지 편익과 비교해야 합니다.",
        ),
        "posco_implications": (
            "POSCO는 포항 2고로 AI와 광양 2전로 원터치 자동화라는 서로 다른 제어 사례를 "
            "보유합니다. 두 사례를 하나의 ‘AI 적용’으로 합치지 말고 공정별 센서, 예측 "
            "대상, 운전자 권한, 자동 실행 범위와 성과 기준을 공통 양식으로 관리해야 합니다.",
            "광양 2전로의 25개 수동 조작 통합과 97% 예측 정확도는 구체적이지만, 정확도의 "
            "정의·오차분포·제품별 편차·수동 개입·인터록 작동 이력까지 있어야 장기 폐루프 "
            "성능을 판정할 수 있습니다. 포항·인도네시아 확대 계획은 실제 배치와 분리합니다.",
            "JFE의 전 고로 CPS와 7개 소결설비 전개는 수평 확산의 비교 기준입니다. POSCO도 "
            "단일 대표 사례보다 설비별 배치율, 재사용 가능한 모델·데이터 표준, 현장별 "
            "재학습 비용과 정량 성과 공개 수준을 비교하는 편이 유용합니다.",
            "우선 모니터링 지표는 센서 결측률·지연, 모델 오차와 신뢰구간, 드리프트 경보, "
            "권고 채택률, 자동제어 사용률, 수동 복귀·인터록 횟수, 품질·수율·에너지의 "
            "보정 후 효과, 가동률, 장애복구시간과 OT 보안 사고입니다.",
        ),
        "related_projects": (
            "PRJ-POSCO-GWANGYANG-ONE-TOUCH-CONVERTER",
            "PRJ-JFE-SINTER-CPS-ROLLOUT",
        ),
        "watch": (
            "적용 공정·설비 수·운전기간, 모델 입력과 검증 기준, 조언·사람 승인·폐루프 "
            "중 실제 권한, 수동 전환·인터록·OT 보안, 기준선이 공개된 정량 성과와 다른 "
            "공장으로의 재현 여부를 확인해야 합니다."
        ),
    },
    "low-temperature aqueous iron electrolysis": {
        "label": "저온 수계 전해제철 (Aqueous Iron Electrolysis)",
        "category": "저온 전기화학·습식제련 기반 철 생산",
        "description": (
            "철광석을 수용액에서 용해·정제한 뒤 전기로 철을 석출하는 저온 제철 "
            "경로입니다. 고온 용융산화물 전기분해와 달리 재생전력의 간헐 운전에 "
            "대응할 잠재력이 있지만 전해액 순환, 전극 수명과 대형화 검증이 필요합니다."
        ),
        "scope_note": (
            "이 문서에서 다루는 경로는 고온 용융염 전기분해가 아니라, 광석을 "
            "수용액에서 용해·분리한 뒤 철을 전착하는 저온 경로입니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["저품위·고불순물 철광석"] --> B["분쇄·수계 슬러리"]\n'
            '    B --> C["산성 용해 — 철 이온화"]\n'
            '    C --> D["1단 전기화학 스택 — 산·알칼리 생성"]\n'
            '    D --> E["고액·불순물 분리"]\n'
            '    E --> F["수산화철 중간체·정제 철 용액"]\n'
            '    F --> G["2단 전해채취 스택 — 음극 철 전착"]\n'
            '    P["간헐성 재생전력"] --> D\n'
            '    P --> G\n'
            '    G --> H["99%+ 고순도 철판"]\n'
            '    H --> I["박리·절단·압밀·물류"]\n'
            '    I --> J["EAF 금속원"]\n'
            '    I -. 선택 경로 .-> K["철 기반 배터리 소재"]\n'
            '    D --> R["산·알칼리 재생·공정수 순환"]\n'
            '    R --> C\n'
            '    E --> W["실리카·알루미나 등 잔사·부산물"]\n'
            '    V["핵심 병목: 전류효율·막/전극 수명·불순물 축적·수세·폐수"] -. 운전창 .-> D\n'
            '    V -. 운전창 .-> G\n'
            '    classDef feed fill:#EEF2E8,stroke:#5C7D3E,color:#20242C\n'
            '    classDef electro fill:#3F66C9,stroke:#3158B8,color:#FFFFFF\n'
            '    classDef recycle fill:#EAF0FB,stroke:#3F66C9,color:#20242C\n'
            '    classDef product fill:#24724A,stroke:#195C39,color:#FFFFFF\n'
            '    classDef risk fill:#FBE9E9,stroke:#B74848,color:#20242C\n'
            '    class A,B,C,E,F feed\n'
            '    class D,G,P electro\n'
            '    class R,W recycle\n'
            '    class H,I,J,K product\n'
            '    class V risk'
        ),
        "process_legend": (
            "**색상 범례 (AI 재구성):** 녹회색=원료·용해·분리 · 청색=전기화학 스택·전력 · "
            "연청색=약품·공정수 순환과 잔사 · 녹색=철 제품·후단 · 적색=확대 운전 병목"
        ),
        "diagram_note": (
            "위 흐름도는 Electra와 ARPA-E가 공개한 2단 전기화학 개념을 기능 단위로 "
            "재구성한 것입니다. 실제 전해액 조성, 막·전극 재료, 셀 직렬·병렬 배열, "
            "물질수지와 폐수처리 설계는 공개되지 않았습니다."
        ),
        "analysis_points": (
            "저온이라는 표현은 공정 전체의 에너지 부담이 작다는 뜻이 아닙니다. 광석 "
            "분쇄·용해, 산·알칼리 재생, 불순물 분리, 전해채취, 철판 박리·건조·압밀과 "
            "공정수 처리를 모두 포함한 kWh/t-Fe와 시약 보충량이 필요합니다.",
            "두 개의 전기화학 스택은 역할이 다릅니다. 첫 스택은 산·염기와 원료 정제를 "
            "담당하고 두 번째 스택은 금속 철을 전착하므로, 어느 한쪽의 전류효율·막 저항·"
            "가동률이 낮아도 전체 생산능력과 원가가 제한됩니다.",
            "고불순물 광석 수용 능력은 불순물이 사라진다는 뜻이 아니라 용액·고체 잔사로 "
            "이동한다는 뜻입니다. Al·Si·P·Ti·Mg와 미량금속이 용해·침전·막 오염·제품 "
            "순도에 미치는 영향과 부산물 판로를 광종별로 확인해야 합니다.",
            "철 전착은 수소발생과 경쟁할 수 있으므로 pH, 철 이온 농도, 전류밀도, 온도와 "
            "유동이 전류효율·표면 형상·박리성에 함께 영향을 줍니다. 99%+ 순도만으로 "
            "산업 생산성이나 낮은 전력원단위를 입증할 수 없습니다.",
            "간헐 재생전력 추종은 저온 공정의 잠재 장점이지만 정지·재가동 때 용액 조성, "
            "침전, 막 수화, 전극 표면과 열수지가 안정적으로 복원돼야 합니다. 단순 부하 "
            "감축 가능성과 빈번한 사이클 운전 수명을 구분해야 합니다.",
            "전착 철판은 고로 용선이나 DRI와 물성·물류가 다릅니다. 두께·취성·표면 수분, "
            "산소·수소·잔류염, 절단·압밀 밀도와 EAF 장입 거동이 후단 수율과 에너지에 "
            "미치는 영향을 확인해야 합니다.",
            "연산 500 t 시범공장은 상용 제철소보다 여러 자릿수 작습니다. 핵심 확대 지표는 "
            "명목 용량보다 셀 면적당 전류, 연속 캠페인 시간, 스택 가용률, 막·전극 교체주기, "
            "제품 회수 자동화와 실제 월간 생산량입니다.",
        ),
        "posco_implications": (
            "POSCO와 Electra의 공동검증은 HyREX·전기로와 경쟁시키기보다 원료·전력 조건이 "
            "다른 선택지로 비교해야 합니다. 동일 광석 기준 선광·펠릿화 회피 편익과 "
            "습식 분쇄·약품·전해·폐수 부담을 하나의 시스템 경계에서 계산할 필요가 있습니다.",
            "광양 전기로 투입 시험 전에는 전착 철의 벌크밀도, 수분·염소·황·인·수소, "
            "용해속도, 슬래그량, Fe 수율과 장입 자동화를 검증해야 합니다. 고순도 수치와 "
            "자동차강판용 실제 금속원 적합성은 같은 판단이 아닙니다.",
            "국내에서의 경제성은 전력가격뿐 아니라 산·알칼리 순환, 용수·폐수, 불순물 "
            "잔사 처리와 광석 물류에 민감합니다. 저가 재생전력 시간대 추종이 설비 이용률 "
            "저하를 상쇄하는지 시간대별 운전모델로 확인해야 합니다.",
            "우선 모니터링 지표는 kWh/t-Fe, 전류효율, 셀 전압·전류밀도, 스택 가용률, "
            "막·전극 수명, 산·알칼리·물 보충량, 광종별 철 회수율, 제품 순도·수분·"
            "잔류염, 잔사량, 월간 생산량과 EAF 용해 성과입니다.",
        ),
        "related_projects": (
            "PRJ-ELECTRA-CLEAN-IRON-DEMO",
            "PRJ-ARCELORMITTAL-VOLTERON",
        ),
        "watch": (
            "전력원단위·전류효율, 산·알칼리·공정수 회수율, 광종별 철 회수와 불순물 "
            "거동, 막·전극 수명, 스택 가동률, 전착 철판 자동 회수, 500 tpy 실제 "
            "월간 생산량과 EAF 장입 시험, 다음 규모 투자 결정을 확인해야 합니다."
        ),
    },
    "high-grade EAF and scrap impurity removal": {
        "label": "고급강 EAF·스크랩 불순물 제거",
        "category": "스크랩 품질관리·전기로 정련·고급강 품질 통합",
        "description": (
            "스크랩에 축적되는 구리·주석 같은 잔류원소를 용해 전에 막거나 분리하고, "
            "질소·인·황은 전기로와 2차정련에서 각기 다른 반응으로 제어해 자동차강판·"
            "전기강판 같은 고급강의 성분·표면·청정도를 맞추는 통합 기술군입니다."
        ),
        "scope_note": (
            "‘불순물 제거’를 하나의 노내 처리로 보지 않습니다. 구리·주석은 통상적인 "
            "산화슬래그로 제거하기 어려워 해체·파쇄·선별·희석 또는 아직 개발 중인 "
            "탈동 공정이 핵심인 반면, 인은 산화·염기성 슬래그, 질소는 공기 차단·CO "
            "기포·진공 등 서로 다른 제어창을 사용합니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["제품 설계·해체 — 전선·모터·도금재 분리"] --> B["파쇄·해방 — Cu 부착물 노출"]\n'
            '    B --> C["센서·영상·XRF/LIBS 선별 + 질량·로트 추적"]\n'
            '    C --> D{"스크랩 성분 판정"}\n'
            '    D --> E["청정 스크랩·자체발생 스크랩"]\n'
            '    D --> F["Cu·Sn 높은 분획 — 재선별·다른 제품군"]\n'
            '    G["DRI·HBI·용선 — 희석·금속원 보완"] --> H["등급별 장입 배합"]\n'
            '    E --> H\n'
            '    H --> I["EAF 용해 — 공기 유입·질소 흡수 최소화"]\n'
            '    I --> J["산화·염기성 슬래그 — P·Si 등 제어"]\n'
            '    J --> K["출강·래들 정련 — 탈황·합금·개재물 제어"]\n'
            '    K --> L["진공·가스교반 — 필요 등급의 N·H 제어"]\n'
            '    L --> M["연주·가열·압연 — Cu 열간취성 관리"]\n'
            '    F -. 실험·개발 경로 .-> N["고체 전처리·침출·열기계 분리"]\n'
            '    N -. 적격 분획 .-> H\n'
            '    I -. 통상 산화정련으로 Cu·Sn 제거 곤란 .-> O["용탕 탈동 후보 — 진공증류·황화슬래그 등"]\n'
            '    O -. 대부분 연구·특수공정 .-> K\n'
            '    classDef upstream fill:#EAF0FB,stroke:#3F66C9,color:#20242C\n'
            '    classDef blend fill:#E7F3EE,stroke:#24724A,color:#20242C\n'
            '    classDef steelmaking fill:#3F66C9,stroke:#3158B8,color:#FFFFFF\n'
            '    classDef risk fill:#FBE9E9,stroke:#B74848,color:#20242C\n'
            '    classDef research fill:#FFF2D9,stroke:#B97800,color:#20242C\n'
            '    class A,B,C,D upstream\n'
            '    class E,G,H blend\n'
            '    class I,J,K,L,M steelmaking\n'
            '    class F risk\n'
            '    class N,O research'
        ),
        "process_legend": (
            "**색상 범례 (AI 재구성):** 청색=용해 전 품질관리 · 녹색=적격 금속원·배합 · "
            "진한 청색=EAF·2차정련·압연 · 적색=고불순물 분획 · 황색=아직 개발·특수공정"
        ),
        "diagram_note": (
            "위 도식은 공개 학술자료와 기업·정부 프로젝트를 공정 위치별로 재구성한 "
            "것입니다. 모든 불순물이 모든 단계를 거치는 것이 아니며, 제품 규격에 따라 "
            "원료 차단·희석·정련·내성 설계를 조합합니다."
        ),
        "analysis_points": (
            "Cu·Sn과 P·S·N을 같은 ‘정련 부하’로 합산하면 투자 판단이 왜곡됩니다. "
            "P는 산소퍼텐셜과 CaO계 슬래그로 이동시킬 수 있지만 Cu는 Fe보다 산화되기 "
            "어려워 통상 산화정련에서 용강에 남습니다. 해결 설비의 위치부터 다릅니다.",
            "탈동의 가장 현실적인 기준선은 ‘용탕에서 뺀 양’보다 ‘용해 전에 들어오지 "
            "않게 한 양’입니다. 전선·모터를 해체하고, 충분히 파쇄해 Cu 부착물을 해방한 "
            "뒤 선별해야 하므로 회수율·철 손실·처리량·로트별 성분 편차를 함께 봐야 합니다.",
            "RGB 영상은 노출된 전선·코일을 빠르게 찾을 수 있지만 벌크 화학성분을 직접 "
            "측정하지 않습니다. XRF·LIBS도 표면 상태와 점측정의 대표성 문제가 있어 "
            "센서 결과를 벨트 질량·입도·로트와 연결하고 용해 분석으로 보정해야 합니다.",
            "DRI·HBI·용선 희석은 즉시 적용 가능한 품질 수단이지만 불순물을 제거하지 "
            "않고 평균농도를 낮춥니다. 청정 1차 철의 비용·탄소집약도·맥석·탄소와 "
            "저급 스크랩 사용 확대 편익을 등급별 최적화 문제로 관리해야 합니다.",
            "진공증류·황화슬래그·침출·고온 고체처리 등은 이론·실험 경로가 존재해도 "
            "상용 대량처리와 동일하지 않습니다. 처리시간, 복사열 손실, 반응제 회수, "
            "철 수율, S·C·N 재보정과 부산물 처분까지 포함한 캠페인 근거가 필요합니다.",
            "저질소강은 전기로 본체만의 문제가 아닙니다. 장입재 질소, 개방 아크의 공기, "
            "출강 재산화, 포밍슬래그·CO 교반, 진공처리가 연결되므로 탭 질소와 제품 질소, "
            "진공 처리시간을 등급별로 추적해야 합니다.",
            "고급강 가능 여부는 ‘한 강종 성공’과 ‘전 제품 대체’ 사이에 큰 간격이 있습니다. "
            "자동차 외판, 초고장력강, 전기강판은 허용 원소·표면·개재물·텍스처 요구가 "
            "다르므로 투입 스크랩 범위와 제품별 합격률을 함께 공개해야 합니다.",
            "구리 내성 압연·합금 설계는 균열을 억제할 수 있지만 Cu를 순환계에서 없애지 "
            "않습니다. 장기 순환성은 내성 기술과 분리·정제 기술의 역할을 구분해 평가해야 "
            "하며, 낮은 등급으로만 보내는 다운사이클링을 제거 성과로 계산하면 안 됩니다.",
        ),
        "posco_implications": (
            "광양 250만 톤 전기로의 고급강 경쟁력은 노체 용량보다 장입금속원 장부가 "
            "좌우할 수 있습니다. 스크랩 공급사별 Cu·Sn·Ni·Cr, 자체발생 스크랩, 용선·"
            "HBI/DRI 희석량과 제품 주문을 heat 단위로 연결하는 품질 원가 모델이 필요합니다.",
            "국내 자동차·가전 폐스크랩은 구리 배선·모터를 포함하므로 파쇄업체와 공동으로 "
            "해체성, 해방도, 센서 선별, 철 회수율을 검증할 가치가 큽니다. Sortera형 설비는 "
            "기존 비철 선별 플랫폼과 철스크랩 탈동 모듈을 구분해 실증해야 합니다.",
            "Nippon Steel의 10 t/charge 시험 EAF와 Hirohata 사례는 대형 EAF용 탈인·"
            "탈질과 제품 믹스의 비교 기준입니다. POSCO도 최고품질 한 heat보다 월간 "
            "등급별 합격률, 재처리율, tap-to-tap, 전극·슬래그·진공 비용을 비교해야 합니다.",
            "우선 모니터링 지표는 입고·장입·용강 Cu/Sn/N/P/S, 선별 회수율과 철 손실, "
            "희석용 DRI/HBI·용선 비율, 탭 질소, 슬래그 FeO·염기도·P 분배, 진공시간, "
            "제품별 합격률·표면결함·다운그레이드율, 저급 스크랩 추가 사용량입니다.",
        ),
        "related_projects": (
            "PRJ-SORTERA-SCRAP-DECOPPER",
            "PRJ-PURESCRAP-EU-SCRAP-PURITY",
            "PRJ-POSCO-GWANGYANG-EAF",
            "PRJ-JFE-KURASHIKI-LARGE-EAF",
        ),
        "watch": (
            "스크랩 종류·해방도·센서 판정의 대표성, Cu·Sn 실제 제거율과 철 손실, "
            "DRI/HBI·용선 희석 의존도, 탭 N·P·S, 처리량·가동률, 제품별 합격률과 "
            "대형 EAF 장기 생산 실적을 확인해야 합니다."
        ),
    },
    "hydrogen-based fine-ore reduction": {
        "label": "무펠릿 미분광 수소환원 (Fluidized-bed Hydrogen Reduction)",
        "category": "미분광 전처리·유동층 직접환원·전기용융 통합",
        "description": (
            "철광석 미분을 소결광이나 통상적인 환원용 펠릿으로 만들지 않고, 수소가 "
            "주성분인 환원가스로 유동화해 직접환원하는 기술군입니다. 펠릿화 공정과 "
            "그 연료·바인더 부담을 줄일 수 있지만, 입도분포·분진 비산·철 섬유 성장에 "
            "따른 고착과 유동층 붕괴, 뜨거운 환원철의 후단 이송이 성패를 좌우합니다."
        ),
        "scope_note": (
            "‘무펠릿’은 모든 조립을 금지한다는 뜻이 아닙니다. Circored는 통상적인 "
            "DR 펠릿을 생략하지만 50 μm 이하 초미분을 바인더와 함께 미세 조립할 수 "
            "있습니다. 또한 HYFOR·HyREX의 다단 유동층과 Circored의 순환·기포 유동층은 "
            "반응기 구성과 운전창이 다르므로 동일 공정으로 합산하지 않습니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["정광·미분광 — 품위·입도·맥석·수분 확인"] --> B["건조·예열·필요시 산화 — 약 800~900°C급"]\n'
            '    B --> C{"유동층 구성"}\n'
            '    C --> D["HYFOR·HyREX형 — 다단 유동층 캐스케이드"]\n'
            '    C --> E["Circored형 — 순환 유동층(CFB) + 기포 유동층(BFB)"]\n'
            '    F["수소계 환원가스"] --> G["가스 가열·정제·재순환"]\n'
            '    G --> D\n'
            '    G --> E\n'
            '    D --> H["고온 미분 환원철(HDRI)"]\n'
            '    E --> H\n'
            '    D -. 비산분 .-> I["사이클론·집진·분진 회수"]\n'
            '    E -. 비산분 .-> I\n'
            '    I -. 재순환 .-> B\n'
            '    H --> J{"후단 제품·이송"}\n'
            '    J --> K["냉각·압축 — DRI/HBI"]\n'
            '    J --> L["밀폐 고온이송 — 전기용융로(ESF)"]\n'
            '    L --> M["용선·슬래그 — 전로 또는 제강"]\n'
            '    N["고착 감시 — ΔP·온도·가스속도·응집"] -. 운전창 제약 .-> D\n'
            '    N -. 운전창 제약 .-> E\n'
            '    classDef feed fill:#EAF0FB,stroke:#3F66C9,color:#20242C\n'
            '    classDef reactor fill:#3F66C9,stroke:#3158B8,color:#FFFFFF\n'
            '    classDef recycle fill:#E7F3EE,stroke:#24724A,color:#20242C\n'
            '    classDef product fill:#F5F6F7,stroke:#6D7785,color:#20242C\n'
            '    classDef risk fill:#FBE9E9,stroke:#B74848,color:#20242C\n'
            '    class A,B,C feed\n'
            '    class D,E reactor\n'
            '    class F,G,I recycle\n'
            '    class H,J,K,L,M product\n'
            '    class N risk'
        ),
        "process_legend": (
            "**색상 범례 (AI 재구성):** 청색=원료 전처리·경로 분기 · 진한 청색=유동층 "
            "환원 · 녹색=환원가스·분진 순환 · 회색=환원철·용융 제품 · 적색=고착 운전 제약"
        ),
        "diagram_note": (
            "위 도식은 HYFOR·HyREX·Circored 공식 자료와 고착 연구를 공통 기능으로 "
            "재구성한 비교도입니다. 특정 플랜트의 배관계장도나 실제 설비 배치도가 아니며, "
            "각 기술의 반응기 수·가스 흐름·초미분 처리 방식은 서로 다릅니다."
        ),
        "analysis_points": (
            "이 기술의 경제적 가설은 ‘펠릿 가격을 아낀다’에서 끝나지 않습니다. 선광 "
            "정광을 직접 쓰면 소결·펠릿 설비와 그 배출을 줄일 수 있지만, 건조·예열·"
            "가스 순환·집진·분진 회수·고온 이송 설비가 새로 필요합니다. 원료부터 "
            "용선까지의 총 에너지·수율·설비비를 같은 경계에서 비교해야 합니다.",
            "유동화 가능한 입도창은 공급사가 제시하는 평균 입도만으로 판단할 수 없습니다. "
            "광석의 열적 파쇄로 운전 중 초미분이 늘 수 있고, 넓은 입도분포에서는 큰 입자가 "
            "덜 환원되는 동안 작은 입자는 비산합니다. 입도별 체류시간·금속화율·비산률과 "
            "회수 후 재투입 횟수를 질량수지로 확인해야 합니다.",
            "고착은 단순히 ‘입자가 녹아 붙는 현상’이 아닙니다. 환원 중 새로 생성된 금속철 "
            "표면과 철 whisker가 입자 사이를 연결해 유동성을 잃게 할 수 있습니다. 온도, "
            "가스속도, 압력, 광석 품위·입자형상·맥석이 함께 작용하므로 한 광종의 단기 "
            "성공을 다른 정광과 상업 반응기로 확대하면 안 됩니다.",
            "온도를 낮추면 고착을 줄일 수 있지만 환원속도와 가스 이용률이 낮아질 수 있고, "
            "가스속도를 높이면 접촉·응집은 줄어도 압축·가열 동력, 비산과 수소 이용률이 "
            "악화될 수 있습니다. 고착 제어는 코팅·혼광·미세조립·단계환원·반응기 구조를 "
            "포함한 다목적 운전 최적화 문제입니다.",
            "HYFOR의 다단 캐스케이드와 Circored의 순환·기포 유동층 조합은 서로 다른 "
            "체류시간·열수지 해법입니다. ‘유동층’이라는 이름만으로 처리량·금속화율을 "
            "비교하지 말고 각 단계의 온도, 압력강하, 고체 순환, 가스 조성과 환원도를 "
            "같은 기준으로 정렬해야 합니다.",
            "무펠릿 경로도 초미분 관리는 피할 수 없습니다. Circored는 50 μm 이하 분획을 "
            "바인더로 미세조립할 수 있으므로, 펠릿 공정 생략 편익에서 미세조립·건조 비용과 "
            "바인더가 환원·슬래그에 미치는 영향을 제외하면 안 됩니다.",
            "환원철이 약 600°C의 미분 상태로 나오면 재산화·발화·분진 폭발 위험과 열손실이 "
            "생깁니다. HBI로 압축하면 수송성은 좋아지지만 냉각·재가열 손실이 생기고, ESF로 "
            "직결하면 밀폐 고온이송의 신뢰성과 양 설비의 가동률 동기화가 핵심이 됩니다.",
            "Circored의 1999년 Trinidad 실증과 30만 톤 이상 HBI 생산은 중요한 장기 이력이나, "
            "현재의 재생수소·고품위 정광·ESF 통합 상업설비를 곧바로 입증하지는 않습니다. "
            "과거 운전의 정지 원인·제품 품질과 최신 설계 변경을 분리해 읽어야 합니다.",
            "파일럿의 배치당 투입량이나 시간당 처리량은 반응 검증 지표이지 상업 준비도 그 "
            "자체가 아닙니다. 장기 캠페인에서 압력강하 안정성, 벽면 부착, 사이클론 마모, "
            "가스 정제, 내화물·배관 수명, 정비시간과 전체 철 회수율이 공개되어야 합니다.",
        ),
        "posco_implications": (
            "POSCO HyREX의 핵심 경쟁력은 FINEX에서 축적한 분광 유동층 경험을 수소계 "
            "가스와 ESF에 재구성하는 데 있습니다. 그러나 FINEX의 석탄가스·공정열과 "
            "HyREX의 수소계 열수지는 다르므로 기존 가동경험을 수소 실적으로 간주하면 "
            "안 됩니다. 반응기별 가스조성·보조열·금속화율을 별도로 공개해야 합니다.",
            "포항 HyREX 실증은 건조기, 다단 유동층, 고온 환원철 이송, ESF, 집진, 출선과 "
            "슬래그 처리까지 하나의 공정열차로 검증해야 의미가 있습니다. 1 t/h ESF의 "
            "첫 용선 생산은 용융 단위조작의 근거이며, 30만 t/y 통합 실증의 연속운전 "
            "증거와는 분리해 관리해야 합니다.",
            "HYFOR·Circored는 외부 벤치마크로서 가치가 다릅니다. HYFOR는 다양한 정광의 "
            "다단 수소 유동층 파일럿 운전, Circored는 상업 크기 설계와 과거 HBI 실증 "
            "이력을 제공합니다. POSCO는 동일 정광 샘플을 기준으로 입도창·분진율·"
            "금속화율·수소이용률·고착 한계를 비교하는 공급사 중립 시험이 필요합니다.",
            "우선 모니터링 지표는 원료 광종·품위·입도분포, 건조·예열 에너지, 반응기별 "
            "온도·압력강하·가스속도, 수소 원단위와 재순환율, 금속화율 분포, 비산분·철 "
            "손실·재순환 횟수, 고착·비계획 정지, HDRI 온도, ESF 철 회수율·슬래그량, "
            "전체 설비 가동률과 제품 톤당 전력·수소·배출량입니다.",
        ),
        "related_projects": (
            "PRJ-HYFOR-DONAWITZ-PILOT",
            "PRJ-HY4SMELT",
            "PRJ-POSCO-HYREX-DEMO",
        ),
        "watch": (
            "광종별 입도창·열적 파쇄, 반응기별 ΔP·고착·비산, 수소 이용률과 금속화율 "
            "분포, 분진 회수 후 철 수율, 고온 환원철 이송, ESF 통합 가동률, 장기 캠페인 "
            "정비 이력과 원료부터 용선까지의 에너지·배출 경계를 확인해야 합니다."
        ),
    },
    "hydrogen plasma smelting reduction": {
        "label": "수소 플라즈마 용융환원 (HPSR)",
        "category": "직류 아크·수소 플라즈마 기반 단일단계 용융환원",
        "description": (
            "수소를 직류 아크에서 분자·원자·이온 상태로 활성화해 철광석 미분의 "
            "환원과 용융을 하나의 밀폐 반응기에서 수행하는 장기 제철 경로입니다. "
            "고체 DRI를 거치지 않고 저탄소 용강을 직접 만들 잠재력이 있지만, 현재 "
            "공개 근거는 Donawitz 배치·파일럿과 연속화 연구 단계입니다."
        ),
        "scope_note": (
            "여기서 HPSR은 일반 수소 DRI나 전기용융로와 구분합니다. 수소가 환원제인 "
            "동시에 플라즈마 아크가 용융 열원을 제공하며, 용융욕과 플라즈마의 계면에서 "
            "최종 환원이 일어납니다. ‘단일단계’는 보조 예열·사전환원·배가스 회수까지 "
            "불필요하다는 뜻이 아니며, 확대 설계는 오히려 이 전단·후단 통합을 검토합니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["미분광·잔사 — 품위·수분·입도·맥석 확인"] --> B["선택: 배가스 예열·FeO까지 사전환원"]\n'
            '    C["Ar + H₂"] --> D["중공 흑연전극 — 가스·광석 연속 공급"]\n'
            '    B --> D\n'
            '    D --> E["직류 아크 플라즈마 — 흑연 음극 ↔ 용융욕 양극"]\n'
            '    E --> F["플라즈마–용융산화물 계면"]\n'
            '    F --> G["Fe₂O₃ → Fe₃O₄ → FeO → Fe"]\n'
            '    G --> H["저탄소 용강·슬래그"]\n'
            '    H --> I["반연속·연속 출강 목표"]\n'
            '    F -. 생성 .-> J["H₂O(g) + 미반응 H₂ + Ar + 분진·전극기원 가스"]\n'
            '    J --> K["집진·응축·가스 회수"]\n'
            '    K -. 현열·H₂ 재이용 .-> B\n'
            '    K -. 응축수 .-> L["전해수소 재생 개념"]\n'
            '    M["OES·카메라·전압·전류·아크 길이"] --> N["모델 기반 아크·투입 제어"]\n'
            '    N -. 출력·투입 명령 .-> D\n'
            '    O["위험: 아크 불안정·전극/내화물 마모·Fe 증발·광학 차폐"] -. 운전창 .-> E\n'
            '    classDef feed fill:#EAF0FB,stroke:#3F66C9,color:#20242C\n'
            '    classDef plasma fill:#3F66C9,stroke:#3158B8,color:#FFFFFF\n'
            '    classDef product fill:#E7F3EE,stroke:#24724A,color:#20242C\n'
            '    classDef recycle fill:#F5F6F7,stroke:#6D7785,color:#20242C\n'
            '    classDef control fill:#FFF2D9,stroke:#B97800,color:#20242C\n'
            '    classDef risk fill:#FBE9E9,stroke:#B74848,color:#20242C\n'
            '    class A,B,C,D feed\n'
            '    class E,F,G plasma\n'
            '    class H,I product\n'
            '    class J,K,L recycle\n'
            '    class M,N control\n'
            '    class O risk'
        ),
        "process_legend": (
            "**색상 범례 (AI 재구성):** 청색=원료·플라즈마 가스 공급 · 진한 청색=아크·"
            "계면 환원 · 녹색=용강·슬래그 · 회색=배가스·열 회수 · 황색=계측·제어 · "
            "적색=확대 운전 위험"
        ),
        "diagram_note": (
            "위 도식은 K1-MET SuS-F 공식 반응기 구성도, FFG LIGHTBOW 제어 설명과 "
            "공개 학술자료를 기능 단위로 재구성한 것입니다. 실제 Donawitz 설비의 "
            "배관계장도·전극 치수·인터록 또는 향후 200 kg/h 설비의 준공도가 아닙니다."
        ),
        "analysis_points": (
            "HPSR의 핵심 차이는 ‘수소를 뜨겁게 쓴다’가 아니라 플라즈마–용융욕 계면에서 "
            "활성 수소종과 용융 산화철이 반응한다는 점입니다. 분자·원자·이온의 실제 "
            "분포와 계면 도달종은 온도·아크·재결합에 따라 달라지므로 명목 가스 조성만으로 "
            "환원력을 계산하면 안 됩니다.",
            "환원과 용융을 한 반응기에 결합하면 DRI 냉각·저장·재가열 단계를 줄일 수 "
            "있지만, 모든 산화철의 환원속도가 같은 것은 아닙니다. 2025년 in-situ 연구는 "
            "최종 FeO→Fe가 말기에 속도결정 단계가 될 수 있음을 보여줍니다. 완전 금속화 "
            "근처에서는 철 증발도 강해져 수율·집진·광학신호가 동시에 변합니다.",
            "플라즈마는 열원과 환원제를 결합하지만 전기에너지와 수소의 기여를 분리해 "
            "계측해야 합니다. 전력원단위만 낮추면 수소 과잉이나 미환원 산화물이 늘 수 "
            "있고, 수소 투입만 늘리면 이용률과 배가스 회수 부담이 악화됩니다. 톤당 "
            "전력·수소·Ar, 금속화율과 철 수율을 하나의 수지로 공개해야 합니다.",
            "Ar은 아크 안정화에 유용하지만 환원에 기여하지 않고 가열·순환·분리 부하를 "
            "만듭니다. 2025년 확대 시나리오의 25 vol.% Ar은 설계 가정이지 확정 상용 "
            "조건이 아닙니다. 안정성을 유지하면서 Ar 비율을 낮추는 능력이 경제성과 "
            "가스 회수계 크기를 좌우합니다.",
            "중공 흑연전극은 가스와 미분광을 아크 중심으로 공급하지만 마모·산화·열충격을 "
            "받고 탄소계 가스를 만들 수 있습니다. 전극 소비는 비용뿐 아니라 제품 탄소, "
            "CO/CO₂ 배출 경계, 아크 길이와 투입 안정성에 영향을 줍니다. ‘탄소 무사용’과 "
            "‘공정 직접 CO₂ 0’ 주장은 전극 경계를 포함해 다시 확인해야 합니다.",
            "배치당 90 kg, 반응기 최대 90,000 g, 시험 중 100~200 g/min 투입, 목표 "
            "200 kg/h는 서로 다른 지표입니다. 용융욕 보유량·순간 공급률·지속시간·"
            "출강 주기·제품량을 혼용하지 않아야 하며, 200 kg/h 목표를 실제 연속 "
            "생산 실적으로 표현하면 안 됩니다.",
            "확대 설계가 사전환원을 다시 도입하는 것은 단일단계 개념의 실패라기보다 "
            "수소·열 이용률 개선입니다. 배가스의 H₂와 현열로 광석을 FeO까지 만들면 "
            "플라즈마 체류시간과 전극·내화물 부담을 줄일 수 있지만, 전단 반응기·분진·"
            "응축수·가스조성 제어가 추가돼 전체 공정 복잡성은 커집니다.",
            "LIGHTBOW가 지적한 연속 투입 중 아크 출력 제어는 생산성의 중심 과제입니다. "
            "미분광이 아크와 용융욕을 교란하고, 아크 길이·전압·전류·용탕 높이가 서로 "
            "영향을 주므로 단순 정전류 제어로는 부족할 수 있습니다. 모델은 실제 센서 "
            "지연·분진·시야 차폐와 비정상 상태에서 검증되어야 합니다.",
            "OES와 카메라는 H·Fe·O·FeO 방출종을 통해 반응 진행을 볼 수 있지만 수증기와 "
            "분진이 광로를 흡수·차폐합니다. 광학 신호를 금속화율의 직접 측정으로 간주하지 "
            "말고, 배가스 질량분석·전기신호·샘플 화학분석과 융합해야 폐루프 제어에 쓸 수 "
            "있습니다.",
            "저품위광·잔사 처리 가능성은 중요한 장점이지만 맥석이 자동으로 제거되는 것은 "
            "아닙니다. 슬래그량·염기도·점도·P/S 분배, 철 손실, 내화물 반응과 출강 분리가 "
            "제품 품질과 에너지에 직접 연결됩니다. 특정 합성광·소량 실험의 탈인 결과를 "
            "상업 광종 전반으로 확장하면 안 됩니다.",
        ),
        "posco_implications": (
            "POSCO에는 HyREX 유동층–ESF가 더 가까운 실행 경로이므로 HPSR은 대체안보다 "
            "장기 옵션·특수 원료 처리 벤치마크로 보는 편이 현실적입니다. 비교 경계는 "
            "미분광 전처리부터 용선·용강까지이며, HPSR의 Ar·전극·가스회수와 HyREX의 "
            "유동층·고온이송·ESF 부담을 같은 기준으로 놓아야 합니다.",
            "HPSR의 직접 용강 경로가 입증되면 저품위광, 제철 잔사, 미세 산화물의 고부가 "
            "회수에 먼저 적용될 수 있습니다. POSCO는 대량 조강 경로만 보지 말고 더스트·"
            "슬러지·산화스케일별 철 회수율, P/S/Zn 거동, 슬래그·분진 처리비를 기준으로 "
            "소형 파일럿 가치도 평가할 수 있습니다.",
            "Donawitz의 200 kg/h 연속화 목표는 POSCO 1 t/h ESF와 단순 용량 비교가 "
            "불가능합니다. HPSR은 환원·용융·출강을 포함한 목표 처리량이고, POSCO 수치는 "
            "용융 파일럿 처리량입니다. 운전시간·실제 광석량·제품량·금속화·가동률을 "
            "정렬한 뒤 비교해야 합니다.",
            "우선 모니터링 지표는 용융욕 질량과 실제품량, 연속 투입·출강 시간, 아크 "
            "소호·재점호 횟수, 전압·전류·아크 길이 변동, H₂·Ar·전력 원단위와 가스 "
            "회수율, 전극·내화물 소비, 금속화율·Fe 수율·철 증발, 슬래그량·P/S 분배, "
            "OES 가용률, 분진·수증기 차폐와 제품 탄소입니다.",
        ),
        "related_projects": (
            "PRJ-SUSTEEL-DONAWITZ",
            "PRJ-LIGHTBOW-HPSR-CONTROL",
            "PRJ-H2PLASMARED-EU",
        ),
        "watch": (
            "200 kg/h 연속화의 실제 달성 여부, 연속 투입·출강 시간과 가동률, 아크 "
            "안정성·Ar 비율, H₂·전력 원단위, 배가스 회수, 전극·내화물 소비, Fe 증발·"
            "철 수율, 광종별 슬래그·P/S 거동, 모델 기반 제어와 2026년 이후 후속 일정을 "
            "확인해야 합니다."
        ),
    },
    "microwave biomass ironmaking": {
        "label": "마이크로웨이브·바이오매스 환원제철 (BioIron)",
        "category": "바이오매스 내장 브리켓의 마이크로웨이브 고체환원",
        "description": (
            "철광석 미분과 바이오매스를 밀착 혼합·브리켓화하고, 무산소 분위기에서 "
            "마이크로웨이브로 입자 내부를 가열해 바이오매스 열분해 가스와 고정탄소로 "
            "고체 환원철을 만드는 경로입니다. 제품은 완성강이 아니라 탄소 함유 DRI이므로 "
            "냉각·패시베이션과 후단 용융·슬래그 분리가 필요합니다."
        ),
        "scope_note": (
            "이 문서는 Rio Tinto BioIron의 공개 특허·독일 소형 파일럿과 건설이 중단된 "
            "서호주 1 t/h 선형 노상로 설계를 중심으로 다룹니다. 바이오차를 기존 고로·"
            "소결·EAF에 일부 대체 투입하는 일반 바이오매스 활용과, 마이크로웨이브 "
            "용융로 자체는 별도 기술입니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["Pilbara 미분광·플럭스·흑연 첨가제"] --> C["분쇄·계량·혼합"]\n'
            '    B["밀짚·톱밥 등 지속가능 바이오매스"] --> C\n'
            '    C --> D["그린 브리켓 성형·스크리닝"]\n'
            '    D --> E["선형 노상로 예열·사전환원 구역"]\n'
            '    G["천연가스 시동 + 공정가스 부분연소"] --> E\n'
            '    E --> R["컴팩터 롤 — 층고 균질화·가스/분진 차단"]\n'
            '    R --> F["마이크로웨이브 구역 — 최대 12개 혼·도파관"]\n'
            '    P["재생전력"] --> M["마이크로웨이브 발생기·튜너"]\n'
            '    M --> F\n'
            '    N["질소 불활성화·누설 차폐"] --> F\n'
            '    F --> Q["바이오매스 열분해·CO/고정탄소 환원"]\n'
            '    Q --> X["Fe₂O₃ → Fe₃O₄ → FeO → Fe + 탄소함유 DRI"]\n'
            '    X --> H["스크루 냉각기"] --> I["60–72 h 공기/N₂ 패시베이션"]\n'
            '    I --> J["저장·HBI 또는 유도로/용융로"]\n'
            '    J --> K["용선·슬래그 → BOF/EAF 정련"]\n'
            '    Q --> O["CO·탄화수소·분진 배가스"]\n'
            '    O --> E\n'
            '    O --> T["후연소기 → 분무냉각 → 백필터 → 굴뚝"]\n'
            '    V["위험: 전자장 불균일·침투깊이·열점·브리켓 붕괴·분진폭발"] -. 운전창 .-> F\n'
            '    classDef feed fill:#EEF2E8,stroke:#5C7D3E,color:#20242C\n'
            '    classDef process fill:#FFF0D9,stroke:#C77700,color:#20242C\n'
            '    classDef microwave fill:#5667C9,stroke:#3F50AF,color:#FFFFFF\n'
            '    classDef product fill:#7B4A2A,stroke:#5D321A,color:#FFFFFF\n'
            '    classDef gas fill:#F3F4F6,stroke:#6D7785,color:#20242C\n'
            '    classDef risk fill:#FBE9E9,stroke:#B74848,color:#20242C\n'
            '    class A,B,C,D feed\n'
            '    class E,R,Q process\n'
            '    class F,P,M,N microwave\n'
            '    class X,H,I,J,K product\n'
            '    class G,O,T gas\n'
            '    class V risk'
        ),
        "process_legend": (
            "**색상 범례 (AI 재구성):** 녹색=원료·브리켓 · 주황=예열·열분해·환원 · "
            "청색=마이크로웨이브·불활성화 · 갈색=DRI·용융 제품 · 회색=연료·배가스 · "
            "적색=확대 운전 위험"
        ),
        "diagram_note": (
            "위 흐름도는 서호주 DWER 허가 설계와 BioIron 특허 공정을 기능 단위로 "
            "재구성한 것입니다. 실제 1 t/h 노의 배관계장도·전자장 해석·준공도가 "
            "아닙니다."
        ),
        "analysis_points": (
            "BioIron의 핵심은 바이오매스를 외부 가스화해 환원가스를 보내는 방식이 아니라, "
            "광석 미분과 바이오매스를 브리켓 내부에 밀착시켜 열분해 가스·고정탄소의 "
            "확산거리를 줄이는 것입니다. 브리켓 밀도·기공률·수분·바인더·압축강도는 "
            "전자장 흡수와 가스 배출, 붕괴·분진을 동시에 좌우합니다.",
            "마이크로웨이브는 노벽부터 전도하는 열이 아니라 유전손실을 통해 원료 내부에 "
            "열을 만들 수 있지만, ‘균일 체적가열’이 자동으로 보장되지는 않습니다. "
            "광석 상변화·수분 제거·바이오매스 열분해에 따라 유전특성이 계속 바뀌므로 "
            "반사전력·정재파·열점과 냉점을 실시간으로 제어해야 합니다.",
            "특허가 제시한 915 MHz에서 약 5 cm 침투깊이와 5–10 cm 연속 부하 가능성은 "
            "실험에서 도출한 설계 근거입니다. 서호주 설계의 최대 12개 혼과 층고 균질화 "
            "롤은 넓은 노상 전체에 에너지를 고르게 전달하려는 대응이며, 장기 연속 "
            "균일도·혼 수명·오염에 대한 실적은 공개되지 않았습니다.",
            "바이오매스는 100–500°C 구간에서 건조·열분해되어 수증기·타르·탄화수소·CO와 "
            "고정탄소를 만듭니다. 환원 반응은 Fe₂O₃→Fe₃O₄→FeO→Fe로 진행하지만 "
            "실리카와 산화철이 fayalite를 만들면 철 회수·금속화와 후단 슬래그 부하가 "
            "악화될 수 있습니다.",
            "서호주 허가 설계는 ‘마이크로웨이브만으로 가열’하는 단순 공정이 아닙니다. "
            "천연가스 시동, 열분해가스의 부분·완전 연소, 공정가스 재순환, 후연소기와 "
            "유도로가 포함됩니다. 전력·천연가스·바이오탄소·후단 용융을 모두 포함한 "
            "톤당 에너지·배출 경계가 필요합니다.",
            "특허의 1.6 GJ/t 열손실 보정치와 약 2 GJ/t 산업 최적화 가능치는 실증 "
            "원단위가 아닙니다. 같은 실험의 무보정 환산치는 74 GJ/t product이고 "
            "열손실이 약 90%였으므로, 숫자 하나만 떼어 상용 효율로 인용하면 안 됩니다.",
            "2024년 회사의 ‘수소 기반 경로 대비 전력 약 1/3’과 ‘BF–BOF 대비 최대 95% "
            "감축’은 조건부 비교 주장입니다. 재생전력, 빠르게 자라는 지속가능 바이오매스, "
            "토지이용 변화, 운송·건조, 후단 용융, 바이오탄소 회계와 CCS 여부를 동일 "
            "경계에서 검증해야 합니다.",
            "제품은 고금속화 탄소함유 DRI이며 자연발화 위험 때문에 냉각·60–72시간 "
            "패시베이션이 계획됐습니다. 냉간 저장은 조업 유연성을 주지만 현열을 잃고 "
            "재산화 위험이 생기므로, HBI화·고온 직송·후단 용융 중 최적 물류를 별도로 "
            "비교해야 합니다.",
            "서호주 파일럿은 8주 캠페인 뒤 3주 개조정지, 연 2,000시간 운전 계획이었습니다. "
            "이는 상업 플랜트 가동률이 아니라 반복 설계변경을 전제로 한 R&D 계획이며, "
            "2025년 건설 중단은 바로 노 설계 확대 위험이 해소되지 않았음을 보여줍니다.",
            "2025년 중단은 기술 폐기를 뜻하지 않지만 2026년 시운전 계획은 더 이상 "
            "현재 일정이 아닙니다. 시설 건설과 기술 R&D를 분리해, 다음 판단 기준을 "
            "새 노 설계 공개·연속 브리켓 이송·전자장 균일도·가스/분진 관리·실제 "
            "금속화율과 철 수율로 두어야 합니다.",
        ),
        "posco_implications": (
            "BioIron은 HyREX와 마찬가지로 Pilbara급 미분·중저품위 원료의 펠릿 의존도를 "
            "낮추려는 경로지만, 환원제·열전달·제품 형태가 다릅니다. POSCO는 동일 광종으로 "
            "전처리 에너지, 금속화율, 철 수율, 슬래그량, 후단 용융 전력을 비교해야 합니다.",
            "브리켓 내부 환원은 FINEX·HyREX의 미분 유동층과 달리 원료 성형을 다시 "
            "도입합니다. 기존 제철소의 브리켓·분진 재활용 경험을 활용할 수 있으나, "
            "농업잔사 계절성·회분·알칼리·염소·수분과 장거리 물류는 별도 공급망 리스크입니다.",
            "마이크로웨이브 발생기·도파관·혼·차폐·반사전력 계측은 기존 전기로 전력설비와 "
            "다른 역량입니다. 시험한다면 작은 회분 실험보다 연속 이동층에서 층고·상변화에 "
            "따른 전자장 분포와 브리켓 온도 편차를 계측하는 것이 우선입니다.",
            "현재 단계에서는 BioIron을 HyREX 대체 상용안으로 보기보다, 저수소 지역의 "
            "장기 선택지이자 바이오탄소·마이크로웨이브 결합 벤치마크로 관리하는 편이 "
            "타당합니다. 재개 조건은 신규 노 설계, 지속 운전시간, 전력·바이오매스 "
            "원단위, LCA, 후단 용융 제품 품질의 공개입니다.",
        ),
        "related_projects": ("PRJ-BIOIRON-WA-RD",),
        "watch": (
            "중단된 1 t/h 설계의 재개 또는 대체 노형, 최대 12개 혼의 실제 전자장 균일도, "
            "연속 브리켓 이송·붕괴율, 금속화율·철 수율·제품 탄소, 전력·천연가스·"
            "바이오매스 원단위, 타르·분진·슬래그, 지속가능성 인증과 후단 용융 품질을 "
            "확인해야 합니다."
        ),
    },
    "zesty hydrogen flash reduction": {
        "label": "ZESTY 수소 직접 플래시 환원",
        "category": "간접 전기가열 낙하입자식 미분광 수소 직접환원",
        "description": (
            "철광석 미분을 수직 반응관 상부에서 낙하시키고 하부에서 공급한 수소와 "
            "역류 접촉시키면서, 반응관 벽을 외부 전기로 간접가열해 DRI 미분을 만드는 "
            "공정입니다. 통상적인 DR 펠릿을 생략할 수 있지만 초미분 회수, 다관 "
            "scale-out, 수소 재순환과 고온 DRI 안정화가 함께 해결돼야 합니다."
        ),
        "scope_note": (
            "이 문서는 Calix의 Zero Emissions Steel Technology(ZESTY)를 중심으로 "
            "다룹니다. 유동화 가스로 입자를 부유시키는 HyREX·HYFOR 계열과 달리 "
            "중력 낙하입자·역류 수소·간접 벽면가열이 핵심이며, 고온 직접가열형 Utah "
            "Flash Ironmaking Technology와도 운전온도·열전달·산업 프로그램을 구분합니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["철광석 미분 — 입도·품위·수분 확인"] --> B["상부 계량·분산 장입"]\n'
            '    B --> C["수직 반응관 — 입자 중력 낙하"]\n'
            '    P["재생전력"] --> H["외벽 전기가열 — 간접 열전달"]\n'
            '    H --> C\n'
            '    G["수소 — 하부 공급"] --> C\n'
            '    C --> R["Fe₂O₃ → Fe₃O₄ → FeO → Fe"]\n'
            '    R --> D["고온 DRI 미분 — 하부 회수"]\n'
            '    C --> O["상부 H₂·H₂O·동반 미분"]\n'
            '    O --> S["사이클론·집진 — 미분 회수"]\n'
            '    S --> J["회수 미분 — 재투입·처리 방식 실증 필요"]\n'
            '    O --> W["수분 제거"]\n'
            '    W -. 수소 재순환 .-> G\n'
            '    D --> X{"제품 안정화·후단"}\n'
            '    X --> I["부동태화·냉간/고온 브리켓·HBI"]\n'
            '    X --> E["DRI/HBI 후처리·ESF/EAF 적용 시험"]\n'
            '    M["3만 t/y 실증 확대 — 다관 병렬은 제안 경로"] -. 분배·온도 균일도 .-> C\n'
            '    V["위험: 비산·부착·재산화·수소비용"] -. 운전창 .-> C\n'
            '    classDef feed fill:#F5F6F7,stroke:#9BA2AD,color:#20242C\n'
            '    classDef reactor fill:#3F66C9,stroke:#3158B8,color:#FFFFFF\n'
            '    classDef recycle fill:#E7F3EE,stroke:#24724A,color:#20242C\n'
            '    classDef product fill:#EDF2FB,stroke:#3F66C9,color:#20242C\n'
            '    classDef risk fill:#FBE9E9,stroke:#B74848,color:#20242C\n'
            '    class A,B,P,G feed\n'
            '    class C,H,R reactor\n'
            '    class O,S,W,J recycle\n'
            '    class D,X,I,E,M product\n'
            '    class V risk'
        ),
        "process_legend": (
            "**색상 범례 (AI 재구성):** 회색=원료·에너지 · 진한 코발트=간접가열 "
            "플래시 환원 · 녹색=가스·미분 회수 · 옅은 코발트=제품·확대 · 적색=운전 위험"
        ),
        "diagram_note": (
            "위 흐름도는 ARENA 사업자료와 동료심사 논문의 공개 공정을 기능 단위로 "
            "재구성한 것입니다. Rockingham 실증설비의 준공도·배관계장도(P&ID)나 "
            "확정된 다관 배치가 아닙니다."
        ),
        "analysis_points": (
            "간접가열은 수소를 연료가 아니라 환원제로 집중해 쓰고 전력으로 반응열을 "
            "공급할 수 있게 합니다. 다만 이론적 최소 수소량과 실제 플랜트 원단위는 "
            "수분 제거·purge·미반응 수소 재순환을 포함해 구분해야 합니다. 공개 논문에 "
            "정제·압축 사양과 회수 미분 재투입 방식은 확정돼 있지 않습니다.",
            "‘펠릿 불필요’는 ‘선광·건조·분급·집진 불필요’를 뜻하지 않습니다. "
            "저품위광의 맥석이 남으면 DRI 제품량, ESF 슬래그량·전력·플럭스와 철 "
            "회수율에 부담이 이동합니다.",
            "ARENA의 3만 t/y 실증 목표와 논문의 병렬 다관 scale-up 제안은 서로 다른 "
            "근거입니다. 파일럿 단일관의 온도·금속화 성능을 선형 확대할 수 없으며, "
            "관별 광석·수소 분배, 벽면 열플럭스, 고체농도와 정비격리가 독립 변수입니다.",
            "상부로 동반되는 초미분은 집진 부하일 뿐 아니라 철 수율 손실입니다. "
            "평균 금속화율과 함께 입도별 제품·분진 질량수지, 재순환 횟수, 사이클론 "
            "마모와 filter differential pressure가 공개돼야 합니다.",
            "고온 DRI 미분은 재산화·발화·분진폭발 위험이 있어 부동태화, HBI 또는 "
            "밀폐 고온이송이 필요합니다. 환원 반응기 성능과 제품 물류·후단 ESF/EAF "
            "품질을 별도 검증해야 합니다.",
            "ARENA 실증사업의 개시·FEED는 기술의 산업 실행 신호지만 상용 경쟁력 "
            "입증은 아닙니다. Rockingham의 재생수소 가격, 장기 연속운전과 복수 "
            "Pilbara 광종의 toll processing 결과가 다음 판단 기준입니다.",
        ),
        "posco_implications": (
            "HyREX와 동일한 Pilbara 정광을 사용해 원료 전처리, 수소 kg/t-Fe, 전력 "
            "kWh/t-Fe, 금속화율 분포, Fe 수율, 분진 재순환과 ESF 슬래그를 같은 "
            "경계에서 비교해야 합니다.",
            "ZESTY를 HyREX 전체 대체기술로만 보지 말고, ESF 전단의 부분환원 모듈이나 "
            "광종별 전처리-환원 옵션으로 평가할 필요가 있습니다. 최적 부분환원도는 "
            "반응기와 ESF의 합산 전력·철 수율로 결정해야 합니다.",
            "Calix–Rio Tinto의 비독점 공동개발 구조, 반응관·calciner 특허와 라이선스 "
            "조건을 확인해 POSCO 독자시험·협력·회피설계의 FTO를 조기에 검토해야 합니다.",
            "향후 12~36개월 선행지표는 Rockingham 인허가·FID/EPC, 수소 공급계약, "
            "정격 단일관과 다관 모듈의 연속시간, 광종별 금속화–Fe수율–분진–에너지 "
            "동시 데이터, HBI/ESF 고객시험과 CAPEX/OPEX 갱신입니다.",
            "판단 질문은 ‘실측 원단위가 이론값에 얼마나 접근하는가’, ‘관별 분배편차를 "
            "어떻게 계측·제어하는가’, ‘고온 DRI 미분을 어떤 형태로 ESF에 연결하는가’, "
            "‘수소가격 상승 후에도 펠릿 생략 편익이 남는가’입니다.",
        ),
        "related_projects": ("PRJ-ZESTY-ROCKINGHAM-DEMO",),
        "watch": (
            "향후 12~36개월 동안 Rockingham의 인허가·FID·EPC와 수소계약, 단일관·다관 "
            "연속운전 시간, 광종별 금속화율·Fe 수율·분진회수, 실측 수소·전력원단위, "
            "HBI/ESF 제품검증, CAPEX/OPEX 갱신과 Rio Tinto의 배치·라이선스 결정을 "
            "확인해야 합니다."
        ),
    },
    "hisarna cyclone smelting reduction": {
        "label": "HIsarna 사이클론 용융환원",
        "category": "미분광 사이클론 예비환원·용융과 탄소계 용융욕 최종환원",
        "description": (
            "미분 철광석과 산소를 상부 Cyclone Converter Furnace(CCF)에 직접 투입해 "
            "예비환원·용융하고, 하부 Smelting Reduction Vessel(SRV)의 석탄·용융욕에서 "
            "최종 환원해 용선을 만드는 공정입니다. 미분광을 직접 투입해 소결과 코크스 "
            "제조를 생략하지만 탄소 환원과 산소제조가 남아 CCUS·대체탄소원과 함께 "
            "평가해야 합니다."
        ),
        "scope_note": (
            "이 문서는 Tata Steel의 CCF와 HIsmelt계 bath smelting을 결합한 HIsarna를 "
            "다룹니다. 코크스 충전층을 유지하는 BF-CCUS와 달리 일체형 사이클론-용융욕 "
            "반응기이며, 수소 고체환원 뒤 ESF에서 녹이는 DRI–ESF 경로와도 구분합니다."
        ),
        "process_mermaid": (
            'flowchart TB\n'
            '    A["미분 철광석·산소"] --> C["상부 CCF — 회전 고온유동"]\n'
            '    C --> D["비행 중 예비환원·용융"]\n'
            '    D --> F["용융 산화철 방울·벽면막 하강"]\n'
            '    K["분탄 — SRV 주입"] --> S["하부 SRV — 용융 슬래그·철욕"]\n'
            '    F --> S\n'
            '    S --> R["FeO 최종환원·침탄"]\n'
            '    R --> H["용선 출선"]\n'
            '    R --> L["슬래그 출재"]\n'
            '    S --> G["CO·H₂·분진 상향가스"]\n'
            '    G --> C\n'
            '    Z["산소"] --> P["reflux chamber — 후연소"]\n'
            '    C --> P\n'
            '    P --> Q["quench·집진·가스정제"]\n'
            '    Q --> X["고농도 CO₂ — 압축·수송·CCUS 검토"]\n'
            '    V["위험: ore carryover·foaming·내화물·고-Al 슬래그"] -. 운전창 .-> C\n'
            '    V -. 운전창 .-> S\n'
            '    classDef feed fill:#F5F6F7,stroke:#9BA2AD,color:#20242C\n'
            '    classDef cyclone fill:#3F66C9,stroke:#3158B8,color:#FFFFFF\n'
            '    classDef bath fill:#B4552D,stroke:#8E3F20,color:#FFFFFF\n'
            '    classDef gas fill:#E7F3EE,stroke:#24724A,color:#20242C\n'
            '    classDef product fill:#EDF2FB,stroke:#3F66C9,color:#20242C\n'
            '    classDef risk fill:#FBE9E9,stroke:#B74848,color:#20242C\n'
            '    class A,K,Z feed\n'
            '    class C,D,F cyclone\n'
            '    class S,R bath\n'
            '    class G,P,Q,X gas\n'
            '    class H,L product\n'
            '    class V risk'
        ),
        "process_legend": (
            "**색상 범례 (AI 재구성):** 회색=원료 · 코발트=CCF 예비환원·용융 · "
            "갈색=SRV 용융욕 최종환원 · 녹색=배가스·CCUS · 옅은 코발트=용선·슬래그 · "
            "적색=확대 운전 위험"
        ),
        "diagram_note": (
            "위 흐름도는 Tata Steel 공식 설명과 동료심사 CFD 논문을 기능 단위로 "
            "재구성한 것입니다. IJmuiden 파일럿 또는 Jamshedpur 실증로의 준공도·"
            "배관계장도(P&ID)가 아닙니다."
        ),
        "analysis_points": (
            "HIsarna의 원료 자유도는 소결·코크스를 없애는 데서 오지만, 맥석을 "
            "없애지는 않습니다. 고-Al₂O₃·저품위광은 슬래그 부피·점도·융점, flux와 "
            "열부하, 탈황·탈인, 철 수율을 동시에 바꿉니다.",
            "상부 CCF의 ore carryover는 Fe 수율·집진 부하와 하부 SRV 투입량을 "
            "변화시키고, 하부 bath foaming과 후연소는 CCF 열전달·내화물과 연결됩니다. "
            "CCF와 SRV를 독립 장치처럼 최적화할 수 없습니다.",
            "6만 t/y 명목 파일럿에서 약 100만 t/y 실증으로 확대할 때 cyclone 체류시간, "
            "droplet 궤적, 벽면막, 산소·분체 분배와 냉각면 열플럭스가 선형으로 유지되지 "
            "않습니다. 실제 연속 캠페인과 가동률이 CFD 설계보다 우선적인 검증치입니다.",
            "HIsarna는 기본적으로 탄소계 환원 공정입니다. 소결·코크스 생략에 따른 "
            "감축과 고농도 CO₂의 포집 잠재력은 회사 주장으로 구분하고, 산소제조·석탄·"
            "배가스 정제·CO₂ 수송·저장까지 포함한 순회피량을 요구해야 합니다.",
            "reflux chamber의 내화물 두께·열손실·CO 변동은 pilot inspection과 CFD "
            "문헌에서 scale-up 변수로 확인됩니다. Jamshedpur 실증 원료 사양은 아직 "
            "미공개이므로 IJmuiden의 고-Al 원료 시험과 분리해 추적해야 합니다.",
            "Tata 이사회가 승인한 것은 엔지니어링과 규제 절차의 개시입니다. FID, EPC, "
            "착공, 준공·가동을 같은 상태로 표시하지 않고 후속 공시를 단계별로 보존해야 합니다.",
        ),
        "posco_implications": (
            "FINEX, HIsarna, BF-CCUS와 HyREX–ESF를 동일 광석·제품 경계에서 비교해 "
            "원료전처리, O₂, 석탄/H₂, 전력, 슬래그, 용선 P/S와 CO₂ 저장비를 정렬해야 합니다.",
            "POSCO의 FINEX·용융환원 경험은 HIsarna 평가에 유리하지만 CCF의 in-flight "
            "melting과 일체형 SRV 후연소는 별도 노형·제어 문제입니다. 분진·droplet·"
            "bath coupling의 계측과 모델 검증 역량을 비교해야 합니다.",
            "Jamshedpur의 구체 원료 사양은 미공개입니다. 향후 공개되는 광석 Al₂O₃·"
            "맥석 범위, basicity, slag kg/t, FeO, P/S 분배와 campaign length를 "
            "IJmuiden 시험 데이터와 구분해 추적해야 합니다.",
            "향후 12~36개월 선행지표는 Jamshedpur 설계사/EPC·환경인허가, 예산·FID·"
            "착공, 공개 원료사양과 광종별 캠페인, 연속시간·가동률, coal–gas–biocarbon 조합, "
            "CO₂ 저장 파트너·오프테이크와 Tata의 라이선스 정책입니다.",
            "판단 질문은 ‘CCUS 없이 얻는 순감축이 얼마인가’, ‘1 Mt/y 확대 시 CCF "
            "carryover와 SRV foaming을 어떻게 제어하는가’, ‘FINEX 대비 원료·용선 "
            "품질과 총비용은 어떤가’, ‘Tata의 글로벌 IP가 FTO에 주는 제약은 무엇인가’입니다.",
        ),
        "related_projects": ("PRJ-HISARNA-JAMSHEDPUR-DEMO",),
        "watch": (
            "향후 12~36개월 동안 Jamshedpur 실증의 설계사·EPC·인허가·FID·착공, 공개 "
            "원료사양과 광종별 장기 캠페인·용선·슬래그 품질, 연속운전 시간·가동률, 석탄·산소 "
            "원단위, 내화물·냉각 수명, CO₂ 포집·운송·저장 계약과 글로벌 라이선스 "
            "정책을 확인해야 합니다."
        ),
    },
}
TECHNOLOGY_SENSING_DASHBOARDS = {
    "hydrogen direct reduced iron": {
        "leading_indicators": (
            "상업 규모에서 천연가스 보조 없이 실제 수소 비율, 연속운전 시간, "
            "금속화율·제품 탄소·클러스터링 지수를 함께 공개",
            "전력·수소 공급계약, 환경허가, FID, 착공, 시운전이 목표일에서 실제 "
            "이정표로 순차 전환",
            "광종·펠릿별 수소 kg/t-DRI, 가스 가열전력, HDRI 온도와 후단 EAF "
            "kWh/t를 동일 캠페인 경계로 제시",
        ),
        "warning_signals": (
            "HYBRIT처럼 일정 지연으로 기한부 지원이 철회되거나, Stegra처럼 대규모 "
            "추가 조달 뒤에도 공식 일정이 계속 검토 상태",
            "‘hydrogen-ready’ 또는 구매계약만 반복하고 실제 수소비율·연간 생산량·"
            "품질인증 결과가 공개되지 않음",
        ),
        "decision_questions": (
            "HyREX와 샤프트 DRI를 원료 전처리·수소·전력·후단 용융까지 같은 시스템 "
            "경계에서 비교하면 어느 조건에서 우위가 바뀌는가?",
            "외부 HBI 조달, 자체 DRI, 미분광 환원 중 무엇을 핵심 자산으로 두고 "
            "어떤 경로를 공급망 헤지로 유지할 것인가?",
            "보조금·저가 수소가 지연될 때 천연가스 브리지 운전의 탄소 lock-in을 "
            "어떤 투자 gate로 제한할 것인가?",
        ),
    },
    "electric smelting furnace": {
        "leading_indicators": (
            "1 t/h급 파일럿에서 광종별 7일 이상 캠페인, 연속 장입·분리 출선, "
            "철 회수율·슬래그 FeO·전극·내화물 데이터를 함께 공개",
            "저금속화·고맥석 DRI의 허용 범위를 명목치가 아니라 물질수지와 용선 "
            "C·Si·P·S 품질로 반복 검증",
            "상용 개념설계의 110 MW·1.2 Mt/y 주장을 고객 원료 시험, EPC 보증과 "
            "장기 availability 데이터로 전환",
        ),
        "warning_signals": (
            "첫 출선 사진이나 공급사 설계치만 있고 campaign length, slag kg/t, "
            "철 손실, 실제 가동률이 비공개",
            "ESF와 EAF를 혼용해 아크 노출·배치 용해를 연속 침지저항 가열 실적으로 "
            "오인하거나 후단 BOF 통합비용을 제외",
        ),
        "decision_questions": (
            "HyREX 환원물의 입도·금속화·맥석 분포에 맞는 bath depth, 전극, "
            "슬래그 전도도와 출선 체계는 무엇인가?",
            "ESF가 DR-grade 펠릿 프리미엄 절감으로 추가 전력·플럭스·슬래그 처리비를 "
            "상쇄하는 광석 품위 경계는 어디인가?",
            "독립 상용 플랫폼으로 확보할지 HyREX 통합 실증의 하위 모듈로 검증할지 "
            "투자 순서를 어떻게 나눌 것인가?",
        ),
    },
    "molten oxide electrolysis": {
        "leading_indicators": (
            "셀 전류·전압, 전류효율, kWh/t-Fe, 금속·산소 수율을 수백~수천 시간 "
            "연속운전과 함께 공개",
            "불활성 양극 부식·전해질 오염·금속 회수·내화물 수명 데이터를 셀 교체 "
            "주기와 물질수지로 제시",
            "단일 tap을 넘어 복수 산업 셀의 병렬운전, 제품 규격과 고객 제강시험, "
            "상용 부지 EPC 이정표가 확인",
        ),
        "warning_signals": (
            "셀 크기·campaign hours·전류효율 없이 ‘고순도 철’ 또는 투자·제휴 발표만 반복",
            "전력의 탄소집약도, 양극·전해질 보충, 산소 부산물 크레딧을 제외한 "
            "선택적 에너지·배출 비교",
        ),
        "decision_questions": (
            "MOE를 2030년대 대규모 제선 대체로 볼지, 고순도 철·특수합금용 선도시장 "
            "옵션으로 볼지 어떤 실증 gate에서 구분할 것인가?",
            "POSCO가 확보해야 할 핵심은 셀 운전, 불활성 양극, 전해질, 출탕·정련 중 "
            "어느 IP·공정 패키지인가?",
            "수소계 경로 대비 전력망·원료·제품 가치의 교차점은 어떤 지역과 제품군에서 "
            "먼저 형성되는가?",
        ),
    },
    "blast furnace CCUS": {
        "leading_indicators": (
            "고로·열연 등 실제 배가스에서 연속운전 시간, 포집률·순도, 용매 열화, "
            "재생열·압축전력을 같은 기간으로 공개",
            "포집장치 연결을 넘어 CO2 운송·영구저장 계약 또는 CCU 제품의 반복 출하·"
            "실제 이용률과 전과정 avoided-CO2가 확인",
            "Gent 300 kg/day 파일럿의 가스원 확대와 D-CRBN의 CO2→CO 전환율·"
            "제품가스 순도·kWh/t-CO가 공개",
        ),
        "warning_signals": (
            "‘세계 최초 연결’·첫 바지선 출하만 반복하고 월간 생산량·가동률·"
            "물질·에너지수지가 비공개",
            "포집 CO2를 영구저장과 단기 제품전환으로 구분하지 않거나, 증기·전력·"
            "압축·수송을 제외한 gross capture만 감축량으로 제시",
        ),
        "decision_questions": (
            "고로 잔존수명 동안 포집·수송·저장 투자를 회수할 수 있는 입지와 시점은 어디인가?",
            "저장망이 없는 제철소에서 에탄올·CO 전환의 반복 오프테이크와 탄소회계가 "
            "CCS 대비 경쟁력을 갖는 조건은 무엇인가?",
            "Gent의 변동 불순물·용매·플라즈마 결과를 POSCO 고로·열연 배가스 조성에 "
            "어떤 시험으로 이전 검증할 것인가?",
        ),
    },
    "low-carbon ironmaking": {
        "leading_indicators": (
            "발표 용량이 허가·FID·착공·시운전·인증 출하로 전환되는 비율과 소요기간",
            "제품별 Scope 1·2·상류 Scope 3, 스크랩 추가성, 전력·수소 탄소집약도를 "
            "동일 산정경계와 제3자 검증으로 공개",
            "EAF·DRI·ESF·전기분해·CCUS별 실제 생산량·가동률과 인프라 계약을 "
            "마스터 타임라인에서 비교",
        ),
        "warning_signals": (
            "목표 용량을 현재 저탄소 생산능력으로 합산하거나, MOU·지원선정을 "
            "운전 실적으로 표현",
            "일정 철회·재검토·건설 둔화를 지우고 새 목표일만 남기거나 서로 다른 "
            "배출경계로 기술 우열을 비교",
        ),
        "decision_questions": (
            "광양 EAF, HyREX, 외부 HBI, ESF, BF-CCUS를 제품군·자산수명·인프라 "
            "제약별로 어떤 순서와 option value로 배치할 것인가?",
            "기술 하나의 최저 배출보다 공급차질·전력가격·수소지연을 견디는 포트폴리오 "
            "복원력을 어떻게 계량할 것인가?",
            "각 경로의 중단·축소·확대 gate를 어떤 공개 또는 자체 실증 KPI에 연결할 것인가?",
        ),
    },
    "smart steelworks": {
        "leading_indicators": (
            "권고·사람승인·제한 폐루프·완전자율을 구분하고 자동제어 적용시간, "
            "수동개입·override·interlock 빈도를 공개",
            "동일 모델을 다른 노·라인·사업장에 이전해 품질·연료·수율의 기준선 대비 "
            "효과와 모델 드리프트를 반복 검증",
            "데이터 단절·센서 이상·모델 불확실성에서 안전계층과 rollback이 실제로 "
            "작동한 시험 기록을 확보",
        ),
        "warning_signals": (
            "97% 정확도처럼 표본·목표변수·기준선이 없는 단일 모델 지표만 반복",
            "대시보드·디지털 트윈 구축을 폐루프 운전으로 표현하면서 조작권한·"
            "수동개입률·OT 보안 경계는 미공개",
        ),
        "decision_questions": (
            "AI에 맡길 조작변수와 사람이 유지할 승인점을 안전·품질 책임별로 어디에 둘 것인가?",
            "정확도보다 override 원인·개입률·interlock·경제성과를 전사 공통 KPI로 "
            "수집할 수 있는가?",
            "물리모델과 ML 중 어느 계층을 안전 기준계로 두고 해외 제철소 이전 시 "
            "재검증 책임을 누가 갖는가?",
        ),
    },
    "low-temperature aqueous iron electrolysis": {
        "leading_indicators": (
            "500 t/y급 시설에서 월간 생산량, stack uptime, 전류효율, kWh/t-Fe, "
            "제품 순도와 고객 EAF qualification을 함께 공개",
            "막·전극 수명, 산·알칼리·공정수 회수, 실광석 철 회수율·불순물 분배를 "
            "4시간 시험이 아닌 장기 캠페인으로 검증",
            "Electra·Volteron·Fortescue가 pilot 목표를 commissioning·반복 생산·"
            "후속 상용 모듈 FID로 전환",
        ),
        "warning_signals": (
            "명목 용량·구매의향·TRL 목표만 갱신되고 실제 월별 생산·전력·소모품 "
            "데이터와 납품 품질 결과가 없음",
            "고순도 시약 또는 정제원료 결과를 저품위 실광석 성능으로 일반화하거나 "
            "전류효율 최고값을 시스템 에너지로 환산",
        ),
        "decision_questions": (
            "수계 전해를 벌크 철 대체와 고순도 철 premium 시장 중 어디에 먼저 적용할 것인가?",
            "광석 전처리·침출·막·전착 회수·폐액 중 POSCO가 직접 확보할 병목 IP는 무엇인가?",
            "MOE·수소 DRI 대비 전력·물·시약·원료 품위의 crossover를 어떤 자체 "
            "bench/pilot 시험으로 확인할 것인가?",
        ),
    },
    "high-grade EAF and scrap impurity removal": {
        "leading_indicators": (
            "실제 처리량 t/h, lot별 Cu·Sn·Ni·Cr 예측오차, 철 회수율과 질량수지를 공개",
            "R260·42CrMo4 등 목표 강종을 산업 규모로 반복 생산하며 저품위 스크랩 "
            "투입 증가와 제품 합격률·수율을 함께 입증",
            "PURESCRAP 종료일 충돌을 grant amendment·최종보고서로 해소하고 SSAB·"
            "VASD 제강 검증 결과를 공개",
        ),
        "warning_signals": (
            "센서 스테이션 설치나 AI 분류 정확도만 발표하고 bulk chemistry 오차·"
            "처리량·강종 합격률이 비공개",
            "Cu 제거율을 철 손실·에너지·부산물과 분리하거나 DRI/HBI 희석 의존도를 "
            "스크랩 고도화 성능으로 계산",
        ),
        "decision_questions": (
            "센서 결과를 장입 lot 배합·EAF·LF 분석까지 연결하는 digital thread를 "
            "어떤 데이터 표준으로 구축할 것인가?",
            "저품위 스크랩 확대의 원가 편익이 목표 강종 합격률·수율·철 손실까지 "
            "포함해 유지되는 경계는 어디인가?",
            "PURESCRAP·Sortera 결과를 광양 대형 EAF의 원료 사양과 어떤 대조시험으로 "
            "검증할 것인가?",
        ),
    },
    "hydrogen-based fine-ore reduction": {
        "leading_indicators": (
            "HyREX의 실제 착공·EPC, 반응기별 장기 ΔP·고착·비산, 광종별 금속화 "
            "분포와 Fe 수율을 단계별 시험운전에서 공개",
            "50 kg/batch 시험로에서 300,000 t/y 통합실증으로 확대할 때 수소이용률, "
            "분진 회수, 고온이송과 ESF 통합 가동률을 함께 검증",
            "2028 설비완공 목표와 2030 운전조건·기술성숙 목표를 구분해 실제 "
            "commissioning·ramp-up 이력으로 전환",
        ),
        "warning_signals": (
            "부지승인·목표 착공일을 건설 진척으로 표현하거나, 기계적 완공을 "
            "상용 운전기술 확보로 간주",
            "평균 금속화율만 공개하고 입도별 비산·응집, reactor train 편차, "
            "수소·전력·철 질량수지가 없음",
        ),
        "decision_questions": (
            "광종별 유동화·sticking 운전창과 ESF의 허용 FeO·맥석 창을 하나의 "
            "통합시험계획으로 어떻게 연결할 것인가?",
            "HyREX 독자 확대와 ZESTY·HYFOR·샤프트 DRI benchmark를 어떤 공통 KPI로 "
            "비교할 것인가?",
            "착공·실증 지연 시 확보할 외부 DRI/HBI 또는 대체 환원 기술의 hedge는 무엇인가?",
        ),
    },
    "hydrogen plasma smelting reduction": {
        "leading_indicators": (
            "100 kg급 batch 시험에서 5 t DC-EAF 캠페인으로 넘어가 연속 투입·출강, "
            "금속화·철수율·H2/Ar·kWh/t를 함께 공개",
            "아크 안정성·plasma length, Fe 증발·분진, 전극·내화물 마모와 slag-metal "
            "분리를 장기 캠페인에서 검증",
            "H2PlasmaRed의 TRL 5→7 목표를 retrofit 완료, 2026 캠페인 결과와 "
            "독립 material/energy balance로 입증",
        ),
        "warning_signals": (
            "설비 명목 100/200 kg을 달성 처리량으로 혼용하거나 batch charge·무출강 "
            "시험을 연속 공정으로 표현",
            "부분환원 90분 시험의 조건부 내화물·단열 개선을 상용 에너지 원단위와 "
            "가동률로 확대 해석",
        ),
        "decision_questions": (
            "HPSR을 벌크 1차철 경로, EAF retrofit, 저품위광·부산물 처리 중 어느 "
            "use case로 집중할 것인가?",
            "HyREX–ESF 대비 환원·용융 일체화 편익이 Ar·전극·내화물·Fe 증발 부담을 "
            "상쇄하는 조건은 무엇인가?",
            "논문별 100 kg/200 kg 범위 차이를 장치 버전·캠페인별로 어떤 검증 데이터로 해소할 것인가?",
        ),
    },
    "microwave biomass ironmaking": {
        "leading_indicators": (
            "중단 원인을 반영한 노 설계 freeze, 신규 부지·허가·FID와 연속 파일럿 "
            "재착수 일정이 확인",
            "최대 12개 혼의 전자장·온도 균일도, 연속 브리켓 이송·붕괴, 금속화율·"
            "Fe 수율·제품 탄소와 완전 물질수지를 공개",
            "전력·천연가스·바이오매스 원단위, 타르·분진·슬래그 및 공급망 "
            "지속가능성을 동일 캠페인으로 검증",
        ),
        "warning_signals": (
            "‘R&D 지속’ 문구만 있고 redesign·재허가·재착수의 구체 이정표가 없음",
            "소형 batch의 전력 또는 감축 최고값을 1 t/h 연속 설비로 확대하면서 "
            "전자장·열·가스 균일도와 공급망을 제외",
        ),
        "decision_questions": (
            "Rio Tinto의 노 설계·전자장·브리켓층 위험이 POSCO 연구에 어떻게 재현되는가?",
            "재착수 전 최소 gate를 연속운전 시간, 금속화율, Fe 수율, 에너지수지 중 "
            "어떤 조합으로 둘 것인가?",
            "직접 투자보다 redesign·파트너·특허 움직임을 추적하는 option-value 전략이 "
            "현재 단계에 더 적절한가?",
        ),
    },
    "zesty hydrogen flash reduction": {
        "leading_indicators": (
            "Rockingham의 환경허가·FID·EPC·수소계약이 30,000 t/y 실증 착공·시운전으로 전환",
            "단일관과 병렬 다관 모듈에서 연속시간, 관별 분배편차, 금속화–Fe수율–"
            "분진–수소·전력 원단위를 광종별로 동시 공개",
            "DRI/HBI 안정화와 복수 철강사의 BF-BOF·ESF/EAF 제품시험, CAPEX/OPEX "
            "갱신이 확인",
        ),
        "warning_signals": (
            "54 kg H2/t 이론값 또는 파일럿 최대 95% 금속화를 실증플랜트 평균 실적으로 표현",
            "회수 미분 재투입, 수소 정제·압축, 다관 배치와 고온이송이 확정되지 "
            "않았는데 완성 공정도처럼 제시",
        ),
        "decision_questions": (
            "HyREX와 같은 Pilbara 광석 경계에서 펠릿 생략 편익이 수소·전력·분진·"
            "ESF 슬래그 부담을 상쇄하는가?",
            "관별 분배와 정비격리를 어떻게 계측·제어하고 단일관 성능을 plant "
            "availability로 변환할 것인가?",
            "협력·라이선스·독자시험 중 어떤 방식으로 반응관·calciner IP와 FTO를 확보할 것인가?",
        ),
    },
    "hisarna cyclone smelting reduction": {
        "leading_indicators": (
            "Jamshedpur 약 1 Mt/y 계획이 엔지니어링·규제 절차에서 예산·FID·EPC·"
            "착공으로 실제 전환",
            "공개 원료사양별 CCF carryover, SRV foaming, 연속시간·가동률, 용선·"
            "슬래그 품질, 석탄·산소 원단위를 검증",
            "reflux chamber 내화물·열손실·후연소 성능과 CO2 포집·운송·저장 계약을 "
            "장기 캠페인 데이터로 공개",
        ),
        "warning_signals": (
            "2022년 400 kt/y demo·1 Mt/y industrial 설계와 2025년 약 1 Mt/y "
            "demonstration 계획을 같은 단계·확정 용량으로 병합",
            "Jamshedpur 원료 사양이 미공개인데 IJmuiden 고-Al 시험을 현지 실증 "
            "확정조건으로 표현하거나 이사회 승인을 FID·착공으로 표시",
        ),
        "decision_questions": (
            "FINEX·BF-CCUS·HyREX–ESF와 동일 광석·용선 경계에서 HIsarna의 총비용·"
            "순회피 CO2 우위가 생기는 조건은 무엇인가?",
            "1 Mt/y 확대 시 CCF droplet·wall film·carryover와 SRV bath foaming을 "
            "어떤 계측·모델·제어로 검증할 것인가?",
            "Tata의 글로벌 IP가 협력·라이선스·회피설계와 POSCO 용융환원 기술 "
            "포트폴리오에 주는 제약은 무엇인가?",
        ),
    },
}
TECHNOLOGY_NAVIGATION_GROUPS = (
    (
        "환원·용융 경로",
        (
            "hydrogen direct reduced iron",
            "hydrogen-based fine-ore reduction",
            "zesty hydrogen flash reduction",
            "electric smelting furnace",
            "hisarna cyclone smelting reduction",
            "hydrogen plasma smelting reduction",
            "microwave biomass ironmaking",
        ),
    ),
    (
        "전해 기반 경로",
        (
            "molten oxide electrolysis",
            "low-temperature aqueous iron electrolysis",
        ),
    ),
    (
        "기존 설비·순환 경로",
        (
            "blast furnace CCUS",
            "high-grade EAF and scrap impurity removal",
        ),
    ),
    (
        "통합·운영 기술",
        (
            "low-carbon ironmaking",
            "smart steelworks",
        ),
    ),
)
PREDICATE_LABELS = {
    "business_impact_score_1_to_10": "사업영향도",
    "business_impact_rationale": "사업영향도 근거",
    "urgency_score_1_to_10": "긴급도",
    "urgency_rationale": "긴급도 근거",
    "assessment_confidence": "평가 신뢰도",
    "assessed_at": "평가일",
    "impact_path": "영향 경로",
    "recommended_follow_up": "권고 후속조치",
    "global_ev_battery_deployment_2025": "2025년 세계 전기차 배터리 사용량",
    "global_lfp_ev_battery_share_2025": "2025년 세계 LFP 비중",
    "global_lfp_ev_battery_share_2024": "2024년 세계 LFP 비중",
    "lfp_pack_price_discount_vs_nmc_2025": "LFP 팩의 NMC 대비 가격 격차",
    "zesty_hydrogen_flash_reduction_status": "ZESTY 수소 플래시 환원 현황",
    "hisarna_cyclone_smelting_reduction_status": "HIsarna 사이클론 용융환원 현황",
    "project_status": "프로젝트 상태",
    "target_start_date": "목표 가동 시점",
    "project_start_date": "프로젝트 착수 시점",
    "project_completion_date": "단계 완료 시점",
    "target_storage_completion_date": "수소 저장 시험 종료 목표",
    "target_completion_date": "목표 준공 시점",
    "target_commissioning_date": "목표 시운전 시점",
    "construction_start_date": "착공 시점",
    "commissioning_date": "가동·시운전 확인 시점",
    "commercial_operation_date": "상업 가동 시점",
    "capacity_tpy": "연간 생산능력",
    "capacity_tph": "시간당 처리능력",
    "capex_eur": "투자비",
    "capex_usd": "투자비",
    "capex_krw": "투자비",
    "capex_jpy": "투자비",
    "trl": "기술성숙도",
    "process_risk": "공정 안전·환경 위험",
    "investment_announcement_date": "투자 의향 발표 시점",
    "schedule_change": "일정·의사결정 변경",
    "scrap_share_target": "스크랩 사용 목표",
    "product_scope": "목표 제품 범위",
    "government_support_confirmation": "정부 지원 교차검증",
    "target_commercial_operation_date": "목표 상업생산 시점",
    "independent_government_validation": "정부 독립 검증",
    "electrolyzer_long_term_result": "전해조 장기운전 결과",
    "state_aid_amount": "정부 지원 규모",
    "original_capacity_tpy": "기존 승인 용량",
    "hydrogen_support_mechanism": "재생수소 지원 구조",
    "agreement_confirmation": "계약 교차확인",
    "easymelt_status": "EASyMelt 고로 개조 상태",
    "steelworks_ccus_status": "제철소 CCUS 상태",
    "hyrex_process_configuration": "HyREX 공식 공정 구성",
    "process_configuration": "공정 구성",
    "technology_route": "기술 경로",
    "equipment_configuration": "설비 구성",
    "funding_amount": "지원·조달 금액",
    "technical_definition": "기술 정의",
    "cell_configuration": "전해 셀 구성",
    "reactor_configuration": "반응기 구성",
    "operating_temperature": "운전 온도",
    "product_purity": "제품 순도",
    "feedstock_scope": "적용 원료",
    "energy_flexibility": "전력 운전 유연성",
    "downstream_route": "후단 활용",
    "core_reaction": "총괄 반응",
    "process_principle": "작동 원리",
    "electrolyte_system": "전해질계",
    "anode_material": "양극 재료",
    "anode_durability": "양극 내구성",
    "process_mode": "운전 방식",
    "product_form": "제품 형태",
    "byproduct": "부산물",
    "laboratory_variant_temperature": "저온 학술 변형 온도",
    "current_efficiency": "전류효율",
    "energy_intensity_estimate": "전력원단위 추정",
    "emissions_boundary": "배출 경계",
    "infrastructure_requirement": "필요 인프라",
    "economic_assessment": "경제성 평가",
    "development_stage": "공개 개발 단계",
    "scale_status": "확인된 실증 규모",
    "campaign_result": "연속운전 결과",
    "test_result": "시험 결과",
    "commercial_model": "상용화 모델",
    "location": "위치",
    "furnace_volume": "노 용적",
    "pilot_furnace_volume_m3": "시험고로 용적(m³)",
    "reactor_height": "반응기 높이",
    "facility_footprint": "설비 부지 규모",
    "original_target_start_date": "기존 실증 개시 목표",
    "scale_up_plan": "확대 검증 계획",
    "site_scope": "거점별 설비 범위",
    "partners": "참여 기관",
    "expected_co2_reduction": "예상 CO2 감축",
    "performance_disclosure_limit": "공개 성과의 한계",
    "performance_boundary": "성과 해석 경계",
    "laboratory_electrolysis_condition": "학술 실험 조건",
    "ore_feed_scope": "학술 검증 원료 범위",
    "academic_route_scope": "학술 검토 기술 범위",
    "cross_route_constraints": "경로 공통 제약",
    "regional_route_dependency": "지역별 경로 의존성",
    "conference_process_configuration": "학회 공개 공정 구성",
    "original_pilot_capacity_plan": "학회 발표 당시 파일럿 계획",
    "furnace_selection_by_feed_grade": "원료 품위별 용융로 선택",
    "conference_author_stage_assessment": "학회 저자 단계 평가",
    "public_scaleup_evidence_gap": "공개 스케일업 근거 공백",
    "scaleup_methodology": "스케일업 검토 방법",
    "outlet_co2_target": "후단 CO2 농도 목표",
    "emissions_measurement_scope": "배출 측정 범위",
    "reducing_gas_composition": "환원가스 조성",
    "hydrogen_consumption": "수소 원단위",
    "metallization": "금속화율",
    "product_carbon": "제품 탄소",
    "sticking_risk": "스티킹·클러스터링",
    "ore_quality_requirement": "원료 품질 요구",
    "heat_balance": "열수지",
    "eaf_integration": "EAF 연계",
    "electricity_demand_scenario": "전력 인프라 시나리오",
    "emissions_per_tonne": "제품 단위 배출",
    "pilot_output": "파일럿 생산량",
    "storage_flexibility": "수소 저장·운전 유연성",
    "furnace_configuration": "노형·전극 구성",
    "slag_function": "슬래그 기능",
    "slag_basicity_window": "슬래그 염기도 창",
    "carbon_requirement": "잔존 탄소 요구",
    "iron_yield": "철 수율·손실",
    "refractory_and_heat_loss": "내화물·열손실",
    "feed_power_control": "장입·전력 제어",
    "scale_up_requirement": "상용 규모 확대 조건",
    "commercial_reference": "기존 산업 운전 사례",
    "site_selection_date": "부지 선정 시점",
    "funding_announcement_date": "지원 발표 시점",
    "feasibility_start_date": "타당성·FEED 착수 시점",
    "target_fid_date": "최종투자결정 목표",
    "partners": "참여 기관",
    "supplier_configuration": "공급사 구성",
    "capture_point": "포집 대상·지점",
    "gas_condition": "원료가스 조건",
    "capture_route": "포집 공정 경로",
    "separation_method": "분리·흡수 방식",
    "capture_performance": "포집 성능",
    "regeneration_energy": "재생열·에너지 부담",
    "top_gas_recycle": "상부가스 재순환",
    "oxygen_blast": "산소송풍·열수지",
    "compression_transport": "압축·액화·수송",
    "storage_route": "영구 저장 경로",
    "utilization_route": "활용 경로",
    "carbon_accounting": "탄소회계 경계",
    "retrofit_boundary": "개조 범위",
    "system_capture_scope": "제철소 전체 포집 범위",
    "capture_capacity_tpd": "일일 CO2 포집능력",
    "capture_capacity_tpy": "연간 CO2 포집능력",
    "product_capacity_lpy": "연간 제품 생산능력",
    "operating_configuration": "선정 운전 구성",
    "pathway_definition": "전환 경로 정의",
    "route_portfolio": "경로 포트폴리오",
    "secondary_energy_advantage": "스크랩 경로 에너지 이점",
    "scrap_supply_constraint": "스크랩 공급 제약",
    "hydrogen_dri_competitiveness": "수소 DRI 경쟁 조건",
    "hydrogen_dri_deployment_pace": "수소 DRI 배치 속도 시나리오",
    "ccus_capture_scenario": "CCUS 배치 시나리오",
    "emissions_measurement_boundary": "비교 배출 경계",
    "data_quality_requirement": "데이터 품질 요구",
    "methodology_limit": "산정 방법론 한계",
    "near_zero_capacity_2030": "2030 근제로 용량 격차",
    "offtake_gap": "오프테이크 격차",
    "cost_premium_range": "초기 비용 프리미엄",
    "asset_reinvestment_window": "자산 재투자 창",
    "carbon_lock_in_risk": "탄소 고착 위험",
    "infrastructure_dependency": "외부 인프라 의존성",
    "announced_pipeline_2026": "2026 발표 파이프라인",
    "fid_conversion_rate_2026": "FID 전환 비율",
    "electrolysis_readiness": "전기분해 산업화 시계",
    "execution_stage_framework": "실행 단계 판독 기준",
    "scrap_variable_accounting": "스크랩 비율 보정",
    "progress_level_one_threshold": "Progress Level 1 문턱 예시",
    "independent_audit_requirement": "독립 검증 요구",
    "target_product_date": "목표 제품 양산 시점",
    "tower_erection_date": "DR 타워 철골 설치 시점",
    "hydrogen_network_date": "수소망 연결 목표",
    "avoided_emissions_tpy": "연간 CO2 감축·회피량",
    "hydrogen_transition": "수소 전환 순서",
    "architecture_layers": "시스템 계층",
    "sensing_layer": "센서·계측 계층",
    "data_context_layer": "데이터 문맥화",
    "model_layer": "모델 계층",
    "synchronization_requirement": "물리–가상 동기화",
    "digital_thread": "디지털 스레드",
    "interoperability": "상호운용성",
    "vvuq": "검증·검정·불확도 정량화",
    "decision_authority": "의사결정·제어 권한",
    "human_in_loop": "사람 개입 구조",
    "closed_loop_control": "폐루프 자동제어",
    "latency_requirement": "실시간성·지연",
    "fail_safe_fallback": "안전정지·수동 전환",
    "ot_security": "OT 보안 경계",
    "model_drift": "모델 드리프트 관리",
    "traceability": "데이터·결정 추적성",
    "deployment_scope": "현장 배치 범위",
    "performance_metrics": "성과 측정 지표",
    "quantitative_result": "공개 정량 성과",
    "result_limitations": "공개 성과의 한계",
    "scale_out_requirement": "다른 설비 확산 조건",
    "automation_scope": "자동화 범위",
    "model_accuracy": "모델 예측 정확도",
    "economic_benefit": "예상 경제 효과",
    "demonstration_date": "공개 시연 시점",
    "scrap_quality_hierarchy": "스크랩 품질 위계",
    "contaminant_sources": "불순물 유입원",
    "copper_hot_shortness": "구리 열간취성",
    "tin_synergy": "주석의 복합 영향",
    "flat_product_copper_limit": "고급 판재의 구리 기준",
    "shredded_scrap_copper": "파쇄 노폐스크랩의 구리 수준",
    "oxidation_limit": "통상 산화정련의 한계",
    "upstream_liberation": "용해 전 해방·분리",
    "sensor_sorting": "센서·영상 선별",
    "bulk_measurement_limit": "벌크 성분 측정 한계",
    "thermomechanical_separation": "열기계적 분리",
    "dilution_route": "희석·배합 경로",
    "primary_iron_blending": "청정 1차 철 배합",
    "solid_scrap_treatment": "고체 스크랩 처리 후보",
    "melt_extraction_routes": "용탕 추출 후보",
    "vacuum_distillation": "진공증류",
    "sulfide_slagging": "황화슬래그·매트",
    "dephosphorization": "탈인 제어",
    "denitrogenation": "탈질 제어",
    "nitrogen_sources": "질소 유입원",
    "secondary_refining": "2차정련 역할",
    "yield_and_residue": "철 수율·잔사",
    "product_grade_specificity": "제품 등급별 제약",
    "existing_sorting_platform": "기존 선별 플랫폼",
    "process_stages": "공정 단계",
    "vision_classification_result": "영상 분류 연구 결과",
    "reported_nitrogen_reference": "보고된 질소 수준 비교",
    "phosphorus_prediction_result": "종점 인 예측 연구 결과",
    "particle_size_range": "원료 입도 범위",
    "ultrafines_handling": "초미분 처리",
    "preheating_and_oxidation": "건조·예열·산화",
    "fluidization_regime": "유동화 방식",
    "reactor_cascade": "유동층 단계 구성",
    "reduction_temperature": "환원 온도",
    "reduction_degree": "단계별 환원도",
    "gas_recycle": "환원가스 재순환",
    "dust_recycle": "분진 회수·재순환",
    "stage_cyclone_function": "단계별 cyclone 기능",
    "elutriation_risk": "비산·입자 손실 위험",
    "sticking_mechanism": "고착 발생 메커니즘",
    "sticking_controls": "고착 억제 수단",
    "gas_velocity_tradeoff": "가스속도 상충관계",
    "ore_grade_tradeoff": "광석 품위·맥석 영향",
    "particle_morphology": "입자 형상·표면 영향",
    "briquetting_requirement": "압축·브리켓 필요성",
    "hot_dri_transport": "고온 환원철 이송",
    "downstream_product_handling": "후단 제품 처리",
    "historical_demonstration": "과거 실증 이력",
    "pilot_batch_size": "파일럿 회분 투입량",
    "pilot_campaign_plan": "파일럿 캠페인 계획",
    "integrated_process_train": "통합 설비 구성",
    "mou_date": "업무협약 시점",
    "cooperation_agreement_date": "협력계약 체결 시점",
    "supplier_announcement_date": "공급사 발표 시점",
    "first_campaign_date": "최초 시험 캠페인",
    "pilot_first_molten_iron_date": "파일럿 첫 용선 생산",
    "site_preparation_status_date": "부지 준비 확인 시점",
    "equipment_reference": "대표 설비 참고",
    "plasma_species": "활성 수소종",
    "arc_configuration": "플라즈마 아크 구성",
    "electrode_configuration": "전극·원료 공급 구성",
    "electrode_consumption": "전극 소비·탄소 유입",
    "plasma_stabilizer": "플라즈마 안정화 가스",
    "plasma_melt_interface": "플라즈마–용융욕 계면",
    "reduction_sequence": "산화철 환원 순서",
    "rate_limiting_stage": "속도결정 단계",
    "feed_mode": "원료 공급 방식",
    "tapping_mode": "출강 방식",
    "melt_capacity": "용융욕·회분 용량",
    "ore_feed_rate": "시험 원료 공급률",
    "continuous_target_capacity": "연속화 목표 처리량",
    "hydrogen_utilization": "수소 이용률",
    "argon_penalty": "아르곤 안정화 부담",
    "offgas_heat_recovery": "배가스 현열·수소 회수",
    "water_vapor_recovery": "수증기 회수·재전해",
    "optical_monitoring": "광학방출·영상 계측",
    "optical_visibility_limit": "광학계측 시야 한계",
    "iron_evaporation": "철 증발·수율 위험",
    "refractory_exposure": "내화물 노출·마모",
    "pre_reduction_integration": "사전환원 통합",
    "original_target_completion_date": "기존 목표 종료 시점",
    "current_project_completion_date": "현재 공식 종료 시점",
    "pilot_operation_start_date": "파일럿 운전 개시",
    "research_origin_date": "연구 기원",
    "followup_start_date": "후속 프로젝트 착수",
    "followup_phase_completion_date": "중간 후속단계 종료",
    "project_volume_eur": "총 프로젝트 규모",
    "target_trl": "목표 기술성숙도",
    "biomass_role": "바이오매스 역할",
    "biomass_candidates": "바이오매스 후보",
    "agglomerate_form": "원료 성형 형태",
    "microwave_frequency": "마이크로웨이브 주파수",
    "microwave_delivery": "마이크로웨이브 전달계",
    "furnace_zones": "노 구역 구성",
    "linear_hearth_transport": "선형 노상 이송",
    "inerting_and_sealing": "불활성화·전자파 차폐",
    "pyrolysis_gas_role": "열분해가스 역할",
    "bed_depth_control": "층고·분포 제어",
    "microwave_penetration": "마이크로웨이브 침투깊이",
    "reaction_path": "산화철 환원 경로",
    "side_reaction": "부반응·맥석 영향",
    "dri_cooling": "DRI 냉각",
    "dri_passivation": "DRI 패시베이션",
    "downstream_melting": "후단 용융·정련",
    "offgas_treatment": "배가스 처리",
    "pilot_operating_hours": "연간 계획 운전시간",
    "campaign_schedule": "파일럿 캠페인 일정",
    "pilot_horn_count": "마이크로웨이브 혼 구성",
    "laboratory_scale": "실험실 시험 규모",
    "patent_energy_balance": "특허 에너지수지",
    "electricity_comparison_claim": "전력수요 비교 주장",
    "emissions_reduction_claim": "배출감축 주장",
    "biomass_efficiency_claim": "바이오매스 효율 주장",
    "sustainability_boundary": "바이오매스 지속가능성 경계",
    "radiation_safety": "전자파 안전",
    "dust_explosion_risk": "분진폭발 위험",
    "waste_estimate": "허가 설계 폐기물 추정",
    "furnace_design_risk": "노 설계 확대 위험",
    "continued_rd_status": "건설 중단 후 R&D",
    "patent_priority_date": "특허 우선일",
    "small_pilot_result_date": "독일 소형 파일럿 발표",
    "investment_approval_date": "서호주 투자 발표",
    "permit_decision_date": "환경 허가 결정",
    "construction_pause_date": "건설 중단 발표",
    "original_commissioning_target": "기존 시운전 목표",
    "commissioning_target": "시운전 목표",
    "qualification_commitments": "수요사 품질인증 약정",
    "demonstration_financing": "실증 자금조달",
    "commercialization_target": "상용화 목표",
    "latest_pilot_status": "최신 파일럿 운전 상태",
    "pilot_cell_configuration": "파일럿 셀 구성",
    "trl_evidence_caveat": "TRL 근거 해석 주의",
    "latest_scale_up_plan": "최신 규모 확대 계획",
    "deployment_dependency": "산업화 선결조건",
    "fortescue_der_process_route": "Fortescue DER 공정 경로",
    "fortescue_real_ore_faraday_efficiency": "실광석 조건별 전류효율",
    "fortescue_membrane_screening": "분리막 조건 선별 결과",
    "fortescue_membrane_duration": "분리막 단기 운전시간",
    "fortescue_stage_status": "Fortescue DER 단계 현황",
    "fortescue_scale_up_target": "Fortescue DER 확대 목표",
    "fortescue_key_bottlenecks": "Fortescue DER 확인 병목",
    "hybrit_industrial_demo_schedule": "HYBRIT 산업실증 일정",
    "hybrit_demo_power_demand_estimate": "HYBRIT 추가 전력수요 추정",
    "hybrit_innovation_fund_status": "HYBRIT EU 지원협약 상태",
    "hybrit_permit_status": "HYBRIT 환경허가 상태",
    "hybrit_schedule_risk": "HYBRIT 일정 위험",
    "stegra_boden_financing": "Stegra Boden 자금조달",
    "stegra_boden_schedule_status": "Stegra Boden 일정 상태",
    "final_site_approval_date": "최종 부지 승인 시점",
    "construction_schedule": "건설 일정",
    "target_demo_completion_date": "실증설비 완공 목표",
    "trial_operation_window": "단계별 시험운전 기간",
    "h2plasmared_project_period": "H2PlasmaRed 사업기간",
    "h2plasmared_funding": "H2PlasmaRed 사업비·EU 지원",
    "h2plasmared_target": "H2PlasmaRed 실증 목표",
    "h2plasmared_current_status": "H2PlasmaRed 공개 진행상태",
    "pilot_2026_test_basis": "2026년 파일럿 시험 기준",
    "pilot_refractory_result": "파일럿 내화물 결과",
    "pilot_insulation_result": "파일럿 단열 개선 결과",
    "ore_gangue_effect": "광석 맥석 영향",
    "batch_size_interpretation": "회분 규모 해석 주의",
    "metso_pilot_configuration": "Metso Pori 파일럿 구성",
    "metso_campaign_scale": "Metso Pori 캠페인 규모",
    "metso_commercial_design_claim": "Metso 상용설계 주장",
    "supplier_claim_limit": "공급사 주장 검증 한계",
    "total_cost_eur": "총사업비",
    "eu_contribution_eur": "EU 지원액",
    "low_quality_scrap_share_target": "저품질 스크랩 투입 확대 목표",
    "validation_scope": "검증 범위",
    "target_end_date": "목표 종료일",
    "first_barge_shipment_date": "첫 바지선 출하 시점",
    "product_shipment_milestone": "제품 출하 이정표",
    "capture_capacity_kgpd": "일일 CO2 시험 처리율",
    "trial_duration_target": "시험기간 목표",
    "phase_2_target": "2단계 시험 목표",
    "feedgas_risk": "원료가스 불순물 위험",
    "co2_conversion_connection_date": "CO2 전환장치 연결 시점",
    "co2_conversion_route": "CO2 전환 경로",
    "conversion_validation_scope": "전환공정 검증 범위",
    "additional_electricity_demand_twh_per_year": "추가 전력수요 추정",
    "construction_activity_status": "건설 활동 상태",
    "dc_eaf_retrofit_target_tonnes": "DC EAF 개조 목표 규모",
    "electrode_diameter_mm": "전극 직경",
    "environmental_permit_grant_date": "환경허가 승인일",
    "environmental_permit_scope": "환경허가 범위",
    "final_government_site_approval_date": "정부 최종 부지 승인",
    "financing_amount_eur": "종결 자금조달액",
    "financing_round_close_date": "자금조달 종결일",
    "financing_use": "자금 사용 목적",
    "funding_withdrawal_reason": "지원 철회 사유",
    "gangue_effect": "맥석 조성 영향",
    "hearth_dimensions_m": "노상 치수",
    "ijmuiden_pilot_capacity_tpy": "IJmuiden 파일럿 명목규모",
    "pilot_cumulative_hot_metal": "파일럿 누적 용선 생산·BOF 공급",
    "pilot_long_run_record": "파일럿 최장 연속운전·가용률",
    "pilot_peak_productivity": "파일럿 최고 생산성",
    "coal_rate_at_peak_productivity": "최고 생산성 조건 석탄 원단위",
    "feedstock_flexibility_campaign": "석탄 품질 범위 검증",
    "low_grade_ore_campaign": "저품위광·고 Al₂O₃ 슬래그 운전",
    "fossil_carbon_substitution_results": "화석탄소 대체 실적",
    "slag_circularity_campaign": "제강슬래그 순환이용 실증",
    "long_run_upgrade_bottleneck": "장기운전 제한과 설비 보강",
    "innovation_fund_disbursed_eur": "Innovation Fund 지급액",
    "innovation_fund_support_status": "Innovation Fund 지원 상태",
    "innovation_fund_support_withdrawn_eur": "철회된 Innovation Fund 금액",
    "integrated_hpsr_pilot_target_scale": "HPSR 통합 파일럿 목표 규모",
    "key_scale_up_risks": "핵심 scale-up 위험",
    "material_feeding_arrangement_count": "원료 장입 계통 수",
    "metso_conceptual_apparent_power_mva": "Metso 상용 개념 피상전력",
    "metso_conceptual_commercial_capacity_tpy": "Metso 상용 개념 생산능력",
    "metso_conceptual_design_power_mw": "Metso 상용 개념 설계전력",
    "metso_conceptual_electrode_configuration": "Metso 상용 개념 전극 구성",
    "metso_supplier_design_availability": "Metso 공급사 설계 가동률 주장",
    "metso_supplier_design_slag_feo": "Metso 공급사 설계 슬래그 FeO 주장",
    "offgas_system_configuration": "배가스 계통 구성",
    "periodic_report_status_date": "정기보고 진행상태",
    "pilot_fbr_capacity_kg_per_batch": "유동환원 시험로 회분 규모",
    "pilot_fbr_introduction_year": "유동환원 시험로 도입 연도",
    "pilot_hot_metal_capacity_tph": "파일럿 명목 용선 처리율",
    "pilot_metallisation_result": "파일럿 금속화 결과",
    "pilot_ore_feed_rate": "파일럿 광석 투입률",
    "pilot_reactor_configuration": "파일럿 반응기 구성",
    "pilot_wall_temperature_range": "파일럿 벽온 범위",
    "post_permit_decision_status": "허가 후 의사결정 상태",
    "pretreatment_elimination_scope": "생략 가능한 전처리 범위",
    "project_schedule_status": "프로젝트 일정 상태",
    "refractory_comparison_result": "내화물 비교 결과",
    "refractory_inspection_result": "내화물 검사 결과",
    "replacement_eu_funding_plan": "대체 EU 지원 신청 계획",
    "reported_trial_charge_mode": "논문 시험 장입 방식",
    "reported_trial_count": "논문 보고 시험 횟수",
    "reported_trial_stop_condition": "논문 시험 종료 조건",
    "reported_trial_tapping_mode": "논문 시험 출탕 방식",
    "scale_up_method": "제안 scale-up 방식",
    "scale_up_risks": "scale-up 위험",
    "site_development_area_m2": "개발부지 면적",
    "tapping_configuration": "출선·출재 구성",
    "target_five_tonne_campaign_completion_date": "5 t 캠페인 완료 목표",
    "target_groundbreaking_date": "목표 착공 시점",
    "target_pilot_trials_end_date": "파일럿 시험 완료 목표",
    "target_ramp_up_period": "목표 램프업 기간",
    "target_trial_operation_end_date": "단계별 시험운전 목표",
    "test_platform_purpose": "시험 플랫폼 목적",
    "theoretical_hydrogen_minimum": "이론적 최소 수소량",
    "thermal_insulation_energy_result": "단열 적용 에너지 결과",
    "thermal_insulation_phase_separation_result": "단열 적용 상분리 결과",
    "transformer_apparent_power_mva": "변압기 피상전력",
    "trl_baseline": "출발 기술성숙도",
    "trl_target": "목표 기술성숙도",
    "typical_test_campaign_duration_days": "통상 시험 캠페인 기간",
    "typical_test_campaign_feed_tonnes": "통상 시험 캠페인 원료량",
}
TECHNICAL_FEATURE_GROUPS = (
    (
        "시스템·데이터·모델",
        (
            "architecture_layers",
            "sensing_layer",
            "data_context_layer",
            "model_layer",
            "synchronization_requirement",
            "digital_thread",
            "interoperability",
            "vvuq",
        ),
    ),
    (
        "운전 권한·안전·보안",
        (
            "decision_authority",
            "human_in_loop",
            "closed_loop_control",
            "latency_requirement",
            "fail_safe_fallback",
            "ot_security",
            "model_drift",
            "traceability",
        ),
    ),
    (
        "스크랩·잔류원소 관리",
        (
            "scrap_quality_hierarchy",
            "contaminant_sources",
            "copper_hot_shortness",
            "tin_synergy",
            "flat_product_copper_limit",
            "shredded_scrap_copper",
            "oxidation_limit",
            "upstream_liberation",
            "sensor_sorting",
            "bulk_measurement_limit",
            "vision_classification_result",
            "thermomechanical_separation",
            "dilution_route",
            "primary_iron_blending",
            "solid_scrap_treatment",
            "melt_extraction_routes",
            "vacuum_distillation",
            "sulfide_slagging",
            "dephosphorization",
            "denitrogenation",
            "nitrogen_sources",
            "reported_nitrogen_reference",
            "secondary_refining",
            "phosphorus_prediction_result",
            "yield_and_residue",
            "product_grade_specificity",
        ),
    ),
    (
        "반응·셀·공정",
        (
            "core_reaction",
            "process_principle",
            "process_configuration",
            "conference_process_configuration",
            "fortescue_der_process_route",
            "cell_configuration",
            "pilot_cell_configuration",
            "reactor_configuration",
            "furnace_configuration",
            "metso_pilot_configuration",
            "electrolyte_system",
            "anode_material",
            "anode_durability",
            "reducing_gas_composition",
            "heat_balance",
            "process_mode",
            "capture_point",
            "gas_condition",
            "capture_route",
            "separation_method",
            "top_gas_recycle",
            "oxygen_blast",
            "pathway_definition",
            "route_portfolio",
            "preheating_and_oxidation",
            "fluidization_regime",
            "reactor_cascade",
            "gas_recycle",
            "dust_recycle",
            "stage_cyclone_function",
            "sticking_mechanism",
            "sticking_controls",
            "integrated_process_train",
            "plasma_species",
            "arc_configuration",
            "electrode_configuration",
            "plasma_melt_interface",
            "reduction_sequence",
            "rate_limiting_stage",
            "optical_monitoring",
            "furnace_zones",
            "linear_hearth_transport",
            "inerting_and_sealing",
            "pyrolysis_gas_role",
            "bed_depth_control",
            "microwave_delivery",
            "reaction_path",
            "furnace_selection_by_feed_grade",
        ),
    ),
    (
        "원료·운전·제품",
        (
            "operating_temperature",
            "laboratory_variant_temperature",
            "feedstock_scope",
            "ore_feed_scope",
            "academic_route_scope",
            "laboratory_electrolysis_condition",
            "product_form",
            "product_purity",
            "metallization",
            "product_carbon",
            "byproduct",
            "energy_flexibility",
            "hydrogen_consumption",
            "ore_quality_requirement",
            "sticking_risk",
            "slag_function",
            "slag_basicity_window",
            "carbon_requirement",
            "iron_yield",
            "downstream_route",
            "eaf_integration",
            "secondary_energy_advantage",
            "scrap_supply_constraint",
            "scrap_variable_accounting",
            "particle_size_range",
            "ultrafines_handling",
            "reduction_temperature",
            "reduction_degree",
            "elutriation_risk",
            "gas_velocity_tradeoff",
            "ore_grade_tradeoff",
            "particle_morphology",
            "briquetting_requirement",
            "hot_dri_transport",
            "downstream_product_handling",
            "feed_mode",
            "tapping_mode",
            "melt_capacity",
            "ore_feed_rate",
            "continuous_target_capacity",
            "hydrogen_utilization",
            "argon_penalty",
            "electrode_consumption",
            "iron_evaporation",
            "refractory_exposure",
            "pre_reduction_integration",
            "offgas_heat_recovery",
            "water_vapor_recovery",
            "optical_visibility_limit",
            "biomass_role",
            "biomass_candidates",
            "agglomerate_form",
            "microwave_frequency",
            "microwave_penetration",
            "side_reaction",
            "dri_cooling",
            "dri_passivation",
            "downstream_melting",
            "pilot_horn_count",
            "laboratory_scale",
            "fortescue_real_ore_faraday_efficiency",
            "fortescue_membrane_screening",
            "fortescue_membrane_duration",
            "fortescue_key_bottlenecks",
            "pilot_2026_test_basis",
            "pilot_refractory_result",
            "pilot_insulation_result",
            "ore_gangue_effect",
            "batch_size_interpretation",
        ),
    ),
    (
        "에너지·환경·경제",
        (
            "current_efficiency",
            "energy_intensity_estimate",
            "emissions_boundary",
            "emissions_per_tonne",
            "infrastructure_requirement",
            "electricity_demand_scenario",
            "hybrit_demo_power_demand_estimate",
            "economic_assessment",
            "refractory_and_heat_loss",
            "feed_power_control",
            "capture_performance",
            "regeneration_energy",
            "compression_transport",
            "storage_route",
            "utilization_route",
            "carbon_accounting",
            "retrofit_boundary",
            "system_capture_scope",
            "hydrogen_dri_competitiveness",
            "ccus_capture_scenario",
            "emissions_measurement_boundary",
            "data_quality_requirement",
            "methodology_limit",
            "cross_route_constraints",
            "regional_route_dependency",
            "cost_premium_range",
            "infrastructure_dependency",
            "progress_level_one_threshold",
            "offgas_treatment",
            "patent_energy_balance",
            "electricity_comparison_claim",
            "emissions_reduction_claim",
            "biomass_efficiency_claim",
            "sustainability_boundary",
            "radiation_safety",
            "dust_explosion_risk",
            "waste_estimate",
        ),
    ),
    (
        "실증·산업화",
        (
            "development_stage",
            "scale_status",
            "scale_up_plan",
            "original_pilot_capacity_plan",
            "conference_author_stage_assessment",
            "public_scaleup_evidence_gap",
            "scaleup_methodology",
            "pilot_output",
            "test_result",
            "performance_disclosure_limit",
            "campaign_result",
            "storage_flexibility",
            "scale_up_requirement",
            "commercial_reference",
            "commercial_model",
            "hydrogen_dri_deployment_pace",
            "near_zero_capacity_2030",
            "offtake_gap",
            "asset_reinvestment_window",
            "carbon_lock_in_risk",
            "announced_pipeline_2026",
            "fid_conversion_rate_2026",
            "electrolysis_readiness",
            "execution_stage_framework",
            "independent_audit_requirement",
            "deployment_scope",
            "performance_metrics",
            "quantitative_result",
            "result_limitations",
            "scale_out_requirement",
            "historical_demonstration",
            "pilot_batch_size",
            "pilot_campaign_plan",
            "pilot_operating_hours",
            "campaign_schedule",
            "furnace_design_risk",
            "continued_rd_status",
            "commissioning_target",
            "qualification_commitments",
            "demonstration_financing",
            "commercialization_target",
            "latest_pilot_status",
            "trl_evidence_caveat",
            "latest_scale_up_plan",
            "deployment_dependency",
            "fortescue_stage_status",
            "fortescue_scale_up_target",
            "hybrit_industrial_demo_schedule",
            "hybrit_innovation_fund_status",
            "hybrit_permit_status",
            "hybrit_schedule_risk",
            "stegra_boden_financing",
            "stegra_boden_schedule_status",
            "h2plasmared_project_period",
            "h2plasmared_funding",
            "h2plasmared_target",
            "h2plasmared_current_status",
            "metso_campaign_scale",
            "metso_commercial_design_claim",
            "supplier_claim_limit",
        ),
    ),
)
PROJECT_TIMELINE_PREDICATES = {
    "project_start_date": "착수",
    "project_completion_date": "단계 완료",
    "target_start_date": "목표 일정",
    "target_completion_date": "목표 일정",
    "target_commissioning_date": "목표 일정",
    "construction_start_date": "실행 일정",
    "commissioning_date": "실행 일정",
    "commercial_operation_date": "실행 일정",
    "target_storage_completion_date": "목표 일정",
    "site_selection_date": "실행 일정",
    "funding_announcement_date": "실행 일정",
    "feasibility_start_date": "실행 일정",
    "target_fid_date": "목표 일정",
    "target_product_date": "목표 일정",
    "tower_erection_date": "실행 일정",
    "hydrogen_network_date": "목표 일정",
    "demonstration_date": "실행 일정",
    "mou_date": "협력 이력",
    "cooperation_agreement_date": "협력 이력",
    "supplier_announcement_date": "공식 발표",
    "first_campaign_date": "실증 이력",
    "pilot_first_molten_iron_date": "실증 이력",
    "site_preparation_status_date": "실행 현황",
    "original_target_completion_date": "기존 목표",
    "current_project_completion_date": "현재 공식 일정",
    "pilot_operation_start_date": "실증 이력",
    "research_origin_date": "연구 이력",
    "followup_start_date": "후속 단계",
    "followup_phase_completion_date": "후속 단계",
    "patent_priority_date": "특허 이력",
    "small_pilot_result_date": "실증 이력",
    "investment_approval_date": "투자 발표",
    "permit_decision_date": "허가 이력",
    "construction_pause_date": "중단 발표",
    "original_commissioning_target": "기존 목표",
    "investment_announcement_date": "투자 의향 발표",
    "schedule_change": "일정·의사결정 변화",
    "target_commercial_operation_date": "목표 상업생산 시점",
    "target_end_date": "목표 일정",
    "first_barge_shipment_date": "출하 이력",
    "co2_conversion_connection_date": "설비 연결",
    "environmental_permit_grant_date": "허가 이력",
    "final_government_site_approval_date": "부지 승인",
    "financing_round_close_date": "자금조달",
    "target_groundbreaking_date": "목표 일정",
}
PROJECT_DISPLAY_NAMES = {
    "PRJ-ZESTY-ROCKINGHAM-DEMO": "Calix ZESTY Rockingham 3만 t/y 실증 계획",
    "PRJ-HISARNA-JAMSHEDPUR-DEMO": "Tata Steel Jamshedpur HIsarna 약 100만 t/y 실증 계획",
    "PRJ-HYBRIT-GALLIVARE-DEMO": "HYBRIT Gällivare 무화석 스펀지철 산업 실증",
    "PRJ-STEGRA-BODEN": "Stegra Boden 통합 그린스틸 프로젝트",
    "PRJ-H2PLASMARED-EU": "EU H2PlasmaRed 통합 실증",
    "PRJ-PURESCRAP-EU-SCRAP-PURITY": "EU PURESCRAP 스크랩 순도 검증",
    "PRJ-ARCELORMITTAL-GHENT-MHI-CO2-PILOT": "ArcelorMittal Gent MHI CO2 포집·전환 파일럿",
    "PRJ-BIOIRON-WA-RD": "BioIron 연구개발 시설 (Western Australia)",
    "PRJ-ELECTRA-CLEAN-IRON-DEMO": "Electra 청정철 시범공장",
    "PRJ-HY4SMELT": "HY4Smelt 실증 프로젝트",
    "PRJ-HYFOR-DONAWITZ-PILOT": "HYFOR Donawitz 수소환원 파일럿",
    "PRJ-POSCO-HYREX-DEMO": "POSCO 포항 HyREX 통합 실증",
    "PRJ-SUSTEEL-DONAWITZ": "voestalpine Donawitz SuSteel·SuS-F",
    "PRJ-LIGHTBOW-HPSR-CONTROL": "LIGHTBOW HPSR 아크 제어 연구",
    "PRJ-BOSTON-METAL-MOE-WOBURN": "Boston Metal Woburn MOE 산업 셀",
    "PRJ-HYBRIT-LULEA-PILOT": "HYBRIT 룰레오 수소 DRI 파일럿",
    "PRJ-NEOSMELT-KWINANA": "NeoSmelt Kwinana DRI–ESF 파일럿",
    "PRJ-METSO-PORI-DRI-SMELTING-PILOT": "Metso Pori DRI 용융 파일럿",
    "PRJ-ULCOS-TGR-BF": "ULCOS 상부가스 재순환 고로",
    "PRJ-TATA-JAMSHEDPUR-BF-CCU": "Tata Jamshedpur 고로가스 CCU",
    "PRJ-STEELANOL-GHENT": "ArcelorMittal Ghent Steelanol",
    "PRJ-CARBON2CHEM-DUISBURG": "thyssenkrupp Duisburg Carbon2Chem",
    "PRJ-POSCO-GWANGYANG-EAF": "POSCO 광양 250만 톤 전기로",
    "PRJ-SSAB-LULEA-ELECTRIC-MILL": "SSAB Luleå 신규 전기제철소",
    "PRJ-TK-H2STEEL-DUISBURG": "thyssenkrupp Duisburg tkH2Steel",
    "PRJ-POSCO-GWANGYANG-ONE-TOUCH-CONVERTER": "POSCO 광양 2전로 원터치 자동화",
    "PRJ-JFE-SINTER-CPS-ROLLOUT": "JFE 일본 7개 소결설비 CPS 전개",
    "PRJ-TATA-SINTER-DIGITAL-TWIN": "Tata 소결 디지털 트윈",
    "PRJ-MOLTEN-SULFIDE-ELECTROLYSIS": "용융 황화물 전해 프로젝트",
    "PRJ-SORTERA-SCRAP-DECOPPER": "Sortera 스크랩 구리 제거 프로젝트",
    "PRJ-BAOWU-ZHANJIANG-H2-SHAFT-EAF": "China Baowu Zhanjiang 수소 샤프트로–전기로 라인",
    "PRJ-NIPPON-HASAKI-H2-DRI": "Nippon Steel Hasaki 수소 DRI 시험로",
    "PRJ-NIPPON-JAPAN-EAF-CONVERSION": "Nippon Steel 일본 3개 거점 전기로 전환",
    "PRJ-NIPPON-KIMITSU-COURSE50": "Nippon Steel Kimitsu COURSE50 실증",
    "PRJ-NIPPON-USS-BIG-RIVER-DRI": "Nippon Steel·U. S. Steel Big River DRI",
    "PRJ-NUCOR-CONVENT-DRI-CCS": "Nucor Convent DRI–CCS",
    "PRJ-NUCOR-GALLATIN-EAF-CCUS": "Nucor Gallatin EAF 탄소포집 파일럿",
    "PRJ-NUCOR-WEST-VIRGINIA-SHEET-MILL": "Nucor West Virginia 첨단 판재 공장",
    "PRJ-ARCELORMITTAL-DUNKIRK-EAF": "ArcelorMittal Dunkirk 대형 전기로",
    "PRJ-ARCELORMITTAL-VOLTERON": "ArcelorMittal–John Cockerill Volteron",
    "PRJ-TATA-JAMSHEDPUR-EASYMELT": "Tata Jamshedpur EASyMelt 산업 실증",
    "PRJ-TATA-IJMUIDEN-DRP-EAF": "Tata Steel IJmuiden DRP–EAF 전환",
    "PRJ-JFE-KURASHIKI-LARGE-EAF": "JFE Kurashiki 대형 고효율 전기로",
    "PRJ-JFE-CHIBA-NO4-EAF": "JFE 치바 제4제강 전기로",
    "PRJ-JFE-CHIBA-CARBON-RECYCLING-BF": "JFE Chiba 150 m³ 탄소순환 시험고로",
}
CLAIM_STATUS_LABELS = {
    "active": "현재 유효",
    "superseded": "후속 정보로 대체",
    "disputed": "근거 충돌",
    "cancelled": "취소",
    "stale": "재검증 필요",
}
CLAIM_CROSS_VALIDATION_LABELS = {
    "single": "단일 출처",
    "independent": "독립 교차확인",
    "conflicted": "출처 상충",
    "unknown": "근거 미확인",
}
CROSS_VALIDATION_EXCLUDED_PREDICATES = REQUIRED_SIGNAL_PREDICATES | {
    "affected_business",
    "collected_at",
    "response_deadline",
}
CLAIM_ACTION_LABELS = {
    "created": "신규 확인",
    "verified": "재검증",
    "superseded": "후속 정보로 대체",
    "disputed": "근거 충돌",
    "cancelled": "취소 확인",
}
CLAIM_ACTION_LABELS = {
    "created": "신규 등록",
    "verified": "재검증",
    "status_changed": "상태 변경",
    "coexistence_confirmed": "공존 확인",
    "review_supersede": "검토 후 대체",
    "review_coexist": "검토 후 공존",
    "review_dispute": "검토 후 충돌",
}
RAW_DIR = Path(".system/raw")
SOURCE_RECORDS_DIR = Path(".system/source-records")
SOURCE_CANDIDATES_DIR = Path(".system/source-candidates")
CLAIMS_DIR = Path(".system/claims")
SIGNALS_DIR = Path(".system/signals")
SIGNAL_VERSIONS_DIR = Path(".system/signal-versions")
INSIGHTS_DIR = Path(".system/insights")
RISK_FACTORS_DIR = Path(".system/risk-factors")
OBSERVATIONS_DIR = Path(".system/observations")
EVENTS_DIR = Path(".system/events")
COMPANY_IMPACTS_DIR = Path(".system/company-impacts")
SCENARIOS_DIR = Path(".system/scenarios")
SYSTEMATIC_ANALYSES_DIR = Path(".system/systematic-analyses")
PENDING_REVIEWS_DIR = Path(".system/reviews/pending")
RESOLVED_REVIEWS_DIR = Path(".system/reviews/resolved")
RUNS_DIR = Path(".system/runs")
MEDIA_DIR = Path("assets/media")
MEDIA_KINDS = {
    "facility_photo",
    "process_diagram",
    "equipment_drawing",
    "patent_figure",
    "academic_figure",
    "ai_reconstruction",
    "other",
}
MEDIA_KIND_LABELS = {
    "facility_photo": "실제 설비 사진",
    "process_diagram": "공정 개념도",
    "equipment_drawing": "장치 구성도",
    "patent_figure": "특허 도면",
    "academic_figure": "학술 자료 그림",
    "ai_reconstruction": "AI 재구성",
    "other": "기술 이미지",
}
MEDIA_DISPLAY_OVERRIDES = {
    # Google Patents serves these figures as tall, full patent-sheet images.
    # Keep their patent identity, but prevent a single portrait page from
    # dominating the article viewport.
    "MED-7D0824C55537": {
        "display_width": "compact",
    },
    "MED-FA0ECC96CB3C": {
        "display_width": "compact",
    },
    # This source image documents a partnership signing, not the process or
    # equipment. Retain it in the evidence record but keep the reader-facing
    # technology dossier focused on plant hardware.
    "MED-098B84E432A7": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    # The official page labels this asset as a NEDO COURSE50 image. Browser
    # inspection confirmed that it is the experimental-furnace photograph,
    # not the adjacent process flowsheet.
    "MED-01444A20637B": {
        "kind": "facility_photo",
        "caption": (
            "Nippon Steel Kimitsu COURSE50·Super COURSE50 시험고로 공식 사진"
        ),
        "alt_text": (
            "Nippon Steel Kimitsu의 COURSE50 고로 수소환원 시험설비"
        ),
    },
    # Visual inspection of the POSCO original confirmed that this is a
    # completion-ceremony stage photograph, not a plant or furnace view.
    # Preserve the registered evidence record, but do not surface it on
    # reader-facing pages when technical equipment imagery is expected.
    "MED-88CFD1B16754": {
        "kind": "other",
        "caption": "POSCO 광양 전기로 공장 준공식 무대 및 참석자 사진",
        "alt_text": "POSCO 광양 전기로 공장 준공식 행사 무대",
        "display_eligible": False,
        "hero_eligible": False,
    },
    # User visual identification corrected the location: the supplier page
    # uses a Pohang Works panorama as a contextual header even though the
    # release concerns the Gwangyang EAF order. Never present it as Gwangyang
    # project evidence.
    "MED-EF872DB2DAAD": {
        "kind": "facility_photo",
        "caption": (
            "POSCO 포항제철소 설비 전경. Tenova 광양 전기로 공급 발표의 "
            "문맥용 헤더 이미지로 사용됐으나 광양 설비 사진이 아니므로 표시 제외"
        ),
        "alt_text": "POSCO 포항제철소 설비 전경",
        "display_eligible": False,
        "hero_eligible": False,
    },
    # This steel-specific diagram exposes the sinter bed, sensor inputs,
    # hybrid model and control feedback, so it is more explanatory for the
    # smart-steelworks dossier than a generic manufacturing-twin image.
    "MED-C33AA7D4CB6D": {
        "hero_priority": -20,
    },
    # Superseded AI concept images remain in immutable evidence records, but
    # corrected process-flow versions are the only reader-facing variants.
    "MED-7B53D844AF8D": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    "MED-0899E249E8FA": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    "MED-1D4B045DD76D": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    "MED-667CEDEE9C8F": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    "MED-23BDA82376B5": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    "MED-EC43E3167DA9": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    "MED-49CEB753F6E6": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    # This AI redraw incorrectly stacked four beds inside one pressure shell
    # and showed open gravity transfer against the counter-current reducing
    # gas. Public HyREX/FINEX material instead shows separate reactors in a
    # cascade, with stage cyclones and pressure-aware solids transfer.
    "MED-A3F73A83EE4F": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    "MED-8C16D5A1B89E": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    "MED-D0FBFEAE165E": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    "MED-F5940F4D2FEC": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    "MED-52C2D1320144": {
        "display_eligible": False,
        "hero_eligible": False,
    },
    # This intermediate smart-steelworks redraw still allowed a visual bypass
    # around the single operator-approval path. Preserve it for provenance,
    # but do not publish it as a control architecture.
    "MED-6FA3CF1F55A0": {
        "display_eligible": False,
        "hero_eligible": False,
    },
}
SOURCE_DISPLAY_CORRECTIONS = {
    "SRC-20260725-C888600A": (
        "2026-07-25 사람 검토에서 이 보관 원문의 ‘Gwangyang Works aerial "
        "view’ 식별이 잘못된 것으로 확인되었습니다. Tenova 발표의 헤더 사진은 "
        "포항제철소 전경이며 광양 전기로의 설비 사진이 아닙니다. 불변 원문은 "
        "변경하지 않고 해당 이미지를 모든 독자용 문서에서 제외했습니다."
    ),
}
MEDIA_RIGHTS = {"permitted", "link_only", "ai_generated"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
SETTINGS_LIST_SECTIONS = {
    "분석 관점": "focus",
    "우선 기업": "companies",
    "우선 회사·사업축": "company_axes",
    "우선 기술": "technologies",
    "우선 프로젝트": "projects",
    "우선 국가": "countries",
    "중점 관찰 항목": "priority_predicates",
    "우선 출처 유형": "source_priority",
    "학술 탐색 범위": "academic_scope",
    "리스크 신호": "negative_signals",
    "보고서 중점": "report_sections",
}
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


def today() -> str:
    return date.today().isoformat()


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def validate_date(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD: {value}") from exc
    return value


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    doi = re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
        "",
        str(value).strip(),
        flags=re.IGNORECASE,
    ).strip()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi, flags=re.IGNORECASE):
        raise ValueError(f"Invalid DOI: {value}")
    return doi


def academic_metadata(args: argparse.Namespace) -> dict[str, Any] | None:
    supplied = getattr(args, "academic", None)
    if isinstance(supplied, dict):
        return supplied

    authors = list(
        dict.fromkeys(
            str(author).strip()
            for author in (getattr(args, "author", None) or [])
            if str(author).strip()
        )
    )
    metadata = {
        "kind": getattr(args, "academic_kind", None),
        "authors": authors,
        "venue": getattr(args, "venue", None),
        "doi": normalize_doi(getattr(args, "doi", None)),
        "conference_name": getattr(args, "conference_name", None),
        "conference_date": validate_date(
            getattr(args, "conference_date", None), "conference_date"
        ),
        "conference_location": getattr(args, "conference_location", None),
        "peer_review_status": getattr(args, "peer_review_status", None),
    }
    return {key: value for key, value in metadata.items() if value not in (None, [], "")}


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"URL must include scheme and host: {url}")
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ]
    path = re.sub(r"/+", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            urlencode(sorted(query)),
            "",
        )
    )


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def normalized_sha256(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_media_type(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    return "text/markdown"


def safe_slug(value: str, limit: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9가-힣]+", "-", value.casefold()).strip("-")
    return (slug[:limit].rstrip("-") or "item")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        handle.write(text)
        temp_name = handle.name
    replace_with_retry(temp_name, path)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=path.parent) as handle:
        handle.write(data)
        temp_name = handle.name
    replace_with_retry(temp_name, path)


def replace_with_retry(temp_name: str, path: Path, attempts: int = 10) -> None:
    """Replace a projection file despite short-lived Windows indexer locks."""
    try:
        for attempt in range(attempts):
            try:
                os.replace(temp_name, path)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        temp_path = Path(temp_name)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def write_json(path: Path, value: dict[str, Any]) -> None:
    if write_logical_json(path, value):
        inferred = infer_root_and_collection(path)
        if inferred is not None:
            root, collection = inferred
            if collection == "sources" and value.get("schema_version") == SOURCE_SCHEMA_VERSION:
                put_source_asset(root, value)
            elif collection == "claims" and value.get("claim_version_id"):
                put_claim_version(root, value)
            elif collection == "observations" and value.get("observation_version_id"):
                put_observation_version(root, value)
            elif collection == "events" and value.get("event_version_id"):
                put_event_version(root, value)
        return
    if path.name == "watchlist.json" and path.parent.name == "config":
        put_settings(path.parent.parent, "watchlist", value)
        return
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    logical = read_logical_json(path)
    if logical is not None:
        return logical
    if path.name == "watchlist.json" and path.parent.name == "config":
        settings = get_settings(path.parent.parent, "watchlist")
        if settings is not None:
            return settings
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def load_json_objects(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    logical = list_logical_json(directory)
    if logical is not None:
        return logical
    if not directory.exists():
        return []
    return [(path, read_json(path)) for path in sorted(directory.glob("*.json"))]


def append_log(root: Path, operation: str, detail: str) -> None:
    append_operation_log(root, timestamp(), operation, detail)


def emit(value: dict[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    try:
        print(payload)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((payload + "\n").encode("utf-8"))


def require_store(root: Path) -> Path:
    resolved = root.resolve()
    db_path = database_path(resolved)
    if not db_path.is_file():
        raise ValueError(
            "Not a market-sensing-intelligence SQLite store. Run scaffold or "
            f"migrate-to-sqlite first. Missing: {db_path}"
        )
    sync_settings_store(resolved)
    return resolved


def default_watchlist() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "companies": [
            "POSCO",
            "POSCO Holdings",
            "POSCO International",
            "POSCO E&C",
            "POSCO Future M",
            "POSCO Flow",
            "POSCO Mobility Solution",
            "POSCO Steeleon",
        ],
        "technologies": [],
        "projects": [],
        "countries": [],
        "source_priority": [
            "company_release",
            "company_ir",
            "government",
            "regulator",
            "permit",
            "exchange_filing",
            "industry_body",
            "specialist_media",
            "reputable_media",
        ],
        "academic_scope": [
            "journal_article",
            "conference_paper",
            "conference_presentation",
            "preprint",
        ],
        "negative_signals": [
            "delay",
            "postpone",
            "suspend",
            "cancel",
            "cost overrun",
            "permit denied",
            "funding withdrawn",
            "supply disruption",
            "price shock",
            "policy change",
            "sanction",
            "deadline",
            "competitor action",
        ],
        "search_overlap_days": 5,
        "claim_stale_days": 180,
    }


WIKI_SETTINGS_TEMPLATE = """# 포스코그룹 마켓센싱 관심사 설정

이 파일은 사람이 수정하는 최상위 설정입니다. `##` 제목은 바꾸지 말고 각 목록의
항목을 추가·삭제하세요. 비워도 되는 목록은 항목을 모두 지우면 됩니다.
다음 스킬 명령 실행 시 `market-sensing-wiki/config/watchlist.json`에 자동 반영됩니다.

## 분석 관점

- 포스코 철강사업에 직접적인 영향을 주는 외부 변화
- 포스코홀딩스 리튬사업에 직접적인 영향을 주는 외부 변화
- 포스코홀딩스 전략광물사업의 신규 진입·조달·가공·투자 조건을 바꾸는 외부 변화
- 포스코인터내셔널 에너지사업에 직접적인 영향을 주는 외부 변화
- 포스코인터내셔널 식량·팜사업의 곡물 생산·가공·유통·트레이딩과 팜 농장·정제,
  바이오연료 원료 조달 조건을 바꾸는 외부 변화
- 포스코이앤씨 건설·인프라사업에 직접적인 영향을 주는 외부 변화
- 포스코퓨처엠 이차전지소재사업에 직접적인 영향을 주는 외부 변화
- 포스코플로우 철강·원료 물류사업에 직접적인 영향을 주는 외부 변화
- 포스코모빌리티솔루션 구동모터코아·강건재가공사업에 직접적인 영향을 주는 외부 변화
- 포스코스틸리온 도금·컬러강판사업에 직접적인 영향을 주는 외부 변화
- 사용자가 조사 기간만 제시하면 모든 우선 기업을 자동 점검하고, 유효한 변화가 없는 회사는 Signal을 강제하지 않음
- 대상 회사를 직접 언급하지 않더라도 사업 영향 경로가 명확한 외부 변화
- 사업영향도와 긴급도에 기반한 정보 가치 판단
- 사업영향도와 긴급도는 각각 1~10점으로 평가하고 점수 근거와 평가 신뢰도를 함께 제시
- 회사 영향 경로가 확인되면 중요도가 낮아도 1~4점 관찰 Signal로 발행
- 8점은 상한이 아니며 전사 범위·즉시성·지연 손실·불가역성이 확인되면 10점 부여
- 조사일, 원문 발표일, 사건 발생일, 효력 발생일을 서로 구분하고 확인되지 않은 날짜는 추정하지 않음
- 회사 영향 경로가 불명확한 단순 산업 동향은 제외

## 우선 기업

- POSCO
- POSCO Holdings
- POSCO International
- POSCO E&C
- POSCO Future M
- POSCO Flow
- POSCO Mobility Solution
- POSCO Steeleon

## 우선 회사·사업축

- POSCO | 철강
- POSCO Holdings | 리튬·전략광물
- POSCO International | 에너지·식량·팜
- POSCO E&C | 건설·인프라
- POSCO Future M | 이차전지소재
- POSCO Flow | 철강·원료 물류
- POSCO Mobility Solution | 구동모터코아·강건재가공
- POSCO Steeleon | 도금·컬러강판

## 우선 기술


## 우선 프로젝트

## 우선 국가

## 중점 관찰 항목

- business_axis
- collected_at
- published_at
- event_date
- effective_date
- assessed_at
- business_impact_score_1_to_10
- business_impact_rationale
- urgency_score_1_to_10
- urgency_rationale
- assessment_confidence
- impact_path
- response_deadline
- affected_business
- recommended_follow_up

## 우선 출처 유형

- company_release
- company_ir
- government
- regulator
- permit
- exchange_filing
- industry_body
- specialist_media
- reputable_media

## 학술 탐색 범위

- journal_article
- conference_paper
- conference_presentation
- preprint

## 리스크 신호

- delay
- postpone
- suspend
- cancel
- cost overrun
- permit denied
- funding withdrawn
- supply disruption
- price shock
- policy change
- sanction
- deadline
- competitor action

## 보고서 중점

- 해당 정보가 연결되는 회사와 사업축
- 조사일시, 원문 발표일, 사건 발생일, 효력 발생일
- 발생한 사건과 확인된 사실
- 사업에 영향을 미치는 구체적인 경로
- 사업영향도 1~10점과 판단 근거
- 긴급도 1~10점, 대응 필요 시점과 판단 근거
- 평가 시각과 평가 신뢰도
- 임직원이 확인할 후속 관찰 항목
- 사실, 출처의 주장, AI 분석의 구분
- 영향 경로가 불명확한 단순 동향의 제외

## 운영 값

- 검색 겹침 일수: 5
- Claim 재검증 일수: 180
"""


def settings_path_for(root: Path) -> Path:
    return root.resolve().parent / "WIKI-SETTINGS.md"


def parse_markdown_settings(path: Path) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            heading = line[3:].strip()
            current_key = SETTINGS_LIST_SECTIONS.get(heading)
            if current_key:
                settings[current_key] = []
            elif heading == "운영 값":
                current_key = "operational_values"
            else:
                current_key = None
            continue
        if current_key is None:
            continue
        if not line.startswith("- "):
            if (
                current_key != "operational_values"
                and line
                and settings.get(current_key)
            ):
                settings[current_key][-1] += " " + line
            continue
        value = re.sub(r"^\[[ xX]\]\s*", "", line[2:].strip()).strip()
        if not value:
            continue
        if current_key == "operational_values":
            name, separator, raw_value = value.partition(":")
            if not separator:
                continue
            key = {
                "검색 겹침 일수": "search_overlap_days",
                "Claim 재검증 일수": "claim_stale_days",
            }.get(name.strip())
            if key:
                try:
                    parsed_value = int(raw_value.strip())
                except ValueError as exc:
                    raise ValueError(
                        f"{path.name}: {name.strip()} must be an integer"
                    ) from exc
                if parsed_value < 0:
                    raise ValueError(
                        f"{path.name}: {name.strip()} must not be negative"
                    )
                settings[key] = parsed_value
        else:
            settings[current_key].append(value)
    return settings


def effective_settings(root: Path) -> dict[str, Any]:
    sync_settings_store(root)
    settings = read_json(root / "config" / "watchlist.json")
    markdown_path = settings_path_for(root)
    if markdown_path.is_file():
        settings["settings_source"] = str(markdown_path)
    else:
        settings["settings_source"] = str(
            root / "config" / "watchlist.json"
        )
    return settings


def sync_settings_store(root: Path) -> dict[str, Any]:
    markdown_path = settings_path_for(root)
    json_path = root / "config" / "watchlist.json"
    current = get_settings(root, "watchlist")
    if current is None:
        current = default_watchlist()
        put_settings(root, "watchlist", current)
    if not markdown_path.is_file():
        return {
            "changed": False,
            "markdown": str(markdown_path),
            "database": str(database_path(root)),
        }
    updated = {**current, **parse_markdown_settings(markdown_path)}
    changed = updated != current
    if changed:
        write_json(json_path, updated)
    return {
        "changed": changed,
        "markdown": str(markdown_path),
        "database": str(database_path(root)),
    }


def sync_settings(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    if not database_path(root).is_file():
        raise ValueError(
            "Not a market-sensing-intelligence SQLite store. Run scaffold first. Missing: "
            + str(database_path(root))
        )
    result = sync_settings_store(root)
    return {"action": "settings_synced", **result}


def show_settings(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    return {"action": "settings", **effective_settings(root)}


STORE_AGENTS = """# Market Sensing Intelligence 저장소 지침

- 이 저장소의 최종 산출물은 MkDocs 사이트나 GUI가 아니라 단일 SQLite 스냅샷
  `data/market_sensing.db`입니다. 조사·검증·구조화·발행 결과와 근거 계보를 이 파일 안에
  완결된 데이터 계약으로 저장하세요.
- 이 SQLite 스냅샷은 별도 Codex 프로젝트 `WX_Hackathon_2026`의 MyPIN이 importer로 읽는
  입력 파일입니다. 스키마·데이터·관계·무결성·이식 가능성을 최우선으로 검증하고,
  소비 프로젝트가 파일 하나만으로 필요한 내용을 재현할 수 있게 하세요.
- 모든 영속 저장과 다른 프로그램으로의 전달은 `data/market_sensing.db` 파일 하나로
  끝내세요. 기계가 재사용할 내용은 가능한 한 자유서술 문자열보다 DB 안의
  `payload_json` 등 JSON 필드에 명시적인 키·타입·배열·객체로 구조화하고, 식별·검색·
  관계·무결성 값은 정규 SQLite 컬럼으로 보존하세요. Markdown은 사람용 표현이 필요할
  때만 DB TEXT에 병행하며 구조화 JSON을 대신하지 않습니다. JSON·Markdown 파일은
  임시 명령 입력으로만 사용하고 영속 산출물로 남기지 마세요.
- MkDocs 브라우저와 GUI는 SQLite 결과를 사람이 확인하는 중간 검증면입니다. 화면에만
  반영되거나 MyPIN importer가 읽을 수 없는 변경은 완료가 아니며, 브라우저 확인으로
  SQLite 저장과 무결성 검증을 대신하지 마세요.
- 사용자의 조사·Signal·저장·화면·검증 요구는 특정 문서 한 건의 수동 편집이 아니라
  Skill의 재현 가능한 공통 동작 변경으로 해석하세요. 특정 Signal은 수용 테스트 사례로
  사용하되, 사용자가 예외 범위를 명시하지 않는 한 ID·제목·주제를 하드코딩하지 말고
  다른 조사에도 같은 공용 명령·스키마·렌더러·검증이 적용되게 하세요. 사실 결론 자체는
  해당 Signal 근거에만 귀속하세요.
- 조사·검색·보고 전에 상위 `WIKI-SETTINGS.md`를 읽으세요.
- `조사해`, `조사만 해줘`는 모두 Source·Claim·Signal 발행과 검증까지 수행하세요.
  `저장하지 말 것`, `읽기 전용`, `초안만`이 명시된 경우에만 저장을 생략하세요.
- 조사 결과를 저장하는 작업은 Source·Claim에서 끝내지 말고 `add-signal`로 관측 변화
  제목, 변화 유형, 사업 시사점, 문단 Insight, UI용 구조화 분석 JSON, 읽기용 산문 분석을
  연결한 뒤 MkDocs
  화면까지 검증하세요.
- 구조화 분석은 `analysis_structured`, 산문은 `analysis_markdown`으로 같은 SQLite Insight
  `payload_json`에 저장하며 별도 보고서 링크로 대신하지 마세요.
- Signal 상세는 제목·분류 배지 바로 다음부터 구조화/산문 탭을 시작하세요. 구조화 탭은
  시나리오·사업 영향·키 드라이버·근거와 시점·반증과 다음 행동을 JSON 필드로 렌더링하고,
  산문 탭은 고정 목차를 덧붙이지 않은 자연스러운 리서치 본문을 그대로 렌더링하세요.
  연결 원문만 탭 아래 공통 영역에 둡니다.
- Signal 작성 전 `../skills/market-sensing-intelligence/references/signal-analysis-template.md`를 읽으세요.
- Signal 제목·사업 시사점·문단 작성 전
  `../skills/market-sensing-intelligence/references/editorial-style.md`를 읽고 평이한
  한국어를 사용하세요. 제목은 관측된 변화만 짧게 적고 사업영향은 완전문장인
  `사업 시사점`으로 분리하세요.
- Signal에는 `정책·규제`, `수급·가격`, `경쟁사`, `투자·프로젝트`, `공급망·물류`,
  `고객·계약`, `기술·운영`, `재무·실적` 중 하나의 변화 유형을 저장하세요. 사람 화면에는
  회사 pill 1개, 사업축 pill 1개와 변화 유형 pill 1개를 회사 → 사업축 → 변화 유형
  순서로 표시하고 회사명을 일반 텍스트로 반복하지 마세요.
- 외부 시장·정책·경쟁사·거래상대 변화는 `core_market_signal`, 대상 회사의 투자·증산·
  실적·공정 진척은 `execution_context/company_execution`으로 분리하세요. 회사 자체 발표만
  근거인 실행 사실을 core로 발행하지 말고, run×사업축마다 core 비중 70% 이상을 유지하세요.
- What-if는 Signal의 기본 구성입니다. 주제가 정량 영향과 본질적으로 맞지 않거나 동일
  충격을 대표 Signal에서 이미 계산한 경우가 아니면 공개정보와 합리적 대용변수로
  영향액을 숫자로 먼저 제시하는 방어·기준·압박 모델을 만들고 `set-impact-estimate`로 연결하세요. 내부값 비공개는
  생략 사유가 아닙니다. 모든 Insight는 `quantification_decision.status`를 `modeled` 또는
  `not_applicable` JSON으로 저장하고 `deferred`·`내부 입력 대기`를 사용하지 마세요.
  핵심 가정 3~8개는 근거·단위·범위를 가진 슬라이더와 직접입력으로 조정되게 하세요.
- 총노출액과 순영향액을 구분하고 가격·물량·원가·계약 전가·대응비용을 사업이론에 맞게
  분해하세요. 회사 실제값이 아니면 낮은 신뢰도와 넓은 범위를 명시하고 중복효과를
  합산하지 마세요.
- `.system/raw/`의 등록 원문을 수정하거나 삭제하지 마세요.
- 수치·날짜·일정·투자비·용량은 `.system/claims/`의 원자적 claim으로 관리하세요.
- 기존 주장과 다른 값은 자동 덮어쓰지 말고 `.system/reviews/pending/`으로 보내세요.
- 오래된 정보는 삭제하지 말고 `superseded`, `disputed`, `cancelled`, `stale`로 전환하세요.
- `index.md`, `REVIEW.md`, 회사·기술·프로젝트·출처 문서는 자동 생성본입니다.
- 사실과 AI 분석을 분리하고 모든 핵심 사실은 내부 Claim과 Source로 추적하세요.
  MkDocs 본문에는 Claim ID·predicate·raw 경로 같은 시스템 필드를 노출하지 마세요.
- 설비·공정 이미지가 필요하면 `add-image`로 Source에 연결하고 원문·캡션·유형·권리 상태를 기록하세요.
- 권리가 불명확한 이미지는 복제하지 말고 `link_only`로 원문 링크만 보존하세요.
- 검색 범위, 쿼리, 접근 실패를 `.system/runs/`에 기록하세요.
"""

TREND_REPORT_INDEX = """# 동향 보고서

> 마지막 기준일 이후 새로 확인되거나 달라진 우선 기업의 사업축에 영향을 주는 외부 변화만
> 모아 보는 변화 중심 브리프입니다.

!!! abstract "현재 발행 상태"

    **아직 발행된 동향 보고서가 없습니다.**

    첫 보고서가 발행되면 최신 보고서부터 이 페이지에 표시됩니다.

## 보고서에서 바로 확인할 내용

| 구분 | 확인 내용 |
| --- | --- |
| **사업 영향** | 영향을 받는 회사·사업축과 구체적인 영향 경로 |
| **판단 가치** | 사업영향도·긴급도와 그 판단 근거 |
| **후속 대응** | 확인 시점, 담당 관점, 추가 관찰 항목 |

## 읽는 순서

1. 상단 요약에서 보고 기간과 핵심 변화 건수를 확인합니다.
2. 변화 표에서 기업·프로젝트별 최신 상태와 근거를 확인합니다.
3. 위험 신호와 사람 검토 대기 항목을 별도로 확인합니다.
4. `AI 분석`은 확인된 사실과 구분해 참고합니다.

## 발행된 보고서

!!! info "발행 대기"

    현재 표시할 보고서가 없습니다. 조사와 근거 검증이 완료된 보고서만 이 목록에
    추가됩니다.

??? info "운영 안내"

    위키가 실행 중이면 새로 생성되거나 수정된 보고서는 자동으로 화면에 반영됩니다.
    이 화면은 저장된 보고서를 보여주며, 새로운 자료 조사와 보고서 작성은 별도의
    Market Sensing Intelligence 작업에서 수행됩니다.
"""


def scaffold(root: Path) -> dict[str, Any]:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    db_path = database_path(root)
    database_existed = db_path.exists()
    initialize_sqlite(root)
    if not database_existed:
        created.append(str(db_path.relative_to(root)))
    if get_settings(root, "watchlist") is None:
        put_settings(root, "watchlist", default_watchlist())
        created.append("sqlite:wiki_settings/watchlist")

    settings_path = settings_path_for(root)
    if not settings_path.exists():
        atomic_write_text(settings_path, WIKI_SETTINGS_TEMPLATE)
        created.append("../WIKI-SETTINGS.md")

    append_log(root, "scaffold", "Created or verified the market sensing intelligence store.")
    return {
        "action": "scaffolded",
        "root": str(root),
        "database": str(db_path),
        "created": created,
        "storage": "sqlite",
    }


def source_records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return load_json_objects(root / SOURCE_RECORDS_DIR)


def source_record_by_id(root: Path, source_id: str) -> tuple[Path, dict[str, Any]]:
    path = root / SOURCE_RECORDS_DIR / f"{source_id}.json"
    record = read_logical_json(path)
    if record is None:
        raise ValueError(f"Unknown source ID: {source_id}")
    return path, record


def token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9가-힣]{3,}", normalize_text(text)[:120_000]))


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def near_duplicate_candidates(
    root: Path,
    title: str,
    content: str,
    records: list[tuple[Path, dict[str, Any]]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    incoming_tokens = token_set(content)
    for _, record in records:
        title_score = SequenceMatcher(
            None, normalize_text(title), normalize_text(record.get("title", ""))
        ).ratio()
        content_score = 0.0
        existing_bytes = get_source_content(root, str(record.get("source_id", "")))
        if existing_bytes is not None:
            existing = existing_bytes.decode("utf-8", errors="replace")
            content_score = jaccard(incoming_tokens, token_set(existing))
        if content_score >= 0.90 or (title_score >= 0.90 and content_score >= 0.72):
            candidates.append(
                {
                    "source_id": record["source_id"],
                    "title_similarity": round(title_score, 3),
                    "content_similarity": round(content_score, 3),
                }
            )
    return sorted(
        candidates,
        key=lambda item: (item["content_similarity"], item["title_similarity"]),
        reverse=True,
    )


def next_source_id(collected_at: str, content_hash: str, records_dir: Path) -> str:
    compact_date = collected_at.replace("-", "")
    inferred = collection_for_directory(records_dir)
    root = inferred[0] if inferred else records_dir.parent.parent
    for length in (8, 10, 12, 16, 32, 64):
        source_id = f"SRC-{compact_date}-{content_hash[:length].upper()}"
        if not record_exists(root, "sources", source_id):
            return source_id
    raise RuntimeError("Could not allocate a unique source ID")


def add_supporting_source(
    root: Path,
    related_source: str,
    title: str,
    url: str | None,
    publisher: str,
    published_at: str | None,
) -> dict[str, Any]:
    path, record = source_record_by_id(root, related_source)
    canonical_url = canonicalize_url(url)
    supporting = record.setdefault("supporting_sources", [])
    if canonical_url and any(
        item.get("canonical_url") == canonical_url for item in supporting
    ):
        return {
            "action": "supporting_source_exists",
            "source_id": related_source,
            "canonical_url": canonical_url,
        }
    supporting.append(
        {
            "title": title,
            "url": url,
            "canonical_url": canonical_url,
            "publisher": publisher,
            "published_at": published_at,
            "collected_at": today(),
        }
    )
    write_json(path, record)
    sync_obsidian_store(root)
    append_log(
        root,
        "supporting-source",
        f"Added a republication/supporting URL to {related_source}: {url or title}",
    )
    return {
        "action": "supporting_source",
        "source_id": related_source,
        "canonical_url": canonical_url,
    }


def create_duplicate_review(
    root: Path,
    content_path: Path,
    metadata: dict[str, Any],
    candidates: list[dict[str, Any]],
    content_hash: str,
) -> dict[str, Any]:
    review_id = f"REV-DUP-{content_hash[:12].upper()}"
    candidate_text = content_path.read_text(encoding="utf-8", errors="replace")
    put_artifact(
        root,
        review_id,
        "source_candidate",
        str(metadata.get("title") or review_id),
        markdown_text=candidate_text,
        metadata={"content_sha256": content_hash},
    )
    review = {
        "review_id": review_id,
        "type": "duplicate_candidate",
        "created_at": timestamp(),
        "candidate_artifact_id": review_id,
        "candidate": metadata,
        "possible_duplicates": candidates,
        "allowed_decisions": ["supporting", "accept-new", "reject"],
        "status": "pending",
    }
    review_path = root / PENDING_REVIEWS_DIR / f"{review_id}.json"
    write_json(review_path, review)
    sync_obsidian_store(root)
    append_log(
        root,
        "review-required",
        f"{review_id}: possible duplicate of "
        + ", ".join(item["source_id"] for item in candidates),
    )
    return {
        "action": "review_required",
        "review_id": review_id,
        "type": "duplicate_candidate",
        "candidates": candidates,
    }


def add_source(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    content_path = Path(args.content_file).resolve()
    if not content_path.is_file():
        raise ValueError(f"Content file does not exist: {content_path}")
    validate_date(args.published_at, "published_at")
    collected_at = validate_date(args.collected_at, "collected_at") or today()
    if args.source_type not in SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {args.source_type}")
    source_modality = validate_modality(getattr(args, "source_modality", None))
    if args.reliability not in SOURCE_RELIABILITY:
        raise ValueError(f"Invalid reliability: {args.reliability}")
    academic = academic_metadata(args)
    if args.source_type == "academic":
        if not academic or academic.get("kind") not in ACADEMIC_KINDS:
            raise ValueError(
                "academic sources require --academic-kind "
                f"({', '.join(sorted(ACADEMIC_KINDS))})"
            )
    elif academic:
        raise ValueError("Academic metadata requires source_type=academic")

    if args.supporting_of:
        return add_supporting_source(
            root,
            args.supporting_of,
            args.title,
            args.url,
            args.publisher,
            args.published_at,
        )

    raw_bytes = content_path.read_bytes()
    byte_hash = raw_sha256(raw_bytes)
    media_type = source_media_type(raw_bytes)
    content = raw_bytes.decode("utf-8") if media_type.startswith("text/") else ""
    content_hash = normalized_sha256(content) if content else byte_hash
    records = source_records(root)

    for _, record in records:
        if record.get("content_sha256") == content_hash:
            return {
                "action": "exact_duplicate",
                "source_id": record["source_id"],
                "title": record.get("title"),
            }

    canonical_url = canonicalize_url(args.url)
    url_versions = [
        record
        for _, record in records
        if canonical_url and record.get("canonical_url") == canonical_url
    ]
    previous_version = (
        sorted(
            url_versions,
            key=lambda item: (
                item.get("published_at") or "",
                item.get("collected_at") or "",
            ),
        )[-1]["source_id"]
        if url_versions
        else None
    )

    candidates = (
        near_duplicate_candidates(root, args.title, content, records)
        if content
        else []
    )
    metadata = {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "title": args.title,
        "url": args.url,
        "canonical_url": canonical_url,
        "publisher": args.publisher,
        "published_at": args.published_at,
        "collected_at": collected_at,
        "source_type": args.source_type,
        "source_modality": source_modality,
        "language": args.language,
        "reliability": args.reliability,
        "content_sha256": content_hash,
        "media_type": media_type,
        **({"academic": academic} if academic else {}),
    }
    if candidates and not args.force:
        return create_duplicate_review(
            root, content_path, metadata, candidates, content_hash
        )

    records_dir = root / SOURCE_RECORDS_DIR
    source_id = next_source_id(collected_at, content_hash, records_dir)
    record = {
        "source_id": source_id,
        **metadata,
        "raw_sha256": byte_hash,
        "raw_ref": f"sqlite:wiki_source_contents:{source_id}",
        "previous_version": previous_version,
        "supporting_sources": [],
        "images": [],
    }
    write_json(records_dir / f"{source_id}.json", record)
    put_source_asset(root, record)
    put_source_content(root, source_id, raw_bytes, media_type=media_type)
    sync_obsidian_store(root)
    append_log(
        root,
        "add-source",
        f"{source_id}: {args.title}"
        + (f" (new version of {previous_version})" if previous_version else ""),
    )
    return {
        "action": "created",
        "source_id": source_id,
        "raw_ref": record["raw_ref"],
        "previous_version": previous_version,
    }


def set_academic_metadata(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    record_path, record = source_record_by_id(root, args.source_id)
    if record.get("source_type") != "academic":
        raise ValueError(
            f"{args.source_id} has source_type={record.get('source_type')!r}; "
            "academic metadata requires source_type=academic"
        )
    metadata = academic_metadata(args)
    if not metadata or metadata.get("kind") not in ACADEMIC_KINDS:
        raise ValueError(
            "academic metadata requires --academic-kind "
            f"({', '.join(sorted(ACADEMIC_KINDS))})"
        )
    existing = record.get("academic")
    merged = dict(existing) if isinstance(existing, dict) else {}
    merged.update(metadata)
    record["academic"] = merged
    published_at = validate_date(
        getattr(args, "published_at", None), "published_at"
    )
    if published_at:
        record["published_at"] = published_at
    write_json(record_path, record)
    sync_obsidian_store(root)
    append_log(
        root,
        "academic-metadata",
        f"Updated academic metadata for {args.source_id}: "
        f"{merged.get('kind')} {merged.get('doi') or ''}".strip(),
    )
    return {
        "action": "academic_metadata_updated",
        "source_id": args.source_id,
        "academic": merged,
    }


def image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("Unsupported image format. Use PNG, JPEG, GIF, or WebP.")


def web_url(value: str | None, name: str) -> str | None:
    canonical = canonicalize_url(value)
    if canonical and urlsplit(canonical).scheme not in {"http", "https"}:
        raise ValueError(f"{name} must use http or https")
    return canonical


def add_image(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    record_path, record = source_record_by_id(root, args.source_id)
    image_file_value = getattr(args, "image_file", None)
    image_url_value = getattr(args, "image_url", None)
    display_width = getattr(args, "display_width", None)
    hero_priority = getattr(args, "hero_priority", None)
    if bool(image_file_value) == bool(image_url_value):
        raise ValueError("Provide exactly one of --image-file or --image-url")
    if args.kind not in MEDIA_KINDS:
        raise ValueError(f"Invalid image kind: {args.kind}")
    if args.rights_status not in MEDIA_RIGHTS:
        raise ValueError(f"Invalid rights_status: {args.rights_status}")
    if not str(args.caption).strip():
        raise ValueError("caption is required")
    if not str(args.rights_note).strip():
        raise ValueError("rights_note is required")
    if args.kind == "ai_reconstruction" and args.rights_status != "ai_generated":
        raise ValueError("ai_reconstruction must use rights_status=ai_generated")
    if args.rights_status == "ai_generated" and args.kind != "ai_reconstruction":
        raise ValueError("rights_status=ai_generated requires kind=ai_reconstruction")
    if args.rights_status == "link_only" and not image_url_value:
        raise ValueError("link_only images require --image-url")
    if display_width not in {None, "compact", "detail"}:
        raise ValueError("display_width must be compact or detail")
    if hero_priority is not None and not -1000 <= int(hero_priority) <= 1000:
        raise ValueError("hero_priority must be between -1000 and 1000")
    subject_ids = list(
        dict.fromkeys(
            str(item).strip()
            for item in getattr(args, "subject_id", []) or []
            if str(item).strip()
        )
    )

    image_url = web_url(image_url_value, "image_url")
    origin_url = web_url(
        getattr(args, "origin_url", None) or record.get("url") or image_url,
        "origin_url",
    )
    if not origin_url:
        raise ValueError("origin_url is required when the source has no URL")

    data: bytes | None = None
    extension: str | None = None
    if args.rights_status != "link_only":
        if image_file_value:
            image_file = Path(image_file_value).resolve()
            if not image_file.is_file():
                raise ValueError(f"Image file does not exist: {image_file}")
            data = image_file.read_bytes()
        else:
            assert image_url is not None
            request = Request(
                image_url,
                headers={"User-Agent": "SteelIntelligenceWiki/1.0"},
            )
            with urlopen(request, timeout=20) as response:
                data = response.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("Image exceeds the 20 MB limit")
        extension = image_extension(data)

    fingerprint = raw_sha256(
        data
        if data is not None
        else f"{args.source_id}\x1f{image_url}\x1f{args.caption}".encode("utf-8")
    )
    media_id = f"MED-{fingerprint[:12].upper()}"
    images = record.setdefault("images", [])
    if any(item.get("media_id") == media_id for item in images):
        return {
            "action": "image_exists",
            "source_id": args.source_id,
            "media_id": media_id,
        }

    local_ref: str | None = None
    if data is not None and extension is not None:
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }[extension]
        put_binary_asset(
            root,
            media_id,
            data,
            source_id=args.source_id,
            media_type=media_type,
            metadata={"extension": extension},
        )
        local_ref = f"sqlite:wiki_binary_assets:{media_id}"

    images.append(
        {
            "media_id": media_id,
            "kind": args.kind,
            "caption": str(args.caption).strip(),
            "alt_text": str(getattr(args, "alt_text", None) or args.caption).strip(),
            "creator": str(getattr(args, "creator", None) or "").strip() or None,
            "image_url": image_url,
            "origin_url": origin_url,
            "rights_status": args.rights_status,
            "rights_note": str(args.rights_note).strip(),
            "collected_at": today(),
            "content_sha256": fingerprint if data is not None else None,
            "local_ref": local_ref,
            **({"subject_ids": subject_ids} if subject_ids else {}),
            **({"display_width": display_width} if display_width else {}),
            **(
                {"hero_priority": int(hero_priority)}
                if hero_priority is not None
                else {}
            ),
        }
    )
    write_json(record_path, record)
    sync_obsidian_store(root)
    append_log(
        root,
        "add-image",
        f"{media_id}: attached to {args.source_id} ({args.kind}, {args.rights_status})",
    )
    return {
        "action": "image_added",
        "source_id": args.source_id,
        "media_id": media_id,
        "local_ref": local_ref,
    }


def claim_id_for(subject_id: str, predicate: str, value: str) -> str:
    digest = hashlib.sha256(
        "\x1f".join(
            [subject_id.strip().upper(), predicate.strip().casefold(), normalize_text(value)]
        ).encode("utf-8")
    ).hexdigest()
    return f"CLM-{digest[:12].upper()}"


def claim_records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return load_json_objects(root / CLAIMS_DIR)


def signal_records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return load_json_objects(root / SIGNALS_DIR)


def signal_version_records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return load_json_objects(root / SIGNAL_VERSIONS_DIR)


def insight_records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return load_json_objects(root / INSIGHTS_DIR)


def risk_factor_records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return load_json_objects(root / RISK_FACTORS_DIR)


def observation_records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return load_json_objects(root / OBSERVATIONS_DIR)


def event_records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return load_json_objects(root / EVENTS_DIR)


def systematic_analysis_records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return load_json_objects(root / SYSTEMATIC_ANALYSES_DIR)


def verify_risk_factor_ids(root: Path, risk_factor_ids: list[str]) -> None:
    known = {
        str(record.get("risk_factor_id"))
        for _, record in risk_factor_records(root)
        if record.get("status") == "active"
    }
    missing = sorted(set(risk_factor_ids) - known)
    if missing:
        raise ValueError("Unknown active risk factor IDs: " + ", ".join(missing))


def add_risk_factor(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    value = validate_risk_factor(
        {
            "risk_factor_id": args.risk_factor_id,
            "taxonomy_version": args.taxonomy_version,
            "name": args.name,
            "definition": args.definition,
            "category": args.category,
            "parent_risk_factor_id": args.parent_risk_factor_id,
            "aliases": args.alias or [],
            "status": args.status,
            "valid_from": args.valid_from,
            "valid_to": args.valid_to,
        }
    )
    parent = value.get("parent_risk_factor_id")
    if parent:
        verify_risk_factor_ids(root, [str(parent)])
    put_risk_factor(root, value)
    append_log(root, "add-risk-factor", f"{value['risk_factor_id']}: {value['name']}")
    return {"action": "risk_factor_created", **value}


def add_observation(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    verify_source_ids(root, [args.source_id])
    verify_source_modality(root, [args.source_id], args.modality)
    verify_risk_factor_ids(root, args.risk_factor_id)
    try:
        numeric_value: object = float(args.value)
    except ValueError:
        numeric_value = args.value
    value = observation_version(
        {
            "observation_id": args.observation_id,
            "version_no": args.version_no,
            "series_key": args.series_key,
            "metric_kind": args.metric_kind,
            "value": numeric_value,
            "unit": args.unit,
            "observed_at": args.observed_at,
            "source_id": args.source_id,
            "modality": args.modality,
            "risk_factor_ids": args.risk_factor_id,
            "verification_status": args.verification_status,
        }
    )
    write_json(
        root / OBSERVATIONS_DIR / f"{value['observation_version_id']}.json", value
    )
    put_observation_version(root, value)
    put_risk_factor_links(
        root,
        subject_kind="observation",
        subject_version_id=value["observation_version_id"],
        risk_factor_ids=value["risk_factor_ids"],
        created_at=value["created_at"],
    )
    return {"action": "observation_created", **value}


def add_event(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    verify_source_ids(root, args.source_id)
    verify_source_modality(root, args.source_id, args.modality)
    verify_risk_factor_ids(root, args.risk_factor_id)
    value = event_version(
        {
            "event_id": args.event_id,
            "version_no": args.version_no,
            "event_type": args.event_type,
            "actor_ref": args.actor_ref,
            "target_ref": args.target_ref,
            "observed_at": args.observed_at,
            "effective_at": args.effective_at,
            "before_value": args.before_value,
            "after_value": args.after_value,
            "unit": args.unit,
            "source_ids": args.source_id,
            "modality": args.modality,
            "risk_factor_ids": args.risk_factor_id,
            "status": args.status,
        }
    )
    write_json(root / EVENTS_DIR / f"{value['event_version_id']}.json", value)
    put_event_version(root, value)
    put_risk_factor_links(
        root,
        subject_kind="event",
        subject_version_id=value["event_version_id"],
        risk_factor_ids=value["risk_factor_ids"],
        created_at=value["created_at"],
    )
    return {"action": "event_created", **value}


def run_systematic_signal_analysis(args: argparse.Namespace) -> dict[str, Any]:
    """Run and persist version-pinned statistical candidate evidence."""

    root = require_store(Path(args.root))
    signal = _records_by_id(signal_records(root), "signal_id").get(args.signal_id)
    if signal is None:
        raise ValueError(f"Unknown signal ID: {args.signal_id}")
    signal_version_id = str(signal.get("signal_version_id") or "")
    spec_path = Path(args.spec_file).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    declared_version = str(spec.get("signal_version_id") or "")
    if declared_version and declared_version != signal_version_id:
        raise ValueError(
            "analysis spec signal_version_id must match the Signal's active immutable version"
        )
    spec["signal_version_id"] = signal_version_id
    observations = _records_by_id(observation_records(root), "observation_version_id")
    result = run_systematic_analysis(spec, observations)

    known_versions = {
        str(record.get("signal_version_id")) for _, record in signal_version_records(root)
    }
    components = result["analysis_scope"]["component_signal_version_ids"]
    missing_components = sorted(set(components) - known_versions)
    if missing_components:
        raise ValueError(
            "Unknown component Signal versions: " + ", ".join(missing_components)
        )
    verify_risk_factor_ids(
        root,
        list(dict.fromkeys(item["risk_factor_id"] for item in result["input_series"])),
    )
    put_systematic_analysis(root, result)

    insight_id = str(signal.get("insight_id") or "")
    insight_path = root / INSIGHTS_DIR / f"{insight_id}.json"
    insight = read_json(insight_path)
    candidates = result["results"]["risk_factor_contribution"]
    risk_factor_names = {
        str(record.get("risk_factor_id")): str(record.get("name") or "").strip()
        for _, record in risk_factor_records(root)
    }
    insight["systematic_analytics"] = {
        "schema_version": 1,
        "latest_result_version_id": result["analysis_result_version_id"],
        "status": result["status"],
        "as_of": result["as_of"],
        "analysis_scope": result["analysis_scope"],
        "method_types": result["method_types"],
        "risk_factor_candidates": [
            {
                "label": risk_factor_names.get(
                    str(candidate["risk_factor_id"]), "확인할 시장 변수"
                ),
                "contribution_score": candidate["contribution_score"],
                "basis_count": candidate["basis_count"],
            }
            for candidate in candidates
        ],
        "limitations": result["limitations"],
    }
    insight["updated_at"] = timestamp()
    write_json(insight_path, insight)
    sync_obsidian_store(root)
    append_log(
        root,
        "run-systematic-analysis",
        f"{args.signal_id}: {result['analysis_result_version_id']} ({result['status']})",
    )
    return {
        "action": "systematic_analysis_created",
        "signal_id": args.signal_id,
        "analysis_result_version_id": result["analysis_result_version_id"],
        "status": result["status"],
        "candidate_count": len(candidates),
        "content_digest": result["content_digest"],
    }


def run_record_by_id(root: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    for path, record in load_json_objects(root / RUNS_DIR):
        if str(record.get("run_id") or "") == run_id:
            return path, record
    raise ValueError(f"Unknown run ID: {run_id}")


def required_research_cells(
    settings: dict[str, Any],
    *,
    company_ids: list[str] | None = None,
    business_axes: list[str] | None = None,
) -> list[dict[str, str]]:
    """Freeze every configured company/business-axis cell into a research run."""
    cells: list[dict[str, str]] = []
    unknown: list[str] = []
    for raw_name in settings.get("companies", []):
        company_name = str(raw_name).strip()
        company_id = COMPANY_NAME_TO_ID.get(company_name)
        if not company_id:
            unknown.append(company_name or "<blank>")
            continue
        axes = MARKET_SENSING_COMPANY_AXES.get(company_id, ())
        if not axes:
            unknown.append(company_name)
            continue
        cells.extend(
            {"company_id": company_id, "business_axis": business_axis}
            for business_axis in axes
        )
    if unknown:
        raise ValueError(
            "priority companies are missing governed company/business-axis mappings: "
            + ", ".join(unknown)
        )
    selected_company_ids = {
        str(company_id).strip() for company_id in (company_ids or []) if str(company_id).strip()
    }
    unknown_company_ids = sorted(selected_company_ids - set(MARKET_SENSING_COMPANY_AXES))
    if unknown_company_ids:
        raise ValueError(
            "unknown explicit company IDs: " + ", ".join(unknown_company_ids)
        )
    selected_axes = {
        str(business_axis).strip()
        for business_axis in (business_axes or [])
        if str(business_axis).strip()
    }
    unknown_axes = sorted(selected_axes - ALL_MARKET_SENSING_AXES)
    if unknown_axes:
        raise ValueError("unknown explicit business axes: " + ", ".join(unknown_axes))
    if selected_company_ids:
        cells = [cell for cell in cells if cell["company_id"] in selected_company_ids]
    if selected_axes:
        cells = [cell for cell in cells if cell["business_axis"] in selected_axes]
    if not cells:
        raise ValueError(
            "research run requires at least one company/axis cell after explicit scope filters"
        )
    return cells


def initial_research_coverage(
    required_cells: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "cells_checked": [
            {
                **cell,
                "status": "pending",
                "channels": [],
                "search_strategies": [],
                "candidate_ids": [],
                "limitations": [],
                "next_trigger": "",
            }
            for cell in required_cells
        ],
        "candidates": [],
        "high_risk_gaps": [],
        "limitations": [],
        "next_triggers": [],
        "no_signal_reasons_by_company": {},
    }


def evaluate_research_coverage(
    run: dict[str, Any], signals: list[dict[str, Any]]
) -> list[str]:
    """Reject completed runs that can hide untouched or thinly searched cells."""
    run_id = str(run.get("run_id") or "<unknown-run>")
    contract = run.get("research_contract")
    if not isinstance(contract, dict) or int(contract.get("version") or 0) < 1:
        return []
    contract_version = int(contract.get("version") or 0)
    mode = str(contract.get("mode") or "coverage_managed")
    if mode == "count_limited":
        target_count = contract.get("target_count")
        if (
            not isinstance(target_count, int)
            or isinstance(target_count, bool)
            or target_count < 1
        ):
            return [f"{run_id}: count-limited research needs a positive target_count"]
        listed_signal_ids = {
            str(signal_id).strip()
            for signal_id in run.get("signal_ids", [])
            if str(signal_id).strip()
        }
        published_signal_ids = {
            str(signal.get("signal_id") or "").strip()
            for signal in signals
            if signal.get("status", "active") == "active"
            and str(signal.get("signal_id") or "").strip()
            in listed_signal_ids
        }
        if len(published_signal_ids) < target_count:
            return [
                f"{run_id}: count-limited research published "
                f"{len(published_signal_ids)}/{target_count} requested Signals"
            ]
        return []
    if mode not in {"coverage_managed", "user_scoped"}:
        return [f"{run_id}: unknown research mode {mode!r}"]
    required_raw = contract.get("required_company_axes")
    if not isinstance(required_raw, list) or not required_raw:
        return [f"{run_id}: research contract has no required company/axis cells"]

    findings: list[str] = []
    required: list[tuple[str, str]] = []
    for index, item in enumerate(required_raw):
        if not isinstance(item, dict):
            findings.append(f"{run_id}: required cell #{index + 1} must be an object")
            continue
        pair = (
            str(item.get("company_id") or "").strip(),
            str(item.get("business_axis") or "").strip(),
        )
        if not all(pair):
            findings.append(f"{run_id}: required cell #{index + 1} is incomplete")
            continue
        if pair in required:
            findings.append(f"{run_id}: duplicate required cell {pair[0]}/{pair[1]}")
            continue
        required.append(pair)

    coverage = run.get("coverage")
    if not isinstance(coverage, dict):
        return [*findings, f"{run_id}: completed research run has no coverage ledger"]
    if coverage.get("schema_version") != 1:
        findings.append(f"{run_id}: coverage schema_version must be 1")

    candidates_by_id: dict[str, dict[str, Any]] = {}
    candidate_fingerprints: dict[tuple[str, str, str, str], str] = {}
    candidates_by_day: Counter[str] = Counter()
    published_signal_ids_by_day: dict[str, set[str]] = defaultdict(set)
    published_date_by_signal_id: dict[str, str] = {}
    signals_by_id = {
        str(signal.get("signal_id") or "").strip(): signal
        for signal in signals
        if str(signal.get("signal_id") or "").strip()
    }
    candidates = coverage.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
        findings.append(f"{run_id}: coverage.candidates must be a list")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            findings.append(f"{run_id}: candidate #{index + 1} must be an object")
            continue
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if not candidate_id:
            findings.append(f"{run_id}: candidate #{index + 1} needs candidate_id")
            continue
        if candidate_id in candidates_by_id:
            findings.append(f"{run_id}: duplicate candidate {candidate_id}")
            continue
        candidates_by_id[candidate_id] = candidate
        if contract_version < 3:
            continue
        # Historical backfills are dense by the date represented by the source.
        # detected_at remains the honest first-known date and must not be backdated
        # merely to pass the daily-density gate. Older v4 ledgers did not have
        # candidate_date, so retain detected_at as a read-only fallback.
        candidate_date_value = candidate.get("candidate_date") or candidate.get(
            "detected_at"
        )
        try:
            candidate_date = validate_date(candidate_date_value, "candidate_date")
        except ValueError:
            candidate_date = None
        if not candidate_date or not (
            str(run.get("date_from")) <= candidate_date <= str(run.get("date_to"))
        ):
            findings.append(
                f"{run_id}/{candidate_id}: candidate_date must be inside the run period"
            )
        else:
            candidates_by_day[candidate_date] += 1
        if candidate.get("detected_at") is not None:
            try:
                validate_date(candidate.get("detected_at"), "detected_at")
            except ValueError:
                findings.append(
                    f"{run_id}/{candidate_id}: detected_at must be a valid first-known date"
                )
        company_id = str(candidate.get("company_id") or "").strip()
        business_axis = str(candidate.get("business_axis") or "").strip()
        if not company_supports_business_axis(company_id, business_axis):
            findings.append(f"{run_id}/{candidate_id}: invalid company/business-axis pair")
        change_type = str(candidate.get("change_type") or "").strip()
        if change_type not in SIGNAL_TYPES:
            findings.append(f"{run_id}/{candidate_id}: invalid change_type {change_type!r}")
        if len(str(candidate.get("title") or "").strip()) < 10:
            findings.append(f"{run_id}/{candidate_id}: title must describe the observed change")
        try:
            source_url = canonicalize_url(candidate.get("source_url"))
        except ValueError:
            source_url = None
        if not source_url or urlsplit(source_url).scheme not in {"http", "https"}:
            findings.append(f"{run_id}/{candidate_id}: source_url is required")
        title = " ".join(str(candidate.get("title") or "").casefold().split())
        fingerprint = (company_id, business_axis, source_url or "", title)
        previous_candidate_id = candidate_fingerprints.get(fingerprint)
        if previous_candidate_id:
            findings.append(
                f"{run_id}/{candidate_id}: duplicates observed change {previous_candidate_id}"
            )
        else:
            candidate_fingerprints[fingerprint] = candidate_id
        disposition = str(candidate.get("disposition") or "").strip()
        if disposition not in RESEARCH_CANDIDATE_DISPOSITIONS:
            findings.append(f"{run_id}/{candidate_id}: invalid disposition {disposition!r}")
        if disposition in {"watchlist", "rejected"} and len(str(candidate.get("reason") or "").strip()) < 12:
            findings.append(f"{run_id}/{candidate_id}: {disposition} needs a specific reason")
        if disposition == "published_signal":
            signal_id = str(candidate.get("signal_id") or "").strip()
            signal = signals_by_id.get(signal_id)
            if not signal_id:
                findings.append(f"{run_id}/{candidate_id}: published_signal needs signal_id")
            elif signal is None or signal.get("status", "active") != "active":
                findings.append(
                    f"{run_id}/{candidate_id}: published_signal must reference an active Signal"
                )
            elif (
                company_id
                not in {
                    str(item).strip()
                    for item in signal.get("company_ids", [])
                    if str(item).strip()
                }
                or str(signal.get("business_axis") or "").strip() != business_axis
            ):
                findings.append(
                    f"{run_id}/{candidate_id}: published Signal company/business-axis does not match"
                )
            elif candidate_date:
                previous_date = published_date_by_signal_id.get(signal_id)
                if previous_date and previous_date != candidate_date:
                    findings.append(
                        f"{run_id}/{candidate_id}: active Signal {signal_id} is already "
                        f"counted on {previous_date} and cannot satisfy another calendar day"
                    )
                else:
                    published_date_by_signal_id[signal_id] = candidate_date
                    published_signal_ids_by_day[candidate_date].add(signal_id)

    if contract_version >= 3:
        date_from = date.fromisoformat(str(run.get("date_from")))
        date_to = date.fromisoformat(str(run.get("date_to")))
        minimum_per_day = int((
            contract.get("minimum_published_signals_per_day")
            if contract_version >= 5
            else contract.get("minimum_candidates_per_day")
        ) or 3)
        if contract_version == 3:
            minimum_candidates = ((date_to - date_from).days + 1) * minimum_per_day
            if len(candidates_by_id) < minimum_candidates:
                findings.append(
                    f"{run_id}: detection density is "
                    f"{len(candidates_by_id)}/{minimum_candidates}; time-bounded "
                    "research requires the period-level candidate minimum"
                )
        elif contract_version == 4:
            cursor = date_from
            while cursor <= date_to:
                day_text = cursor.isoformat()
                actual = candidates_by_day.get(day_text, 0)
                if actual < minimum_per_day:
                    findings.append(
                        f"{run_id}/{day_text}: daily detection density is "
                        f"{actual}/{minimum_per_day}; time-bounded research requires "
                        "the minimum on every calendar day"
                    )
                cursor += timedelta(days=1)
        else:
            cursor = date_from
            while cursor <= date_to:
                day_text = cursor.isoformat()
                actual = len(published_signal_ids_by_day.get(day_text, set()))
                if actual < minimum_per_day:
                    findings.append(
                        f"{run_id}/{day_text}: daily published Signal availability is "
                        f"{actual}/{minimum_per_day}; monthly and recurring research "
                        "requires distinct active Signals visible in MyPIN on every calendar day"
                    )
                cursor += timedelta(days=1)

    cells_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    cells = coverage.get("cells_checked")
    if not isinstance(cells, list):
        cells = []
        findings.append(f"{run_id}: coverage.cells_checked must be a list")
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            findings.append(f"{run_id}: coverage cell #{index + 1} must be an object")
            continue
        pair = (
            str(cell.get("company_id") or "").strip(),
            str(cell.get("business_axis") or "").strip(),
        )
        if not all(pair):
            findings.append(f"{run_id}: coverage cell #{index + 1} is incomplete")
            continue
        if pair in cells_by_pair:
            findings.append(f"{run_id}: duplicate coverage cell {pair[0]}/{pair[1]}")
            continue
        cells_by_pair[pair] = cell

    for company_id, business_axis in required:
        cell_label = f"{run_id}/{company_id}/{business_axis}"
        cell = cells_by_pair.get((company_id, business_axis))
        if cell is None:
            findings.append(f"{cell_label}: required coverage cell was not checked")
            continue
        status = str(cell.get("status") or "")
        if status not in RESEARCH_CELL_STATUSES:
            findings.append(f"{cell_label}: invalid coverage status {status!r}")
        elif status == "pending":
            findings.append(f"{cell_label}: coverage is still pending")
        elif status == "blocked":
            findings.append(f"{cell_label}: blocked coverage cannot close the run")

        channels = {
            str(channel)
            for channel in (cell.get("channels") or [])
            if str(channel) in RESEARCH_EVIDENCE_CHANNELS
        }
        unknown_channels = sorted(
            {
                str(channel)
                for channel in (cell.get("channels") or [])
                if str(channel) not in RESEARCH_EVIDENCE_CHANNELS
            }
        )
        if unknown_channels:
            findings.append(
                f"{cell_label}: unknown evidence channels {', '.join(unknown_channels)}"
            )
        if len(channels) < 2:
            findings.append(
                f"{cell_label}: at least two independent evidence channels are required"
            )

        candidate_ids = {
            str(candidate_id).strip()
            for candidate_id in (cell.get("candidate_ids") or [])
            if str(candidate_id).strip()
        }
        unknown_candidate_ids = sorted(candidate_ids - set(candidates_by_id))
        if contract_version >= 3 and unknown_candidate_ids:
            findings.append(
                f"{cell_label}: candidate_ids missing from coverage.candidates: "
                + ", ".join(unknown_candidate_ids)
            )
        strategies = cell.get("search_strategies")
        if not isinstance(strategies, list):
            strategies = []
            findings.append(f"{cell_label}: search_strategies must be a list")
        valid_strategies: list[dict[str, Any]] = []
        for strategy_index, strategy in enumerate(strategies):
            if not isinstance(strategy, dict):
                findings.append(
                    f"{cell_label}: search strategy #{strategy_index + 1} must be an object"
                )
                continue
            strategy_name = str(strategy.get("strategy") or "").strip()
            channel = str(strategy.get("channel") or "").strip()
            high_impact = strategy.get("new_high_impact_candidates")
            new_candidates = strategy.get("new_candidates")
            if not strategy_name or channel not in channels:
                findings.append(
                    f"{cell_label}: search strategy #{strategy_index + 1} needs a name "
                    "and one of the cell's governed channels"
                )
                continue
            if (
                not isinstance(high_impact, int)
                or isinstance(high_impact, bool)
                or high_impact < 0
                or not isinstance(new_candidates, int)
                or isinstance(new_candidates, bool)
                or new_candidates < 0
            ):
                findings.append(
                    f"{cell_label}: search strategy #{strategy_index + 1} yields must be non-negative integers"
                )
                continue
            if contract_version >= 2:
                query = str(strategy.get("query") or "").strip()
                executed_at = str(strategy.get("executed_at") or "").strip()
                change_types = {
                    str(item).strip()
                    for item in (strategy.get("change_types") or [])
                    if str(item).strip()
                }
                if len(query) < 8:
                    findings.append(
                        f"{cell_label}: search strategy #{strategy_index + 1} "
                        "needs the concrete executed query"
                    )
                    continue
                try:
                    datetime.fromisoformat(executed_at)
                except ValueError:
                    findings.append(
                        f"{cell_label}: search strategy #{strategy_index + 1} "
                        "needs an ISO executed_at timestamp"
                    )
                    continue
                unknown_change_types = sorted(change_types - set(SIGNAL_TYPES))
                if not change_types or unknown_change_types:
                    findings.append(
                        f"{cell_label}: search strategy #{strategy_index + 1} "
                        "needs governed change_types"
                    )
                    continue
            valid_strategies.append(strategy)

        last_three = valid_strategies[-3:]
        diminishing_yield = (
            len(valid_strategies) >= 3
            and len({str(item.get("strategy")) for item in last_three}) == 3
            and (
                contract_version < 2
                or len({str(item.get("channel")) for item in last_three}) >= 2
            )
            and (
                contract_version < 2
                or len(
                    {
                        str(change_type)
                        for item in last_three
                        for change_type in (item.get("change_types") or [])
                    }
                )
                >= 3
            )
            and all(
                int(
                    item.get(
                        "new_candidates"
                        if contract_version >= 2
                        else "new_high_impact_candidates"
                    )
                    or 0
                )
                == 0
                for item in last_three
            )
        )
        if len(candidate_ids) < 8 and not diminishing_yield:
            findings.append(
                f"{cell_label}: closure needs 8 unique candidates or three distinct "
                "consecutive strategies with zero new high-impact candidates"
            )
        if status in {"no_change", "blocked"}:
            limitations = [
                str(item).strip()
                for item in (cell.get("limitations") or [])
                if str(item).strip()
            ]
            if not limitations or len(str(cell.get("next_trigger") or "").strip()) < 10:
                findings.append(
                    f"{cell_label}: {status} needs a limitation and a concrete next trigger"
                )

    extra_pairs = sorted(set(cells_by_pair) - set(required))
    for company_id, business_axis in extra_pairs:
        findings.append(
            f"{run_id}/{company_id}/{business_axis}: coverage cell is outside the frozen contract"
        )

    unresolved_gaps = [
        item
        for item in (coverage.get("high_risk_gaps") or [])
        if not isinstance(item, dict) or item.get("resolved") is not True
    ]
    if unresolved_gaps:
        findings.append(
            f"{run_id}: {len(unresolved_gaps)} high-risk coverage gaps remain unresolved"
        )

    signal_company_ids = {
        str(company_id)
        for signal in signals
        if signal.get("status", "active") == "active"
        for company_id in signal.get("company_ids", [])
    }
    reasons = coverage.get("no_signal_reasons_by_company")
    if not isinstance(reasons, dict):
        reasons = {}
    for company_id in sorted({company_id for company_id, _ in required}):
        if company_id in signal_company_ids:
            continue
        reason = reasons.get(company_id)
        if (
            not isinstance(reason, dict)
            or len(str(reason.get("reason") or "").strip()) < 20
            or len(str(reason.get("next_trigger") or "").strip()) < 10
        ):
            findings.append(
                f"{run_id}/{company_id}: no published Signal; record a specific "
                "non-publication reason and next re-search trigger"
            )
    return findings


def scout_run(args: argparse.Namespace) -> dict[str, Any]:
    """Create, update, and close a coverage-gated adaptive research run."""
    root = require_store(Path(args.root))
    run_id = str(args.run_id).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", run_id):
        raise ValueError("run_id must be 3-128 safe characters: letters, digits, ._- ")

    requested_target_count = getattr(args, "target_count", None)
    if requested_target_count is not None and requested_target_count < 1:
        raise ValueError("target_count must be at least 1")

    try:
        run_path, run = run_record_by_id(root, run_id)
        created = False
    except ValueError:
        date_from = validate_date(getattr(args, "date_from", None), "date_from")
        date_to = validate_date(getattr(args, "date_to", None), "date_to")
        if not date_from or not date_to:
            raise ValueError("new scout run requires --date-from and --date-to")
        if date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        explicit_company_ids = list(getattr(args, "company_id", None) or [])
        explicit_business_axes = list(getattr(args, "business_axis", None) or [])
        user_scope = str(getattr(args, "user_scope", None) or "").strip()
        has_explicit_scope = bool(
            requested_target_count is not None
            or explicit_company_ids
            or explicit_business_axes
            or user_scope
        )
        required_cells = required_research_cells(
            effective_settings(root),
            company_ids=explicit_company_ids,
            business_axes=explicit_business_axes,
        )
        research_mode = (
            "count_limited"
            if requested_target_count is not None
            else "user_scoped"
            if has_explicit_scope
            else "coverage_managed"
        )
        run_path = root / RUNS_DIR / f"{run_id}.json"
        run = {
            "run_id": run_id,
            "status": "in_progress",
            "started_at": timestamp(),
            "date_from": date_from,
            "date_to": date_to,
            "signal_ids": [],
            "results": {"new_sources": 0, "new_claims": 0, "new_signals": 0},
            "research_contract": {
                "version": RUN_RESEARCH_CONTRACT_VERSION,
                "mode": research_mode,
                "required_company_axes": required_cells,
                "minimum_independent_channels_per_cell": 2,
                "candidate_target_per_cell": 8,
                "minimum_published_signals_per_day": 3,
                "diminishing_yield_searches": 3,
                **(
                    {"target_count": requested_target_count}
                    if requested_target_count is not None
                    else {}
                ),
                **({"user_directive": user_scope} if user_scope else {}),
            },
            "signal_contract": {
                **RUN_SIGNAL_CONTRACT,
                "required_business_axes": sorted(
                    {str(item["business_axis"]) for item in required_cells}
                ),
                "documented_axis_gaps": [],
                "signal_ids": [],
            },
            "coverage": (
                {
                    **initial_research_coverage([]),
                    "count_limited": {
                        "target_count": requested_target_count,
                        "selection_note": "사용자가 결과 개수를 명시한 제한 탐색",
                    },
                }
                if requested_target_count is not None
                else initial_research_coverage(required_cells)
            ),
        }
        created = True

    existing_contract = run.get("research_contract") or {}
    existing_target_count = existing_contract.get("target_count")
    if not created and requested_target_count is not None:
        if existing_contract.get("mode") != "count_limited":
            raise ValueError("cannot convert an existing coverage-managed run to count-limited")
        if requested_target_count != existing_target_count:
            raise ValueError(
                f"target_count is frozen at run creation: {existing_target_count}"
            )

    coverage_file = getattr(args, "coverage_file", None)
    if coverage_file:
        coverage_payload = read_json(Path(coverage_file))
        signal_contract_payload = coverage_payload.get("signal_contract")
        if isinstance(signal_contract_payload, dict):
            documented_axis_gaps = signal_contract_payload.get("documented_axis_gaps")
            if documented_axis_gaps is not None:
                if not isinstance(documented_axis_gaps, list):
                    raise ValueError("signal_contract.documented_axis_gaps must be a list")
                signal_contract = dict(run.get("signal_contract") or RUN_SIGNAL_CONTRACT)
                signal_contract["documented_axis_gaps"] = documented_axis_gaps
                run["signal_contract"] = signal_contract
        coverage = coverage_payload
        if "coverage" in coverage_payload and isinstance(coverage_payload["coverage"], dict):
            coverage = coverage_payload["coverage"]
        run["coverage"] = coverage
        referenced_signal_ids = [
            str(candidate.get("signal_id") or "").strip()
            for candidate in coverage.get("candidates", [])
            if isinstance(candidate, dict)
            and candidate.get("disposition") == "published_signal"
            and str(candidate.get("signal_id") or "").strip()
        ]
        if referenced_signal_ids:
            run["signal_ids"] = list(
                dict.fromkeys([*run.get("signal_ids", []), *referenced_signal_ids])
            )
            signal_contract = dict(run.get("signal_contract") or RUN_SIGNAL_CONTRACT)
            signal_contract["signal_ids"] = list(
                dict.fromkeys([*signal_contract.get("signal_ids", []), *referenced_signal_ids])
            )
            run["signal_contract"] = signal_contract
        run["coverage_updated_at"] = timestamp()

    completed = bool(getattr(args, "complete", False))
    if completed:
        listed_signal_ids = {
            str(signal_id).strip()
            for signal_id in run.get("signal_ids", [])
            if str(signal_id).strip()
        }
        run_signals = [
            signal
            for _, signal in signal_records(root)
            if str(signal.get("run_id") or "") == run_id
            or str(signal.get("signal_id") or "") in listed_signal_ids
        ]
        coverage_findings = evaluate_research_coverage(run, run_signals)
        if (
            int((run.get("research_contract") or {}).get("version") or 0) >= 2
            and (run.get("research_contract") or {}).get("mode") != "count_limited"
        ):
            claims_by_id = {
                str(claim.get("claim_id") or ""): claim
                for _, claim in claim_records(root)
                if claim.get("claim_id")
            }
            coverage_findings.extend(
                evaluate_run_signal_contract(
                    run_id,
                    run_signals,
                    claims_by_id,
                    dict(run.get("signal_contract") or RUN_SIGNAL_CONTRACT),
                )
            )
        if coverage_findings:
            run["status"] = "in_progress"
            run.pop("completed_at", None)
            write_json(run_path, run)
            raise ValueError(
                "research coverage gate failed:\n- " + "\n- ".join(coverage_findings)
            )
        run["status"] = "completed"
        run["completed_at"] = timestamp()

    write_json(run_path, run)
    append_log(
        root,
        "scout",
        f"{run_id}: {'completed' if completed else 'initialized' if created else 'updated'}",
    )
    return {
        "action": "scout_completed" if completed else "scout_initialized" if created else "scout_updated",
        "run_id": run_id,
        "status": run.get("status"),
        "required_cells": len(
            (run.get("research_contract") or {}).get("required_company_axes", [])
        ),
        "checked_cells": len((run.get("coverage") or {}).get("cells_checked", [])),
        "research_mode": (run.get("research_contract") or {}).get("mode"),
        "target_count": (run.get("research_contract") or {}).get("target_count"),
    }


def _stable_node_id(prefix: str, *values: object) -> str:
    digest = hashlib.sha256(
        "\x1f".join(normalize_text(str(value)) for value in values).encode("utf-8")
    ).hexdigest()
    return f"{prefix}-{digest[:12].upper()}"


def _records_by_id(
    records: list[tuple[Path, dict[str, Any]]], key: str
) -> dict[str, dict[str, Any]]:
    return {
        str(record.get(key)): record
        for _, record in records
        if record.get(key)
    }


def validate_signal_analysis(
    markdown: str, *, require_h2_start: bool = True
) -> None:
    """Reject thin summaries that cannot serve as the document-level layer."""
    text = markdown.strip()
    first_line = next(
        (line.strip() for line in text.splitlines() if line.strip()), ""
    )
    if require_h2_start and not re.fullmatch(r"##\s+\S.*", first_line):
        raise ValueError(
            "analysis Markdown must start with a conclusion-led ## section heading; "
            "do not leave an unheaded lead paragraph or repeat the Signal title as H1"
        )
    lead = first_markdown_prose_paragraph(text)
    if not lead or not re.search(r"[가-힣]", lead):
        raise ValueError("analysis Markdown must begin with a plain Korean explanation")
    opaque_lead = sorted(
        term for term in OPAQUE_SIGNAL_TITLE_TERMS if term in lead.casefold()
    )
    if opaque_lead:
        raise ValueError(
            "analysis lead contains unexplained internal or translated jargon: "
            + ", ".join(opaque_lead)
        )
    required_concepts = {
        "확인된 변화": ("확인된 변화", "무엇이 바뀌"),
        "사업 영향 경로": ("사업 영향", "전달되는", "영향 경로"),
        "조건부 시나리오": ("시나리오",),
        "관찰 지표": ("확인할 지표", "관찰 지표"),
        "다음 산출물": ("다음 산출물", "의사결정에 필요한"),
        "판단의 한계": ("판단의 한계", "평가의 한계"),
    }
    missing = [
        label
        for label, alternatives in required_concepts.items()
        if not any(term in text for term in alternatives)
    ]
    if missing:
        raise ValueError(
            "analysis Markdown is missing required sections: " + ", ".join(missing)
        )
    if len(text) < 1200:
        raise ValueError("analysis Markdown must be document-level (at least 1200 characters)")
    headings = [
        match.group(1).strip()
        for match in re.finditer(r"^#{2,4}\s+(.+)$", text, flags=re.MULTILINE)
    ]
    if len(headings) < 5:
        raise ValueError("analysis Markdown must use at least five meaningful sections")
    if re.search(r"^#\s+", text, flags=re.MULTILINE):
        raise ValueError("analysis Markdown must not repeat the structured H1 title")
    h2_headings = re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)
    h3_headings = re.findall(r"^###\s+(.+)$", text, flags=re.MULTILINE)
    if not 3 <= len(h2_headings) <= 5:
        raise ValueError(
            "analysis Markdown must use three to five conclusion-led H2 chapters"
        )
    if len(h3_headings) > 10:
        raise ValueError(
            "analysis Markdown is fragmented into too many H3 subsections; "
            "merge short checklist-like sections into the surrounding argument"
        )
    polite_sentence_headings = [
        heading
        for heading in headings
        if re.search(r"(?:니다|하세요|해요|돼요|이에요|예요)[.!?]?$", heading)
    ]
    if polite_sentence_headings:
        raise ValueError(
            "analysis headings must use concise research-report headline style "
            "instead of polite sentence endings: "
            + ", ".join(polite_sentence_headings)
        )
    numbered_headings = [
        heading
        for heading in headings
        if re.match(r"\d+(?:\.\d+)+(?:[.\s]|$)", heading)
    ]
    if numbered_headings:
        raise ValueError(
            "analysis Markdown must not store generated decimal section numbers: "
            + ", ".join(numbered_headings)
        )
    generic_h2 = {
        "판단 질문과 잠정 결론",
        "판단 제안",
        "확인된 변화 요약",
        "사업 판단 요약",
        "확인된 변화와 시점",
        "일반적 해석과 확인된 차이",
        "통념과 확인된 간극",
        "포스코에 전달되는 사업 영향",
        "포스코홀딩스에 전달되는 사업 영향",
        "포스코인터내셔널에 전달되는 사업 영향",
        "사업 영향 경로",
        "사업 시나리오",
        "조건부 사업 시나리오",
        "조건부 시나리오",
        "지금 확인할 지표",
        "의사결정에 필요한 다음 산출물",
        "결론을 확정·폐기할 조건",
        "판단의 한계",
        "공개 근거 확인",
        "왜 중요한가",
        "근거 세부사항",
        "판단 근거 세부사항",
    }
    repeated_schema_headings = [
        heading for heading in h2_headings if heading in generic_h2
    ]
    if repeated_schema_headings:
        raise ValueError(
            "analysis H2 headings must state report-specific conclusions instead of "
            "repeating the analysis template: "
            + ", ".join(repeated_schema_headings)
        )
    uncertainty_markers = (
        "확인되지 않",
        "확인하지 못",
        "공개하지 않",
        "공개되지 않",
        "확정은 아",
        "확정이 아",
        "미확정",
        "불확실",
    )
    uncertainty_mentions = sum(text.count(marker) for marker in uncertainty_markers)
    if uncertainty_mentions > 2:
        raise ValueError(
            "analysis Markdown repeats uncertainty throughout the report; "
            "state confirmed findings in the body and consolidate unresolved limits "
            "once near the falsification or judgment-boundary section"
        )
    table_rows = [
        line
        for line in text.splitlines()
        if line.strip().startswith("|")
        and not re.fullmatch(r"[|:\- ]+", line.strip())
    ]
    if len(table_rows) < 4 or not any("시나리오" in row for row in table_rows):
        raise ValueError("analysis Markdown must include a scenario table with three scenarios")
    monitoring_match = re.search(
        r"^(?:#{2,4}\s+[^\n]*(?:확인할|관찰)\s*지표[^\n]*|"
        r"\*\*[^\n]*(?:확인할|관찰)\s*지표[^\n]*\*\*:?)\s*$"
        r"(.*?)(?=^#{2,4}\s+|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not monitoring_match or len(re.findall(r"^\s*-\s+", monitoring_match.group(1), re.MULTILINE)) < 3:
        raise ValueError("analysis Markdown must include at least three monitoring indicators")
    output_match = re.search(
        r"^(?:#{2,4}\s+[^\n]*(?:다음\s+산출물|의사결정에\s+필요한)[^\n]*|"
        r"\*\*[^\n]*(?:다음\s+산출물|의사결정에\s+필요한)[^\n]*\*\*:?)\s*$"
        r"(.*?)(?=^#{2,4}\s+|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not output_match or len(re.findall(r"^\s*\d+\.\s+", output_match.group(1), re.MULTILINE)) < 3:
        raise ValueError("analysis Markdown must include at least three decision outputs")
    if "!!! warning" not in text:
        raise ValueError("analysis Markdown must mark the judgment boundary with a warning")


def rewrite_analysis_headings(
    markdown: str, replacements: dict[str, str]
) -> str:
    """Replace exact Markdown H2-H4 labels without touching report prose."""
    if not replacements:
        raise ValueError("heading replacements must not be empty")
    normalized: dict[str, str] = {}
    for old, new in replacements.items():
        old_heading = str(old).strip()
        new_heading = str(new).strip()
        if not old_heading or not new_heading:
            raise ValueError("heading replacements require non-empty old and new labels")
        if new_heading.startswith("#") or "\n" in new_heading:
            raise ValueError("replacement headings must be plain single-line labels")
        normalized[old_heading] = new_heading

    replaced: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        level, heading = match.groups()
        heading = heading.strip()
        replacement = normalized.get(heading)
        if replacement is None:
            return match.group(0)
        replaced.add(heading)
        return f"{level} {replacement}"

    rewritten = re.sub(
        r"^(#{2,4})\s+(.+)$", replace, markdown, flags=re.MULTILINE
    )
    missing = sorted(set(normalized) - replaced)
    if missing:
        raise ValueError("headings not found in analysis Markdown: " + ", ".join(missing))
    validate_signal_analysis(rewritten)
    return rewritten


def _structured_analysis_key(value: Any, field: str) -> str:
    key = str(value or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        raise ValueError(f"{field} must be stable lower snake_case")
    return key


def validate_structured_analysis(
    value: Any,
    *,
    allowed_claim_ids: set[str] | None = None,
    allowed_source_ids: set[str] | None = None,
    require_current_schema: bool = False,
    importance_score: int | None = None,
) -> dict[str, Any]:
    """Validate the UI-ready JSON representation stored beside narrative Markdown."""
    if not isinstance(value, dict):
        raise ValueError("structured analysis must be a JSON object")
    schema_version = value.get("schema_version")
    if schema_version not in SUPPORTED_STRUCTURED_ANALYSIS_SCHEMA_VERSIONS:
        raise ValueError(
            "structured analysis schema_version must be one of: "
            + ", ".join(str(item) for item in sorted(SUPPORTED_STRUCTURED_ANALYSIS_SCHEMA_VERSIONS))
        )
    if require_current_schema and schema_version != STRUCTURED_ANALYSIS_SCHEMA_VERSION:
        raise ValueError(
            "structured analysis must use current schema_version "
            f"{STRUCTURED_ANALYSIS_SCHEMA_VERSION}"
        )
    sections = value.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("structured analysis sections must be a non-empty array")

    section_keys: set[str] = set()
    item_keys: set[str] = set()
    items_by_key: dict[str, dict[str, Any]] = {}
    for section_index, section in enumerate(sections):
        field = f"sections[{section_index}]"
        if not isinstance(section, dict):
            raise ValueError(f"{field} must be an object")
        section_key = _structured_analysis_key(section.get("key"), f"{field}.key")
        if section_key in section_keys:
            raise ValueError(f"structured analysis section key is duplicated: {section_key}")
        section_keys.add(section_key)
        if not str(section.get("title") or "").strip():
            raise ValueError(f"{field}.title is required")
        items = section.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError(f"{field}.items must be a non-empty array")

        for item_index, item in enumerate(items):
            item_field = f"{field}.items[{item_index}]"
            if not isinstance(item, dict):
                raise ValueError(f"{item_field} must be an object")
            item_key = _structured_analysis_key(item.get("key"), f"{item_field}.key")
            if item_key in item_keys:
                raise ValueError(f"structured analysis item key is duplicated: {item_key}")
            item_keys.add(item_key)
            items_by_key[item_key] = item
            if not str(item.get("label") or "").strip():
                raise ValueError(f"{item_field}.label is required")
            display = str(item.get("display") or "").strip()
            if display not in STRUCTURED_ANALYSIS_DISPLAY_TYPES:
                raise ValueError(
                    f"{item_field}.display must be one of: "
                    + ", ".join(sorted(STRUCTURED_ANALYSIS_DISPLAY_TYPES))
                )
            if display == "text":
                if not str(item.get("value") or "").strip():
                    raise ValueError(f"{item_field}.value is required for text")
            elif display == "list":
                entries = item.get("items")
                if not isinstance(entries, list) or not entries or any(
                    not str(entry or "").strip() for entry in entries
                ):
                    raise ValueError(f"{item_field}.items must contain non-empty strings")
            elif display == "flow":
                steps = item.get("steps")
                if not isinstance(steps, list) or len(steps) < 3 or any(
                    not str(step or "").strip() for step in steps
                ):
                    raise ValueError(f"{item_field}.steps must contain at least three strings")
            else:
                columns = item.get("columns")
                rows = item.get("rows")
                if not isinstance(columns, list) or len(columns) < 2:
                    raise ValueError(f"{item_field}.columns must contain at least two columns")
                column_keys: set[str] = set()
                for column_index, column in enumerate(columns):
                    if not isinstance(column, dict):
                        raise ValueError(f"{item_field}.columns[{column_index}] must be an object")
                    column_key = _structured_analysis_key(
                        column.get("key"), f"{item_field}.columns[{column_index}].key"
                    )
                    if column_key in column_keys:
                        raise ValueError(f"{item_field} column key is duplicated: {column_key}")
                    column_keys.add(column_key)
                    if not str(column.get("label") or "").strip():
                        raise ValueError(f"{item_field}.columns[{column_index}].label is required")
                if not isinstance(rows, list) or not rows:
                    raise ValueError(f"{item_field}.rows must be a non-empty array")
                for row_index, row in enumerate(rows):
                    if not isinstance(row, dict) or set(row) != column_keys:
                        raise ValueError(
                            f"{item_field}.rows[{row_index}] keys must match the column keys"
                        )
                    if any(not str(cell or "").strip() for cell in row.values()):
                        raise ValueError(f"{item_field}.rows[{row_index}] contains an empty cell")

            for reference_field, allowed in (
                ("claim_ids", allowed_claim_ids),
                ("source_ids", allowed_source_ids),
            ):
                references = item.get(reference_field, [])
                if not isinstance(references, list) or any(
                    not str(reference or "").strip() for reference in references
                ):
                    raise ValueError(f"{item_field}.{reference_field} must be an array of IDs")
                if allowed is not None:
                    unknown = sorted({str(reference) for reference in references} - allowed)
                    if unknown:
                        raise ValueError(
                            f"{item_field}.{reference_field} contains unlinked IDs: "
                            + ", ".join(unknown)
                        )

    required_keys = (
        STRUCTURED_ANALYSIS_REQUIRED_KEYS
        if schema_version == STRUCTURED_ANALYSIS_SCHEMA_VERSION
        else STRUCTURED_ANALYSIS_LEGACY_REQUIRED_KEYS
    )
    if schema_version == STRUCTURED_ANALYSIS_SCHEMA_VERSION and importance_score is not None:
        if importance_score >= 5:
            required_keys = required_keys | STRUCTURED_ANALYSIS_MID_SCORE_REQUIRED_KEYS
        if importance_score >= 8:
            required_keys = required_keys | STRUCTURED_ANALYSIS_HIGH_SCORE_REQUIRED_KEYS
    missing = sorted(required_keys - item_keys)
    if missing:
        raise ValueError(
            "structured analysis is missing required item keys: " + ", ".join(missing)
        )
    if schema_version >= 2:
        missing_sections = sorted(
            STRUCTURED_ANALYSIS_REQUIRED_SECTION_KEYS - section_keys
        )
        if missing_sections:
            raise ValueError(
                f"structured analysis schema v{schema_version} is missing decision-dashboard sections: "
                + ", ".join(missing_sections)
            )
    if schema_version == STRUCTURED_ANALYSIS_SCHEMA_VERSION:
        table_contracts = {
            "scenarios": ({"case", "condition", "meaning", "action"}, 3),
            "monitoring_indicators": (
                {"indicator", "current_state", "threshold", "decision_effect", "owner", "cadence"},
                3,
            ),
            "opportunity": ({"condition", "effect", "action"}, 1),
            "risk": ({"condition", "effect", "action"}, 1),
            "quantification_decision": ({"status", "basis", "next_input"}, 1),
            "escalation_triggers": ({"condition", "current_status", "decision_effect"}, 2),
            "deescalation_triggers": ({"condition", "current_status", "decision_effect"}, 2),
            "timing": ({"event", "date_or_condition", "status"}, 3),
        }
        if importance_score is not None and importance_score >= 5:
            table_contracts["response_options"] = (
                {"option", "benefit", "cost_or_risk", "activation_condition"},
                2,
            )
        for item_key, (required_columns, minimum_rows) in table_contracts.items():
            item = items_by_key.get(item_key)
            if item is None:
                continue
            if item.get("display") != "table":
                raise ValueError(f"structured analysis {item_key} must use table display")
            column_keys = {
                str(column.get("key"))
                for column in item.get("columns", [])
                if isinstance(column, dict)
            }
            missing_columns = sorted(required_columns - column_keys)
            if missing_columns:
                raise ValueError(
                    f"structured analysis {item_key} is missing columns: "
                    + ", ".join(missing_columns)
                )
            if len(item.get("rows", [])) < minimum_rows:
                raise ValueError(
                    f"structured analysis {item_key} must contain at least "
                    f"{minimum_rows} rows"
                )
        quantification_status = structured_quantification_status(value)
        if quantification_status not in QUANTIFICATION_DECISION_STATUSES:
            raise ValueError(
                "structured analysis quantification_decision status must be "
                "modeled or not_applicable"
            )
    return value


def read_structured_analysis(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"invalid structured analysis JSON: {exc}") from exc
    return validate_structured_analysis(value)


OPAQUE_SIGNAL_TITLE_TERMS = {
    "램프업",
    "게이트",
    "트리거",
    "자본규율",
    "공급곡선",
    "구조적 공백",
    "first gas",
    "phase 2",
    "capex 기준",
    "의 교차",
}
NON_FACTUAL_SIGNAL_TITLE_TERMS = {
    "재산정 필요",
    "재검토 필요",
    "대응 필요",
    "검토 필요",
    "해야",
    "관건",
    "우려",
}
POLITE_SIGNAL_TITLE_ENDING = re.compile(
    r"(?:합니다|됩니다|입니다|필요합니다|강화합니다|앞당깁니다)[.!?]?\s*$"
)


def first_markdown_prose_paragraph(markdown: str) -> str:
    """Return the first reader-facing prose paragraph, skipping Markdown chrome."""
    paragraph: list[str] = []
    in_fence = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line:
            if paragraph:
                break
            continue
        if re.match(r"^#{1,6}\s+", line):
            continue
        if line.startswith(("|", "!!!", "???", ">")):
            continue
        if re.match(r"^(?:[-*+]\s+|\d+\.\s+)", line):
            continue
        paragraph.append(line)
    return re.sub(r"\s+", " ", " ".join(paragraph)).strip()


def validate_signal_type(value: Any) -> str:
    signal_type = re.sub(r"\s+", " ", str(value or "")).strip()
    if signal_type not in SIGNAL_TYPES:
        raise ValueError("signal_type must be one of: " + ", ".join(SIGNAL_TYPES))
    return signal_type


def validate_signal_classification(role_value: Any, origin_value: Any) -> tuple[str, str]:
    """Validate whether a Signal is external sensing or execution context."""
    role = str(role_value or "").strip()
    origin = str(origin_value or "").strip()
    if role not in SIGNAL_ROLES:
        raise ValueError("signal_role must be one of: " + ", ".join(SIGNAL_ROLES))
    if origin not in SIGNAL_ORIGINS:
        raise ValueError("signal_origin must be one of: " + ", ".join(SIGNAL_ORIGINS))
    if origin not in SIGNAL_ROLE_ORIGINS[role]:
        allowed = ", ".join(sorted(SIGNAL_ROLE_ORIGINS[role]))
        raise ValueError(f"signal_role {role} only permits signal_origin: {allowed}")
    return role, origin


def source_is_owned_by_target_company(
    source: dict[str, Any], company_ids: list[str]
) -> bool:
    """Return true only for a target company's own newsroom or IR source."""
    if source.get("source_type") not in COMPANY_OWNED_SOURCE_TYPES:
        return False
    hosts = []
    for field in ("canonical_url", "url"):
        try:
            hosts.append(urlsplit(str(source.get(field) or "")).hostname or "")
        except ValueError:
            pass
    identity = normalize_text(" ".join([str(source.get("publisher") or ""), *hosts]))
    return any(
        normalize_text(term) in identity
        for company_id in company_ids
        for term in TARGET_COMPANY_SOURCE_TERMS.get(company_id, ())
    )


def core_signal_uses_only_target_company_sources(
    signal: dict[str, Any], sources_by_id: dict[str, dict[str, Any]]
) -> bool:
    """Detect a self-announcement incorrectly elevated to a core market signal."""
    if signal.get("signal_role") != "core_market_signal":
        return False
    sources = [
        sources_by_id[source_id]
        for source_id in (str(item) for item in signal.get("source_ids", []))
        if source_id in sources_by_id
    ]
    company_ids = [str(item) for item in signal.get("company_ids", [])]
    return bool(sources) and all(
        source_is_owned_by_target_company(source, company_ids) for source in sources
    )


def evaluate_run_signal_contract(
    run_id: str,
    signals: list[dict[str, Any]],
    claims_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any] | None = None,
) -> list[str]:
    """Check external-signal share and single-asset concentration per business axis."""
    contract = contract or RUN_SIGNAL_CONTRACT
    minimum_core_ratio = float(contract.get("minimum_core_market_ratio", 0.7))
    concentration_threshold = float(
        contract.get("single_asset_concentration_threshold", 0.5)
    )
    minimum_signals = int(contract.get("single_asset_minimum_signals", 3))
    contract_version = int(contract.get("version") or 1)
    minimum_axis_signals = int(contract.get("minimum_signals_per_axis", 3))
    minimum_observation_ratio = float(
        contract.get("minimum_observation_band_ratio", 0.2)
    )
    minimum_management_ratio = float(
        contract.get("minimum_management_band_ratio", 0.2)
    )
    maximum_executive_ratio = float(
        contract.get("maximum_executive_band_ratio", 0.5)
    )
    maximum_single_score_ratio = float(
        contract.get("maximum_single_score_ratio", 0.5)
    )
    documented_gaps = {
        str(item.get("axis")): item
        for item in contract.get("documented_axis_gaps", [])
        if isinstance(item, dict)
        and str(item.get("axis") or "").strip()
        and len(str(item.get("reason") or "").strip()) >= 20
        and len(str(item.get("next_trigger") or "").strip()) >= 10
    }
    findings: list[str] = []
    by_axis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        if signal.get("status", "active") == "active":
            by_axis[str(signal.get("business_axis") or "미분류")].append(signal)

    required_axes = {
        str(axis).strip()
        for axis in contract.get("required_business_axes", [])
        if str(axis).strip()
    }
    for axis in sorted(set(by_axis) | required_axes):
        axis_signals = by_axis.get(axis, [])
        total = len(axis_signals)
        core_count = sum(
            signal.get("signal_role") == "core_market_signal"
            for signal in axis_signals
        )
        ratio = core_count / total if total else 0.0
        if total and ratio + 1e-12 < minimum_core_ratio:
            findings.append(
                f"{run_id}/{axis}: external core market signals are "
                f"{core_count}/{total} ({ratio:.0%}); minimum is {minimum_core_ratio:.0%}"
            )

        gap = documented_gaps.get(axis)
        gap_matches = bool(gap) and int(gap.get("actual_signals", -1)) == total
        if contract_version >= 2 and total < minimum_axis_signals and not gap_matches:
            findings.append(
                f"{run_id}/{axis}: only {total} Signals detected; "
                f"vitality target is at least {minimum_axis_signals} per completed monitoring run"
            )

        if contract_version >= 2 and total >= minimum_axis_signals:
            band_scores = [
                max(
                    int((signal.get("business_impact") or {}).get("score") or 0),
                    int((signal.get("urgency") or {}).get("score") or 0),
                )
                for signal in axis_signals
            ]
            observation_count = sum(score <= 4 for score in band_scores)
            management_count = sum(5 <= score <= 7 for score in band_scores)
            executive_count = sum(score >= 8 for score in band_scores)
            observation_ratio = observation_count / total
            management_ratio = management_count / total
            executive_ratio = executive_count / total
            score_counts = Counter(band_scores)
            clustered_score, clustered_count = max(
                score_counts.items(), key=lambda item: item[1]
            )
            if observation_ratio + 1e-12 < minimum_observation_ratio:
                findings.append(
                    f"{run_id}/{axis}: 1~4점 관찰 Signal이 "
                    f"{observation_count}/{total}건으로 {minimum_observation_ratio:.0%} 미만; "
                    "저강도 변화가 승격 단계에서 누락됐는지 확인 필요"
                )
            if management_ratio + 1e-12 < minimum_management_ratio:
                findings.append(
                    f"{run_id}/{axis}: 5~7점 관리 Signal이 "
                    f"{management_count}/{total}건으로 {minimum_management_ratio:.0%} 미만"
                )
            if executive_ratio - 1e-12 > maximum_executive_ratio:
                findings.append(
                    f"{run_id}/{axis}: 8~10점 경영 Signal이 "
                    f"{executive_count}/{total}건으로 {maximum_executive_ratio:.0%} 초과; "
                    "중요 이슈만 통과시키는 승격 편향 또는 점수 인플레이션 검토 필요"
                )
            if clustered_count / total - 1e-12 > maximum_single_score_ratio:
                findings.append(
                    f"{run_id}/{axis}: {clustered_score}점이 "
                    f"{clustered_count}/{total}건으로 {maximum_single_score_ratio:.0%} 초과; "
                    "점수 근거가 개별 영향 경로를 충분히 구분하는지 확인 필요"
                )

        if total < minimum_signals:
            continue
        asset_counts: dict[str, int] = defaultdict(int)
        for signal in axis_signals:
            asset_ids = {
                str(claims_by_id[claim_id].get("subject_id") or "")
                for claim_id in (str(item) for item in signal.get("claim_ids", []))
                if claim_id in claims_by_id
                and str(claims_by_id[claim_id].get("subject_id") or "").startswith(
                    ("PRJ-", "FAC-")
                )
            }
            for asset_id in asset_ids:
                asset_counts[asset_id] += 1
        if not asset_counts:
            continue
        asset_id, asset_count = max(asset_counts.items(), key=lambda item: item[1])
        concentration = asset_count / total
        if concentration > concentration_threshold:
            findings.append(
                f"{run_id}/{axis}: {asset_id} appears in {asset_count}/{total} Signals "
                f"({concentration:.0%}); single asset limit is {concentration_threshold:.0%}"
            )
    return findings


def validate_signal_copy(title: str, sentence: str, summary: str) -> None:
    """Reject reader-facing copy that is opaque or too thin for the Signal surface."""
    raw_title = str(title or "")
    title = re.sub(r"\s+", " ", raw_title).strip()
    sentence = re.sub(r"\s+", " ", str(sentence or "")).strip()
    summary = re.sub(r"\s+", " ", str(summary or "")).strip()
    if not 8 <= len(title) <= 45:
        raise ValueError("signal title must be between 8 and 45 characters")
    if "\n" in raw_title or "\r" in raw_title or POLITE_SIGNAL_TITLE_ENDING.search(title):
        raise ValueError("signal title must use a concise observed-change style")
    if "…" in title or "..." in title:
        raise ValueError(
            "signal title must describe one observed change without headline-style ellipsis"
        )
    lowered_title = title.casefold()
    opaque = sorted(term for term in OPAQUE_SIGNAL_TITLE_TERMS if term in lowered_title)
    if opaque:
        raise ValueError(
            "signal title contains unexplained internal or translated jargon: "
            + ", ".join(opaque)
        )
    non_factual = sorted(
        term for term in NON_FACTUAL_SIGNAL_TITLE_TERMS if term in title
    )
    if non_factual:
        raise ValueError(
            "signal title must name the observed change, not a business implication "
            "or recommendation: "
            + ", ".join(non_factual)
        )
    if not re.search(r"[가-힣]", title):
        raise ValueError("signal title must contain a clear Korean explanation")
    if not 20 <= len(sentence) <= 180:
        raise ValueError("signal sentence must be between 20 and 180 characters")
    if not re.search(r"[.!?]\s*$", sentence):
        raise ValueError("signal sentence must end as a complete sentence")
    if not 70 <= len(summary) <= 500:
        raise ValueError("signal summary must be between 70 and 500 characters")
    summary_sentence_count = len(re.findall(r"[.!?](?:\s|$)", summary))
    if summary_sentence_count not in range(2, 5):
        raise ValueError("signal summary must use between two and four clear sentences")
    lead_text = f"{sentence} {summary}".casefold()
    opaque_lead = sorted(term for term in OPAQUE_SIGNAL_TITLE_TERMS if term in lead_text)
    if opaque_lead:
        raise ValueError(
            "signal lead contains unexplained internal or translated jargon: "
            + ", ".join(opaque_lead)
        )


def validate_score_rationale(field_name: str, score: int, rationale: Any) -> str:
    """Require a concise but decision-auditable explanation for each score."""
    text = re.sub(r"\s+", " ", str(rationale or "")).strip()
    if not SCORE_RATIONALE_MIN_LENGTH <= len(text) <= SCORE_RATIONALE_MAX_LENGTH:
        raise ValueError(
            f"{field_name} rationale must be between "
            f"{SCORE_RATIONALE_MIN_LENGTH} and {SCORE_RATIONALE_MAX_LENGTH} characters"
        )
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", text))
    if sentence_count not in range(3, 5):
        raise ValueError(
            f"{field_name} rationale must use three or four clear sentences"
        )
    if f"{score}점" not in text:
        raise ValueError(f"{field_name} rationale must explain why it is {score}점")
    if not SCORE_RATIONALE_BOUNDARY_PATTERN.search(text):
        raise ValueError(
            f"{field_name} rationale must explain the adjacent-score boundary"
        )
    return text


def validate_assumption_challenge(value: Any) -> dict[str, Any]:
    """Validate the decision-oriented record that makes a core Signal surprising."""
    if not isinstance(value, dict):
        raise ValueError("core market Signal requires an assumption_challenge object")
    if value.get("schema_version") != ASSUMPTION_CHALLENGE_SCHEMA_VERSION:
        raise ValueError("assumption_challenge schema_version must be 1")
    for field in (
        "baseline_assumption",
        "observed_break",
        "decision_change",
        "falsification_check",
    ):
        text = re.sub(r"\s+", " ", str(value.get(field) or "")).strip()
        if not 20 <= len(text) <= 300:
            raise ValueError(f"assumption_challenge.{field} must be 20-300 characters")
    pattern = str(value.get("pattern") or "")
    if pattern not in SURPRISE_PATTERNS:
        raise ValueError(
            "assumption_challenge.pattern must be one of "
            + ", ".join(sorted(SURPRISE_PATTERNS))
        )
    score = value.get("surprise_score")
    if not isinstance(score, int) or score not in range(1, 6):
        raise ValueError("assumption_challenge.surprise_score must be an integer from 1 to 5")
    return value


IMPACT_EXPRESSION_OPERATIONS = {"add", "subtract", "multiply", "divide", "negate"}
IMPACT_INPUT_KINDS = {"verified", "derived", "assumption"}
QUANTIFICATION_DECISION_STATUSES = {"modeled", "not_applicable"}
QUANTIFICATION_NOT_APPLICABLE_REASONS = {
    "subject_not_quantifiable",
    "duplicate_impact_model",
}


def _validate_impact_expression(expression: Any, variable_ids: set[str], path: str) -> None:
    if isinstance(expression, (int, float)) and not isinstance(expression, bool):
        if not math.isfinite(float(expression)):
            raise ValueError(f"{path} must contain finite numbers")
        return
    if not isinstance(expression, dict):
        raise ValueError(f"{path} must be a number or expression object")
    if set(expression) == {"var"}:
        variable_id = str(expression["var"])
        if variable_id not in variable_ids:
            raise ValueError(f"{path} references unknown variable: {variable_id}")
        return
    operation = expression.get("op")
    arguments = expression.get("args")
    if operation not in IMPACT_EXPRESSION_OPERATIONS:
        raise ValueError(f"{path} has unsupported operation: {operation}")
    if not isinstance(arguments, list) or not arguments:
        raise ValueError(f"{path}.args must be a non-empty list")
    if operation == "negate" and len(arguments) != 1:
        raise ValueError(f"{path} negate requires exactly one argument")
    if operation in {"subtract", "divide"} and len(arguments) != 2:
        raise ValueError(f"{path} {operation} requires exactly two arguments")
    for index, argument in enumerate(arguments):
        _validate_impact_expression(argument, variable_ids, f"{path}.args[{index}]")


def validate_impact_estimate(value: dict[str, Any]) -> dict[str, Any]:
    """Validate a portable, non-executable What-if calculation model."""
    if not isinstance(value, dict):
        raise ValueError("impact estimate must be a JSON object")
    if value.get("schema_version") != 1:
        raise ValueError("impact estimate schema_version must be 1")
    for field in ("title", "description", "as_of", "confidence", "notice"):
        if not str(value.get(field) or "").strip():
            raise ValueError(f"impact estimate is missing {field}")
    validate_date(str(value["as_of"]), "impact estimate as_of")
    if value.get("confidence") not in CLAIM_CONFIDENCE:
        raise ValueError("impact estimate confidence must be high, medium, or low")

    variables = value.get("variables")
    if not isinstance(variables, list) or not 3 <= len(variables) <= 8:
        raise ValueError("impact estimate must contain between three and eight variables")
    variable_ids: set[str] = set()
    for index, variable in enumerate(variables):
        path = f"variables[{index}]"
        if not isinstance(variable, dict):
            raise ValueError(f"{path} must be an object")
        variable_id = str(variable.get("id") or "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,48}", variable_id):
            raise ValueError(f"{path}.id must be stable snake_case")
        if variable_id in variable_ids:
            raise ValueError(f"duplicate impact variable: {variable_id}")
        variable_ids.add(variable_id)
        for field in ("label", "unit", "basis"):
            if not str(variable.get(field) or "").strip():
                raise ValueError(f"{path} is missing {field}")
        if variable.get("kind") not in IMPACT_INPUT_KINDS:
            raise ValueError(f"{path}.kind must be verified, derived, or assumption")
        numeric_values = {}
        for field in ("min", "max", "step", "default"):
            candidate = variable.get(field)
            if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
                raise ValueError(f"{path}.{field} must be numeric")
            candidate = float(candidate)
            if not math.isfinite(candidate):
                raise ValueError(f"{path}.{field} must be finite")
            numeric_values[field] = candidate
        if numeric_values["min"] >= numeric_values["max"]:
            raise ValueError(f"{path}.min must be lower than max")
        if numeric_values["step"] <= 0:
            raise ValueError(f"{path}.step must be positive")
        if not numeric_values["min"] <= numeric_values["default"] <= numeric_values["max"]:
            raise ValueError(f"{path}.default must be within min and max")
        source_ids = variable.get("source_ids", [])
        if not isinstance(source_ids, list) or not all(
            isinstance(source_id, str) for source_id in source_ids
        ):
            raise ValueError(f"{path}.source_ids must be a string list")
        if variable.get("kind") == "verified" and not source_ids:
            raise ValueError(f"{path} verified input requires source_ids")

    outputs = value.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("impact estimate must contain at least one output")
    output_ids: set[str] = set()
    primary_count = 0
    for index, output in enumerate(outputs):
        path = f"outputs[{index}]"
        if not isinstance(output, dict):
            raise ValueError(f"{path} must be an object")
        output_id = str(output.get("id") or "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,48}", output_id):
            raise ValueError(f"{path}.id must be stable snake_case")
        if output_id in output_ids:
            raise ValueError(f"duplicate impact output: {output_id}")
        output_ids.add(output_id)
        for field in ("label", "unit"):
            if not str(output.get(field) or "").strip():
                raise ValueError(f"{path} is missing {field}")
        decimals = output.get("decimals", 0)
        if not isinstance(decimals, int) or decimals not in range(0, 4):
            raise ValueError(f"{path}.decimals must be between 0 and 3")
        if output.get("primary") is True:
            primary_count += 1
        _validate_impact_expression(output.get("expression"), variable_ids, f"{path}.expression")
    if primary_count != 1:
        raise ValueError("impact estimate must have exactly one primary output")

    presets = value.get("presets")
    if not isinstance(presets, list) or len(presets) < 3:
        raise ValueError("impact estimate must contain at least three scenario presets")
    for index, preset in enumerate(presets):
        path = f"presets[{index}]"
        if not isinstance(preset, dict) or not str(preset.get("label") or "").strip():
            raise ValueError(f"{path} must contain a label")
        preset_values = preset.get("values")
        if not isinstance(preset_values, dict) or set(preset_values) != variable_ids:
            raise ValueError(f"{path}.values must cover every variable exactly once")
        for variable in variables:
            variable_id = variable["id"]
            candidate = preset_values[variable_id]
            if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
                raise ValueError(f"{path}.{variable_id} must be numeric")
            if not float(variable["min"]) <= float(candidate) <= float(variable["max"]):
                raise ValueError(f"{path}.{variable_id} is outside its slider range")
    return value


def read_impact_estimate(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    return validate_impact_estimate(read_json(Path(path_value)))


def validate_quantification_decision(
    value: dict[str, Any],
    impact_estimate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the explicit model-or-exception decision stored on every Insight."""
    if not isinstance(value, dict):
        raise ValueError("quantification_decision must be a JSON object")
    if value.get("schema_version") != 1:
        raise ValueError("quantification_decision schema_version must be 1")
    status = str(value.get("status") or "")
    if status not in QUANTIFICATION_DECISION_STATUSES:
        raise ValueError(
            "quantification_decision status must be modeled or not_applicable"
        )
    assessed_at = str(value.get("assessed_at") or "")
    validate_date(assessed_at, "quantification_decision assessed_at")
    basis = str(value.get("basis") or "").strip()
    if len(basis) < 40:
        raise ValueError("quantification_decision basis must be at least 40 characters")

    if status == "modeled":
        if impact_estimate is None:
            raise ValueError("modeled quantification_decision requires impact_estimate")
        return value

    if impact_estimate is not None:
        raise ValueError("not_applicable quantification_decision cannot have impact_estimate")
    reason_code = str(value.get("reason_code") or "")
    if reason_code not in QUANTIFICATION_NOT_APPLICABLE_REASONS:
        raise ValueError(
            "not_applicable reason_code must be subject_not_quantifiable or "
            "duplicate_impact_model"
        )
    required_inputs = value.get("required_inputs")
    if not isinstance(required_inputs, list) or not required_inputs or any(
        not str(item or "").strip() for item in required_inputs
    ):
        raise ValueError("not_applicable required_inputs must contain non-empty strings")
    if not str(value.get("reconsider_when") or "").strip():
        raise ValueError("not_applicable reconsider_when is required")
    related_signal_ids = value.get("related_signal_ids", [])
    if not isinstance(related_signal_ids, list) or any(
        not str(signal_id or "").strip() for signal_id in related_signal_ids
    ):
        raise ValueError("not_applicable related_signal_ids must be a string list")
    if reason_code == "duplicate_impact_model" and not related_signal_ids:
        raise ValueError(
            "duplicate_impact_model requires at least one related_signal_id"
        )
    return value


def modeled_quantification_decision(estimate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "modeled",
        "assessed_at": estimate["as_of"],
        "basis": (
            "공개 확인값·공개자료 역산·AI 가정을 구분한 검증된 What-if 모델을 "
            "연결했으며, 범위와 신뢰도를 함께 표시합니다."
        ),
    }


def read_quantification_decision(
    path_value: str | None,
    impact_estimate: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not path_value:
        return None
    return validate_quantification_decision(
        read_json(Path(path_value)), impact_estimate
    )


def structured_quantification_status(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for section in value.get("sections", []):
        if not isinstance(section, dict):
            continue
        for item in section.get("items", []):
            if not isinstance(item, dict) or item.get("key") != "quantification_decision":
                continue
            rows = item.get("rows")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return str(rows[0].get("status") or "")
    return None


def sync_structured_quantification_decision(
    value: Any, decision: dict[str, Any]
) -> None:
    if not isinstance(value, dict):
        return
    for section in value.get("sections", []):
        if not isinstance(section, dict):
            continue
        for item in section.get("items", []):
            if not isinstance(item, dict) or item.get("key") != "quantification_decision":
                continue
            rows = item.get("rows")
            if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
                return
            rows[0]["status"] = decision["status"]
            rows[0]["basis"] = decision["basis"]
            rows[0]["next_input"] = (
                "내부 실제값으로 공개 대용변수와 가정 범위를 교체"
                if decision["status"] == "modeled"
                else str(decision.get("reconsider_when") or "재검토 조건 확인")
            )
            return


def add_signal(args: argparse.Namespace) -> dict[str, Any]:
    """Create a governed Signal and Insight linked to evidence and a research run."""
    root = require_store(Path(args.root))
    run_id = str(getattr(args, "run_id", "") or "").strip()
    if not run_id:
        raise ValueError("run_id is required for Signal publication")
    run_path, run_record = run_record_by_id(root, run_id)
    impact_score = int(args.business_impact_score)
    urgency_score = int(args.urgency_score)
    if (
        impact_score not in range(1, SIGNAL_SCORE_MAX + 1)
        or urgency_score not in range(1, SIGNAL_SCORE_MAX + 1)
    ):
        raise ValueError(
            f"business impact and urgency scores must be between 1 and {SIGNAL_SCORE_MAX}"
        )
    business_impact_rationale = validate_score_rationale(
        "business_impact", impact_score, args.business_impact_rationale
    )
    urgency_rationale = validate_score_rationale(
        "urgency", urgency_score, args.urgency_rationale
    )
    if args.assessment_confidence not in CLAIM_CONFIDENCE:
        raise ValueError(f"Invalid assessment confidence: {args.assessment_confidence}")
    validate_signal_copy(args.title, args.sentence, args.paragraph)
    signal_type = validate_signal_type(getattr(args, "signal_type", None))
    signal_role, signal_origin = validate_signal_classification(
        getattr(args, "signal_role", None), getattr(args, "signal_origin", None)
    )
    assumption_challenge = None
    if signal_role == "core_market_signal":
        assumption_challenge = validate_assumption_challenge(
            {
                "schema_version": ASSUMPTION_CHALLENGE_SCHEMA_VERSION,
                "baseline_assumption": getattr(args, "baseline_assumption", None),
                "observed_break": getattr(args, "observed_break", None),
                "decision_change": getattr(args, "decision_change", None),
                "pattern": getattr(args, "surprise_pattern", None),
                "surprise_score": getattr(args, "surprise_score", None),
                "falsification_check": getattr(args, "falsification_check", None),
            }
        )

    claim_ids = list(dict.fromkeys(args.claim_id))
    claims_by_id = _records_by_id(claim_records(root), "claim_id")
    missing_claims = [claim_id for claim_id in claim_ids if claim_id not in claims_by_id]
    if missing_claims:
        raise ValueError(f"Unknown claim IDs: {', '.join(missing_claims)}")
    source_ids = list(
        dict.fromkeys(
            str(source_id)
            for claim_id in claim_ids
            for source_id in claims_by_id[claim_id].get("source_ids", [])
        )
    )
    verify_source_ids(root, source_ids)
    risk_factor_ids = list(dict.fromkeys(args.risk_factor_id))
    verify_risk_factor_ids(root, risk_factor_ids)
    observations_by_id = _records_by_id(
        observation_records(root), "observation_version_id"
    )
    events_by_id = _records_by_id(event_records(root), "event_version_id")
    observation_ids = list(dict.fromkeys(getattr(args, "observation_id", None) or []))
    event_ids = list(dict.fromkeys(getattr(args, "event_id", None) or []))
    missing_observations = sorted(set(observation_ids) - set(observations_by_id))
    missing_events = sorted(set(event_ids) - set(events_by_id))
    if missing_observations:
        raise ValueError("Unknown Observation versions: " + ", ".join(missing_observations))
    if missing_events:
        raise ValueError("Unknown Event versions: " + ", ".join(missing_events))

    document_value = getattr(args, "document_path", None)
    document_path = Path(document_value) if document_value else None
    if document_path is not None:
        if document_path.is_absolute() or ".." in document_path.parts:
            raise ValueError("document_path must be relative to the wiki root")
        if get_artifact(root, document_path.as_posix()) is None:
            raise ValueError(
                "document_path must reference a SQLite artifact ID; "
                f"not found: {document_path.as_posix()}"
            )

    assessed_at = validate_date(args.assessed_at, "assessed_at") or today()
    response_deadline = validate_date(args.response_deadline, "response_deadline")
    analysis_file = getattr(args, "analysis_file", None)
    if not analysis_file:
        raise ValueError("analysis_file is required for a document-level signal")
    analysis_markdown = Path(analysis_file).read_text(encoding="utf-8").strip()
    validate_signal_analysis(analysis_markdown)
    structured_analysis_file = getattr(args, "structured_analysis_file", None)
    if not structured_analysis_file:
        raise ValueError(
            "structured_analysis_file is required for a UI-ready document-level signal"
        )
    analysis_structured = read_structured_analysis(structured_analysis_file)
    impact_estimate = read_impact_estimate(getattr(args, "impact_estimate_file", None))
    quantification_decision = read_quantification_decision(
        getattr(args, "quantification_decision_file", None), impact_estimate
    )
    if impact_estimate is not None and quantification_decision is None:
        quantification_decision = modeled_quantification_decision(impact_estimate)
    if quantification_decision is None:
        raise ValueError(
            "Signal publication requires impact_estimate_file or a "
            "not_applicable quantification_decision_file"
        )
    if structured_quantification_status(analysis_structured) != quantification_decision["status"]:
        raise ValueError(
            "structured quantification_decision status must match the Insight decision"
        )
    company_ids = list(dict.fromkeys(args.company_id))
    invalid_pairs = [
        f"{company_id}={args.business_axis}"
        for company_id in company_ids
        if not company_supports_business_axis(company_id, args.business_axis)
    ]
    if invalid_pairs:
        raise ValueError(
            "Invalid company/business-axis pairs: " + ", ".join(invalid_pairs)
        )
    sources_by_id = _records_by_id(source_records(root), "source_id")
    validate_structured_analysis(
        analysis_structured,
        allowed_claim_ids=set(claim_ids),
        allowed_source_ids=set(source_ids),
        require_current_schema=True,
        importance_score=max(impact_score, urgency_score),
    )
    proposed_signal = {
        "signal_role": signal_role,
        "signal_origin": signal_origin,
        "assumption_challenge": assumption_challenge,
        "source_ids": source_ids,
        "company_ids": company_ids,
    }
    if core_signal_uses_only_target_company_sources(proposed_signal, sources_by_id):
        raise ValueError(
            "core_market_signal cannot rely only on target-company releases; "
            "classify it as execution_context/company_execution or add independent "
            "external evidence"
        )
    selected_predicates = {
        str(claims_by_id[claim_id].get("predicate") or "") for claim_id in claim_ids
    }
    missing_predicates = sorted(REQUIRED_SIGNAL_PREDICATES - selected_predicates)
    if missing_predicates:
        raise ValueError(
            "Signal is missing required assessment claims: "
            + ", ".join(missing_predicates)
        )
    claims_by_predicate = {
        str(claims_by_id[claim_id].get("predicate") or ""): claims_by_id[claim_id]
        for claim_id in claim_ids
    }
    expected_values = {
        "business_axis": args.business_axis,
        "business_impact_score_1_to_10": str(impact_score),
        "business_impact_rationale": business_impact_rationale,
        "urgency_score_1_to_10": str(urgency_score),
        "urgency_rationale": urgency_rationale,
        "assessment_confidence": args.assessment_confidence,
        "assessed_at": assessed_at,
    }
    mismatched = [
        predicate
        for predicate, expected in expected_values.items()
        if normalize_text(str(claims_by_predicate[predicate].get("value") or ""))
        != normalize_text(str(expected))
    ]
    if mismatched:
        raise ValueError(
            "Signal fields disagree with assessment claims: " + ", ".join(mismatched)
        )
    insight_id = _stable_node_id(
        "INS", args.title, args.paragraph, document_path.as_posix() if document_path else "", *claim_ids
    )
    now = timestamp()
    evidence_refs: list[dict[str, Any]] = []
    for claim_id in claim_ids:
        claim = claims_by_id[claim_id]
        claim_version_id = str(claim.get("claim_version_id") or "").strip()
        if not claim_version_id:
            raise ValueError(f"{claim_id} has no canonical claim_version_id")
        claim_source_ids = [str(item) for item in claim.get("source_ids", [])]
        modalities = {
            validate_modality(sources_by_id[source_id].get("source_modality"))
            for source_id in claim_source_ids
        }
        if len(modalities) != 1:
            raise ValueError(
                f"{claim_id} mixes source modalities; split it into atomic evidence versions"
            )
        evidence_refs.append(
            {
                "kind": "claim",
                "version_id": claim_version_id,
                "modality": next(iter(modalities)),
                "relation": "contradict" if claim.get("status") == "disputed" else "support",
                "source_ids": claim_source_ids,
            }
        )
    evidence_refs.extend(
        {
            "kind": "observation",
            "version_id": observation_id,
            "modality": observations_by_id[observation_id]["modality"],
            "relation": "support",
            "source_ids": [observations_by_id[observation_id]["source_id"]],
        }
        for observation_id in observation_ids
    )
    evidence_refs.extend(
        {
            "kind": "event",
            "version_id": event_id,
            "modality": events_by_id[event_id]["modality"],
            "relation": "support",
            "source_ids": events_by_id[event_id]["source_ids"],
        }
        for event_id in event_ids
    )
    business_impact = {
        "score": impact_score,
        "rationale": business_impact_rationale,
    }
    urgency = {
        "score": urgency_score,
        "rationale": urgency_rationale,
        "response_deadline": response_deadline,
    }
    existing_signal_versions = [
        value
        for _, value in signal_version_records(root)
        if value.get("canonical_key") == args.canonical_key
    ]
    replaced_insight_ids = {
        str(value.get("insight_id") or "")
        for _, value in signal_records(root)
        if value.get("canonical_key") == args.canonical_key
        and value.get("insight_id")
    }
    signal_version, company_impacts, scenarios = build_signal_bundle(
        canonical_key=args.canonical_key,
        title=args.title.strip(),
        sentence=args.sentence.strip(),
        signal_type=signal_type,
        signal_role=signal_role,
        signal_origin=signal_origin,
        assessed_at=assessed_at,
        risk_factor_ids=risk_factor_ids,
        evidence_refs=evidence_refs,
        company_ids=company_ids,
        business_axis=args.business_axis.strip(),
        business_impact=business_impact,
        urgency=urgency,
        assessment_confidence=args.assessment_confidence,
        structured_analysis=analysis_structured,
        created_at=now,
        version_no=max(
            (int(value.get("version_no") or 0) for value in existing_signal_versions),
            default=0,
        )
        + 1,
    )
    signal_id = signal_version["signal_id"]
    insight = {
        "schema_version": INSIGHT_SCHEMA_VERSION,
        "insight_id": insight_id,
        "title": args.title.strip(),
        "summary": args.paragraph.strip(),
        "analysis_markdown": analysis_markdown,
        "analysis_structured": analysis_structured,
        "quantification_decision": quantification_decision,
        "impact_estimate": impact_estimate,
        "document_path": document_path.as_posix() if document_path else None,
        "company_ids": company_ids,
        "business_axis": args.business_axis.strip(),
        "claim_ids": claim_ids,
        "source_ids": source_ids,
        "created_at": now,
        "updated_at": now,
        "run_id": run_id,
    }
    signal = {
        "schema_version": SIGNAL_SCHEMA_VERSION,
        "signal_id": signal_id,
        "signal_version_id": signal_version["signal_version_id"],
        "version_no": signal_version["version_no"],
        "canonical_key": signal_version["canonical_key"],
        "risk_factor_ids": risk_factor_ids,
        "evidence_refs": signal_version["evidence_refs"],
        "company_impact_version_ids": signal_version["company_impact_version_ids"],
        "scenario_version_ids": signal_version["scenario_version_ids"],
        "sentence": args.sentence.strip(),
        "signal_type": signal_type,
        "signal_role": signal_role,
        "signal_origin": signal_origin,
        "assumption_challenge": assumption_challenge,
        "insight_id": insight_id,
        "company_ids": company_ids,
        "business_axis": args.business_axis.strip(),
        "business_impact": business_impact,
        "urgency": urgency,
        "score_scale": {
            "version": 1,
            "minimum": 1,
            "maximum": SIGNAL_SCORE_MAX,
            "calibration": "rubric_v1",
        },
        "assessed_at": assessed_at,
        "detected_at": now,
        "assessment_confidence": args.assessment_confidence,
        "claim_ids": claim_ids,
        "source_ids": source_ids,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "run_id": run_id,
    }
    write_json(root / INSIGHTS_DIR / f"{insight_id}.json", insight)
    write_json(root / SIGNALS_DIR / f"{signal_id}.json", signal)
    referenced_insight_ids = {
        str(value.get("insight_id") or "")
        for _, value in signal_records(root)
        if value.get("insight_id")
    }
    for replaced_insight_id in replaced_insight_ids - {insight_id}:
        if replaced_insight_id not in referenced_insight_ids:
            delete_record(root, "insights", replaced_insight_id)
    write_json(
        root / SIGNAL_VERSIONS_DIR / f"{signal_version['signal_version_id']}.json",
        signal_version,
    )
    for impact in company_impacts:
        write_json(
            root / COMPANY_IMPACTS_DIR / f"{impact['company_impact_version_id']}.json",
            impact,
        )
    for scenario in scenarios:
        write_json(
            root / SCENARIOS_DIR / f"{scenario['scenario_version_id']}.json",
            scenario,
        )
    put_signal_analytics_bundle(root, signal_version, company_impacts, scenarios)
    published_signal_ids = list(
        dict.fromkeys([*run_record.get("signal_ids", []), signal_id])
    )
    run_record["signal_ids"] = published_signal_ids
    signal_contract = dict(run_record.get("signal_contract") or RUN_SIGNAL_CONTRACT)
    signal_contract["signal_ids"] = list(
        dict.fromkeys([*signal_contract.get("signal_ids", []), signal_id])
    )
    contract_signal_ids = {
        str(item) for item in signal_contract.get("signal_ids", [])
    }
    axis_signal_counts: Counter[str] = Counter(
        str(item.get("business_axis") or "미분류")
        for _, item in signal_records(root)
        if (
            str(item.get("run_id") or "") == run_id
            or str(item.get("signal_id") or "") in contract_signal_ids
        )
        and item.get("status", "active") == "active"
    )
    documented_axis_gaps = signal_contract.get("documented_axis_gaps")
    if isinstance(documented_axis_gaps, list):
        signal_contract["documented_axis_gaps"] = [
            {
                **gap,
                "actual_signals": axis_signal_counts.get(
                    str(gap.get("axis") or ""), 0
                ),
            }
            if isinstance(gap, dict)
            else gap
            for gap in documented_axis_gaps
        ]
    run_record["signal_contract"] = signal_contract
    if signal_role == "core_market_signal":
        discovery_contract = dict(
            run_record.get("discovery_contract") or RUN_DISCOVERY_CONTRACT
        )
        discovery_contract["signal_ids"] = list(
            dict.fromkeys([*discovery_contract.get("signal_ids", []), signal_id])
        )
        run_record["discovery_contract"] = discovery_contract
    run_record.setdefault("results", {})["new_signals"] = len(published_signal_ids)
    write_json(run_path, run_record)
    sync_obsidian_store(root)
    append_log(root, "add-signal", f"{signal_id}: {args.title}")
    return {
        "action": "created",
        "signal_id": signal_id,
        "signal_version_id": signal_version["signal_version_id"],
        "insight_id": insight_id,
    }


def refresh_signal_analytics_version(
    root: Path, signal: dict[str, Any], insight: dict[str, Any]
) -> dict[str, Any]:
    """Append the next canonical version after evidence, analysis, or scoring changes."""

    canonical_key = str(signal.get("canonical_key") or "").strip()
    risk_factor_ids = [str(item) for item in signal.get("risk_factor_ids", [])]
    verify_risk_factor_ids(root, risk_factor_ids)
    claims_by_id = _records_by_id(claim_records(root), "claim_id")
    sources_by_id = _records_by_id(source_records(root), "source_id")
    evidence_refs: list[dict[str, Any]] = [
        dict(item)
        for item in signal.get("evidence_refs", [])
        if isinstance(item, dict) and item.get("kind") != "claim"
    ]
    for claim_id in signal.get("claim_ids", []):
        claim = claims_by_id.get(str(claim_id))
        if claim is None:
            raise ValueError(f"Unknown claim ID: {claim_id}")
        version_id = str(claim.get("claim_version_id") or "")
        if not version_id:
            raise ValueError(f"{claim_id} has no canonical claim_version_id")
        source_ids = [str(item) for item in claim.get("source_ids", [])]
        modalities = {
            validate_modality(sources_by_id[source_id].get("source_modality"))
            for source_id in source_ids
        }
        if len(modalities) != 1:
            raise ValueError(f"{claim_id} mixes source modalities")
        evidence_refs.append(
            {
                "kind": "claim",
                "version_id": version_id,
                "modality": next(iter(modalities)),
                "relation": "contradict" if claim.get("status") == "disputed" else "support",
                "source_ids": source_ids,
            }
        )
    versions = [
        value
        for _, value in signal_version_records(root)
        if value.get("signal_id") == signal.get("signal_id")
    ]
    now = timestamp()
    signal_version, company_impacts, scenarios = build_signal_bundle(
        canonical_key=canonical_key,
        title=str(insight.get("title") or ""),
        sentence=str(signal.get("sentence") or ""),
        signal_type=str(signal.get("signal_type") or ""),
        signal_role=str(signal.get("signal_role") or ""),
        signal_origin=str(signal.get("signal_origin") or ""),
        assessed_at=str(signal.get("assessed_at") or ""),
        risk_factor_ids=risk_factor_ids,
        evidence_refs=evidence_refs,
        company_ids=[str(item) for item in signal.get("company_ids", [])],
        business_axis=str(signal.get("business_axis") or ""),
        business_impact=dict(signal.get("business_impact") or {}),
        urgency=dict(signal.get("urgency") or {}),
        assessment_confidence=str(signal.get("assessment_confidence") or ""),
        structured_analysis=dict(insight.get("analysis_structured") or {}),
        created_at=now,
        version_no=max((int(value.get("version_no") or 0) for value in versions), default=0) + 1,
        stable_signal_id=str(signal.get("signal_id") or ""),
    )
    for value, directory, id_field in (
        (signal_version, SIGNAL_VERSIONS_DIR, "signal_version_id"),
        *(
            (impact, COMPANY_IMPACTS_DIR, "company_impact_version_id")
            for impact in company_impacts
        ),
        *((scenario, SCENARIOS_DIR, "scenario_version_id") for scenario in scenarios),
    ):
        write_json(root / directory / f"{value[id_field]}.json", value)
    put_signal_analytics_bundle(root, signal_version, company_impacts, scenarios)
    signal.update(
        {
            "signal_version_id": signal_version["signal_version_id"],
            "version_no": signal_version["version_no"],
            "evidence_refs": signal_version["evidence_refs"],
            "company_impact_version_ids": signal_version["company_impact_version_ids"],
            "scenario_version_ids": signal_version["scenario_version_ids"],
            "updated_at": now,
        }
    )
    write_json(root / SIGNALS_DIR / f"{signal['signal_id']}.json", signal)
    return signal_version


def set_structured_analysis(args: argparse.Namespace) -> dict[str, Any]:
    """Attach or replace validated UI-ready JSON without changing narrative analysis."""
    root = require_store(Path(args.root))
    signals = _records_by_id(signal_records(root), "signal_id")
    signal = signals.get(args.signal_id)
    if signal is None:
        raise ValueError(f"Unknown signal ID: {args.signal_id}")
    insight_id = str(signal.get("insight_id") or "")
    insight_paths = {
        str(record.get("insight_id")): (path, record)
        for path, record in insight_records(root)
        if record.get("insight_id")
    }
    if insight_id not in insight_paths:
        raise ValueError(f"Broken insight link: {insight_id}")
    analysis = read_structured_analysis(args.structured_analysis_file)
    if analysis is None:
        raise ValueError("structured_analysis_file is required")
    insight_path, insight = insight_paths[insight_id]
    validate_structured_analysis(
        analysis,
        allowed_claim_ids={str(item) for item in insight.get("claim_ids", [])},
        allowed_source_ids={str(item) for item in insight.get("source_ids", [])},
        require_current_schema=True,
        importance_score=max(
            int((signal.get("business_impact") or {}).get("score") or 0),
            int((signal.get("urgency") or {}).get("score") or 0),
        ),
    )
    insight["schema_version"] = INSIGHT_SCHEMA_VERSION
    insight["analysis_structured"] = analysis
    insight["updated_at"] = timestamp()
    signal_version = refresh_signal_analytics_version(root, signal, insight)
    write_json(insight_path, insight)
    append_log(
        root,
        "set-structured-analysis",
        f"{args.signal_id}: schema v{analysis['schema_version']}",
    )
    return {
        "action": "structured_analysis_updated",
        "signal_id": args.signal_id,
        "insight_id": insight_id,
        "schema_version": STRUCTURED_ANALYSIS_SCHEMA_VERSION,
        "signal_version_id": signal_version["signal_version_id"],
    }


def set_signal_analysis(args: argparse.Namespace) -> dict[str, Any]:
    """Replace narrative analysis and optionally replace its UI representation."""
    root = require_store(Path(args.root))
    signals = _records_by_id(signal_records(root), "signal_id")
    signal = signals.get(args.signal_id)
    if signal is None:
        raise ValueError(f"Unknown signal ID: {args.signal_id}")
    insight_id = str(signal.get("insight_id") or "")
    insight_paths = {
        str(record.get("insight_id")): (path, record)
        for path, record in insight_records(root)
        if record.get("insight_id")
    }
    if insight_id not in insight_paths:
        raise ValueError(f"Broken insight link: {insight_id}")

    insight_path, insight = insight_paths[insight_id]
    analysis_markdown = Path(args.analysis_file).read_text(encoding="utf-8").strip()
    validate_signal_analysis(analysis_markdown)
    structured_analysis_file = getattr(args, "structured_analysis_file", None)
    analysis_structured = (
        read_structured_analysis(structured_analysis_file)
        if structured_analysis_file
        else insight.get("analysis_structured")
    )
    if analysis_structured is None:
        raise ValueError(
            "structured_analysis_file is required when the Insight has no existing "
            "structured analysis"
        )

    claims_by_id = _records_by_id(claim_records(root), "claim_id")
    claim_ids = list(
        dict.fromkeys(
            [
                *(str(item) for item in signal.get("claim_ids", [])),
                *(str(item) for item in getattr(args, "claim_id", [])),
            ]
        )
    )
    missing_claims = [claim_id for claim_id in claim_ids if claim_id not in claims_by_id]
    if missing_claims:
        raise ValueError(f"Unknown claim IDs: {', '.join(missing_claims)}")
    source_ids = list(
        dict.fromkeys(
            str(source_id)
            for claim_id in claim_ids
            for source_id in claims_by_id[claim_id].get("source_ids", [])
        )
    )
    verify_source_ids(root, source_ids)
    validate_structured_analysis(
        analysis_structured,
        allowed_claim_ids=set(claim_ids),
        allowed_source_ids=set(source_ids),
        require_current_schema=True,
        importance_score=max(
            int((signal.get("business_impact") or {}).get("score") or 0),
            int((signal.get("urgency") or {}).get("score") or 0),
        ),
    )

    now = timestamp()
    insight["schema_version"] = INSIGHT_SCHEMA_VERSION
    insight["analysis_markdown"] = analysis_markdown
    insight["analysis_structured"] = analysis_structured
    insight["claim_ids"] = claim_ids
    insight["source_ids"] = source_ids
    insight["updated_at"] = now
    signal["claim_ids"] = claim_ids
    signal["source_ids"] = source_ids
    signal["updated_at"] = now
    signal_version = refresh_signal_analytics_version(root, signal, insight)
    write_json(insight_path, insight)
    sync_obsidian_store(root)
    append_log(root, "set-signal-analysis", f"{args.signal_id}: {len(claim_ids)} claims")
    return {
        "action": "signal_analysis_updated",
        "signal_id": args.signal_id,
        "insight_id": insight_id,
        "claim_ids": claim_ids,
        "source_ids": source_ids,
        "signal_version_id": signal_version["signal_version_id"],
    }


def rewrite_signal_report_headings(args: argparse.Namespace) -> dict[str, Any]:
    """Apply user-supplied exact heading maps through the normal analysis update path."""
    root = require_store(Path(args.root))
    mapping_path = Path(args.mapping_file)
    try:
        mapping_payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid heading mapping file: {exc}") from exc
    if not isinstance(mapping_payload, dict) or not mapping_payload:
        raise ValueError("heading mapping file must map signal IDs to heading maps")

    signals = _records_by_id(signal_records(root), "signal_id")
    insights = _records_by_id(insight_records(root), "insight_id")
    rewritten_by_signal: dict[str, str] = {}
    for signal_id, replacements in mapping_payload.items():
        signal = signals.get(str(signal_id))
        if signal is None:
            raise ValueError(f"Unknown signal ID: {signal_id}")
        insight = insights.get(str(signal.get("insight_id") or ""))
        if insight is None:
            raise ValueError(f"Broken insight link for Signal: {signal_id}")
        if not isinstance(replacements, dict):
            raise ValueError(f"{signal_id}: heading map must be an object")
        rewritten_by_signal[str(signal_id)] = rewrite_analysis_headings(
            str(insight.get("analysis_markdown") or ""), replacements
        )

    updated: list[dict[str, Any]] = []
    for signal_id, markdown in rewritten_by_signal.items():
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".md", delete=False
            ) as handle:
                handle.write(markdown)
                temp_path = Path(handle.name)
            updated.append(
                set_signal_analysis(
                    argparse.Namespace(
                        root=str(root),
                        signal_id=signal_id,
                        analysis_file=str(temp_path),
                        structured_analysis_file=None,
                        claim_id=[],
                    )
                )
            )
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
    return {
        "action": "signal_report_headings_rewritten",
        "updated_count": len(updated),
        "signal_ids": [item["signal_id"] for item in updated],
    }


def set_impact_estimate(args: argparse.Namespace) -> dict[str, Any]:
    """Attach or replace a validated What-if model on an existing Signal."""
    root = require_store(Path(args.root))
    signals = _records_by_id(signal_records(root), "signal_id")
    signal = signals.get(args.signal_id)
    if signal is None:
        raise ValueError(f"Unknown signal ID: {args.signal_id}")
    insight_id = str(signal.get("insight_id") or "")
    insight_paths = {
        str(record.get("insight_id")): (path, record)
        for path, record in insight_records(root)
        if record.get("insight_id")
    }
    if insight_id not in insight_paths:
        raise ValueError(f"Broken insight link: {insight_id}")
    estimate = read_impact_estimate(args.estimate_file)
    if estimate is None:
        raise ValueError("estimate_file is required")
    referenced_sources = {
        str(source_id)
        for variable in estimate["variables"]
        for source_id in variable.get("source_ids", [])
    }
    verify_source_ids(root, sorted(referenced_sources))
    insight_path, insight = insight_paths[insight_id]
    decision = modeled_quantification_decision(estimate)
    insight["impact_estimate"] = estimate
    insight["quantification_decision"] = decision
    sync_structured_quantification_decision(
        insight.get("analysis_structured"), decision
    )
    insight["updated_at"] = timestamp()
    write_json(insight_path, insight)
    sync_obsidian_store(root)
    append_log(root, "set-impact-estimate", f"{args.signal_id}: {estimate['title']}")
    return {
        "action": "impact_estimate_updated",
        "signal_id": args.signal_id,
        "insight_id": insight_id,
    }


def set_quantification_decision(args: argparse.Namespace) -> dict[str, Any]:
    """Record the narrow not-applicable exception for a Signal without a model."""
    root = require_store(Path(args.root))
    signals = _records_by_id(signal_records(root), "signal_id")
    signal = signals.get(args.signal_id)
    if signal is None:
        raise ValueError(f"Unknown signal ID: {args.signal_id}")
    insight_id = str(signal.get("insight_id") or "")
    insight_paths = {
        str(record.get("insight_id")): (path, record)
        for path, record in insight_records(root)
        if record.get("insight_id")
    }
    if insight_id not in insight_paths:
        raise ValueError(f"Broken insight link: {insight_id}")
    insight_path, insight = insight_paths[insight_id]
    if insight.get("impact_estimate") is not None:
        raise ValueError(
            "Signal already has impact_estimate; replace the model instead of "
            "marking it not_applicable"
        )
    decision = read_quantification_decision(args.decision_file)
    if decision is None or decision.get("status") != "not_applicable":
        raise ValueError("decision_file must use status not_applicable")
    unknown_related = sorted(
        set(decision.get("related_signal_ids", [])) - set(signals)
    )
    if unknown_related:
        raise ValueError(
            "Unknown related Signal IDs: " + ", ".join(unknown_related)
        )
    insight["quantification_decision"] = decision
    sync_structured_quantification_decision(
        insight.get("analysis_structured"), decision
    )
    insight["updated_at"] = timestamp()
    write_json(insight_path, insight)
    sync_obsidian_store(root)
    append_log(
        root,
        "set-quantification-decision",
        f"{args.signal_id}: {decision['reason_code']}",
    )
    return {
        "action": "quantification_decision_updated",
        "signal_id": args.signal_id,
        "insight_id": insight_id,
        "status": decision["status"],
    }


def set_signal_assessment(args: argparse.Namespace) -> dict[str, Any]:
    """Reassess an existing Signal on the governed 1-10 rubric with claim history."""
    root = require_store(Path(args.root))
    signal_paths = {
        str(record.get("signal_id")): (path, record)
        for path, record in signal_records(root)
    }
    if args.signal_id not in signal_paths:
        raise ValueError(f"Unknown signal ID: {args.signal_id}")
    signal_path, signal = signal_paths[args.signal_id]
    insight_id = str(signal.get("insight_id") or "")
    insight_path = root / INSIGHTS_DIR / f"{insight_id}.json"
    if not record_exists(root, "insights", insight_id):
        raise ValueError(f"Broken insight link: {insight_id}")
    insight = read_json(insight_path)

    impact_score = int(args.business_impact_score)
    urgency_score = int(args.urgency_score)
    if impact_score not in range(1, SIGNAL_SCORE_MAX + 1):
        raise ValueError(f"business impact score must be between 1 and {SIGNAL_SCORE_MAX}")
    if urgency_score not in range(1, SIGNAL_SCORE_MAX + 1):
        raise ValueError(f"urgency score must be between 1 and {SIGNAL_SCORE_MAX}")
    business_impact_rationale = validate_score_rationale(
        "business_impact", impact_score, args.business_impact_rationale
    )
    urgency_rationale = validate_score_rationale(
        "urgency", urgency_score, args.urgency_rationale
    )
    assessed_at = validate_date(args.assessed_at, "assessed_at") or today()

    exceptional_basis = {
        "enterprise_scope": str(getattr(args, "enterprise_scope", None) or "").strip(),
        "immediate_action": str(getattr(args, "immediate_action", None) or "").strip(),
        "delay_loss": str(getattr(args, "delay_loss", None) or "").strip(),
        "irreversibility": str(getattr(args, "irreversibility", None) or "").strip(),
    }
    if impact_score == 10 and not all(exceptional_basis.values()):
        raise ValueError(
            "사업영향도 10점은 --enterprise-scope, --immediate-action, --delay-loss, "
            "--irreversibility 근거가 모두 필요합니다"
        )

    claims_by_id = _records_by_id(claim_records(root), "claim_id")
    claim_paths = {claim_id: root / CLAIMS_DIR / f"{claim_id}.json" for claim_id in claims_by_id}
    active_by_predicate = {
        str(claims_by_id[claim_id].get("predicate") or ""): claims_by_id[claim_id]
        for claim_id in (str(item) for item in insight.get("claim_ids", []))
        if claim_id in claims_by_id and claims_by_id[claim_id].get("status") == "active"
    }
    updates = {
        "business_impact_score_1_to_10": str(impact_score),
        "business_impact_rationale": business_impact_rationale,
        "urgency_score_1_to_10": str(urgency_score),
        "urgency_rationale": urgency_rationale,
        "assessment_confidence": str(args.assessment_confidence),
        "assessed_at": assessed_at,
    }
    replacements: dict[str, str] = {}
    for predicate, value in updates.items():
        old_claim = active_by_predicate.get(predicate)
        if old_claim is None:
            raise ValueError(f"{args.signal_id}: missing active assessment claim {predicate}")
        old_id = str(old_claim["claim_id"])
        if normalize_text(str(old_claim.get("value") or "")) == normalize_text(value):
            continue
        new_id = claim_id_for(str(old_claim.get("subject_id") or ""), predicate, value)
        new_claim = claims_by_id.get(new_id)
        if new_claim is None:
            new_claim = {
                **old_claim,
                "schema_version": CLAIM_SCHEMA_VERSION,
                "claim_id": new_id,
                "claim_version_id": _stable_node_id("CLMV", new_id, 1, *old_claim.get("source_ids", [])),
                "version_no": 1,
                "value": value,
                "status": "active",
                "first_seen": assessed_at,
                "last_verified": assessed_at,
                "supersedes": [old_id],
                "coexists_with": [],
                "history": [
                    {
                        "date": assessed_at,
                        "action": "created",
                        "reason": str(args.reason).strip(),
                        "source_ids": list(old_claim.get("source_ids", [])),
                    }
                ],
            }
            write_json(root / CLAIMS_DIR / f"{new_id}.json", new_claim)
            put_claim_version(root, new_claim)
            if new_claim.get("risk_factor_ids"):
                put_risk_factor_links(
                    root,
                    subject_kind="claim",
                    subject_version_id=new_claim["claim_version_id"],
                    risk_factor_ids=list(new_claim["risk_factor_ids"]),
                )
            claims_by_id[new_id] = new_claim
        elif new_claim.get("status") == "superseded":
            new_claim["schema_version"] = CLAIM_SCHEMA_VERSION
            new_claim["version_no"] = int(new_claim.get("version_no") or 1) + 1
            new_claim["claim_version_id"] = _stable_node_id(
                "CLMV", new_id, new_claim["version_no"], *new_claim.get("source_ids", [])
            )
            new_claim["status"] = "active"
            new_claim.pop("superseded_by", None)
            new_claim["last_verified"] = assessed_at
            new_claim.setdefault("history", []).append(
                {
                    "date": assessed_at,
                    "action": "reactivated",
                    "reason": str(args.reason).strip(),
                    "source_ids": list(new_claim.get("source_ids", [])),
                }
            )
            write_json(root / CLAIMS_DIR / f"{new_id}.json", new_claim)
            put_claim_version(root, new_claim)
            if new_claim.get("risk_factor_ids"):
                put_risk_factor_links(
                    root,
                    subject_kind="claim",
                    subject_version_id=new_claim["claim_version_id"],
                    risk_factor_ids=list(new_claim["risk_factor_ids"]),
                )
        elif new_claim.get("status") != "active":
            raise ValueError(
                f"{new_id}: only a superseded reassessment claim can be reactivated"
            )
        old_claim["status"] = "superseded"
        old_claim["schema_version"] = CLAIM_SCHEMA_VERSION
        old_claim["version_no"] = int(old_claim.get("version_no") or 1) + 1
        old_claim["claim_version_id"] = _stable_node_id(
            "CLMV", old_id, old_claim["version_no"], *old_claim.get("source_ids", [])
        )
        old_claim["superseded_by"] = new_id
        old_claim.setdefault("history", []).append(
            {
                "date": assessed_at,
                "action": "superseded",
                "reason": str(args.reason).strip(),
            }
        )
        write_json(claim_paths[old_id], old_claim)
        put_claim_version(root, old_claim)
        if old_claim.get("risk_factor_ids"):
            put_risk_factor_links(
                root,
                subject_kind="claim",
                subject_version_id=old_claim["claim_version_id"],
                risk_factor_ids=list(old_claim["risk_factor_ids"]),
            )
        replacements[old_id] = new_id

    def replace_claim_ids(record: dict[str, Any]) -> None:
        record["claim_ids"] = list(
            dict.fromkeys(
                replacements.get(str(claim_id), str(claim_id))
                for claim_id in record.get("claim_ids", [])
            )
        )

    replace_claim_ids(signal)
    replace_claim_ids(insight)
    structured_replacements = {
        str(claim_id): str(claim.get("superseded_by"))
        for claim_id, claim in claims_by_id.items()
        if str(claim.get("superseded_by") or "").strip()
    }
    structured_replacements.update(replacements)

    def replace_structured_claim_ids(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "claim_ids" and isinstance(item, list):
                    value[key] = list(
                        dict.fromkeys(
                            structured_replacements.get(
                                str(claim_id), str(claim_id)
                            )
                            for claim_id in item
                        )
                    )
                else:
                    replace_structured_claim_ids(item)
        elif isinstance(value, list):
            for item in value:
                replace_structured_claim_ids(item)

    replace_structured_claim_ids(insight.get("analysis_structured"))
    signal["business_impact"] = {
        **(signal.get("business_impact") or {}),
        "score": impact_score,
        "rationale": business_impact_rationale,
    }
    signal["urgency"] = {
        **(signal.get("urgency") or {}),
        "score": urgency_score,
        "rationale": urgency_rationale,
    }
    signal["assessment_confidence"] = args.assessment_confidence
    signal["assessed_at"] = assessed_at
    signal["score_scale"] = {
        "version": 1,
        "minimum": 1,
        "maximum": SIGNAL_SCORE_MAX,
        "calibration": "rubric_v1",
        "note": "기존·신규 구분 없이 같은 1~10 rubric으로 재평가",
    }
    if impact_score == 10:
        signal["exceptional_score_basis"] = exceptional_basis
    else:
        signal.pop("exceptional_score_basis", None)
    signal["updated_at"] = timestamp()
    insight["updated_at"] = timestamp()
    write_json(insight_path, insight)
    signal_version = refresh_signal_analytics_version(root, signal, insight)
    sync_obsidian_store(root)
    append_log(root, "set-signal-assessment", f"{args.signal_id}: {impact_score}/{urgency_score}")
    return {
        "action": "signal_assessment_updated",
        "signal_id": args.signal_id,
        "business_impact_score": impact_score,
        "urgency_score": urgency_score,
        "assessment_confidence": args.assessment_confidence,
        "superseded_claims": len(replacements),
        "signal_version_id": signal_version["signal_version_id"],
    }


def migrate_signal_scores(args: argparse.Namespace) -> dict[str, Any]:
    """Migrate governed Signal assessments from the legacy 1-5 scale to 1-10."""
    root = require_store(Path(args.root))
    migration_date = validate_date(
        getattr(args, "migrated_at", None), "migrated_at"
    ) or today()
    old_predicates = {
        "business_impact_score_1_to_5": "business_impact_score_1_to_10",
        "urgency_score_1_to_5": "urgency_score_1_to_10",
    }
    claim_paths = {claim["claim_id"]: path for path, claim in claim_records(root)}
    claims_by_id = _records_by_id(claim_records(root), "claim_id")
    replacement_ids: dict[str, str] = {}
    migrated_claims = 0

    for old_id, old_claim in list(claims_by_id.items()):
        old_predicate = str(old_claim.get("predicate") or "")
        new_predicate = old_predicates.get(old_predicate)
        if not new_predicate or old_claim.get("status") != "active":
            continue
        try:
            legacy_score = int(str(old_claim.get("value") or ""))
        except ValueError as exc:
            raise ValueError(f"{old_id}: legacy score must be an integer") from exc
        if legacy_score not in range(1, 6):
            raise ValueError(f"{old_id}: legacy score must be between 1 and 5")
        # Preserve ordinal meaning without inflating the old maximum into the new
        # exceptional 9-10 band. Those scores require a fresh rubric assessment.
        calibrated_score = {1: 1, 2: 3, 3: 5, 4: 7, 5: 8}[legacy_score]
        new_value = str(calibrated_score)
        new_id = claim_id_for(
            str(old_claim.get("subject_id") or ""), new_predicate, new_value
        )
        existing_new = claims_by_id.get(new_id)
        if existing_new and existing_new.get("status") != "active":
            raise ValueError(f"{new_id}: migrated score claim already exists but is not active")
        if not existing_new:
            new_claim = {
                **old_claim,
                "claim_id": new_id,
                "predicate": new_predicate,
                "value": new_value,
                "status": "active",
                "first_seen": migration_date,
                "last_verified": migration_date,
                "supersedes": [old_id],
                "coexists_with": [],
                "history": [
                    {
                        "date": migration_date,
                        "action": "created",
                        "reason": "담당 임원 지침에 따라 1~5 평가를 임시 기준점의 1~10 척도로 전환; 8점은 상한이 아니며 새 rubric 재평가 대상",
                        "source_ids": list(old_claim.get("source_ids", [])),
                    }
                ],
            }
            write_json(root / CLAIMS_DIR / f"{new_id}.json", new_claim)
            claims_by_id[new_id] = new_claim
            migrated_claims += 1

        old_claim["status"] = "superseded"
        old_claim["superseded_by"] = new_id
        old_claim.setdefault("history", []).append(
            {
                "date": migration_date,
                "action": "superseded",
                "reason": "평가 척도를 1~5에서 1~10으로 전환",
            }
        )
        write_json(claim_paths[old_id], old_claim)
        replacement_ids[old_id] = new_id

    migrated_signals = 0
    for signal_path, signal in signal_records(root):
        if signal.get("schema_version") == SIGNAL_SCHEMA_VERSION:
            if (signal.get("score_scale") or {}).get("calibration") != "legacy_anchor":
                continue
            if not any(
                str(claim_id) in replacement_ids for claim_id in signal.get("claim_ids", [])
            ):
                continue
        elif signal.get("schema_version") != 2:
            raise ValueError(
                f"{signal.get('signal_id')}: expected schema_version 2 before score migration"
            )
        else:
            for field in ("business_impact", "urgency"):
                score = (signal.get(field) or {}).get("score")
                if not isinstance(score, int) or score not in range(1, 6):
                    raise ValueError(
                        f"{signal.get('signal_id')}: legacy {field} score must be between 1 and 5"
                    )
                signal[field]["score"] = {1: 1, 2: 3, 3: 5, 4: 7, 5: 8}[score]
        signal["score_scale"] = {
            "version": 1,
            "minimum": 1,
            "maximum": SIGNAL_SCORE_MAX,
            "calibration": "legacy_anchor",
            "note": "기존 1~5 평가는 1·3·5·7·8 임시 기준점으로 이관하며 8점은 상한이 아님; 기존 Signal도 새 rubric에서 9~10점 재평가 가능",
        }
        signal["schema_version"] = SIGNAL_SCHEMA_VERSION
        signal["claim_ids"] = [
            replacement_ids.get(str(claim_id), str(claim_id))
            for claim_id in signal.get("claim_ids", [])
        ]
        signal["updated_at"] = timestamp()
        write_json(signal_path, signal)

        insight_id = str(signal.get("insight_id") or "")
        insight_path = root / INSIGHTS_DIR / f"{insight_id}.json"
        if not record_exists(root, "insights", insight_id):
            raise ValueError(f"{signal.get('signal_id')}: missing Insight {insight_id}")
        insight = read_json(insight_path)
        insight["claim_ids"] = [
            replacement_ids.get(str(claim_id), str(claim_id))
            for claim_id in insight.get("claim_ids", [])
        ]
        insight["updated_at"] = timestamp()
        write_json(insight_path, insight)
        migrated_signals += 1

    sync_obsidian_store(root)
    append_log(
        root,
        "migrate-signal-scores",
        f"1~5 -> calibrated 1~10: {migrated_signals} Signals, {migrated_claims} assessment Claims",
    )
    return {
        "action": "signal_scores_migrated",
        "schema_version": SIGNAL_SCHEMA_VERSION,
        "signals": migrated_signals,
        "claims": migrated_claims,
    }


def _legacy_risk_factor(signal: dict[str, Any]) -> dict[str, Any]:
    """Create one stable governed risk factor for a legacy axis/change-type pair."""

    business_axis = str(signal.get("business_axis") or "미분류").strip()
    signal_type = str(signal.get("signal_type") or "외부 변화").strip()
    digest = hashlib.sha256(
        f"{business_axis}\0{signal_type}".encode("utf-8")
    ).hexdigest()[:16].upper()
    categories = {
        "정책·규제": "POLICY_REGULATION",
        "수급·가격": "SUPPLY_DEMAND",
        "경쟁사": "COMPETITION",
        "투자·프로젝트": "INVESTMENT_PROJECT",
        "공급망·물류": "SUPPLY_CHAIN",
        "고객·계약": "CUSTOMER_CONTRACT",
        "기술·운영": "TECHNOLOGY_OPERATIONS",
        "재무·실적": "FINANCE_PERFORMANCE",
    }
    return validate_risk_factor(
        {
            "risk_factor_id": f"RF-{digest}",
            "taxonomy_version": 1,
            "name": f"{business_axis} · {signal_type}",
            "definition": (
                f"{business_axis} 사업축에서 {signal_type} 변화가 사업 판단과 대응 시점을 "
                "바꾸는 공통 위험요인"
            ),
            "category": categories.get(signal_type, "MARKET_CHANGE"),
            "status": "active",
        }
    )


def migrate_analytics_contract(args: argparse.Namespace) -> dict[str, Any]:
    """Adopt legacy Source, Claim, Insight, and Signal rows into the canonical contract."""

    root = require_store(Path(args.root))
    backup_path = (
        root
        / "data"
        / "backups"
        / f"market_sensing-before-analytics-contract-{datetime.now().strftime('%Y%m%dT%H%M%S')}.db"
    )
    online_backup(root, backup_path)

    migrated_sources = 0
    for path, source in source_records(root):
        changed = (
            source.get("schema_version") != SOURCE_SCHEMA_VERSION
            or not source.get("source_modality")
        )
        source["schema_version"] = SOURCE_SCHEMA_VERSION
        source["source_modality"] = validate_modality(
            source.get("source_modality") or args.legacy_source_modality
        )
        if changed:
            source["updated_at"] = timestamp()
            migrated_sources += 1
        write_json(path, source)
        put_source_asset(root, source)

    migrated_claims = 0
    for path, claim in claim_records(root):
        changed = (
            claim.get("schema_version") != CLAIM_SCHEMA_VERSION
            or not claim.get("claim_version_id")
            or int(claim.get("version_no") or 0) < 1
        )
        claim["schema_version"] = CLAIM_SCHEMA_VERSION
        claim["version_no"] = max(1, int(claim.get("version_no") or 1))
        claim["claim_version_id"] = str(
            claim.get("claim_version_id")
            or _stable_node_id(
                "CLMV",
                str(claim.get("claim_id") or ""),
                str(claim["version_no"]),
                *(str(item) for item in claim.get("source_ids", [])),
            )
        )
        claim["risk_factor_ids"] = list(
            dict.fromkeys(str(item) for item in claim.get("risk_factor_ids", []))
        )
        if changed:
            migrated_claims += 1
        write_json(path, claim)
        put_claim_version(root, claim)

    migrated_signals = 0
    created_risk_factors: set[str] = set()
    insights = _records_by_id(insight_records(root), "insight_id")
    for _, signal in signal_records(root):
        if (
            signal.get("schema_version") == SIGNAL_SCHEMA_VERSION
            and signal.get("canonical_key")
            and signal.get("signal_version_id")
            and signal.get("risk_factor_ids")
            and signal.get("evidence_refs")
        ):
            continue
        insight_id = str(signal.get("insight_id") or "")
        insight = insights.get(insight_id)
        if insight is None:
            raise ValueError(f"{signal.get('signal_id')}: missing Insight {insight_id}")
        insight["schema_version"] = INSIGHT_SCHEMA_VERSION
        write_json(root / INSIGHTS_DIR / f"{insight_id}.json", insight)

        risk_factor = _legacy_risk_factor(signal)
        put_risk_factor(root, risk_factor)
        created_risk_factors.add(str(risk_factor["risk_factor_id"]))
        signal_id = str(signal.get("signal_id") or "")
        suffix = signal_id.removeprefix("SIG-").casefold()
        signal.update(
            {
                "schema_version": SIGNAL_SCHEMA_VERSION,
                "canonical_key": str(
                    signal.get("canonical_key") or f"legacy.signal.{suffix}"
                ),
                "risk_factor_ids": list(
                    dict.fromkeys(
                        [
                            *(str(item) for item in signal.get("risk_factor_ids", [])),
                            str(risk_factor["risk_factor_id"]),
                        ]
                    )
                ),
            }
        )
        refresh_signal_analytics_version(root, signal, insight)
        migrated_signals += 1

    sync_obsidian_store(root)
    append_log(
        root,
        "migrate-analytics-contract",
        (
            f"Source {migrated_sources}, Claim {migrated_claims}, Signal "
            f"{migrated_signals}, RiskFactor {len(created_risk_factors)}"
        ),
    )
    return {
        "action": "analytics_contract_migrated",
        "backup": str(backup_path),
        "sources": migrated_sources,
        "claims": migrated_claims,
        "signals": migrated_signals,
        "risk_factors": len(created_risk_factors),
    }


def _archive_excerpt(root: Path, source: dict[str, Any], limit: int = 2400) -> str | None:
    raw = get_source_content(root, str(source.get("source_id") or ""))
    if raw is None:
        return None
    text = raw.decode("utf-8", errors="replace").strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def trace_signal(args: argparse.Namespace) -> dict[str, Any]:
    """Return progressively deeper graph context for an LLM or web client."""
    root = require_store(Path(args.root))
    depth = int(args.depth)
    if depth not in range(1, 5):
        raise ValueError("depth must be between 1 and 4")
    signals = _records_by_id(signal_records(root), "signal_id")
    signal = signals.get(args.signal_id)
    if signal is None:
        raise ValueError(f"Unknown signal ID: {args.signal_id}")
    result: dict[str, Any] = {"action": "signal_trace", "depth": depth, "signal": signal}
    if depth == 1:
        return result
    insight = _records_by_id(insight_records(root), "insight_id").get(
        str(signal.get("insight_id"))
    )
    if insight is None:
        raise ValueError(f"Broken insight link: {signal.get('insight_id')}")
    result["insight"] = insight
    if depth == 2:
        return result
    claims_by_id = _records_by_id(claim_records(root), "claim_id")
    document_id = str(insight.get("document_path") or "")
    document_artifact = get_artifact(root, document_id) if document_id else None
    result["document"] = {
        "artifact_id": document_id or None,
        "structured": insight.get("analysis_structured"),
        "markdown": insight.get("analysis_markdown")
        or (document_artifact or {}).get("markdown_text"),
    }
    result["claims"] = [
        claims_by_id[claim_id]
        for claim_id in insight.get("claim_ids", [])
        if claim_id in claims_by_id
    ]
    if depth == 3:
        return result
    sources_by_id = _records_by_id(source_records(root), "source_id")
    result["sources"] = [
        {
            **sources_by_id[source_id],
            "archive_excerpt": _archive_excerpt(root, sources_by_id[source_id]),
        }
        for source_id in insight.get("source_ids", [])
        if source_id in sources_by_id
    ]
    result["edges"] = {
        "signal_to_insight": [signal["signal_id"], insight["insight_id"]],
        "insight_to_claims": insight.get("claim_ids", []),
        "claims_to_sources": {
            claim["claim_id"]: claim.get("source_ids", []) for claim in result["claims"]
        },
    }
    return result


def markdown_cell(value: Any) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("[[", "\\[\\[")
    )


def humanize_timestamp(value: Any) -> str:
    """Render an ISO timestamp compactly for reader-facing tables."""
    timestamp_value = str(value or "-")
    if "T" in timestamp_value and len(timestamp_value) >= 16:
        return timestamp_value[:16].replace("T", " ")
    return timestamp_value


def markdown_alt(value: Any) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def media_for_display(media: dict[str, Any]) -> dict[str, Any]:
    override = MEDIA_DISPLAY_OVERRIDES.get(str(media.get("media_id") or ""))
    return {**media, **override} if override else media


def media_width_class(media: dict[str, Any]) -> str:
    """Keep ordinary photos compact; reserve wide display for readable diagrams."""
    display_width = str(media.get("display_width") or "")
    if display_width == "compact":
        return ".steel-media-compact"
    if display_width == "detail":
        return ".steel-media-detail"
    kind = str(media.get("kind") or "other")
    if kind in {
        "equipment_drawing",
        "patent_figure",
        "academic_figure",
        "process_diagram",
    }:
        return ".steel-media-detail"
    return ".steel-media-compact"


def source_ids_with_subject_media(
    source_ids: list[str],
    sources_by_id: dict[str, dict[str, Any]],
    subject_id: str | None,
) -> list[str]:
    """Include explicitly scoped media even when its source supports a related subject."""
    ordered = list(dict.fromkeys(source_ids))
    if not subject_id:
        return ordered
    seen = set(ordered)
    for source_id, source in sources_by_id.items():
        if source_id in seen:
            continue
        if any(
            subject_id
            in {
                str(item)
                for item in media.get("subject_ids", [])
                if str(item)
            }
            for media in source.get("images", [])
        ):
            ordered.append(source_id)
            seen.add(source_id)
    return ordered


def media_gallery_lines(
    source_ids: list[str],
    sources_by_id: dict[str, dict[str, Any]],
    excluded_media_ids: set[str] | None = None,
    subject_id: str | None = None,
) -> list[str]:
    items: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    excluded = excluded_media_ids or set()
    for source_id in source_ids_with_subject_media(
        source_ids, sources_by_id, subject_id
    ):
        for media in sources_by_id.get(source_id, {}).get("images", []):
            media_id = str(media.get("media_id", ""))
            display_media = media_for_display(media)
            if display_media.get("display_eligible") is False:
                continue
            scoped_subjects = {
                str(item)
                for item in display_media.get("subject_ids", [])
                if str(item)
            }
            if scoped_subjects and subject_id and subject_id not in scoped_subjects:
                continue
            if media_id and media_id not in seen and media_id not in excluded:
                seen.add(media_id)
                items.append((source_id, display_media))
    if not items:
        return []

    lines = ["", "## 설비·공정 이미지", ""]
    for source_id, media in items:
        kind = str(media.get("kind") or "other")
        kind_label = MEDIA_KIND_LABELS.get(kind, "기술 이미지")
        caption = str(media.get("caption") or kind_label)
        local_path = str(media.get("local_path") or "")
        image_url = str(media.get("image_url") or "")
        origin_url = str(media.get("origin_url") or "")
        width_class = media_width_class(media)
        if local_path:
            lines.extend(
                [
                    f"![{markdown_alt(media.get('alt_text') or caption)}]"
                    f"(../{local_path}){{ .steel-media-image {width_class} }}",
                    "",
                ]
            )
        elif image_url:
            lines.extend(
                [
                    f"![{markdown_alt(media.get('alt_text') or caption)}]"
                    f"(<{image_url}>){{ .steel-media-image {width_class} }}",
                    "",
                ]
            )
        source_link = wikilink(Path("sources") / f"{source_id}.md", source_id)
        details = [
            f"출처 {source_link}",
            f"권리 `{markdown_cell(media.get('rights_status') or '-')}`",
        ]
        if origin_url:
            details.append(f"[원문 페이지]({origin_url})")
        creator = str(media.get("creator") or "")
        if creator:
            details.append(f"작성·촬영 {markdown_cell(creator)}")
        lines.extend(
            [
                f"**{markdown_cell(kind_label)}.** {markdown_cell(caption)}",
                "",
                "- " + " · ".join(details),
                f"- 권리 메모: {markdown_cell(media.get('rights_note') or '-')}",
                "",
            ]
        )
    return lines


def representative_image_lines(
    source_ids: list[str],
    sources_by_id: dict[str, dict[str, Any]],
    subject_id: str | None = None,
    preferred_kinds: tuple[str, ...] = (
        "equipment_drawing",
        "patent_figure",
        "academic_figure",
        "process_diagram",
        "facility_photo",
        "ai_reconstruction",
        "other",
    ),
) -> tuple[list[str], set[str]]:
    kind_priority = {
        kind: index for index, kind in enumerate(preferred_kinds)
    }
    candidates: list[tuple[int, int, int, str, dict[str, Any]]] = []
    for source_id in source_ids_with_subject_media(
        source_ids, sources_by_id, subject_id
    ):
        for raw_media in sources_by_id.get(source_id, {}).get("images", []):
            media = media_for_display(raw_media)
            if (
                media.get("display_eligible") is False
                or media.get("hero_eligible") is False
            ):
                continue
            scoped_subjects = {
                str(item)
                for item in media.get("subject_ids", [])
                if str(item)
            }
            if scoped_subjects and subject_id and subject_id not in scoped_subjects:
                continue
            local_path = str(media.get("local_path") or "")
            image_url = str(media.get("image_url") or "")
            media_kind = str(media.get("kind") or "other")
            manual_rank = int(media.get("hero_priority") or 0)
            preferred_rank = kind_priority.get(
                media_kind,
                len(kind_priority),
            )
            if local_path:
                candidates.append(
                    (manual_rank, preferred_rank, 0, source_id, media)
                )
            elif image_url:
                candidates.append(
                    (manual_rank, preferred_rank, 1, source_id, media)
                )

    if not candidates:
        return ([], set())

    _, _, _, source_id, media = min(
        candidates,
        key=lambda item: (item[0], item[1], item[2], item[3]),
    )
    local_path = str(media.get("local_path") or "")
    image_url = str(media.get("image_url") or "")
    media_id = str(media.get("media_id") or "")
    caption = str(media.get("caption") or "기술 대표 이미지")
    kind = str(media.get("kind") or "other")
    rights_status = str(media.get("rights_status") or "-")
    origin_url = str(media.get("origin_url") or "")
    width_class = media_width_class(media)
    image_target = f"../{local_path}" if local_path else f"<{image_url}>"
    metadata = [
        markdown_cell(MEDIA_KIND_LABELS.get(kind, "기술 이미지")),
        f"권리 `{markdown_cell(rights_status)}`",
        f"출처 {wikilink(Path('sources') / f'{source_id}.md', source_id)}",
    ]
    if origin_url:
        metadata.append(f"[원문 페이지]({origin_url})")
    return (
        [
            "",
            f"![{markdown_alt(media.get('alt_text') or caption)}]"
            f"({image_target})"
            f"{{ .steel-media-image .steel-hero-image {width_class} }}",
            "",
            f"*대표 이미지 — {markdown_cell(caption)} "
            f"({' · '.join(metadata)})*",
            "",
        ],
        {media_id} if media_id else set(),
    )


def subject_path(subject_id: str) -> Path:
    prefix = subject_id.partition("-")[0].upper()
    folder = SUBJECT_FOLDERS.get(prefix, "entities")
    filename = re.sub(r"[^A-Za-z0-9가-힣._-]+", "-", subject_id).strip("-")
    return Path(folder) / f"{filename or 'entity'}.md"


def technology_page_path(technology: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", technology.casefold()).strip("-")
    return Path("technologies") / f"TEC-{slug or 'technology'}.md"


def subject_display_name(subject_id: str, settings: dict[str, Any]) -> str:
    prefix, _, remainder = subject_id.partition("-")
    if prefix.upper() == "PRJ":
        return PROJECT_DISPLAY_NAMES.get(subject_id, subject_id)
    if prefix.upper() != "COM" or not remainder:
        return subject_id
    governed_name = next(
        (
            company_name
            for company_name, company_id in COMPANY_NAME_TO_ID.items()
            if company_id == subject_id
        ),
        None,
    )
    if governed_name:
        return governed_name
    normalized_subject = re.sub(r"[^a-z0-9]+", "", remainder.casefold())
    companies = sorted(
        settings.get("companies", []),
        key=lambda company: len(re.sub(r"[^a-z0-9]+", "", str(company).casefold())),
        reverse=True,
    )
    for company in companies:
        normalized_company = re.sub(r"[^a-z0-9]+", "", str(company).casefold())
        if normalized_subject == normalized_company:
            return str(company)
    return remainder.replace("-", " ")


def reader_subject_name(subject_id: str, settings: dict[str, Any]) -> str:
    if subject_id.startswith("TEC-"):
        for technology, detail in TECHNOLOGY_DETAILS.items():
            if technology_page_path(technology).stem == subject_id:
                return str(detail.get("label") or technology)
    return subject_display_name(subject_id, settings)


def wikilink(path: Path, label: str) -> str:
    target = path.with_suffix("").as_posix()
    return f"[[{target}|{markdown_cell(label)}]]"


def source_reference(
    source_id: str, _sources_by_id: dict[str, dict[str, Any]]
) -> str:
    return wikilink(
        Path("sources") / f"{source_id}.md",
        ":material-link-variant:",
    )


def claim_source_references(
    claim: dict[str, Any], sources_by_id: dict[str, dict[str, Any]]
) -> str:
    return ", ".join(
        source_reference(str(source_id), sources_by_id)
        for source_id in claim.get("source_ids", [])
    )


def source_footnote_reference(source_id: str) -> str:
    return f"[^{source_id.casefold()}]"


def claim_source_footnote_references(claim: dict[str, Any]) -> str:
    return "".join(
        source_footnote_reference(str(source_id))
        for source_id in claim.get("source_ids", [])
    )


def source_footnote_definition(
    source_id: str, sources_by_id: dict[str, dict[str, Any]]
) -> str:
    record = sources_by_id.get(source_id, {})
    title = markdown_cell(record.get("title") or source_id)
    publisher = markdown_cell(record.get("publisher") or "발행자 미상")
    published_at = markdown_cell(record.get("published_at") or "게시일 미상")
    url = str(record.get("url") or "")
    original = f"[원문]({url}) · " if url else ""
    archive = wikilink(
        Path("sources") / f"{source_id}.md",
        "보관 원문·메타데이터",
    )
    academic = record.get("academic") if isinstance(record.get("academic"), dict) else {}
    doi = str(academic.get("doi") or "")
    academic_suffix = f" DOI: [{doi}](https://doi.org/{doi})." if doi else ""
    return (
        f"[^{source_id.casefold()}]: **{title}** — {publisher}, "
        f"{published_at}.{academic_suffix} {original}{archive}"
    )


def claim_source_dates(
    claim: dict[str, Any],
    sources_by_id: dict[str, dict[str, Any]],
    field: str,
) -> str:
    dates = sorted(
        {
            str(sources_by_id.get(str(source_id), {}).get(field))
            for source_id in claim.get("source_ids", [])
            if sources_by_id.get(str(source_id), {}).get(field)
        }
    )
    return ", ".join(dates) if dates else "미상"


def claim_evidence_label(
    claim: dict[str, Any], sources_by_id: dict[str, dict[str, Any]]
) -> str:
    labels = {
        "company_release": "회사 발표",
        "company_ir": "회사 IR",
        "government": "정부·공공자료",
        "permit": "인허가 자료",
        "patent": "특허",
        "academic": "학술 연구",
        "equipment_supplier": "설비 공급사",
        "specialist_media": "전문매체",
        "general_media": "일반 언론",
        "other": "기타",
    }
    academic_labels = {
        "journal_article": "학술지 논문",
        "conference_paper": "학회 논문",
        "conference_presentation": "학회 발표",
        "preprint": "프리프린트",
        "thesis": "학위논문",
        "research_report": "연구보고서",
    }
    result: list[str] = []
    for source_id in claim.get("source_ids", []):
        record = sources_by_id.get(str(source_id), {})
        source_type = str(record.get("source_type") or "other")
        label = labels.get(source_type, labels["other"])
        if source_type == "academic" and isinstance(record.get("academic"), dict):
            label = academic_labels.get(
                str(record["academic"].get("kind") or ""),
                label,
            )
        if label not in result:
            result.append(label)
    return "·".join(result) or "근거 유형 미상"


def claim_cross_validation_status(claim: dict[str, Any]) -> str:
    """Derive Claim corroboration without treating it as a publish gate."""
    if str(claim.get("status") or "") == "disputed":
        return "conflicted"
    source_ids = {
        str(source_id).strip()
        for source_id in claim.get("source_ids", [])
        if str(source_id).strip()
    }
    if len(source_ids) >= 2:
        return "independent"
    if len(source_ids) == 1:
        return "single"
    return "unknown"


def claim_is_cross_validatable(claim: dict[str, Any]) -> bool:
    """Keep source corroboration labels on externally verifiable facts."""
    return str(claim.get("predicate") or "") not in CROSS_VALIDATION_EXCLUDED_PREDICATES


def claim_cross_validation_label(claim: dict[str, Any]) -> str:
    status = claim_cross_validation_status(claim)
    return CLAIM_CROSS_VALIDATION_LABELS[status]


def claim_cross_validation_table_lines(
    claims: list[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
    *,
    limit: int = 12,
) -> list[str]:
    """Render Claim-level corroboration in the evidence section only."""
    claims = [claim for claim in claims if claim_is_cross_validatable(claim)]
    if not claims:
        return []
    lines = [
        "**교차검증**",
        "",
        "| 근거 항목 | 상태 | 원문 |",
        "| --- | --- | ---: |",
    ]
    for index, claim in enumerate(claims[:limit], start=1):
        predicate = str(claim.get("predicate") or "")
        label = PREDICATE_LABELS.get(predicate) or f"확인 근거 {index}"
        links = [
            wikilink(Path("sources") / f"{source_id}.md", "근거 보기")
            for source_id in dict.fromkeys(
                str(item) for item in claim.get("source_ids", [])
            )
            if source_id in sources_by_id
        ]
        lines.append(
            f"| **{markdown_cell(label)}** "
            f"| {markdown_cell(claim_cross_validation_label(claim))} "
            f"| {' · '.join(links) if links else '-'} |"
        )
    lines.append("")
    return lines


def humanize_claim_value(value: Any) -> str:
    """Clean internal shorthand for reader-facing dossiers without mutating claims."""
    text = str(value).replace(
        "Zhanjiang 근제로 라인",
        "Zhanjiang near-zero-carbon 생산라인",
    )
    exact_labels = {
        "research and development facility development": "연구개발 시설 구축 중",
        "construction": "건설 중",
        "USD 5.6 million federal funding selection": (
            "미 연방정부 지원 대상 선정 · 560만 달러"
        ),
        "USD 3 million federal funding selection": (
            "미 연방정부 지원 대상 선정 · 300만 달러"
        ),
        "USD 143 million": "1억 4,300만 달러 (USD 143 million)",
        "500 tpy": "연간 500톤 (500 tpy)",
        "3 tonnes per hour": "시간당 3톤 (3 tonnes per hour)",
    }
    return exact_labels.get(text, text)


def claim_latest_history_reason(claim: dict[str, Any]) -> str:
    if claim_is_data_correction(claim):
        return "입력 과정에서 누락된 통화 기호·금액을 공식 원문 기준으로 교정"
    for event in reversed(claim.get("history", [])):
        reason = str(event.get("reason") or "").strip()
        if reason:
            return reason
    return "-"


def claim_is_data_correction(claim: dict[str, Any]) -> bool:
    correction_signals = (
        "powershell",
        "입력 오류",
        "입력오류",
        "오탈자",
        "누락된 통화",
        "원문대로 교정",
    )
    return any(
        signal in str(event.get("reason") or "").casefold()
        for event in claim.get("history", [])
        for signal in correction_signals
    )


def humanize_historical_claim_value(claim: dict[str, Any]) -> str:
    if (
        str(claim.get("status") or "") == "superseded"
        and claim_is_data_correction(claim)
    ):
        return "입력 교정으로 대체됨 — 현재 유효 Claim과 원문 금액 참조"
    return humanize_claim_value(claim.get("value", ""))


def claim_stage(value: Any) -> tuple[str, str]:
    text = str(value).casefold()
    if any(
        signal in text
        for signal in (
            "진행 불가",
            "중단",
            "취소",
            "연기",
            "postpone",
            "cancel",
            "suspend",
        )
    ):
        return (
            "중단·연기 신호",
            "공식 발표에 실행 차질이 명시된 상태이므로 기존 목표 일정과 투자 지속 여부를 "
            "우선 재확인해야 합니다.",
        )
    if any(
        signal in text
        for signal in (
            "생산 개시",
            "생산을 개시",
            "상업 가동",
            "상업생산",
            "상용 운전",
        )
    ):
        return (
            "가동·현장 적용",
            "설비 준공을 넘어 생산 개시 또는 상용 운전이 확인됩니다. 이용률과 제품 단위 "
            "성과는 후속 운전 데이터로 계속 검증해야 합니다.",
        )
    if "준공" in text:
        return (
            "준공·가동 준비",
            "설비 구축 완료는 확인되지만 안정적인 상용 생산까지 확인된 것은 아닙니다. "
            "시운전, 가동률과 실제 제품 출하를 후속 자료로 확인해야 합니다.",
        )
    if any(
        signal in text
        for signal in ("건설 중", "착공", "조립 시작", "construction")
    ):
        return (
            "건설·구축",
            "설비 투자가 물리적 실행 단계에 들어갔습니다. 준공 일정, 공사비 변동과 "
            "시운전 결과가 다음 판단 기준입니다.",
        )
    operation_is_target = any(
        signal in text
        for signal in ("가동 목표", "가동 예정", "가동 계획", "시운전 예정")
    )
    if not operation_is_target and any(
        signal in text
        for signal in (
            "가동",
            "운영",
            "배치 완료",
            "생산라인",
        )
    ):
        return (
            "가동·현장 적용",
            "연구 발표를 넘어 설비 가동 또는 생산현장 적용이 확인됩니다. 다만 이용률과 "
            "제품 단위 성과는 별도 운전 데이터로 검증해야 합니다.",
        )
    if any(
        signal in text
        for signal in (
            "실증",
            "시험",
            "파일럿",
            "pilot",
            "연구",
            "r&d",
            "개발 단계",
        )
    ):
        return (
            "연구·실증",
            "기술 가능성을 검증하는 단계입니다. 시험 규모의 성공을 상용 생산성과로 "
            "해석하지 않고 규모 확대 계획을 따로 확인해야 합니다.",
        )
    if any(
        signal in text
        for signal in ("계획", "목표", "mou", "투자", "조건부", "예정")
    ):
        return (
            "계획·투자",
            "기업의 방향성과 자원 투입 의지는 확인되지만 실제 설비 성능이나 상용 운전이 "
            "입증된 단계는 아닙니다.",
        )
    return (
        "공식 현황 확인",
        "공식 자료에서 관련 움직임은 확인되지만 단계 구분에 필요한 일정·설비·운전 "
        "정보가 충분하지 않습니다.",
    )


def is_positive_technology_claim(claim: dict[str, Any]) -> bool:
    text = str(claim.get("value", "")).strip().casefold()
    negative_openings = (
        "고로 ccus 근거는 미확인",
        "공식 근거는 미확인",
        "관련 근거는 미확인",
        "근거 미확인",
    )
    return not text.startswith(negative_openings)


def technology_maturity_label(value: Any, technology: str | None = None) -> str:
    """Return a compact, conservative stage label from a source-backed claim."""
    text = str(value).strip().casefold()

    if technology == "low-carbon ironmaking":
        return "경로·프로젝트 확인"

    def has_confirmed_signal(*signals: str) -> bool:
        clauses = re.split(
            r"[.;。]|(?:다만|하지만|그러나|했으나|이나\s+)",
            text,
        )
        return any(
            signal in clause
            and "미확인" not in clause
            and "확인되지 않" not in clause
            and "근거는 아님" not in clause
            for clause in clauses
            for signal in signals
        )

    negative_signal = any(
        signal in text
        for signal in (
            "진행 불가",
            "중단",
            "취소",
            "연기",
            "postpone",
            "cancel",
            "suspend",
        )
    )
    if negative_signal and any(
        signal in text
        for signal in (
            "bremen·eisenhüttenstadt",
            "파일럿 건설",
            "특정 프로젝트",
        )
    ):
        return "일부 프로젝트 중단"
    if negative_signal:
        return "중단·연기"

    if "자체 상용 설비가 아닌 외부 기술 투자" in text:
        return "외부 전략투자"
    if (
        "학술 연구를 지원" in text
        and "자체" in text
        and ("미확인" in text or "확인되지 않" in text)
    ):
        return "외부 연구 지원"
    if "조건부 계획" in text:
        return "조건부 계획"
    if "천연가스 ramp-up 후 수소" in text:
        return "건설·수소전환 조건"
    if (
        has_confirmed_signal("준공")
        and has_confirmed_signal("생산을 개시", "생산 착수")
        and has_confirmed_signal("고급강 양산을 목표", "성분제어 기술을 개발")
    ):
        return "EAF 가동·고급강 개발"
    if (
        re.search(r"\b\d+(?:[.,]\d+)?\s*kg\b", text)
        and has_confirmed_signal("시험", "test")
    ):
        return "소규모 시험"

    commercial_is_target = any(
        signal in text
        for signal in (
            "상용화 목표",
            "상용화 기술 개발",
            "상용 운전 목표",
            "상용 생산 목표",
            "commercial operation target",
        )
    )
    if not commercial_is_target and has_confirmed_signal(
            "상업 생산",
            "상용 생산",
            "상용 운전",
            "commercial production",
            "commercial operation",
            "eaf가 주력",
    ):
        return "상용"

    operation_is_target = any(
        signal in text
        for signal in (
            "가동 목표",
            "가동 예정",
            "가동 계획",
            "시운전 예정",
            "운전 목표",
        )
    )
    if not operation_is_target and has_confirmed_signal(
            "가동",
            "운영",
            "운용",
            "배치 완료",
            "생산 착수",
            "산업 규모 dri 시험 완료",
            "digital twin",
            "global lighthouse",
    ):
        return "가동·적용"

    if has_confirmed_signal("준공"):
        return "준공·시운전"

    if has_confirmed_signal(
            "건설 중",
            "건설 착수",
            "건설 단계",
            "착공",
            "조립 시작",
            "부지를 준비",
            "부지 준비",
            "construction",
    ):
        return "건설·구축"

    if has_confirmed_signal(
            "실증 계획",
            "실증을 위한",
            "실증 예정",
            "투자 결정",
            "투자 단계",
            "전략 투자",
            "계약 체결",
            "조건부 계획",
            "final design",
    ):
        return "계획·투자"

    if has_confirmed_signal(
            "산업 실증",
            "산업규모 실증",
            "산업 규모 실증",
            "반산업 규모",
            "통합 실증",
            "응용 검증",
            "실증",
            "demonstration",
    ):
        return "실증"

    if has_confirmed_signal("파일럿", "pilot"):
        return "파일럿"

    if has_confirmed_signal(
            "연구",
            "r&d",
            "개발 단계",
            "기술 개발",
            "공동개발",
            "개발",
            "시험로",
            "시험 eaf",
    ):
        return "연구"

    if has_confirmed_signal("계획", "목표", "mou", "투자", "예정"):
        return "계획·투자"

    return "단계 미상"


def technology_company_matrix_lines(
    settings: dict[str, Any],
    claims_by_subject: dict[str, list[dict[str, Any]]],
) -> list[str]:
    configured_companies = {
        str(name).casefold(): index
        for index, name in enumerate(settings.get("companies", []))
    }
    companies = sorted(
        (
            (
                subject_id,
                subject_display_name(subject_id, settings),
                subject_path(subject_id),
            )
            for subject_id in claims_by_subject
            if subject_id.startswith("COM-")
        ),
        key=lambda item: (
            configured_companies.get(item[1].casefold(), len(configured_companies)),
            item[1].casefold(),
        ),
    )
    technologies = [
        str(technology) for technology in settings.get("technologies", [])
    ]
    lines = [
        "## 기술별 기업 현황",
        "",
        "기술을 행, 기업을 열로 비교합니다. **단계명**을 선택하면 해당 기업의 근거 "
        "상세로 이동합니다.",
        "",
    ]
    if not companies or not technologies:
        return lines + ["- 매트릭스를 만들 감시 기업 또는 기술이 없습니다.", ""]

    company_headers = [
        wikilink(path, name) for _, name, path in companies
    ]
    lines.extend(
        [
            "| 기술 | " + " | ".join(company_headers) + " |",
            "|---|" + "|".join("---:" for _ in companies) + "|",
        ]
    )
    for technology in technologies:
        predicate = TECHNOLOGY_PREDICATES.get(technology)
        label = str(TECHNOLOGY_DETAILS.get(technology, {}).get("label") or technology)
        row = [wikilink(technology_page_path(technology), label)]
        for subject_id, _, path in companies:
            active_claim = next(
                (
                    claim
                    for claim in claims_by_subject.get(subject_id, [])
                    if claim.get("status") == "active"
                    and claim.get("predicate") == predicate
                    and is_positive_technology_claim(claim)
                ),
                None,
            )
            if active_claim:
                row.append(
                    wikilink(
                        path,
                        technology_maturity_label(
                            active_claim.get("value", ""),
                            technology,
                        ),
                    )
                )
            else:
                row.append("")
        lines.append("| " + " | ".join(row) + " |")
    lines.extend(
        [
            "",
            "> **단계 흐름:** 연구 → 소규모 시험·파일럿 → 실증 → 건설·구축 → "
            "준공·시운전 → 가동·적용 → 상용",
            ">",
            "> **표 읽는 법:** 단계는 현재 저장소에 직접 연결된 Claim의 공개 표현을 "
            "보수적으로 분류한 것입니다. `계획·투자`, `조건부 계획`, "
            "`일부 프로젝트 중단`, `외부 전략투자`, `외부 연구 지원`은 성숙도 단계가 "
            "아닌 별도 실행 신호이며, `단계 미상`은 근거는 있으나 공개 정보만으로 "
            "단계를 구분하기 어렵다는 뜻입니다. 빈 칸은 현재 화면에 표시할 직접 "
            "근거가 없다는 뜻입니다.",
            ">",
            "> `저탄소 제철 종합 경로`는 단일 기술이 아니므로 기업 간 성숙도를 "
            "비교하지 않고 `경로·프로젝트 확인`으로만 표시합니다. 각 회사의 실제 "
            "설비·프로젝트 단계는 개별 기술 행과 연결된 상세 근거에서 확인합니다.",
            "",
        ]
    )
    return lines


def technology_navigation_lines(
    current_technology: str,
    settings: dict[str, Any],
) -> list[str]:
    """Build a compact, collapsed map linking all configured technologies."""
    configured = {str(item) for item in settings.get("technologies", [])}
    current_group = next(
        (
            group
            for group, technologies in TECHNOLOGY_NAVIGATION_GROUPS
            if current_technology in technologies
        ),
        "기타 기술",
    )
    lines = [
        f'??? info "관련 기술 바로가기 · 현재 위치: {markdown_cell(current_group)}"',
        "",
        "    탐색을 위한 편의 분류이며 기술 우열이나 확정된 공정 관계를 뜻하지 않습니다.",
        "",
    ]
    grouped = {
        technology
        for _, technologies in TECHNOLOGY_NAVIGATION_GROUPS
        for technology in technologies
    }
    navigation_groups = [
        *TECHNOLOGY_NAVIGATION_GROUPS,
        ("기타 기술", tuple(sorted(configured - grouped))),
    ]
    for group, technologies in navigation_groups:
        visible = [
            technology
            for technology in technologies
            if technology in configured
        ]
        if not visible:
            continue
        links: list[str] = []
        for technology in visible:
            label = str(
                TECHNOLOGY_DETAILS.get(technology, {}).get("label")
                or technology
            )
            if technology == current_technology:
                links.append(f"**{markdown_cell(label)} · 현재**")
            else:
                links.append(wikilink(technology_page_path(technology), label))
        lines.extend(
            [
                f"    **{markdown_cell(group)}**",
                "",
                "    " + " · ".join(links),
                "",
            ]
        )
    return lines


def technology_company_dossier_lines(
    technology: str,
    settings: dict[str, Any],
    claims_by_subject: dict[str, list[dict[str, Any]]],
    sources_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    detail = TECHNOLOGY_DETAILS.get(technology, {})
    label = str(detail.get("label") or technology)
    predicate = TECHNOLOGY_PREDICATES.get(technology)
    technology_subject_id = technology_page_path(technology).stem
    technical_claims = {
        str(claim.get("predicate")): claim
        for claim in claims_by_subject.get(technology_subject_id, [])
        if claim.get("status") == "active"
    }
    related_project_entries: list[
        tuple[str, list[dict[str, Any]]]
    ] = []
    for project_id in tuple(detail.get("related_projects") or ()):
        project_claims = [
            claim
            for claim in claims_by_subject.get(str(project_id), [])
            if claim.get("status") == "active"
        ]
        if project_claims:
            related_project_entries.append((str(project_id), project_claims))
    configured_companies = {
        str(name).casefold(): index
        for index, name in enumerate(settings.get("companies", []))
    }
    companies = sorted(
        (
            (
                subject_id,
                subject_display_name(subject_id, settings),
                subject_path(subject_id),
            )
            for subject_id in claims_by_subject
            if subject_id.startswith("COM-")
        ),
        key=lambda item: (
            configured_companies.get(item[1].casefold(), len(configured_companies)),
            item[1].casefold(),
        ),
    )
    company_claims: list[
        tuple[str, str, Path, dict[str, Any] | None]
    ] = []
    for subject_id, display_name, path in companies:
        claim = next(
            (
                item
                for item in claims_by_subject.get(subject_id, [])
                if item.get("status") == "active"
                and item.get("predicate") == predicate
            ),
            None,
        )
        company_claims.append((subject_id, display_name, path, claim))

    confirmed = [
        item
        for item in company_claims
        if item[3] and is_positive_technology_claim(item[3])
    ]
    verified_dates = [
        str(item[3].get("last_verified"))
        for item in confirmed
        if item[3] and item[3].get("last_verified")
    ]
    verified_dates.extend(
        str(claim.get("last_verified"))
        for claim in technical_claims.values()
        if claim.get("last_verified")
    )
    as_of = max(verified_dates) if verified_dates else today()
    all_source_ids = sorted(
        {
            str(source_id)
            for _, _, _, claim in confirmed
            if claim
            for source_id in claim.get("source_ids", [])
        }
        | {
            str(source_id)
            for claim in technical_claims.values()
            for source_id in claim.get("source_ids", [])
        }
        | {
            str(source_id)
            for _, project_claims in related_project_entries
            for claim in project_claims
            for source_id in claim.get("source_ids", [])
        }
    )
    direct_hero_source_ids = sorted(
        {
            str(source_id)
            for claim in technical_claims.values()
            for source_id in claim.get("source_ids", [])
        }
    )

    lines = [
        GENERATED_MARKER,
        "",
        f"# {markdown_cell(label)}",
        "",
        f"> 조사 기준일: **{markdown_cell(as_of)}** · 공식·1차 자료 중심 · "
        "사실과 AI 분석을 구분해 작성",
        "",
    ]
    lines.extend(technology_navigation_lines(technology, settings))
    hero_lines, hero_media_ids = representative_image_lines(
        direct_hero_source_ids,
        sources_by_id,
        subject_id=technology_subject_id,
        preferred_kinds=(
            "equipment_drawing",
            "patent_figure",
            "academic_figure",
            "process_diagram",
            "facility_photo",
            "ai_reconstruction",
            "other",
        ),
    )
    if not hero_lines:
        hero_lines, hero_media_ids = representative_image_lines(
            all_source_ids,
            sources_by_id,
            subject_id=technology_subject_id,
            preferred_kinds=(
                "equipment_drawing",
                "patent_figure",
                "academic_figure",
                "process_diagram",
                "facility_photo",
                "ai_reconstruction",
                "other",
            ),
        )
    lines.extend(hero_lines)
    if technical_claims:
        definition = technical_claims.get("technical_definition")
        definition_text = (
            f"{markdown_cell(humanize_claim_value(definition.get('value', '')))} "
            f"{claim_source_footnote_references(definition)}"
            if definition
            else str(detail.get("description") or "")
        )
        summary_rows = [
            ("분류 (편집)", str(detail.get("category") or "저탄소 제철 기술")),
            ("핵심 원리", definition_text),
        ]
        for summary_predicate in (
            "operating_temperature",
            "product_form",
            "product_purity",
            "metallization",
            "product_carbon",
            "feedstock_scope",
            "hydrogen_consumption",
            "energy_intensity_estimate",
            "development_stage",
            "downstream_route",
        ):
            claim = technical_claims.get(summary_predicate)
            if claim:
                summary_rows.append(
                    (
                        PREDICATE_LABELS[summary_predicate],
                        f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                        f"{claim_source_footnote_references(claim)}",
                    )
                )
        lines.extend(
            [
                '!!! abstract "한눈에 보기"',
                "",
                "    | 항목 | 내용 |",
                "    | --- | --- |",
            ]
        )
        lines.extend(
            f"    | **{markdown_cell(row_label)}** | {row_value} |"
            for row_label, row_value in summary_rows
        )
        lines.extend(
            [
                "",
                "## 개요",
                "",
                definition_text,
                "",
                str(detail.get("scope_note") or ""),
                "",
                f"- **근거 확인 기업:** {len(confirmed)}개",
                f"- **직접 연결 근거:** {len(all_source_ids)}건",
                "",
                "## 작동 원리",
                "",
            ]
        )
        for principle_predicate in (
            "core_reaction",
            "process_principle",
            "cell_configuration",
            "reactor_configuration",
        ):
            principle_claim = technical_claims.get(principle_predicate)
            if not principle_claim:
                continue
            lines.append(
                f"- **{PREDICATE_LABELS[principle_predicate]}:** "
                f"{markdown_cell(humanize_claim_value(principle_claim.get('value', '')))} "
                f"{claim_source_footnote_references(principle_claim)}"
            )
        lines.extend(["", "## 공정 구성", ""])
        process_mermaid = str(detail.get("process_mermaid") or "")
        if process_mermaid:
            lines.extend(["```mermaid", process_mermaid, "```", ""])
        process_legend = str(detail.get("process_legend") or "")
        if process_legend:
            lines.extend([process_legend, ""])
        diagram_source_ids = sorted(
            {
                str(source_id)
                for predicate in (
                    "technical_definition",
                    "core_reaction",
                    "process_principle",
                    "cell_configuration",
                )
                if technical_claims.get(predicate)
                for source_id in technical_claims[predicate].get("source_ids", [])
            }
        )
        diagram_references = "".join(
            source_footnote_reference(source_id)
            for source_id in diagram_source_ids
        )
        diagram_note = str(detail.get("diagram_note") or "")
        if not diagram_note:
            diagram_note = (
                "위 흐름도는 공개 자료의 단계를 비교하기 쉽게 재구성한 것입니다. "
                "실제 물질수지·열수지·설비 치수·배관계장·제어 구성을 뜻하는 설계도는 아닙니다."
            )
        lines.extend(
            [
                "!!! note \"도식 해석\"",
                "",
                f"    {markdown_cell(diagram_note)} {diagram_references}",
                "",
                "## 주요 기술 특성",
                "",
            ]
        )
        rendered_feature_predicates: set[str] = set()
        for group_label, group_predicates in TECHNICAL_FEATURE_GROUPS:
            group_claims = [
                (predicate, technical_claims[predicate])
                for predicate in group_predicates
                if predicate in technical_claims
            ]
            if not group_claims:
                continue
            lines.extend(
                [
                    f"### {group_label}",
                    "",
                    "| 구분 | 공개된 내용 | 근거 성격 |",
                    "| --- | --- | --- |",
                ]
            )
            lines.extend(
                f"| **{PREDICATE_LABELS[predicate]}** | "
                f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                f"{claim_source_footnote_references(claim)} | "
                f"{claim_evidence_label(claim, sources_by_id)} |"
                for predicate, claim in group_claims
            )
            rendered_feature_predicates.update(
                predicate for predicate, _ in group_claims
            )
            lines.append("")
        already_presented_predicates = {
            "technical_definition",
            "operating_temperature",
            "product_form",
            "product_purity",
            "metallization",
            "product_carbon",
            "feedstock_scope",
            "hydrogen_consumption",
            "energy_intensity_estimate",
            "development_stage",
            "downstream_route",
            "core_reaction",
            "process_principle",
            "cell_configuration",
            "reactor_configuration",
        } | rendered_feature_predicates
        additional_claims = sorted(
            (
                (predicate_name, claim)
                for predicate_name, claim in technical_claims.items()
                if predicate_name not in already_presented_predicates
            ),
            key=lambda item: (
                PREDICATE_LABELS.get(
                    item[0],
                    item[0].replace("_", " "),
                ).casefold(),
                item[0],
            ),
        )
        if additional_claims:
            lines.extend(
                [
                    "### 최신 실증·검증 정보",
                    "",
                    "기존 분류표에 속하지 않는 최신 공개 결과와 확대 계획을 별도로 "
                    "보존합니다. 목표·계획 문구는 달성 실적으로 해석하지 않습니다.",
                    "",
                    "| 구분 | 공개된 내용 | 근거 성격 |",
                    "| --- | --- | --- |",
                ]
            )
            lines.extend(
                f"| **{PREDICATE_LABELS.get(predicate_name, predicate_name.replace('_', ' '))}** | "
                f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                f"{claim_source_footnote_references(claim)} | "
                f"{claim_evidence_label(claim, sources_by_id)} |"
                for predicate_name, claim in additional_claims
            )
            lines.append("")
        lines.extend(["", "## 공개 개발 연혁", ""])
        dated_sources = sorted(
            (
                (str(sources_by_id[source_id].get("published_at")), source_id)
                for source_id in all_source_ids
                if sources_by_id.get(source_id, {}).get("published_at")
            ),
            key=lambda item: item[0],
        )
        if dated_sources:
            lines.extend(
                [
                    "| 날짜 | 공개 사건 |",
                    "| --- | --- |",
                ]
            )
            for published_at, source_id in dated_sources:
                record = sources_by_id.get(source_id, {})
                lines.append(
                    f"| {markdown_cell(published_at)} | "
                    f"{markdown_cell(record.get('title') or source_id)} "
                    f"{source_footnote_reference(source_id)} |"
                )
        else:
            lines.append("- 게시일이 확인된 공개 자료가 없습니다.")
    else:
        lines.extend(
            [
                "## 기술 개요",
                "",
                str(detail.get("description") or ""),
                "",
                f"- **근거 확인 기업:** {len(confirmed)}개",
                f"- **근거 자료:** {len(all_source_ids)}건",
                f"- **추가 관찰 포인트:** "
                f"{detail.get('watch') or '후속 공식 발표와 실제 운전 데이터를 확인해야 합니다.'}",
                "",
            ]
        )
    lines.extend(
        media_gallery_lines(
            all_source_ids,
            sources_by_id,
            excluded_media_ids=hero_media_ids,
            subject_id=technology_subject_id,
        )
    )
    lines.extend(["", "## 기업별 상세 현황", ""])
    for _, display_name, path, claim in confirmed:
        lines.extend([f"### {wikilink(path, display_name)}", ""])
        stage_label, stage_explanation = claim_stage(claim.get("value", ""))
        lines.extend(
            [
                f"**확인된 현황.** "
                f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                f"{claim_source_footnote_references(claim)}",
                "",
                f"**단계 판단: {stage_label}.** {stage_explanation}",
                "",
                f"- **날짜:** 발표 "
                f"{markdown_cell(claim_source_dates(claim, sources_by_id, 'published_at'))}"
                f" · 수집 "
                f"{markdown_cell(claim_source_dates(claim, sources_by_id, 'collected_at'))}"
                f" · 검증 "
                f"{markdown_cell(claim.get('last_verified') or '-')}",
                "",
            ]
        )

    if related_project_entries:
        lines.extend(
            [
                "## 관련 프로젝트",
                "",
                "기술의 실제 확대 단계를 확인할 수 있도록 프로젝트 문서와 현재 상태를 "
                "직접 연결합니다. 각 프로젝트 문서에는 최근 상태뿐 아니라 확인 가능한 "
                "전체 일정 이력이 표시됩니다.",
                "",
                "| 프로젝트 | 현재 확인 상태 | 일정·규모 |",
                "| --- | --- | --- |",
            ]
        )
        for project_id, project_claims in related_project_entries:
            claims_by_predicate = {
                str(claim.get("predicate") or ""): claim
                for claim in project_claims
            }
            status_claim = claims_by_predicate.get("project_status")
            status_text = (
                f"{markdown_cell(humanize_claim_value(status_claim.get('value', '')))} "
                f"{claim_source_footnote_references(status_claim)}"
                if status_claim
                else "현재 상태 Claim 미등록"
            )
            schedule_parts: list[str] = []
            for predicate_name in (
                "capacity_tpy",
                "capacity_tph",
                "capture_capacity_tpd",
                "capture_capacity_tpy",
                "product_capacity_lpy",
                "scale_status",
                "target_fid_date",
                "target_start_date",
                "target_commissioning_date",
                "commercial_operation_date",
            ):
                schedule_claim = claims_by_predicate.get(predicate_name)
                if not schedule_claim:
                    continue
                schedule_parts.append(
                    f"**{PREDICATE_LABELS.get(predicate_name, predicate_name)}** "
                    f"{markdown_cell(humanize_claim_value(schedule_claim.get('value', '')))} "
                    f"{claim_source_footnote_references(schedule_claim)}"
                )
            project_link = wikilink(
                subject_path(project_id),
                subject_display_name(project_id, settings),
            )
            lines.append(
                f"| **{project_link}** | {status_text} | "
                f"{' · '.join(schedule_parts) if schedule_parts else '-'} |"
            )
        lines.append("")

    analysis_heading = (
        "## 기술적 쟁점과 미공개 데이터"
        if technical_claims
        else "## AI 분석"
    )
    posco_implications = tuple(detail.get("posco_implications") or ())
    source_heading = "## 출처"
    lines.extend(
        [
            analysis_heading,
            "",
            "!!! warning \"AI 분석 — 공개 근거와 구분\"",
            "",
            "    기업별 단계는 인용된 공식 발표 문구를 기준으로 분류한 것으로, "
            "정식 TRL 판정이나 기술 경쟁력 순위가 아닙니다.",
            "",
            f"- **추가 확인이 필요한 데이터:** "
            f"{detail.get('watch') or '후속 공식 발표와 실제 운전 데이터를 확인해야 합니다.'}",
            "- 기업 간 비교에는 시험 규모, 실제 투입 원료·에너지 조건, 상용 운전 "
            "실적과 제품 단위 배출량을 같은 기준으로 적용해야 합니다.",
        ]
    )
    lines.extend(
        f"- {markdown_cell(point)}"
        for point in tuple(detail.get("analysis_points") or ())
    )
    if technical_claims and posco_implications:
        lines.extend(
            [
                "",
                "## POSCO 관점 시사점",
                "",
                "!!! info \"AI 분석 — 전략 검토용\"",
                "",
                "    다음 내용은 공개 근거를 바탕으로 한 비교 분석이며, "
                "POSCO의 공식 결정이나 투자 권고가 아닙니다.",
                "",
            ]
        )
        lines.extend(
            f"- {markdown_cell(point)}"
            for point in posco_implications
        )
    sensing_dashboard = TECHNOLOGY_SENSING_DASHBOARDS.get(technology, {})
    leading_indicators = tuple(
        detail.get("leading_indicators")
        or sensing_dashboard.get("leading_indicators")
        or ()
    )
    warning_signals = tuple(
        detail.get("warning_signals")
        or sensing_dashboard.get("warning_signals")
        or ()
    )
    decision_questions = tuple(
        detail.get("decision_questions")
        or sensing_dashboard.get("decision_questions")
        or ()
    )
    if leading_indicators or warning_signals or decision_questions:
        lines.extend(
            [
                "",
                "## 12–36개월 기술 센싱 대시보드",
                "",
                "!!! info \"AI 분석 — 연구·전략 의사결정용\"",
                "",
                "    아래 항목은 공개된 목표가 실제 성과로 전환되는지를 추적하기 위한 "
                "관찰 프레임입니다. 정식 TRL 판정이나 투자 권고가 아닙니다.",
                "",
            ]
        )
        if leading_indicators:
            lines.extend(["### 성숙도 승격 신호", ""])
            lines.extend(
                f"- {markdown_cell(item)}" for item in leading_indicators
            )
            lines.append("")
        if warning_signals:
            lines.extend(["### 지연·실패 신호", ""])
            lines.extend(
                f"- {markdown_cell(item)}" for item in warning_signals
            )
            lines.append("")
        if decision_questions:
            lines.extend(["### POSCO 판단 질문", ""])
            lines.extend(
                f"- {markdown_cell(item)}" for item in decision_questions
            )
    lines.extend(["", source_heading, ""])
    for source_id in all_source_ids:
        record = sources_by_id.get(source_id, {})
        title = str(record.get("title") or source_id)
        publisher = str(record.get("publisher") or "발행자 미상")
        published_at = str(record.get("published_at") or "게시일 미상")
        url = str(record.get("url") or "")
        internal = wikilink(Path("sources") / f"{source_id}.md", title)
        original = f" · [원문]({url})" if url else ""
        lines.append(
            f"- {internal} — {markdown_cell(publisher)}, "
            f"{markdown_cell(published_at)}{original}"
        )
    if not all_source_ids:
        lines.append("- 등록된 출처가 없습니다.")
    cited_source_ids = [
        source_id
        for source_id in all_source_ids
        if source_footnote_reference(source_id) in "\n".join(lines)
    ]
    if cited_source_ids:
        lines.append("")
        lines.extend(
            source_footnote_definition(source_id, sources_by_id)
            for source_id in cited_source_ids
        )
    return lines


def company_related_projects(
    subject_id: str,
    display_name: str,
    subject_claims: list[dict[str, Any]],
    claims_by_subject: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Find projects connected by shared evidence or an explicit company mention."""
    company_source_ids = {
        str(source_id)
        for claim in subject_claims
        for source_id in claim.get("source_ids", [])
    }
    aliases = {
        re.sub(r"[^a-z0-9]+", "", display_name.casefold()),
        re.sub(
            r"[^a-z0-9]+",
            "",
            subject_id.removeprefix("COM-").replace("-", " ").casefold(),
        ),
    }
    aliases.update(
        token
        for token in re.findall(r"[a-z0-9]+", display_name.casefold())
        if len(token) >= 4
        and token
        not in {
            "steel",
            "metal",
            "group",
            "corporation",
            "company",
            "limited",
        }
    )
    aliases.discard("")

    related: list[tuple[str, list[dict[str, Any]]]] = []
    for project_id, project_claims in claims_by_subject.items():
        if not project_id.startswith("PRJ-"):
            continue
        project_source_ids = {
            str(source_id)
            for claim in project_claims
            for source_id in claim.get("source_ids", [])
        }
        searchable = re.sub(
            r"[^a-z0-9]+",
            "",
            " ".join(
                [
                    project_id,
                    *(
                        str(claim.get("value") or "")
                        for claim in project_claims
                    ),
                ]
            ).casefold(),
        )
        if company_source_ids & project_source_ids or any(
            alias in searchable for alias in aliases
        ):
            related.append((project_id, project_claims))
    return sorted(related, key=lambda item: item[0])


def company_dossier_lines(
    subject_id: str,
    display_name: str,
    subject_claims: list[dict[str, Any]],
    active_claims: list[dict[str, Any]],
    historical_claims: list[dict[str, Any]],
    settings: dict[str, Any],
    sources_by_id: dict[str, dict[str, Any]],
    claims_by_subject: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """Render a company dossier including its source-backed project portfolio."""
    claims_by_predicate = {
        str(claim.get("predicate", "")): claim for claim in active_claims
    }
    technology_claims: list[tuple[str, dict[str, Any]]] = []
    for technology_value in settings.get("technologies", []):
        technology = str(technology_value)
        predicate = TECHNOLOGY_PREDICATES.get(technology)
        claim = claims_by_predicate.get(predicate or "")
        if claim and is_positive_technology_claim(claim):
            technology_claims.append((technology, claim))

    related_projects = company_related_projects(
        subject_id,
        display_name,
        subject_claims,
        claims_by_subject,
    )
    related_project_claims = [
        claim
        for _, project_claims in related_projects
        for claim in project_claims
    ]
    verified_dates = [
        str(claim.get("last_verified"))
        for claim in active_claims + related_project_claims
        if claim.get("last_verified")
    ]
    as_of = max(verified_dates) if verified_dates else today()
    all_source_ids = sorted(
        {
            str(source_id)
            for claim in subject_claims + related_project_claims
            for source_id in claim.get("source_ids", [])
        }
    )
    direct_source_ids = sorted(
        {
            str(source_id)
            for claim in subject_claims
            for source_id in claim.get("source_ids", [])
        }
    )
    explicitly_scoped_related_source_ids = sorted(
        {
            str(source_id)
            for claim in related_project_claims
            for source_id in claim.get("source_ids", [])
            if any(
                subject_id
                in {
                    str(item)
                    for item in media.get("subject_ids", [])
                    if str(item)
                }
                for media in sources_by_id.get(str(source_id), {}).get("images", [])
            )
        }
    )
    company_media_source_ids = sorted(
        set(direct_source_ids) | set(explicitly_scoped_related_source_ids)
    )
    risk_claims = [
        (technology, claim)
        for technology, claim in technology_claims
        if claim_stage(claim.get("value", ""))[0] == "중단·연기 신호"
        or any(
            signal in str(claim.get("value", "")).casefold()
            for signal in ("조건부", "미확인", "완료 실증은")
        )
    ]
    stage_counts: dict[str, int] = defaultdict(int)
    for _, claim in technology_claims:
        stage_counts[claim_stage(claim.get("value", ""))[0]] += 1
    stage_summary = " · ".join(
        f"{stage} {count}건" for stage, count in stage_counts.items()
    ) or "단계 정보 없음"

    lines = [
        GENERATED_MARKER,
        "",
        f"# {markdown_cell(display_name)} 기술 현황",
        "",
        f"> 조사 기준일: **{markdown_cell(as_of)}** · 공식·1차 자료 중심 · "
        "사실과 AI 분석을 구분해 작성",
        "",
        '!!! abstract "한눈에 보기"',
        "",
        "    | 항목 | 확인 내용 |",
        "    | --- | --- |",
        f"    | **확인된 기술** | {len(technology_claims)}개 / "
        f"감시 기술 {len(settings.get('technologies', []))}개 |",
        f"    | **연결 프로젝트** | {len(related_projects)}개 |",
        f"    | **실행 단계** | {markdown_cell(stage_summary)} |",
        f"    | **직접 연결 근거** | {len(all_source_ids)}건 |",
    ]
    hero_lines, hero_media_ids = representative_image_lines(
        direct_source_ids, sources_by_id, subject_id=subject_id
    )
    if not hero_lines:
        hero_lines, hero_media_ids = representative_image_lines(
            explicitly_scoped_related_source_ids,
            sources_by_id,
            subject_id=subject_id,
        )
    lines[6:6] = hero_lines
    if risk_claims:
        lines.extend(["", '!!! warning "주의해서 볼 항목"', ""])
        for technology, claim in risk_claims:
            label = str(
                TECHNOLOGY_DETAILS.get(technology, {}).get("label") or technology
            )
            lines.append(
                f"    - **{markdown_cell(label)}:** "
                f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                f"{claim_source_footnote_references(claim)}"
            )

    lines.extend(
        [
            "",
            "## 기술 포트폴리오",
            "",
            "현재 저장소에서 직접 근거가 확인된 기술만 표시합니다.",
            "",
            "| 기술 | 현재 확인 내용 | 단계 |",
            "| --- | --- | --- |",
        ]
    )
    for technology, claim in technology_claims:
        detail = TECHNOLOGY_DETAILS.get(technology, {})
        label = str(detail.get("label") or technology)
        stage_label, _ = claim_stage(claim.get("value", ""))
        technology_link = wikilink(technology_page_path(technology), label)
        lines.append(
            f"| **{technology_link}** | "
            f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
            f"{claim_source_footnote_references(claim)} | "
            f"**{markdown_cell(stage_label)}** |"
        )
    if not technology_claims:
        lines.append("| - | 현재 직접 근거가 확인된 감시 기술이 없습니다. | - |")

    lines.extend(["", "## 기술별 근거와 확인 과제", ""])
    for technology, claim in technology_claims:
        detail = TECHNOLOGY_DETAILS.get(technology, {})
        label = str(detail.get("label") or technology)
        stage_label, stage_explanation = claim_stage(claim.get("value", ""))
        lines.extend(
            [
                f'??? info "{markdown_cell(label)} · {markdown_cell(stage_label)}"',
                "",
                f"    **확인된 사실:** "
                f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                f"{claim_source_footnote_references(claim)}",
                "",
                f"    **판단 기준:** {stage_explanation}",
                "",
                f"    **확인 날짜:** 발표 "
                f"{markdown_cell(claim_source_dates(claim, sources_by_id, 'published_at'))}"
                f" · 검증 {markdown_cell(claim.get('last_verified') or '-')}",
                "",
                f"    **다음 확인:** "
                f"{detail.get('watch') or '후속 공식 발표와 실제 운전 데이터를 확인해야 합니다.'}",
                "",
            ]
        )

    other_claims = [
        claim
        for claim in active_claims
        if str(claim.get("predicate", ""))
        not in set(TECHNOLOGY_PREDICATES.values())
    ]
    if other_claims:
        lines.extend(
            [
                "## 사업화·프로젝트 지표",
                "",
                "| 항목 | 현재 확인 내용 |",
                "| --- | --- |",
            ]
        )
        for claim in other_claims:
            predicate = str(claim.get("predicate", ""))
            label = PREDICATE_LABELS.get(predicate, predicate.replace("_", " "))
            lines.append(
                f"| **{markdown_cell(label)}** | "
                f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                f"{claim_source_footnote_references(claim)} |"
            )
        lines.append("")

    if related_projects:
        lines.extend(
            [
                "## 주요 프로젝트",
                "",
                "회사 직접 Claim뿐 아니라 같은 원문 근거 또는 참여기관 문구로 연결된 "
                "프로젝트를 함께 표시합니다.",
                "",
                "| 프로젝트 | 현재 상태 | 핵심 일정·규모 |",
                "| --- | --- | --- |",
            ]
        )
        project_summary_predicates = (
            "technology_route",
            "location",
            "capacity_tpy",
            "capacity_tph",
            "capture_capacity_tpd",
            "capture_capacity_tpy",
            "product_capacity_lpy",
            "scale_status",
            "capex_eur",
            "capex_usd",
            "funding_amount",
            "target_fid_date",
            "target_start_date",
            "target_commissioning_date",
            "commercial_operation_date",
        )
        for project_id, project_claims in related_projects:
            active_project_claims = [
                claim
                for claim in project_claims
                if claim.get("status") == "active"
            ]
            by_predicate = {
                str(claim.get("predicate") or ""): claim
                for claim in active_project_claims
            }
            status_claim = by_predicate.get("project_status")
            status_text = (
                f"{markdown_cell(humanize_claim_value(status_claim.get('value', '')))} "
                f"{claim_source_footnote_references(status_claim)}"
                if status_claim
                else "현재 상태 Claim 미등록"
            )
            summary_parts = []
            for predicate in project_summary_predicates:
                claim = by_predicate.get(predicate)
                if not claim:
                    continue
                summary_parts.append(
                    f"**{PREDICATE_LABELS.get(predicate, predicate)}** "
                    f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                    f"{claim_source_footnote_references(claim)}"
                )
            lines.append(
                f"| **{wikilink(subject_path(project_id), subject_display_name(project_id, settings))}** "
                f"| {status_text} | {' · '.join(summary_parts) if summary_parts else '-'} |"
            )

        lines.extend(["", "## 프로젝트별 상세", ""])
        for project_id, project_claims in related_projects:
            project_name = subject_display_name(project_id, settings)
            active_project_claims = [
                claim
                for claim in project_claims
                if claim.get("status") == "active"
            ]
            historical_project_claims = [
                claim
                for claim in project_claims
                if claim.get("status") != "active"
                and not claim_is_data_correction(claim)
            ]
            lines.extend(
                [
                    f'??? info "{markdown_cell(project_name)}"',
                    "",
                    f"    **프로젝트 문서:** "
                    f"{wikilink(subject_path(project_id), project_name)}",
                    "",
                    "    | 항목 | 확인된 내용 |",
                    "    | --- | --- |",
                ]
            )
            for claim in active_project_claims:
                predicate = str(claim.get("predicate") or "")
                label = PREDICATE_LABELS.get(
                    predicate,
                    predicate.replace("_", " ").strip().capitalize(),
                )
                lines.append(
                    f"    | **{markdown_cell(label)}** | "
                    f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                    f"{claim_source_footnote_references(claim)} |"
                )
            timeline_rows = project_timeline_rows(project_claims, sources_by_id)
            if timeline_rows:
                lines.extend(
                    [
                        "",
                        "    **전체 공개 연혁**",
                        "",
                        "    | 날짜 | 구분 | 확인된 사건 |",
                        "    | --- | --- | --- |",
                    ]
                )
                lines.extend(
                    f"    | {markdown_cell(date_value)} | "
                    f"{markdown_cell(event_kind)} | {event_detail} |"
                    for date_value, event_kind, event_detail in timeline_rows
                )
            if historical_project_claims:
                lines.extend(["", "    **변경·중단 이력**", ""])
                for claim in historical_project_claims:
                    predicate = str(claim.get("predicate") or "")
                    label = PREDICATE_LABELS.get(
                        predicate,
                        predicate.replace("_", " ").strip().capitalize(),
                    )
                    status = CLAIM_STATUS_LABELS.get(
                        str(claim.get("status") or ""),
                        str(claim.get("status") or ""),
                    )
                    lines.append(
                        f"    - **{markdown_cell(label)} · {markdown_cell(status)}:** "
                        f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                        f"{claim_source_footnote_references(claim)}"
                    )
            lines.append("")
    else:
        lines.extend(
            [
                "## 프로젝트 정보 공백",
                "",
                '!!! info "추가 조사가 필요한 범위"',
                "",
                "    현재 저장된 Claim과 Source에서는 이 회사에 직접 연결되는 프로젝트를 "
                "확인하지 못했습니다. 회사 페이지가 짧은 것은 표시 누락이 아니라 "
                "프로젝트 단위 원문 조사와 Claim 등록이 아직 부족하다는 뜻입니다.",
                "",
            ]
        )

    lines.extend(
        [
            "## AI 분석",
            "",
            '!!! warning "공개 근거와 구분"',
            "",
            "    - 확인된 사실만으로 기술 경쟁력을 단일 순위로 평가하지 않았습니다. "
            "실증 규모, 상용 운전, 원료·에너지 조건이 서로 다르기 때문입니다.",
            f"    - 현재 자료의 실행 단계 분포는 {markdown_cell(stage_summary)}입니다. "
            "이는 공식 발표 문구를 바탕으로 한 분류이며 정식 TRL 판정이 아닙니다.",
            "    - 다음 갱신에서는 목표치보다 착공·준공·누적 생산량·가동률·제품 단위 "
            "배출량처럼 실행을 입증하는 지표를 우선 확인하는 것이 좋습니다.",
        ]
    )

    if historical_claims:
        lines.extend(["", '??? note "변경 이력"', ""])
        for claim in historical_claims:
            predicate = str(claim.get("predicate", ""))
            label = PREDICATE_LABELS.get(predicate, predicate.replace("_", " "))
            status = CLAIM_STATUS_LABELS.get(
                str(claim.get("status", "")),
                str(claim.get("status", "")),
            )
            lines.append(
                f"    - **{markdown_cell(label)} · {markdown_cell(status)}:** "
                f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
                f"{claim_source_footnote_references(claim)}"
            )

    lines.extend(
        media_gallery_lines(
            company_media_source_ids,
            sources_by_id,
            excluded_media_ids=hero_media_ids,
            subject_id=subject_id,
        )
    )

    lines.extend(
        [
            "",
            "## 근거 자료",
            "",
            "| 자료 | 발행 정보 | 원문 |",
            "| --- | --- | --- |",
        ]
    )
    for source_id in all_source_ids:
        record = sources_by_id.get(source_id, {})
        title = str(record.get("title") or source_id)
        publisher = str(record.get("publisher") or "발행자 미상")
        published_at = str(record.get("published_at") or "게시일 미상")
        url = str(record.get("url") or "")
        internal = wikilink(Path("sources") / f"{source_id}.md", title)
        original = f"[원문 보기]({url})" if url else "-"
        lines.append(
            f"| {internal} | {markdown_cell(publisher)} · "
            f"{markdown_cell(published_at)} | {original} |"
        )
    if not all_source_ids:
        lines.append("| 등록된 근거 자료가 없습니다. | - | - |")
    cited_source_ids = sorted(
        {
            str(source_id)
            for _, claim in technology_claims
            for source_id in claim.get("source_ids", [])
        }
        | {
            str(source_id)
            for claim in other_claims + historical_claims + related_project_claims
            for source_id in claim.get("source_ids", [])
        }
    )
    if cited_source_ids:
        lines.append("")
        lines.extend(
            source_footnote_definition(source_id, sources_by_id)
            for source_id in cited_source_ids
        )
    return lines


def project_timeline_rows(
    subject_claims: list[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
) -> list[tuple[str, str, str]]:
    """Build a complete, source-backed project chronology without hiding old states."""
    events: set[tuple[str, str, str]] = set()
    claims_by_source: dict[str, list[dict[str, Any]]] = {}
    for claim in subject_claims:
        if (
            str(claim.get("status") or "") != "active"
            and claim_is_data_correction(claim)
        ):
            continue
        for source_id in claim.get("source_ids", []):
            claims_by_source.setdefault(str(source_id), []).append(claim)

    for source_id, claims in claims_by_source.items():
        record = sources_by_id.get(source_id, {})
        published_at = str(record.get("published_at") or "")
        collected_at = str(record.get("collected_at") or "")
        event_date = published_at or collected_at or "날짜 미상"
        event_kind = "발표·검증" if published_at else "수집 확인"
        details: list[str] = []
        for claim in claims:
            predicate = str(claim.get("predicate", ""))
            label = PREDICATE_LABELS.get(
                predicate,
                predicate.replace("_", " ").strip().capitalize(),
            )
            status = str(claim.get("status") or "active")
            status_suffix = (
                ""
                if status == "active"
                else f" · {CLAIM_STATUS_LABELS.get(status, status)}"
            )
            detail = (
                f"**{markdown_cell(label)}**: "
                f"{markdown_cell(humanize_claim_value(claim.get('value', '')))}"
                f"{status_suffix}"
            )
            if detail not in details:
                details.append(detail)
        if details:
            events.add(
                (
                    event_date,
                    event_kind,
                    " · ".join(details) + f" {source_footnote_reference(source_id)}",
                )
            )

    for claim in subject_claims:
        if (
            str(claim.get("status") or "") != "active"
            and claim_is_data_correction(claim)
        ):
            continue
        predicate = str(claim.get("predicate", ""))
        event_kind = PROJECT_TIMELINE_PREDICATES.get(predicate)
        if not event_kind:
            continue
        label = PREDICATE_LABELS.get(
            predicate,
            predicate.replace("_", " ").strip().capitalize(),
        )
        raw_value = str(humanize_claim_value(claim.get("value", "")))
        # Preserve the event stated first in the claim. A target claim often
        # carries a later actual date in parentheses (for example,
        # "2025 target; actual 2026-06-17"). Selecting by date precision would
        # incorrectly turn that target into a 2026 event.
        first_date = re.search(
            r"(20\d{2}(?:-\d{2}(?:-\d{2})?)?)(?:년)?",
            raw_value,
        )
        event_date = first_date.group(1) if first_date else raw_value
        if first_date and len(event_date) == 4:
            if raw_value[first_date.end() : first_date.end() + 1] == "년":
                event_date = f"{event_date}년"
        if event_kind == "실행 일정" and any(
            str(sources_by_id.get(str(source_id), {}).get("published_at") or "")
            == event_date
            for source_id in claim.get("source_ids", [])
        ):
            continue
        value = markdown_cell(raw_value)
        events.add(
            (
                event_date,
                event_kind,
                f"**{markdown_cell(label)}**: {value} "
                f"{claim_source_footnote_references(claim)}",
            )
        )

    return sorted(
        events,
        key=lambda event: (
            event[0] == "날짜 미상",
            event[0],
            event[1],
            event[2],
        ),
    )


def project_dossier_lines(
    display_name: str,
    subject_claims: list[dict[str, Any]],
    active_claims: list[dict[str, Any]],
    historical_claims: list[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Render a project page for readers while keeping tracking fields internal."""
    project_subject_id = str(
        next(
            (
                claim.get("subject_id")
                for claim in subject_claims
                if claim.get("subject_id")
            ),
            "",
        )
    )
    all_source_ids = sorted(
        {
            str(source_id)
            for claim in subject_claims
            for source_id in claim.get("source_ids", [])
        }
    )
    verified_dates = [
        str(claim.get("last_verified"))
        for claim in subject_claims
        if claim.get("last_verified")
    ]
    as_of = max(verified_dates) if verified_dates else "미상"
    project_status = next(
        (
            claim
            for claim in active_claims
            if claim.get("predicate") == "project_status"
        ),
        None,
    )

    lines = [
        GENERATED_MARKER,
        "",
        f"# {markdown_cell(display_name)}",
        "",
        f"> 최근 검증 **{markdown_cell(as_of)}** · "
        f"확인된 핵심 정보 **{len(active_claims)}건** · "
        f"직접 연결 근거 **{len(all_source_ids)}건**",
        "",
    ]
    hero_lines, hero_media_ids = representative_image_lines(
        all_source_ids, sources_by_id, subject_id=project_subject_id
    )
    lines.extend(hero_lines)
    lines.extend(
        media_gallery_lines(
            all_source_ids,
            sources_by_id,
            excluded_media_ids=hero_media_ids,
            subject_id=project_subject_id,
        )
    )

    if project_status:
        lines.extend(
            [
                '!!! abstract "현재 상태"',
                "",
                "    "
                f"**{markdown_cell(humanize_claim_value(project_status.get('value', '')))}** "
                f"{claim_source_footnote_references(project_status)}",
                "",
            ]
        )

    lines.extend(
        [
            "## 확인된 핵심 정보",
            "",
            "| 항목 | 확인된 내용 |",
            "| --- | --- |",
        ]
    )
    for claim in active_claims:
        predicate = str(claim.get("predicate", ""))
        label = PREDICATE_LABELS.get(
            predicate,
            predicate.replace("_", " ").strip().capitalize(),
        )
        lines.append(
            f"| **{markdown_cell(label)}** | "
            f"{markdown_cell(humanize_claim_value(claim.get('value', '')))} "
            f"{claim_source_footnote_references(claim)} |"
        )
    if not active_claims:
        lines.append("| 현재 유효한 정보 | 확인된 항목이 없습니다. |")

    timeline_rows = project_timeline_rows(subject_claims, sources_by_id)
    if timeline_rows:
        lines.extend(
            [
                "",
                "## 전체 확인 이력",
                "",
                "현재 상태만 남기지 않고, 등록된 Source와 일정 Claim에서 확인되는 "
                "발표·검증·목표·실행 이력을 모두 시간순으로 표시합니다.",
                "",
                "| 날짜 | 구분 | 확인된 사건 |",
                "| --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| {markdown_cell(event_date)} | {markdown_cell(event_kind)} | {detail} |"
            for event_date, event_kind, detail in timeline_rows
        )

    if historical_claims:
        lines.extend(
            [
                "",
                "## 변경 이력",
                "",
                "| 상태 | 항목 | 이전 내용 | 변경 사유 | 최근 검증 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for claim in historical_claims:
            predicate = str(claim.get("predicate", ""))
            label = PREDICATE_LABELS.get(
                predicate,
                predicate.replace("_", " ").strip().capitalize(),
            )
            status = CLAIM_STATUS_LABELS.get(
                str(claim.get("status", "")),
                str(claim.get("status", "")),
            )
            lines.append(
                f"| **{markdown_cell(status)}** | {markdown_cell(label)} | "
                f"{markdown_cell(humanize_historical_claim_value(claim))} "
                f"{claim_source_footnote_references(claim)} | "
                f"{markdown_cell(claim_latest_history_reason(claim))} | "
                f"{markdown_cell(claim.get('last_verified', ''))} |"
            )

    lines.extend(["", "## 근거 자료", ""])
    for source_id in all_source_ids:
        record = sources_by_id.get(source_id, {})
        title = str(record.get("title") or source_id)
        publisher = str(record.get("publisher") or "발행자 미상")
        published_at = str(record.get("published_at") or "게시일 미상")
        url = str(record.get("url") or "")
        original = f" · [원문 보기]({url})" if url else ""
        archive = wikilink(
            Path("sources") / f"{source_id}.md",
            "보관 원문·메타데이터",
        )
        lines.append(
            f"- **{markdown_cell(title)}** — {markdown_cell(publisher)}, "
            f"{markdown_cell(published_at)}{original} · {archive}"
        )
    if not all_source_ids:
        lines.append("- 등록된 근거 자료가 없습니다.")

    if all_source_ids:
        lines.append("")
        lines.extend(
            source_footnote_definition(source_id, sources_by_id)
            for source_id in all_source_ids
        )
    return lines


def report_page_metadata(path: Path) -> dict[str, str]:
    """Read the small, human-facing metadata needed for report listings."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    metadata: dict[str, str] = {}
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, separator, value = line.partition(":")
            if separator:
                metadata[key.strip()] = value.strip().strip("\"'")
    if not metadata.get("title"):
        metadata["title"] = next(
            (
                line[2:].strip()
                for line in lines
                if line.startswith("# ")
            ),
            path.stem,
        )
    return metadata


def trend_report_index_lines(root: Path) -> list[str]:
    report_files = sorted(
        (root / "reports" / "briefs").glob("*.md"),
        key=lambda path: (
            report_page_metadata(path).get("date", ""),
            path.name,
        ),
        reverse=True,
    )
    report_items = [
        (path, report_page_metadata(path))
        for path in report_files
    ]
    lines = [
        "# 동향 보고서",
        "",
        "> 마지막 기준일 이후 새로 확인되거나 달라진 우선 기업의 사업축에 영향을 주는 외부 변화만",
        "> 모아 보는 변화 중심 브리프입니다.",
        "",
        '!!! abstract "현재 발행 상태"',
        "",
    ]
    if report_items:
        latest_path, latest = report_items[0]
        latest_title = latest.get("title") or latest_path.stem
        lines.extend(
            [
                f"    **발행된 보고서 {len(report_items)}건**",
                "",
                f"    최신 보고서: [{markdown_cell(latest_title)}]"
                f"(briefs/{latest_path.name})",
            ]
        )
    else:
        lines.extend(
            [
                "    **아직 발행된 동향 보고서가 없습니다.**",
                "",
                "    첫 보고서가 발행되면 최신 보고서부터 이 페이지에 표시됩니다.",
            ]
        )
    lines.extend(
        [
            "",
            "## 보고서에서 바로 확인할 내용",
            "",
            "| 구분 | 확인 내용 |",
            "| --- | --- |",
            "| **사업 영향** | 영향을 받는 회사·사업축과 구체적인 영향 경로 |",
            "| **판단 가치** | 사업영향도·긴급도와 그 판단 근거 |",
            "| **후속 대응** | 확인 시점, 담당 관점, 추가 관찰 항목 |",
            "",
            "## 읽는 순서",
            "",
            "1. 상단 요약에서 보고 기간과 핵심 변화 건수를 확인합니다.",
            "2. 변화 표에서 기업·프로젝트별 최신 상태와 근거를 확인합니다.",
            "3. 위험 신호와 사람 검토 대기 항목을 별도로 확인합니다.",
            "4. `AI 분석`은 확인된 사실과 구분해 참고합니다.",
            "",
            "## 발행된 보고서",
            "",
        ]
    )
    if report_items:
        lines.extend(
            [
                "| 발행일 | 보고서 | 관찰 기간 |",
                "| --- | --- | --- |",
            ]
        )
        for path, metadata in report_items:
            title = metadata.get("title") or path.stem
            date_value = metadata.get("date") or "날짜 미상"
            since_value = metadata.get("since")
            period = (
                f"{since_value} ~ {date_value}"
                if since_value
                else "보고서에서 확인"
            )
            lines.append(
                f"| {markdown_cell(date_value)} | "
                f"[{markdown_cell(title)}](briefs/{path.name}) | "
                f"{markdown_cell(period)} |"
            )
    else:
        lines.extend(
            [
                '!!! info "발행 대기"',
                "",
                "    현재 표시할 보고서가 없습니다. 조사와 근거 검증이 완료된 보고서만 "
                "이 목록에 추가됩니다.",
            ]
        )
    lines.extend(
        [
            "",
            '??? info "운영 안내"',
            "",
            "    위키가 실행 중이면 새로 생성되거나 수정된 보고서는 자동으로 화면에 "
            "반영됩니다.",
            "    이 화면은 저장된 보고서를 보여주며, 새로운 자료 조사와 보고서 작성은 "
            "별도의",
            "    Market Sensing Intelligence 작업에서 수행됩니다.",
        ]
    )
    return lines


def update_trend_report_index(root: Path) -> None:
    atomic_write_text(
        root / "reports" / "index.md",
        "\n".join(trend_report_index_lines(root)) + "\n",
    )


def _score_label(score: Any) -> str:
    return f"{score}/{SIGNAL_SCORE_MAX}"


def _confidence_label(value: Any) -> str:
    return {"high": "높음", "medium": "중간", "low": "낮음"}.get(
        str(value), "미정"
    )


def _days_until(date_value: Any) -> str | None:
    try:
        remaining = (date.fromisoformat(str(date_value)) - date.today()).days
    except (TypeError, ValueError):
        return None
    return f"D-{remaining}" if remaining >= 0 else f"D+{abs(remaining)} 경과"


def signal_decision_brief_lines(
    signal: dict[str, Any],
    insight: dict[str, Any],
    claims_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    impact = signal.get("business_impact") or {}
    urgency = signal.get("urgency") or {}
    claims = [
        claims_by_id[str(claim_id)]
        for claim_id in insight.get("claim_ids", [])
        if str(claim_id) in claims_by_id
    ]
    claim_by_predicate = {
        str(claim.get("predicate") or ""): claim for claim in claims
    }
    published_dates = sorted(
        str(claim.get("last_verified") or "") for claim in claims if claim.get("last_verified")
    )
    deadline = urgency.get("response_deadline")
    deadline_count = _days_until(deadline) if deadline else None
    lines = [
        "## 판단 요약",
        "",
        "| 사업영향도 | 긴급도 | 평가 신뢰도 | 평가일 |",
        "| ---: | ---: | --- | --- |",
        f"| **{_score_label(impact.get('score', '-'))}** "
        f"| **{_score_label(urgency.get('score', '-'))}** "
        f"| **{_confidence_label(signal.get('assessment_confidence'))}** "
        f"| {markdown_cell(signal.get('assessed_at') or '-')} |",
        "",
        f"- **영향 경로:** {markdown_cell((claim_by_predicate.get('impact_path') or {}).get('value') or '-')}",
        f"- **사업영향도 근거:** {markdown_cell(impact.get('rationale') or '-')}",
        f"- **긴급도 근거:** {markdown_cell(urgency.get('rationale') or '-')}",
    ]
    if deadline:
        suffix = f" · **{deadline_count}**" if deadline_count else ""
        lines.append(f"- **판단 시한:** {markdown_cell(deadline)}{suffix}")
    lines.extend(
        [
            f"- **근거 범위:** Claim {len(claims)}건 · 원문 {len(insight.get('source_ids', []))}건",
            "",
        ]
    )
    excluded = REQUIRED_SIGNAL_PREDICATES | {
        "event_date",
        "effective_date",
        "collected_at",
        "published_at",
    }
    drivers = [
        claim
        for claim in claims
        if str(claim.get("predicate") or "") not in excluded
        and str(claim.get("predicate") or "") in PREDICATE_LABELS
        and claim.get("status") == "active"
    ][:4]
    if drivers:
        lines.extend(["### 키 드라이버", ""])
        for claim in drivers:
            predicate = str(claim.get("predicate") or "")
            label = PREDICATE_LABELS.get(predicate, predicate.replace("_", " "))
            lines.append(
                f"- **{markdown_cell(label)}:** {markdown_cell(claim.get('value') or '-')}"
            )
        lines.append("")
    return lines


def impact_estimate_block_lines(estimate: dict[str, Any] | None) -> list[str]:
    if not estimate:
        return []
    payload = json.dumps(estimate, ensure_ascii=False, separators=(",", ":"))
    return [
        "## 정량 영향 시뮬레이션",
        "",
        "공개정보와 명시적 가정으로 계산한 예비 추정입니다. 숫자를 먼저 확인한 뒤 "
        "슬라이더로 가정을 바꾸면 결과가 즉시 갱신됩니다.",
        "",
        "```impact-simulator",
        payload,
        "```",
        "",
    ]


def _structured_item_lines(item: dict[str, Any]) -> list[str]:
    """Render one typed JSON item without reparsing prose labels or colon strings."""
    display = str(item.get("display") or "")
    label = markdown_cell(item.get("label") or "구조화 항목")
    lines = [f"**{label}**", ""]
    if display == "text":
        lines.extend([markdown_cell(item.get("value") or "-"), ""])
    elif display == "list":
        entries = item.get("items") if isinstance(item.get("items"), list) else []
        lines.extend(f"- {markdown_cell(entry)}" for entry in entries)
        lines.append("")
    elif display == "flow":
        steps = item.get("steps") if isinstance(item.get("steps"), list) else []
        lines.extend(
            f"{index}. {markdown_cell(step)}"
            for index, step in enumerate(steps, start=1)
        )
        lines.append("")
    elif display == "table":
        columns = [
            column for column in item.get("columns", []) if isinstance(column, dict)
        ]
        column_keys = [str(column.get("key") or "") for column in columns]
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(column.get("label") or column.get("key") or "-")
                for column in columns
            )
            + " |"
        )
        lines.append("| " + " | ".join("---" for _ in columns) + " |")
        for row in item.get("rows", []):
            if isinstance(row, dict):
                lines.append(
                    "| "
                    + " | ".join(markdown_cell(row.get(key) or "-") for key in column_keys)
                    + " |"
                )
        lines.append("")
    return lines


def _structured_key_driver_lines(
    insight: dict[str, Any], claims_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    excluded = REQUIRED_SIGNAL_PREDICATES | {
        "event_date",
        "effective_date",
        "collected_at",
        "published_at",
    }
    drivers = [
        claims_by_id[str(claim_id)]
        for claim_id in insight.get("claim_ids", [])
        if str(claim_id) in claims_by_id
        and str(claims_by_id[str(claim_id)].get("predicate") or "") not in excluded
        and str(claims_by_id[str(claim_id)].get("predicate") or "")
        in PREDICATE_LABELS
        and claims_by_id[str(claim_id)].get("status") == "active"
    ][:6]
    lines: list[str] = []
    for claim in drivers:
        predicate = str(claim.get("predicate") or "")
        label = PREDICATE_LABELS.get(predicate, predicate.replace("_", " "))
        lines.append(
            f"- **{markdown_cell(label)}:** {markdown_cell(claim.get('value') or '-')}"
        )
    return lines


def systematic_analytics_lines(value: Any) -> list[str]:
    """Render the optional reproducible calculation projection without causal wording."""

    if not isinstance(value, dict):
        return []
    status = str(value.get("status") or "")
    as_of = markdown_cell(value.get("as_of") or "-")
    lines = ["**재현 가능한 정량 점검**", ""]
    if status != "completed":
        lines.extend(
            [
                f"- 계산 기준일: {as_of}",
                "- 현재 등록된 검증 관측치가 최소 계산 요건에 미달합니다.",
                "- 자료가 충분해질 때까지 정량 결과를 원인이나 예측으로 사용하지 않습니다.",
                "",
            ]
        )
        return lines
    candidates = value.get("risk_factor_candidates")
    lines.extend(
        [
            f"- 계산 기준일: {as_of}",
            "- 같은 관측 버전과 계산 규칙을 다시 적용해 결과를 확인할 수 있습니다.",
            "",
        ]
    )
    if isinstance(candidates, list) and candidates:
        lines.extend(
            [
                "| 구조변화 기여 후보 | 상대 기여도 | 해석 범위 |",
                "| --- | ---: | --- |",
            ]
        )
        for candidate in candidates[:6]:
            if not isinstance(candidate, dict):
                continue
            score = float(candidate.get("contribution_score") or 0)
            lines.append(
                f"| {markdown_cell(candidate.get('label') or '확인할 시장 변수')} "
                f"| {score:.2f} | 원인 확정이 아닌 추가 검증 후보 |"
            )
        lines.append("")
    limitations = value.get("limitations")
    if isinstance(limitations, list) and limitations:
        lines.extend(["**현재 계산으로 알 수 없는 범위**", ""])
        lines.extend(f"- {markdown_cell(item)}" for item in limitations)
        lines.append("")
    return lines


def structured_analysis_lines(
    value: Any,
    signal: dict[str, Any] | None = None,
    insight: dict[str, Any] | None = None,
    claims_by_id: dict[str, dict[str, Any]] | None = None,
    sources_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Render JSON as a decision dashboard, distinct from the prose report."""
    if not isinstance(value, dict) or not isinstance(value.get("sections"), list):
        return legacy_structured_analysis_lines(
            signal or {}, insight or {}, claims_by_id or {}, sources_by_id or {}
        )

    signal = signal or {}
    insight = insight or {}
    claims_by_id = claims_by_id or {}
    sources_by_id = sources_by_id or {}
    linked_claims = [
        claims_by_id[str(claim_id)]
        for claim_id in insight.get("claim_ids", [])
        if str(claim_id) in claims_by_id
        and claims_by_id[str(claim_id)].get("status") in {"active", "disputed"}
    ]
    if value.get("schema_version") == STRUCTURED_ANALYSIS_SCHEMA_VERSION:
        section_by_key = {
            str(section.get("key")): section
            for section in value["sections"]
            if isinstance(section, dict) and section.get("key")
        }
        ordered_sections = [
            ("scenarios", "시나리오"),
            ("business_impact", "사업 영향"),
            ("key_drivers", "키 드라이버"),
            ("evidence", "근거와 시점"),
            ("falsification_actions", "반증과 다음 행동"),
        ]
        lines: list[str] = []
        for index, (section_key, default_title) in enumerate(
            ordered_sections, start=1
        ):
            section = section_by_key[section_key]
            title = str(section.get("title") or default_title).strip()
            lines.extend([f"**{index}. {markdown_cell(title)}**", ""])
            for item in section.get("items", []):
                if isinstance(item, dict):
                    lines.extend(_structured_item_lines(item))
            if section_key == "evidence":
                lines.extend(
                    claim_cross_validation_table_lines(
                        linked_claims,
                        sources_by_id,
                    )
                )
        return lines

    items_by_key = {
        str(item.get("key")): item
        for section in value["sections"]
        if isinstance(section, dict)
        for item in section.get("items", [])
        if isinstance(item, dict) and item.get("key")
    }
    used: set[str] = set()
    groups = [
        ("시나리오", ("scenarios",)),
        (
            "사업 영향",
            ("impact_path", "opportunity", "risk", "opportunity_cost", "contract_clauses"),
        ),
        ("키 드라이버", ("monitoring_indicators",)),
        (
            "근거와 시점",
            ("verified_change", "regulatory_timeline", "evidence", "source_summary"),
        ),
        (
            "반증과 다음 행동",
            (
                "decision_question",
                "provisional_conclusion",
                "conventional_view_gap",
                "falsification_condition",
                "owner",
                "detection_trigger",
                "decision_outputs",
                "limitations",
            ),
        ),
    ]
    lines: list[str] = []
    for index, (title, keys) in enumerate(groups, start=1):
        # Keep dashboard labels out of the document TOC so the prose report keeps
        # its own independent heading sequence.
        lines.extend([f"**{index}. {title}**", ""])
        if title == "키 드라이버":
            driver_lines = _structured_key_driver_lines(insight, claims_by_id)
            if driver_lines:
                lines.extend(["**확인된 핵심 변수**", "", *driver_lines, ""])
        rendered = False
        for key in keys:
            item = items_by_key.get(key)
            if item is not None:
                lines.extend(_structured_item_lines(item))
                used.add(key)
                rendered = True
        if title == "근거와 시점":
            validation_lines = claim_cross_validation_table_lines(
                linked_claims,
                sources_by_id,
            )
            lines.extend(validation_lines)
            rendered = rendered or bool(validation_lines)
        if not rendered and title not in {"사업 영향", "키 드라이버"}:
            lines.extend(["현재 저장된 구조화 항목이 없습니다.", ""])

    leftovers = [item for key, item in items_by_key.items() if key not in used]
    if leftovers:
        lines.extend(["**6. 추가 판단 정보**", ""])
        for item in leftovers:
            lines.extend(_structured_item_lines(item))
    return lines


def legacy_structured_analysis_lines(
    signal: dict[str, Any],
    insight: dict[str, Any],
    claims_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Project typed legacy fields without reparsing the narrative Markdown."""
    linked_claims = [
        claims_by_id[str(claim_id)]
        for claim_id in insight.get("claim_ids", [])
        if str(claim_id) in claims_by_id
        and claims_by_id[str(claim_id)].get("status") in {"active", "disputed"}
    ]
    claims = [
        claim for claim in linked_claims if claim.get("status") == "active"
    ]
    claim_by_predicate = {
        str(claim.get("predicate") or ""): claim for claim in claims
    }

    def claim_value(predicate: str) -> str:
        return str((claim_by_predicate.get(predicate) or {}).get("value") or "").strip()

    def public_claim_label(
        claim: dict[str, Any], index: int, fallback_prefix: str
    ) -> str:
        predicate = str(claim.get("predicate") or "")
        return PREDICATE_LABELS.get(predicate) or f"{fallback_prefix} {index}"

    impact = signal.get("business_impact") or {}
    urgency = signal.get("urgency") or {}
    deadline = str(urgency.get("response_deadline") or claim_value("response_deadline") or "-")
    confidence = _confidence_label(signal.get("assessment_confidence"))
    source_ids = list(
        dict.fromkeys(
            [str(item) for item in insight.get("source_ids", [])]
            + [
                str(source_id)
                for claim in linked_claims
                for source_id in claim.get("source_ids", [])
            ]
        )
    )
    published_dates = sorted(
        str(sources_by_id[source_id].get("published_at"))
        for source_id in source_ids
        if source_id in sources_by_id and sources_by_id[source_id].get("published_at")
    )
    published_at = published_dates[-1] if published_dates else "-"
    effective_at = claim_value("effective_date") or "-"
    detected_at = str(signal.get("created_at") or "-").split("T", 1)[0]

    lines = [
        "**1. 시나리오**",
        "",
        "| 사업영향도 | 긴급도 | 평가 신뢰도 | 판단 시한 |",
        "| ---: | ---: | --- | --- |",
        f"| **{_score_label(impact.get('score', '-'))}** "
        f"| **{_score_label(urgency.get('score', '-'))}** "
        f"| **{markdown_cell(confidence)}** | {markdown_cell(deadline)} |",
        "",
    ]
    if impact.get("rationale"):
        lines.append(
            f"- **사업영향도 근거:** {markdown_cell(impact.get('rationale'))}"
        )
    if urgency.get("rationale"):
        lines.append(f"- **긴급도 근거:** {markdown_cell(urgency.get('rationale'))}")
    if insight.get("summary"):
        lines.extend(
            ["", "**현재 판단**", "", str(insight.get("summary") or "").strip()]
        )

    impact_path = claim_value("impact_path")
    affected_business = claim_value("affected_business")
    lines.extend(["", "**2. 사업 영향**", ""])
    if impact_path:
        lines.extend(["**영향 경로**", "", markdown_cell(impact_path), ""])
    if affected_business:
        lines.extend(["**영향 대상**", "", markdown_cell(affected_business), ""])
    if signal.get("sentence"):
        lines.extend(
            ["**바꿔야 할 판단**", "", markdown_cell(signal.get("sentence")), ""]
        )

    excluded_driver_predicates = REQUIRED_SIGNAL_PREDICATES | {
        "affected_business",
        "assessed_at",
        "assessment_confidence",
        "business_impact_rationale",
        "business_impact_score_1_to_5",
        "business_impact_score_1_to_10",
        "collected_at",
        "effective_date",
        "event_date",
        "impact_path",
        "published_at",
        "recommended_follow_up",
        "response_deadline",
        "urgency_rationale",
        "urgency_score_1_to_5",
        "urgency_score_1_to_10",
    }
    driver_claims = [
        claim
        for claim in claims
        if str(claim.get("predicate") or "") not in excluded_driver_predicates
    ][:8]
    lines.extend(["**3. 키 드라이버**", ""])
    if driver_claims:
        lines.extend(
            [
                "| 확인사항 | 확인값 | 최근 확인 |",
                "| --- | --- | --- |",
            ]
        )
        for index, claim in enumerate(driver_claims, start=1):
            label = public_claim_label(claim, index, "핵심 변수")
            lines.append(
                f"| **{markdown_cell(label)}** | {markdown_cell(claim.get('value') or '-')} "
                f"| {markdown_cell(claim.get('last_verified') or '-')} |"
            )
        lines.append("")
    else:
        lines.extend(["연결된 핵심 변수를 다음 검토에서 보강합니다.", ""])

    lines.extend(
        [
            "**4. 근거와 시점**",
            "",
            f"**확인된 근거 {len(linked_claims)}건 · 원문 {len(source_ids)}건**",
            "",
            "| 감지일 | 원문 발표일 | 효력 발생일 | 평가일 |",
            "| --- | --- | --- | --- |",
            f"| {markdown_cell(detected_at)} | {markdown_cell(published_at)} "
            f"| {markdown_cell(effective_at)} | {markdown_cell(signal.get('assessed_at') or '-')} |",
            "",
        ]
    )
    evidence_excluded_predicates = {
        "assessed_at",
        "assessment_confidence",
        "business_axis",
        "business_impact_rationale",
        "business_impact_score_1_to_5",
        "business_impact_score_1_to_10",
        "collected_at",
        "published_at",
        "urgency_rationale",
        "urgency_score_1_to_5",
        "urgency_score_1_to_10",
    }
    evidence_claims = [
        claim
        for claim in linked_claims
        if str(claim.get("predicate") or "") not in evidence_excluded_predicates
    ][:12]
    if evidence_claims:
        lines.extend(
            [
                "| 근거 항목 | 확인값 | 교차검증 | 원문 | 최근 확인 |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )
        for index, claim in enumerate(evidence_claims, start=1):
            label = public_claim_label(claim, index, "확인 근거")
            links = [
                wikilink(Path("sources") / f"{source_id}.md", "근거 보기")
                for source_id in claim.get("source_ids", [])
                if str(source_id) in sources_by_id
            ]
            lines.append(
                f"| **{markdown_cell(label)}** | {markdown_cell(claim.get('value') or '-')} "
                f"| {markdown_cell(claim_cross_validation_label(claim))} "
                f"| {' · '.join(links) if links else '-'} "
                f"| {markdown_cell(claim.get('last_verified') or '-')} |"
            )
        lines.append("")

    lines.extend(["**5. 반증과 다음 행동**", ""])
    decision_fields = [
        ("기존 전제", signal.get("baseline_assumption")),
        ("전제를 깨는 관측", signal.get("observed_break")),
        ("바꿀 결정", signal.get("decision_change")),
        ("반증 확인", signal.get("falsification_check")),
        ("다음 행동", claim_value("recommended_follow_up")),
    ]
    rendered_decisions = False
    for label, field_value in decision_fields:
        if field_value:
            lines.extend([f"**{label}**", "", markdown_cell(field_value), ""])
            rendered_decisions = True
    if not rendered_decisions:
        lines.extend(
            [
                "**다음 행동**",
                "",
                markdown_cell(signal.get("sentence") or insight.get("summary") or "-"),
                "",
            ]
        )
    return lines


def tab_content_lines(lines: list[str]) -> list[str]:
    """Indent Markdown so pymdownx.tabbed owns the full nested document."""
    return [f"    {line}" if line else "" for line in lines]


def non_toc_label_lines(lines: list[str]) -> list[str]:
    """Render headings as visual labels without duplicating the narrative TOC."""
    result: list[str] = []
    for line in lines:
        match = re.match(r"^#{2,6}\s+(.+)$", line)
        result.append(f"**{match.group(1)}**" if match else line)
    return result


def demote_markdown_headings(lines: list[str]) -> list[str]:
    """Nest stored narrative sections beneath the page's detailed-analysis heading."""
    result: list[str] = []
    for line in lines:
        match = re.match(r"^(#{2,5})(\s+.+)$", line)
        result.append(f"#{match.group(1)}{match.group(2)}" if match else line)
    return result


def signal_classification_pills_markdown(
    signal: dict[str, Any], settings: dict[str, Any] | None = None
) -> str:
    """Render the governed company, axis, and change type without raw HTML."""
    effective_settings = settings or {}
    companies = " · ".join(
        subject_display_name(str(company_id), effective_settings)
        for company_id in signal.get("company_ids", [])
        if str(company_id).strip()
    ) or "-"
    values = (
        (companies, "company"),
        (str(signal.get("business_axis") or "-"), "axis"),
        (str(signal.get("signal_type") or "-"), "type"),
    )
    return " ".join(
        f"**{markdown_cell(value)}**{{: .signal-pill .signal-pill-{tone} }}"
        for value, tone in values
    )


def signal_page_lines(
    signal: dict[str, Any],
    insight: dict[str, Any],
    claims_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> list[str]:
    impact = signal.get("business_impact") or {}
    urgency = signal.get("urgency") or {}
    source_ids = [str(item) for item in insight.get("source_ids", [])]
    analysis_markdown = str(insight.get("analysis_markdown") or "").strip()
    lines = [
        GENERATED_MARKER,
        "",
        signal_classification_pills_markdown(signal, settings),
        '{: .signal-pills .signal-static-pills aria-label="회사, 사업축과 변화 유형" }',
        "",
        f"# {markdown_cell(insight.get('title') or signal.get('sentence') or '마켓 시그널')}",
        "",
        '!!! abstract "한 문장 시그널"',
        "",
        f"    **{markdown_cell(signal.get('sentence') or '-')}**",
        "",
        "| 사업영향도 | 긴급도 | 평가일 |",
        "| ---: | ---: | --- |",
        f"| **{_score_label(impact.get('score', '-'))}** "
        f"| **{_score_label(urgency.get('score', '-'))}** "
        f"| {markdown_cell(signal.get('assessed_at') or '-')} |",
        "",
        '=== "신호분석"',
        "",
    ]

    structured_lines = structured_analysis_lines(
        insight.get("analysis_structured"),
        signal,
        insight,
        claims_by_id,
        sources_by_id,
    )
    structured_lines.extend(
        systematic_analytics_lines(insight.get("systematic_analytics"))
    )
    if "```impact-simulator" not in analysis_markdown:
        structured_lines.extend(
            [
                "",
                *non_toc_label_lines(
                    impact_estimate_block_lines(insight.get("impact_estimate"))
                ),
            ]
        )
    lines.extend(tab_content_lines(structured_lines))
    lines.extend(["", '=== "보고서"', ""])

    narrative_lines = (
        analysis_markdown.splitlines()
        if analysis_markdown
        else [str(insight.get("summary") or "-").strip()]
    )
    lines.extend(tab_content_lines(narrative_lines))
    lines.append("")
    lines.extend(['??? note "연결된 판단 근거"', ""])
    rendered_claims = 0
    for claim_id in insight.get("claim_ids", []):
        claim = claims_by_id.get(str(claim_id))
        if not claim:
            continue
        links = " · ".join(
            wikilink(Path("sources") / f"{source_id}.md", "원문 근거")
            for source_id in claim.get("source_ids", [])
        )
        predicate = str(claim.get("predicate") or "")
        label = PREDICATE_LABELS.get(predicate, predicate.replace("_", " "))
        validation = (
            f" · **{markdown_cell(claim_cross_validation_label(claim))}**"
            if claim_is_cross_validatable(claim)
            else ""
        )
        lines.append(
            f"    - **{markdown_cell(label)}:** {markdown_cell(claim.get('value') or '-')}"
            f"{validation}"
            + (f" · {links}" if links else "")
        )
        rendered_claims += 1
    if not rendered_claims:
        lines.append("    - 연결된 근거가 없습니다.")
    lines.extend(["", "## 원문", ""])
    for source_id in source_ids:
        source = sources_by_id.get(source_id)
        if not source:
            continue
        label = markdown_cell(source.get("title") or "근거 자료")
        published = markdown_cell(source.get("published_at") or "게시일 미상")
        publisher = markdown_cell(source.get("publisher") or "발행자 미상")
        links = []
        if source.get("url"):
            links.append(f"[원문 링크]({source['url']})")
        links.append(wikilink(Path("sources") / f"{source_id}.md", "보관 원문"))
        lines.append(f"- **{label}** · {publisher} · {published} · {' · '.join(links)}")
    if not source_ids:
        lines.append("- 연결된 원문이 없습니다.")
    return lines


def signal_index_lines(
    signals: list[dict[str, Any]],
    insights_by_id: dict[str, dict[str, Any]],
    settings: dict[str, Any],
) -> list[str]:
    lines = [
        GENERATED_MARKER,
        "",
        "# 마켓 시그널",
        "",
        "사업에 영향을 줄 가능성과 대응 시급성을 기준으로 선별한 관찰 항목입니다. "
        "관심 항목을 누르면 핵심 해석, 상세 분석, 원문 순서로 더 깊게 확인할 수 있습니다.",
        "",
        "| 관심도 | 회사·사업축·변화 유형 | 한 문장 시그널 | 평가일 |",
        "| --- | --- | --- | --- |",
    ]
    ordered = sorted(
        signals,
        key=lambda item: (
            int((item.get("business_impact") or {}).get("score") or 0)
            + int((item.get("urgency") or {}).get("score") or 0),
            str(item.get("assessed_at") or ""),
        ),
        reverse=True,
    )
    for signal in ordered:
        insight = insights_by_id.get(str(signal.get("insight_id")), {})
        impact = (signal.get("business_impact") or {}).get("score", "-")
        urgency = (signal.get("urgency") or {}).get("score", "-")
        sentence = markdown_cell(signal.get("sentence") or "마켓 시그널")
        signal_path = Path("signals") / f"{signal.get('signal_id')}.md"
        lines.append(
            f"| 영향 **{impact}/{SIGNAL_SCORE_MAX}** · 긴급 **{urgency}/{SIGNAL_SCORE_MAX}** "
            f"| {signal_classification_pills_markdown(signal, settings)} "
            f"| {wikilink(signal_path, sentence)} "
            f"| {markdown_cell(signal.get('assessed_at') or '-')} |"
        )
    if not ordered:
        lines.append("| - | - | 현재 등록된 시그널이 없습니다. | - |")
    lines.extend(
        [
            "",
            '!!! info "평가 기준"',
            "",
            "    사업영향도와 긴급도는 각각 1~10점입니다. 점수 자체보다 각 항목의 "
            "영향 경로와 대응 시한을 함께 확인해 주십시오.",
        ]
    )
    return lines


def sync_obsidian_store(root: Path) -> dict[str, Any]:
    """Return the live SQLite projection boundary.

    Per-record Markdown generation was retired when SQLite became canonical.
    MyPIN and other consumers read the same database directly.
    """
    root = root.resolve()
    return {
        "action": "sqlite_canonical",
        "database": str(database_path(root)),
        "generated_files": 0,
    }


def sync_obsidian(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    result = sync_obsidian_store(root)
    append_log(
        root,
        "sync-obsidian",
        "No files generated; SQLite remains the canonical live store.",
    )
    return {"action": "no_file_projection", **result}


def search_terms(query: str) -> list[str]:
    return list(
        dict.fromkeys(
            token
            for token in re.findall(r"[a-z0-9가-힣._-]+", normalize_text(query))
            if len(token) >= 2 or token.isdigit()
        )
    )


def relevance(
    query: str,
    terms: list[str],
    fields: list[tuple[str, Any, int]],
) -> tuple[int, list[str]]:
    normalized_query = normalize_text(query)
    score = 0
    matched: list[str] = []
    for name, raw_value, weight in fields:
        value = normalize_text(str(raw_value or ""))
        if not value:
            continue
        field_score = 0
        if normalized_query and normalized_query in value:
            field_score += weight * 3
        hits = sum(1 for term in terms if term in value)
        field_score += hits * weight
        if field_score:
            score += field_score
            matched.append(name)
    return score, matched


def search_store(args: argparse.Namespace) -> dict[str, Any]:
    """Rank local notes, claims, and sources, then follow note wikilinks once."""
    root = require_store(Path(args.root))
    query = args.query.strip()
    if not query:
        raise ValueError("query must not be empty")
    terms = search_terms(query)
    if not terms:
        raise ValueError("query must contain searchable letters or numbers")
    limit = args.limit
    if limit < 1:
        raise ValueError("limit must be at least 1")
    settings = effective_settings(root)
    configured_predicates = settings.get("priority_predicates", [])
    priority_predicates = {
        predicate: len(configured_predicates) - index
        for index, predicate in enumerate(configured_predicates)
    }

    direct_notes: list[dict[str, Any]] = []
    searchable_documents: list[tuple[str, str, str]] = []
    for _, insight in insight_records(root):
        searchable_documents.append(
            (
                str(insight.get("insight_id") or ""),
                "insight",
                "\n".join(
                    str(insight.get(field) or "")
                    for field in ("title", "summary", "analysis_markdown")
                ),
            )
        )
    for _, signal in signal_records(root):
        searchable_documents.append(
            (
                str(signal.get("signal_id") or ""),
                "signal",
                "\n".join(
                    str(signal.get(field) or "")
                    for field in ("sentence", "business_axis", "signal_type")
                ),
            )
        )
    for artifact in list_artifacts(root):
        searchable_documents.append(
            (
                str(artifact["artifact_id"]),
                str(artifact["artifact_type"]),
                "\n".join(
                    str(artifact.get(field) or "")
                    for field in ("title", "markdown_text", "html_text")
                ),
            )
        )
    for document_id, document_type, text in searchable_documents:
        score, matched = relevance(
            query,
            terms,
            [
                ("id", document_id, 6),
                ("type", document_type, 3),
                ("content", text[:120_000], 2),
            ],
        )
        if score:
            direct_notes.append(
                {
                    "artifact_id": document_id,
                    "artifact_type": document_type,
                    "score": score,
                    "match": "direct",
                    "matched_fields": matched,
                }
            )
    direct_notes.sort(key=lambda item: (-item["score"], item["artifact_id"]))
    notes = direct_notes[:limit]
    followed_links: list[dict[str, str]] = []

    ranked_claims: list[dict[str, Any]] = []
    claims_by_id: dict[str, dict[str, Any]] = {}
    source_to_claims: dict[str, list[str]] = defaultdict(list)
    for _, claim in claim_records(root):
        claim_id = str(claim.get("claim_id", ""))
        claims_by_id[claim_id] = claim
        for source_id in claim.get("source_ids", []):
            source_to_claims[str(source_id)].append(claim_id)
        score, matched = relevance(
            query,
            terms,
            [
                ("subject_id", claim.get("subject_id"), 6),
                ("predicate", claim.get("predicate"), 4),
                ("value", claim.get("value"), 5),
                ("status", claim.get("status"), 2),
            ],
        )
        if score:
            score += priority_predicates.get(claim.get("predicate"), 0)
            ranked_claims.append(
                {
                    "claim_id": claim_id,
                    "subject_id": claim.get("subject_id"),
                    "predicate": claim.get("predicate"),
                    "value": claim.get("value"),
                    "status": claim.get("status"),
                    "confidence": claim.get("confidence"),
                    "last_verified": claim.get("last_verified"),
                    "source_ids": claim.get("source_ids", []),
                    "score": score + (1 if claim.get("status") == "active" else 0),
                    "match": "direct",
                    "matched_fields": matched,
                }
            )
    ranked_claims.sort(
        key=lambda item: (-item["score"], str(item["claim_id"]))
    )

    ranked_sources: list[dict[str, Any]] = []
    sources_by_id: dict[str, dict[str, Any]] = {}
    for _, record in source_records(root):
        source_id = str(record.get("source_id", ""))
        sources_by_id[source_id] = record
        raw_content = get_source_content(root, source_id)
        raw_text = (
            raw_content.decode("utf-8", errors="replace")[:120_000]
            if raw_content is not None
            else ""
        )
        score, matched = relevance(
            query,
            terms,
            [
                ("source_id", source_id, 6),
                ("title", record.get("title"), 6),
                ("publisher", record.get("publisher"), 4),
                ("academic_kind", (record.get("academic") or {}).get("kind"), 4),
                ("authors", (record.get("academic") or {}).get("authors"), 4),
                ("venue", (record.get("academic") or {}).get("venue"), 4),
                ("doi", (record.get("academic") or {}).get("doi"), 6),
                (
                    "conference_name",
                    (record.get("academic") or {}).get("conference_name"),
                    5,
                ),
                ("url", record.get("url"), 2),
                ("raw", raw_text, 1),
            ],
        )
        if score:
            ranked_sources.append(
                {
                    "source_id": source_id,
                    "title": record.get("title"),
                    "publisher": record.get("publisher"),
                    "published_at": record.get("published_at"),
                    "reliability": record.get("reliability"),
                    "academic": record.get("academic"),
                    "url": record.get("url"),
                    "raw_ref": record.get("raw_ref"),
                    "score": score,
                    "match": "direct",
                    "matched_fields": matched,
                }
            )
    ranked_sources.sort(
        key=lambda item: (-item["score"], str(item["source_id"]))
    )

    selected_claims = ranked_claims[:limit]
    selected_sources = ranked_sources[:limit]
    selected_claim_ids = {item["claim_id"] for item in selected_claims}
    selected_source_ids = {item["source_id"] for item in selected_sources}

    for claim in list(selected_claims):
        for source_id in claim["source_ids"]:
            source_id = str(source_id)
            if source_id in selected_source_ids or source_id not in sources_by_id:
                continue
            record = sources_by_id[source_id]
            selected_sources.append(
                {
                    "source_id": source_id,
                    "title": record.get("title"),
                    "publisher": record.get("publisher"),
                    "published_at": record.get("published_at"),
                    "reliability": record.get("reliability"),
                    "academic": record.get("academic"),
                    "url": record.get("url"),
                    "raw_ref": record.get("raw_ref"),
                    "score": 0,
                    "match": "claim_link",
                    "via": claim["claim_id"],
                }
            )
            selected_source_ids.add(source_id)

    for source in list(selected_sources):
        for claim_id in source_to_claims.get(source["source_id"], []):
            if claim_id in selected_claim_ids:
                continue
            claim = claims_by_id[claim_id]
            selected_claims.append(
                {
                    "claim_id": claim_id,
                    "subject_id": claim.get("subject_id"),
                    "predicate": claim.get("predicate"),
                    "value": claim.get("value"),
                    "status": claim.get("status"),
                    "confidence": claim.get("confidence"),
                    "last_verified": claim.get("last_verified"),
                    "source_ids": claim.get("source_ids", []),
                    "score": 0,
                    "match": "source_link",
                    "via": source["source_id"],
                }
            )
            selected_claim_ids.add(claim_id)

    return {
        "action": "search_results",
        "query": query,
        "terms": terms,
        "focus": settings.get("focus", []),
        "priority_predicates": settings.get("priority_predicates", []),
        "notes": notes,
        "claims": selected_claims[: limit * 2],
        "sources": selected_sources[: limit * 2],
        "followed_links": followed_links,
        "verification_required": True,
        "next_step": "Read candidate Claim records and cited SQLite source content before answering.",
    }


def verify_source_ids(root: Path, source_ids: list[str]) -> None:
    missing = [
        source_id
        for source_id in source_ids
        if not record_exists(root, "sources", source_id)
    ]
    if missing:
        raise ValueError("Unknown source IDs: " + ", ".join(missing))


def verify_source_modality(root: Path, source_ids: list[str], modality: str) -> None:
    expected = validate_modality(modality)
    sources_by_id = _records_by_id(source_records(root), "source_id")
    mismatched = [
        source_id
        for source_id in source_ids
        if validate_modality(sources_by_id[source_id].get("source_modality")) != expected
    ]
    if mismatched:
        raise ValueError(
            f"Evidence modality {expected} disagrees with sources: {', '.join(mismatched)}"
        )


def create_claim_review(
    root: Path,
    proposed: dict[str, Any],
    conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    digest = hashlib.sha256(
        (
            proposed["claim_id"]
            + "\x1f"
            + "\x1f".join(sorted(item["claim_id"] for item in conflicts))
        ).encode("utf-8")
    ).hexdigest()
    review_id = f"REV-CLM-{digest[:12].upper()}"
    review = {
        "review_id": review_id,
        "type": "claim_conflict",
        "created_at": timestamp(),
        "subject_id": proposed["subject_id"],
        "predicate": proposed["predicate"],
        "existing_claims": conflicts,
        "proposed_claim": proposed,
        "allowed_decisions": [
            "supersede",
            "keep-existing",
            "coexist",
            "dispute",
            "reject",
        ],
        "status": "pending",
    }
    path = root / PENDING_REVIEWS_DIR / f"{review_id}.json"
    write_json(path, review)
    sync_obsidian_store(root)
    append_log(
        root,
        "review-required",
        f"{review_id}: conflicting values for "
        f"{proposed['subject_id']} / {proposed['predicate']}",
    )
    return {
        "action": "review_required",
        "review_id": review_id,
        "type": "claim_conflict",
        "existing_claim_ids": [item["claim_id"] for item in conflicts],
        "proposed_claim_id": proposed["claim_id"],
    }


def add_claim(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    as_of = validate_date(args.as_of, "as_of") or today()
    if args.confidence not in CLAIM_CONFIDENCE:
        raise ValueError(f"Invalid confidence: {args.confidence}")
    source_ids = list(dict.fromkeys(args.source_id))
    verify_source_ids(root, source_ids)
    risk_factor_ids = list(
        dict.fromkeys(getattr(args, "risk_factor_id", None) or [])
    )
    verify_risk_factor_ids(root, risk_factor_ids)

    claim_id = claim_id_for(args.subject_id, args.predicate, args.value)
    records = claim_records(root)
    active_same: tuple[Path, dict[str, Any]] | None = None
    conflicts: list[dict[str, Any]] = []
    for path, claim in records:
        same_key = (
            claim.get("subject_id") == args.subject_id
            and claim.get("predicate") == args.predicate
        )
        if not same_key or claim.get("status") != "active":
            continue
        if normalize_text(str(claim.get("value", ""))) == normalize_text(args.value):
            active_same = (path, claim)
        else:
            conflicts.append(claim)

    if active_same:
        path, claim = active_same
        old_sources = list(claim.get("source_ids", []))
        claim["source_ids"] = list(dict.fromkeys(old_sources + source_ids))
        claim["last_verified"] = as_of
        claim["schema_version"] = CLAIM_SCHEMA_VERSION
        claim["version_no"] = int(claim.get("version_no") or 1) + 1
        claim["claim_version_id"] = _stable_node_id(
            "CLMV", claim["claim_id"], claim["version_no"], *claim["source_ids"]
        )
        claim["risk_factor_ids"] = list(
            dict.fromkeys([*claim.get("risk_factor_ids", []), *risk_factor_ids])
        )
        claim.setdefault("history", []).append(
            {
                "date": as_of,
                "action": "verified",
                "reason": args.reason,
                "source_ids": source_ids,
            }
        )
        write_json(path, claim)
        put_claim_version(root, claim)
        if claim["risk_factor_ids"]:
            put_risk_factor_links(
                root,
                subject_kind="claim",
                subject_version_id=claim["claim_version_id"],
                risk_factor_ids=claim["risk_factor_ids"],
            )
        sync_obsidian_store(root)
        append_log(
            root,
            "verify-claim",
            f"{claim['claim_id']}: added evidence {', '.join(source_ids)}",
        )
        return {
            "action": "verified_existing",
            "claim_id": claim["claim_id"],
            "source_ids": claim["source_ids"],
        }

    proposed = {
        "schema_version": CLAIM_SCHEMA_VERSION,
        "claim_id": claim_id,
        "claim_version_id": _stable_node_id("CLMV", claim_id, 1, *source_ids),
        "version_no": 1,
        "subject_id": args.subject_id,
        "predicate": args.predicate,
        "value": args.value,
        "status": "active",
        "confidence": args.confidence,
        "first_seen": as_of,
        "last_verified": as_of,
        "source_ids": source_ids,
        "risk_factor_ids": risk_factor_ids,
        "supersedes": [],
        "coexists_with": [],
        "history": [
            {
                "date": as_of,
                "action": "created",
                "reason": args.reason,
                "source_ids": source_ids,
            }
        ],
    }

    if conflicts:
        return create_claim_review(root, proposed, conflicts)

    path = root / CLAIMS_DIR / f"{claim_id}.json"
    if record_exists(root, "claims", claim_id):
        existing = read_json(path)
        return create_claim_review(root, proposed, [existing])
    write_json(path, proposed)
    put_claim_version(root, proposed)
    if risk_factor_ids:
        put_risk_factor_links(
            root,
            subject_kind="claim",
            subject_version_id=proposed["claim_version_id"],
            risk_factor_ids=risk_factor_ids,
        )
    sync_obsidian_store(root)
    append_log(
        root,
        "add-claim",
        f"{claim_id}: {args.subject_id} / {args.predicate} = {args.value}",
    )
    return {"action": "created", "claim_id": claim_id}


def resolve_claim_review(
    root: Path,
    review_path: Path,
    review: dict[str, Any],
    decision: str,
    rationale: str,
) -> dict[str, Any]:
    allowed = set(review.get("allowed_decisions", []))
    if decision not in allowed:
        raise ValueError(
            f"Decision {decision!r} is not allowed. Choose: {', '.join(sorted(allowed))}"
        )
    proposed = review["proposed_claim"]
    conflict_ids = [item["claim_id"] for item in review["existing_claims"]]
    claim_dir = root / CLAIMS_DIR
    changed: list[str] = []
    resolution_date = today()

    existing_claims: list[tuple[Path, dict[str, Any]]] = []
    for claim_id in conflict_ids:
        path = claim_dir / f"{claim_id}.json"
        if record_exists(root, "claims", claim_id):
            existing_claims.append((path, read_json(path)))

    if decision in {"supersede", "coexist", "dispute"}:
        proposed_path = claim_dir / f"{proposed['claim_id']}.json"
        if decision == "supersede":
            proposed["supersedes"] = conflict_ids
            for path, claim in existing_claims:
                claim["status"] = "superseded"
                claim["superseded_by"] = proposed["claim_id"]
                claim.setdefault("history", []).append(
                    {
                        "date": resolution_date,
                        "action": "status_changed",
                        "from": "active",
                        "to": "superseded",
                        "reason": rationale,
                    }
                )
                write_json(path, claim)
                changed.append(claim["claim_id"])
        elif decision == "coexist":
            proposed["coexists_with"] = conflict_ids
            for path, claim in existing_claims:
                links = list(claim.get("coexists_with", []))
                claim["coexists_with"] = list(
                    dict.fromkeys(links + [proposed["claim_id"]])
                )
                claim.setdefault("history", []).append(
                    {
                        "date": resolution_date,
                        "action": "coexistence_confirmed",
                        "with": proposed["claim_id"],
                        "reason": rationale,
                    }
                )
                write_json(path, claim)
                changed.append(claim["claim_id"])
        elif decision == "dispute":
            proposed["status"] = "disputed"
            for path, claim in existing_claims:
                old_status = claim.get("status")
                claim["status"] = "disputed"
                claim.setdefault("history", []).append(
                    {
                        "date": resolution_date,
                        "action": "status_changed",
                        "from": old_status,
                        "to": "disputed",
                        "reason": rationale,
                    }
                )
                write_json(path, claim)
                changed.append(claim["claim_id"])
        proposed.setdefault("history", []).append(
            {
                "date": resolution_date,
                "action": f"review_{decision}",
                "reason": rationale,
            }
        )
        write_json(proposed_path, proposed)
        proposed_risk_factor_ids = [
            str(item) for item in proposed.get("risk_factor_ids", []) if str(item)
        ]
        if proposed_risk_factor_ids:
            put_risk_factor_links(
                root,
                subject_kind="claim",
                subject_version_id=proposed["claim_version_id"],
                risk_factor_ids=proposed_risk_factor_ids,
            )
        changed.append(proposed["claim_id"])

    review["status"] = "resolved"
    review["resolution"] = {
        "decided_at": timestamp(),
        "decision": decision,
        "rationale": rationale,
        "changed_claim_ids": changed,
    }
    resolved_path = root / RESOLVED_REVIEWS_DIR / review_path.name
    write_json(resolved_path, review)
    delete_record(root, "reviews_pending", review["review_id"])
    sync_obsidian_store(root)
    append_log(
        root,
        "resolve-review",
        f"{review['review_id']}: {decision}. {rationale}",
    )
    return {
        "action": "resolved",
        "review_id": review["review_id"],
        "decision": decision,
        "changed_claim_ids": changed,
    }


def resolve_duplicate_review(
    root: Path,
    review_path: Path,
    review: dict[str, Any],
    decision: str,
    rationale: str,
    related_source: str | None,
) -> dict[str, Any]:
    allowed = set(review.get("allowed_decisions", []))
    if decision not in allowed:
        raise ValueError(
            f"Decision {decision!r} is not allowed. Choose: {', '.join(sorted(allowed))}"
        )
    metadata = review["candidate"]
    candidate_id = str(review.get("candidate_artifact_id") or review.get("review_id") or "")
    candidate = get_artifact(root, candidate_id)
    result: dict[str, Any] = {"action": decision}

    if decision == "supporting":
        possible = [
            item["source_id"] for item in review.get("possible_duplicates", [])
        ]
        target = related_source or (possible[0] if len(possible) == 1 else None)
        if not target:
            raise ValueError(
                "Choose the existing source with --related-source. Candidates: "
                + ", ".join(possible)
            )
        result = add_supporting_source(
            root,
            target,
            metadata["title"],
            metadata.get("url"),
            metadata["publisher"],
            metadata.get("published_at"),
        )
    elif decision == "accept-new":
        if not candidate or candidate.get("markdown_text") is None:
            raise ValueError(f"Missing source candidate artifact: {candidate_id}")
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".md", delete=False
        ) as handle:
            handle.write(str(candidate["markdown_text"]))
            candidate_path = Path(handle.name)
        try:
            source_args = argparse.Namespace(
                root=str(root),
                content_file=str(candidate_path),
                title=metadata["title"],
                url=metadata.get("url"),
                publisher=metadata["publisher"],
                published_at=metadata.get("published_at"),
                collected_at=metadata.get("collected_at"),
                source_type=metadata["source_type"],
                language=metadata["language"],
                reliability=metadata["reliability"],
                academic=metadata.get("academic"),
                supporting_of=None,
                force=True,
            )
            result = add_source(source_args)
        finally:
            candidate_path.unlink(missing_ok=True)

    review["status"] = "resolved"
    review["resolution"] = {
        "decided_at": timestamp(),
        "decision": decision,
        "rationale": rationale,
        "result": result,
    }
    resolved_path = root / RESOLVED_REVIEWS_DIR / review_path.name
    write_json(resolved_path, review)
    delete_record(root, "reviews_pending", review["review_id"])
    sync_obsidian_store(root)
    append_log(
        root,
        "resolve-review",
        f"{review['review_id']}: {decision}. {rationale}",
    )
    return {
        "action": "resolved",
        "review_id": review["review_id"],
        "decision": decision,
        "result": result,
    }


def resolve_review(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    review_path = root / PENDING_REVIEWS_DIR / f"{args.review_id}.json"
    if not record_exists(root, "reviews_pending", args.review_id):
        raise ValueError(f"Pending review not found: {args.review_id}")
    review = read_json(review_path)
    if not args.rationale.strip():
        raise ValueError("A non-empty rationale is required")
    if review.get("type") == "claim_conflict":
        return resolve_claim_review(
            root, review_path, review, args.decision, args.rationale.strip()
        )
    if review.get("type") == "duplicate_candidate":
        return resolve_duplicate_review(
            root,
            review_path,
            review,
            args.decision,
            args.rationale.strip(),
            args.related_source,
        )
    raise ValueError(f"Unsupported review type: {review.get('type')!r}")


def parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def audit_store(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    stale_days = args.stale_days
    if stale_days is None:
        settings = effective_settings(root)
        stale_days = int(settings.get("claim_stale_days", 180))

    findings: dict[str, list[str]] = defaultdict(list)
    risk_factors = _records_by_id(risk_factor_records(root), "risk_factor_id")
    for risk_factor_id, risk_factor in risk_factors.items():
        try:
            validate_risk_factor(risk_factor)
        except (TypeError, ValueError) as exc:
            findings["risk_factor_schema"].append(f"{risk_factor_id}: {exc}")
        parent_id = str(risk_factor.get("parent_risk_factor_id") or "")
        if parent_id and parent_id not in risk_factors:
            findings["risk_factor_integrity"].append(
                f"{risk_factor_id}: unknown parent {parent_id}"
            )
    source_ids: set[str] = set()
    for path, record in source_records(root):
        source_id = record.get("source_id")
        if not isinstance(source_id, str):
            findings["source_schema"].append(f"{path.name}: missing source_id")
            continue
        source_ids.add(source_id)
        if record.get("schema_version") != SOURCE_SCHEMA_VERSION:
            findings["source_schema"].append(
                f"{source_id}: schema_version must be {SOURCE_SCHEMA_VERSION}"
            )
        try:
            validate_modality(record.get("source_modality"))
        except ValueError as exc:
            findings["source_schema"].append(f"{source_id}: {exc}")
        if record.get("source_type") not in SOURCE_TYPES:
            findings["source_schema"].append(
                f"{source_id}: invalid source_type {record.get('source_type')!r}"
            )
        if record.get("reliability") not in SOURCE_RELIABILITY:
            findings["source_schema"].append(
                f"{source_id}: invalid reliability {record.get('reliability')!r}"
            )
        academic = record.get("academic")
        if record.get("source_type") == "academic":
            if not isinstance(academic, dict):
                findings["source_schema"].append(
                    f"{source_id}: academic source missing academic metadata"
                )
            else:
                if academic.get("kind") not in ACADEMIC_KINDS:
                    findings["source_schema"].append(
                        f"{source_id}: invalid academic kind {academic.get('kind')!r}"
                    )
                if (
                    academic.get("peer_review_status")
                    and academic.get("peer_review_status") not in PEER_REVIEW_STATUSES
                ):
                    findings["source_schema"].append(
                        f"{source_id}: invalid peer_review_status "
                        f"{academic.get('peer_review_status')!r}"
                    )
                if academic.get("conference_date") and not parse_iso_date(
                    academic.get("conference_date")
                ):
                    findings["source_schema"].append(
                        f"{source_id}: invalid conference_date "
                        f"{academic.get('conference_date')!r}"
                    )
                if academic.get("doi"):
                    try:
                        normalize_doi(str(academic["doi"]))
                    except ValueError:
                        findings["source_schema"].append(
                            f"{source_id}: invalid DOI {academic.get('doi')!r}"
                        )
        elif academic:
            findings["source_schema"].append(
                f"{source_id}: academic metadata on non-academic source"
            )
        for media in record.get("images", []):
            media_id = str(media.get("media_id") or "missing-media-id")
            if media.get("kind") not in MEDIA_KINDS:
                findings["media_schema"].append(
                    f"{source_id}/{media_id}: invalid kind {media.get('kind')!r}"
                )
            if media.get("rights_status") not in MEDIA_RIGHTS:
                findings["media_schema"].append(
                    f"{source_id}/{media_id}: invalid rights_status "
                    f"{media.get('rights_status')!r}"
                )
            for field in ("caption", "alt_text", "origin_url", "rights_note"):
                if not media.get(field):
                    findings["media_schema"].append(
                        f"{source_id}/{media_id}: missing {field}"
                    )
            subject_ids = media.get("subject_ids")
            if subject_ids is not None and (
                not isinstance(subject_ids, list)
                or any(
                    not isinstance(item, str) or not item.strip()
                    for item in subject_ids
                )
            ):
                findings["media_schema"].append(
                    f"{source_id}/{media_id}: invalid subject_ids"
                )
            local_ref = str(media.get("local_ref") or media.get("local_path") or "")
            if media.get("rights_status") == "link_only":
                if local_ref:
                    findings["media_schema"].append(
                        f"{source_id}/{media_id}: link_only must not have local_ref"
                    )
                if not media.get("image_url"):
                    findings["media_schema"].append(
                        f"{source_id}/{media_id}: link_only missing image_url"
                    )
            elif not local_ref:
                findings["media_integrity"].append(
                    f"{source_id}/{media_id}: SQLite image reference missing"
                )
            else:
                image_bytes = get_binary_asset(root, media_id)
                if image_bytes is None:
                    findings["media_integrity"].append(
                        f"{source_id}/{media_id}: SQLite image BLOB missing"
                    )
                elif raw_sha256(image_bytes) != media.get("content_sha256"):
                    findings["media_integrity"].append(
                        f"{source_id}/{media_id}: image BLOB hash changed"
                    )
        raw_bytes = get_source_content(root, source_id)
        if raw_bytes is None:
            findings["source_integrity"].append(f"{source_id}: source content BLOB missing")
        else:
            current_hash = raw_sha256(raw_bytes)
            # Git may materialize tracked Markdown with CRLF on Windows even
            # though the immutable source was registered and hashed with LF.
            # Accept only that transport-level newline conversion; all other
            # byte changes must still fail the integrity audit.
            lf_hash = raw_sha256(raw_bytes.replace(b"\r\n", b"\n"))
            if (
                current_hash != record.get("raw_sha256")
                and lf_hash != record.get("raw_sha256")
            ):
                findings["source_integrity"].append(
                    f"{source_id}: raw file hash changed"
                )

    active_values: dict[
        tuple[str, str], list[tuple[str, str, set[str]]]
    ] = defaultdict(list)
    all_claim_ids: set[str] = set()
    active_claim_ids: set[str] = set()
    for path, claim in claim_records(root):
        claim_id = claim.get("claim_id", path.stem)
        all_claim_ids.add(str(claim_id))
        if claim.get("schema_version") != CLAIM_SCHEMA_VERSION:
            findings["claim_schema"].append(
                f"{claim_id}: schema_version must be {CLAIM_SCHEMA_VERSION}"
            )
        if not str(claim.get("claim_version_id") or "").strip():
            findings["claim_schema"].append(f"{claim_id}: missing claim_version_id")
        if not isinstance(claim.get("version_no"), int) or claim.get("version_no", 0) < 1:
            findings["claim_schema"].append(f"{claim_id}: invalid version_no")
        unknown_risk_factors = sorted(
            set(str(item) for item in claim.get("risk_factor_ids", [])) - set(risk_factors)
        )
        if unknown_risk_factors:
            findings["risk_factor_integrity"].append(
                f"{claim_id}: unknown risk factors {', '.join(unknown_risk_factors)}"
            )
        if claim.get("status") not in CLAIM_STATUS:
            findings["claim_schema"].append(
                f"{claim_id}: invalid status {claim.get('status')!r}"
            )
        if claim.get("confidence") not in CLAIM_CONFIDENCE:
            findings["claim_schema"].append(
                f"{claim_id}: invalid confidence {claim.get('confidence')!r}"
            )
        missing_sources = [
            item for item in claim.get("source_ids", []) if item not in source_ids
        ]
        if missing_sources:
            findings["claim_evidence"].append(
                f"{claim_id}: unknown sources {', '.join(missing_sources)}"
            )
        if not claim.get("source_ids"):
            findings["claim_evidence"].append(f"{claim_id}: no source_ids")
        if claim.get("status") == "active":
            active_claim_ids.add(str(claim_id))
            verified = parse_iso_date(claim.get("last_verified"))
            if verified is None:
                findings["claim_schema"].append(
                    f"{claim_id}: invalid or missing last_verified"
                )
            elif (date.today() - verified).days > stale_days:
                findings["stale_claims"].append(
                    f"{claim_id}: last verified {verified.isoformat()}"
                )
            key = (str(claim.get("subject_id")), str(claim.get("predicate")))
            active_values[key].append(
                (
                    str(claim_id),
                    str(claim.get("value")),
                    {str(item) for item in claim.get("coexists_with", [])},
                )
            )

    for (subject_id, predicate), values in active_values.items():
        unresolved_ids: set[str] = set()
        for index, (claim_id, value, coexist_ids) in enumerate(values):
            for other_id, other_value, other_coexist_ids in values[index + 1 :]:
                if normalize_text(value) == normalize_text(other_value):
                    continue
                if other_id in coexist_ids or claim_id in other_coexist_ids:
                    continue
                unresolved_ids.update((claim_id, other_id))
        if unresolved_ids:
            detail = "; ".join(
                f"{claim_id}={value}"
                for claim_id, value, _ in values
                if claim_id in unresolved_ids
            )
            findings["active_conflicts"].append(
                f"{subject_id} / {predicate}: {detail}"
            )

    observation_versions = _records_by_id(
        observation_records(root), "observation_version_id"
    )
    for observation_version_id, observation in observation_versions.items():
        try:
            observation_version(observation)
        except (TypeError, ValueError) as exc:
            findings["observation_schema"].append(f"{observation_version_id}: {exc}")
        if observation.get("source_id") not in source_ids:
            findings["evidence_integrity"].append(
                f"{observation_version_id}: unknown source {observation.get('source_id')}"
            )
        unknown = sorted(set(observation.get("risk_factor_ids", [])) - set(risk_factors))
        if unknown:
            findings["risk_factor_integrity"].append(
                f"{observation_version_id}: unknown risk factors {', '.join(unknown)}"
            )
    event_versions = _records_by_id(event_records(root), "event_version_id")
    for event_version_id, event in event_versions.items():
        try:
            event_version(event)
        except (TypeError, ValueError) as exc:
            findings["event_schema"].append(f"{event_version_id}: {exc}")
        unknown_sources = sorted(set(event.get("source_ids", [])) - source_ids)
        if unknown_sources:
            findings["evidence_integrity"].append(
                f"{event_version_id}: unknown sources {', '.join(unknown_sources)}"
            )
        unknown = sorted(set(event.get("risk_factor_ids", [])) - set(risk_factors))
        if unknown:
            findings["risk_factor_integrity"].append(
                f"{event_version_id}: unknown risk factors {', '.join(unknown)}"
            )

    audit_claims_by_id = _records_by_id(claim_records(root), "claim_id")
    with sqlite_connection_scope(root) as connection:
        stored_claim_versions = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT claim_version_id, claim_id FROM wiki_claim_versions"
            )
        }
    stored_claim_version_ids = set(stored_claim_versions)
    audit_runs_by_id = _records_by_id(load_json_objects(root / RUNS_DIR), "run_id")
    audit_sources_by_id = _records_by_id(source_records(root), "source_id")
    insights = _records_by_id(insight_records(root), "insight_id")
    referenced_insights: set[str] = set()
    published_claim_ids: set[str] = set()
    published_source_ids: set[str] = set()
    analysis_by_insight: dict[str, str] = {}
    canonical_signal_versions = _records_by_id(
        signal_version_records(root), "signal_version_id"
    )
    systematic_analyses = _records_by_id(
        systematic_analysis_records(root), "analysis_result_version_id"
    )
    for result_id, result in systematic_analyses.items():
        try:
            validate_systematic_analysis_result(result, observation_versions)
        except (TypeError, ValueError) as exc:
            findings["systematic_analytics"].append(f"{result_id}: {exc}")
        signal_version_id = str(result.get("signal_version_id") or "")
        if signal_version_id not in canonical_signal_versions:
            findings["systematic_analytics"].append(
                f"{result_id}: unknown Signal version {signal_version_id or '-'}"
            )
        component_ids = set(
            (result.get("analysis_scope") or {}).get(
                "component_signal_version_ids", []
            )
        )
        unknown_components = sorted(component_ids - set(canonical_signal_versions))
        if unknown_components:
            findings["systematic_analytics"].append(
                f"{result_id}: unknown component Signal versions "
                + ", ".join(unknown_components)
            )
    # Immutable Signal history remains published evidence even after the active
    # Signal points to a newer analysis revision.  Do not reclassify historical
    # Claim and Source links as unpublished merely because a report was edited.
    for signal_version in canonical_signal_versions.values():
        for evidence in signal_version.get("evidence_refs", []):
            if str(evidence.get("kind") or "") == "claim":
                claim_id = stored_claim_versions.get(
                    str(evidence.get("version_id") or "")
                )
                if claim_id:
                    published_claim_ids.add(claim_id)
            published_source_ids.update(
                str(item) for item in evidence.get("source_ids", [])
            )
    company_impact_versions = _records_by_id(
        load_json_objects(root / COMPANY_IMPACTS_DIR), "company_impact_version_id"
    )
    scenario_versions = _records_by_id(
        load_json_objects(root / SCENARIOS_DIR), "scenario_version_id"
    )
    known_signal_ids = {
        str(record.get("signal_id"))
        for _, record in signal_records(root)
        if record.get("signal_id")
    }
    for path, signal in signal_records(root):
        signal_id = str(signal.get("signal_id") or path.stem)
        if signal.get("schema_version") != SIGNAL_SCHEMA_VERSION:
            findings["signal_schema"].append(
                f"{signal_id}: schema_version must be {SIGNAL_SCHEMA_VERSION}; "
                "run the full Signal migration"
            )
        try:
            validate_signal_type(signal.get("signal_type"))
        except ValueError as exc:
            findings["signal_schema"].append(f"{signal_id}: {exc}")
        run_id = str(signal.get("run_id") or "")
        run_contract = (
            audit_runs_by_id.get(run_id, {}).get("signal_contract")
            if run_id
            else None
        )
        contract_signal_ids = {
            str(item)
            for item in (run_contract or {}).get("signal_ids", [])
        }
        has_classification = bool(
            signal.get("signal_role")
            or signal.get("signal_origin")
            or signal_id in contract_signal_ids
        )
        if has_classification:
            try:
                validate_signal_classification(
                    signal.get("signal_role"), signal.get("signal_origin")
                )
            except ValueError as exc:
                findings["signal_schema"].append(f"{signal_id}: {exc}")
            if core_signal_uses_only_target_company_sources(
                signal, audit_sources_by_id
            ):
                findings["signal_quality"].append(
                    f"{signal_id}: core market Signal relies only on target-company "
                    "releases; use execution_context or add independent external evidence"
                )
        discovery_contract = (
            audit_runs_by_id.get(run_id, {}).get("discovery_contract")
            if run_id
            else None
        )
        discovery_signal_ids = {
            str(item) for item in (discovery_contract or {}).get("signal_ids", [])
        }
        if signal_id in discovery_signal_ids:
            try:
                validate_assumption_challenge(signal.get("assumption_challenge"))
            except ValueError as exc:
                findings["signal_quality"].append(f"{signal_id}: {exc}")
        insight_id = str(signal.get("insight_id") or "")
        if not insight_id or insight_id not in insights:
            findings["signal_integrity"].append(
                f"{signal_id}: unknown insight {insight_id or '-'}"
            )
            continue
        referenced_insights.add(insight_id)
        insight = insights[insight_id]
        systematic_projection = insight.get("systematic_analytics")
        if systematic_projection is not None:
            if not isinstance(systematic_projection, dict):
                findings["systematic_analytics"].append(
                    f"{signal_id}: systematic_analytics projection must be an object"
                )
            else:
                result_id = str(
                    systematic_projection.get("latest_result_version_id") or ""
                )
                result = systematic_analyses.get(result_id)
                if result is None:
                    findings["systematic_analytics"].append(
                        f"{signal_id}: unknown systematic analysis result {result_id or '-'}"
                    )
                elif str(result.get("signal_version_id")) != str(
                    signal.get("signal_version_id")
                ):
                    findings["systematic_analytics"].append(
                        f"{signal_id}: systematic analysis targets a different Signal version"
                    )
        insight_schema_version = insight.get("schema_version")
        if insight_schema_version not in {
            LEGACY_INSIGHT_SCHEMA_VERSION,
            INSIGHT_SCHEMA_VERSION,
        }:
            findings["signal_schema"].append(
                f"{insight_id}: schema_version must be "
                f"{LEGACY_INSIGHT_SCHEMA_VERSION} or {INSIGHT_SCHEMA_VERSION}"
            )
        signal_version_id = str(signal.get("signal_version_id") or "")
        canonical_key = str(signal.get("canonical_key") or "")
        if not signal_version_id or signal_version_id not in canonical_signal_versions:
            findings["signal_integrity"].append(
                f"{signal_id}: unknown signal_version_id {signal_version_id or '-'}"
            )
        elif canonical_signal_versions[signal_version_id].get("signal_id") != signal_id:
            findings["signal_integrity"].append(
                f"{signal_id}: canonical version points to another signal"
            )
        if not canonical_key:
            findings["signal_schema"].append(f"{signal_id}: missing canonical_key")
        risk_factor_ids = {str(item) for item in signal.get("risk_factor_ids", [])}
        if not risk_factor_ids:
            findings["signal_schema"].append(f"{signal_id}: no risk_factor_ids")
        unknown_risk_factors = sorted(risk_factor_ids - set(risk_factors))
        if unknown_risk_factors:
            findings["risk_factor_integrity"].append(
                f"{signal_id}: unknown risk factors {', '.join(unknown_risk_factors)}"
            )
        evidence_refs = signal.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            findings["signal_schema"].append(f"{signal_id}: no canonical evidence_refs")
        else:
            known_evidence = {
                "claim": {
                    *stored_claim_version_ids,
                },
                "observation": set(observation_versions),
                "event": set(event_versions),
            }
            for evidence in evidence_refs:
                kind = str(evidence.get("kind") or "")
                version_id = str(evidence.get("version_id") or "")
                if kind not in known_evidence or version_id not in known_evidence.get(kind, set()):
                    findings["evidence_integrity"].append(
                        f"{signal_id}: unknown {kind or 'evidence'} version {version_id or '-'}"
                    )
                try:
                    validate_modality(evidence.get("modality"))
                except ValueError as exc:
                    findings["signal_schema"].append(f"{signal_id}: {exc}")
        for impact_id in signal.get("company_impact_version_ids", []):
            if str(impact_id) not in company_impact_versions:
                findings["signal_integrity"].append(
                    f"{signal_id}: unknown company impact {impact_id}"
                )
        for scenario_id in signal.get("scenario_version_ids", []):
            if str(scenario_id) not in scenario_versions:
                findings["signal_integrity"].append(
                    f"{signal_id}: unknown scenario {scenario_id}"
                )
        if insight_schema_version == INSIGHT_SCHEMA_VERSION:
            try:
                validate_structured_analysis(
                    insight.get("analysis_structured"),
                    allowed_claim_ids={str(item) for item in insight.get("claim_ids", [])},
                    allowed_source_ids={str(item) for item in insight.get("source_ids", [])},
                    require_current_schema=True,
                    importance_score=max(
                        int((signal.get("business_impact") or {}).get("score") or 0),
                        int((signal.get("urgency") or {}).get("score") or 0),
                    ),
                )
            except ValueError as exc:
                findings["signal_schema"].append(
                    f"{insight_id}: invalid structured analysis: {exc}"
                )
        if not run_id or run_id not in audit_runs_by_id:
            findings["signal_integrity"].append(
                f"{signal_id}: missing or unknown run_id {run_id or '-'}"
            )
        else:
            run_signal_ids = {
                str(item) for item in audit_runs_by_id[run_id].get("signal_ids", [])
            }
            if signal_id not in run_signal_ids:
                findings["signal_integrity"].append(
                    f"{signal_id}: run {run_id} does not list this Signal"
                )
        if str(insight.get("run_id") or "") != run_id:
            findings["signal_integrity"].append(
                f"{signal_id}: Signal and Insight run_id differ"
            )
        signal_claim_ids = {str(item) for item in signal.get("claim_ids", [])}
        insight_claim_ids = {str(item) for item in insight.get("claim_ids", [])}
        insight_claims_by_predicate = {
            str(audit_claims_by_id[claim_id].get("predicate") or ""):
            audit_claims_by_id[claim_id]
            for claim_id in insight_claim_ids
            if claim_id in audit_claims_by_id
        }
        insight_predicates = set(insight_claims_by_predicate)
        missing_predicates = sorted(REQUIRED_SIGNAL_PREDICATES - insight_predicates)
        if missing_predicates:
            findings["signal_schema"].append(
                f"{signal_id}: missing assessment claims {', '.join(missing_predicates)}"
            )
        if signal_claim_ids != insight_claim_ids:
            findings["signal_integrity"].append(
                f"{signal_id}: Signal and Insight claim links differ"
            )
        unknown_claims = sorted(insight_claim_ids - all_claim_ids)
        if unknown_claims:
            findings["signal_integrity"].append(
                f"{signal_id}: unknown claims {', '.join(unknown_claims)}"
            )
        published_claim_ids.update(insight_claim_ids & all_claim_ids)
        unknown_sources = sorted(
            {str(item) for item in insight.get("source_ids", [])} - source_ids
        )
        published_source_ids.update(
            {str(item) for item in insight.get("source_ids", [])} & source_ids
        )
        if unknown_sources:
            findings["signal_integrity"].append(
                f"{signal_id}: unknown sources {', '.join(unknown_sources)}"
            )
        for field in ("business_impact", "urgency"):
            assessment = signal.get(field) or {}
            score = assessment.get("score")
            if (
                not isinstance(score, int)
                or score not in range(1, SIGNAL_SCORE_MAX + 1)
            ):
                findings["signal_schema"].append(
                    f"{signal_id}: invalid {field} score {score!r}"
                )
            try:
                validate_score_rationale(
                    field, int(score or 0), assessment.get("rationale")
                )
            except ValueError as exc:
                findings["signal_quality"].append(f"{signal_id}: {exc}")
        if (signal.get("business_impact") or {}).get("score") == 10:
            exceptional_basis = signal.get("exceptional_score_basis")
            required_basis = (
                "enterprise_scope",
                "immediate_action",
                "delay_loss",
                "irreversibility",
            )
            if not isinstance(exceptional_basis, dict) or any(
                not str(exceptional_basis.get(key) or "").strip()
                for key in required_basis
            ):
                findings["signal_schema"].append(
                    f"{signal_id}: 사업영향도 10점은 전사 범위·즉시성·지연 손실·불가역성 "
                    "근거가 모두 필요"
                )
        score_scale = signal.get("score_scale")
        if (
            not isinstance(score_scale, dict)
            or score_scale.get("minimum") != 1
            or score_scale.get("maximum") != SIGNAL_SCORE_MAX
            or score_scale.get("calibration") not in {"rubric_v1", "legacy_anchor"}
        ):
            findings["signal_schema"].append(
                f"{signal_id}: invalid or missing 1~{SIGNAL_SCORE_MAX} score_scale"
            )
        if signal.get("assessment_confidence") not in CLAIM_CONFIDENCE:
            findings["signal_schema"].append(
                f"{signal_id}: invalid assessment_confidence"
            )
        expected_values = {
            "business_axis": signal.get("business_axis"),
            "business_impact_score_1_to_10": str(
                (signal.get("business_impact") or {}).get("score")
            ),
            "business_impact_rationale": (
                signal.get("business_impact") or {}
            ).get("rationale"),
            "urgency_score_1_to_10": str(
                (signal.get("urgency") or {}).get("score")
            ),
            "urgency_rationale": (signal.get("urgency") or {}).get("rationale"),
            "assessment_confidence": signal.get("assessment_confidence"),
            "assessed_at": signal.get("assessed_at"),
        }
        mismatched = [
            predicate
            for predicate, expected in expected_values.items()
            if predicate in insight_claims_by_predicate
            and normalize_text(
                str(insight_claims_by_predicate[predicate].get("value") or "")
            )
            != normalize_text(str(expected or ""))
        ]
        if mismatched:
            findings["signal_integrity"].append(
                f"{signal_id}: fields disagree with claims {', '.join(mismatched)}"
            )
        axis = str(signal.get("business_axis") or "")
        invalid_pairs = [
            f"{company_id}={axis}"
            for company_id in signal.get("company_ids", [])
            if not company_supports_business_axis(str(company_id), axis)
        ]
        if invalid_pairs:
            findings["signal_schema"].append(
                f"{signal_id}: invalid company/business-axis pairs "
                + ", ".join(invalid_pairs)
            )
        analysis = str(insight.get("analysis_markdown") or "")
        try:
            validate_signal_copy(
                str(insight.get("title") or ""),
                str(signal.get("sentence") or ""),
                str(insight.get("summary") or ""),
            )
        except ValueError as exc:
            findings["signal_quality"].append(f"{signal_id}: {exc}")
        try:
            validate_signal_analysis(analysis)
        except ValueError as exc:
            findings["signal_quality"].append(f"{signal_id}: {exc}")
        impact_estimate = insight.get("impact_estimate")
        if impact_estimate is not None:
            try:
                validate_impact_estimate(impact_estimate)
            except ValueError as exc:
                findings["signal_schema"].append(
                    f"{signal_id}: invalid impact estimate: {exc}"
                )
        quantification_decision = insight.get("quantification_decision")
        try:
            validate_quantification_decision(
                quantification_decision, impact_estimate
            )
        except ValueError as exc:
            findings["signal_quality"].append(
                f"{signal_id}: invalid quantification decision: {exc}"
            )
        else:
            structured_status = structured_quantification_status(
                insight.get("analysis_structured")
            )
            if structured_status != quantification_decision["status"]:
                findings["signal_quality"].append(
                    f"{signal_id}: structured quantification status "
                    f"{structured_status or '-'} disagrees with Insight "
                    f"{quantification_decision['status']}"
                )
            unknown_related = sorted(
                set(quantification_decision.get("related_signal_ids", []))
                - known_signal_ids
            )
            if unknown_related:
                findings["signal_integrity"].append(
                    f"{signal_id}: unknown related quantification Signals "
                    + ", ".join(unknown_related)
                )
        analysis_by_insight[insight_id] = analysis

    normalized_contracts = {
        "wiki_source_assets": (
            "source_id",
            source_ids,
        ),
        "wiki_risk_factors": (
            "risk_factor_id",
            set(risk_factors),
        ),
        "wiki_claim_versions": (
            "claim_version_id",
            {
                str(value.get("claim_version_id"))
                for value in audit_claims_by_id.values()
                if value.get("claim_version_id")
            },
        ),
        "wiki_observation_versions": (
            "observation_version_id",
            set(observation_versions),
        ),
        "wiki_event_versions": (
            "event_version_id",
            set(event_versions),
        ),
        "wiki_signal_versions": (
            "signal_version_id",
            set(canonical_signal_versions),
        ),
        "wiki_company_impact_versions": (
            "company_impact_version_id",
            set(company_impact_versions),
        ),
        "wiki_scenario_versions": (
            "scenario_version_id",
            set(scenario_versions),
        ),
        "wiki_systematic_analysis_versions": (
            "analysis_result_version_id",
            set(systematic_analyses),
        ),
    }
    with sqlite_connection_scope(root) as connection:
        for table, (column, expected_ids) in normalized_contracts.items():
            actual_ids = {
                str(row[0])
                for row in connection.execute(f"SELECT {column} FROM {table}")
            }
            missing_ids = sorted(expected_ids - actual_ids)
            orphan_ids = sorted(actual_ids - expected_ids)
            if missing_ids:
                findings["analytics_projection"].append(
                    f"{table}: missing normalized rows {', '.join(missing_ids)}"
                )
            if orphan_ids and table != "wiki_claim_versions":
                findings["analytics_projection"].append(
                    f"{table}: orphan normalized rows {', '.join(orphan_ids)}"
                )
        expected_links: set[tuple[str, str, str]] = set()
        for table, id_column, subject_kind in (
            ("wiki_claim_versions", "claim_version_id", "claim"),
            ("wiki_observation_versions", "observation_version_id", "observation"),
            ("wiki_event_versions", "event_version_id", "event"),
            ("wiki_signal_versions", "signal_version_id", "signal"),
        ):
            for row in connection.execute(f"SELECT {id_column}, payload_json FROM {table}"):
                payload = json.loads(str(row["payload_json"]))
                expected_links.update(
                    (str(risk_factor_id), subject_kind, str(row[id_column]))
                    for risk_factor_id in payload.get("risk_factor_ids", [])
                )
        actual_links = {
            (str(row[0]), str(row[1]), str(row[2]))
            for row in connection.execute(
                "SELECT risk_factor_id, subject_kind, subject_version_id "
                "FROM wiki_risk_factor_links"
            )
        }
        if expected_links != actual_links:
            findings["analytics_projection"].append(
                "wiki_risk_factor_links: normalized link set disagrees with version payloads"
            )
        expected_inputs = {
            (
                result_id,
                str(observation_version_id),
                str(series.get("risk_factor_id")),
                str(series.get("series_key")),
            )
            for result_id, result in systematic_analyses.items()
            for series in result.get("input_series", [])
            for observation_version_id in series.get("observation_version_ids", [])
        }
        actual_inputs = {
            (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in connection.execute(
                "SELECT analysis_result_version_id, observation_version_id, "
                "risk_factor_id, series_key FROM wiki_systematic_analysis_inputs"
            )
        }
        if expected_inputs != actual_inputs:
            findings["analytics_projection"].append(
                "wiki_systematic_analysis_inputs: normalized input set disagrees with result payloads"
            )

    active_signals = [
        signal for _, signal in signal_records(root) if signal.get("status") == "active"
    ]
    if len(active_signals) >= 10:
        for field in ("business_impact", "urgency"):
            scores = [
                int((signal.get(field) or {}).get("score") or 0)
                for signal in active_signals
            ]
            high_band = sum(score >= 9 for score in scores)
            exceptional = sum(score == 10 for score in scores)
            if high_band / len(scores) > 0.25:
                findings["score_calibration"].append(
                    f"{field}: 9~10점이 {high_band}/{len(scores)}건으로 25%를 초과해 상위점수 인플레이션 검토 필요"
                )
            if exceptional / len(scores) > 0.10:
                findings["score_calibration"].append(
                    f"{field}: 예외 등급 10점이 {exceptional}/{len(scores)}건으로 10%를 초과"
                )

    signals_by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_audit_signals: list[dict[str, Any]] = []
    for _, signal in signal_records(root):
        all_audit_signals.append(signal)
        signals_by_run[str(signal.get("run_id") or "")].append(signal)
    for run_id, run in sorted(audit_runs_by_id.items()):
        listed_signal_ids = {
            str(signal_id)
            for signal_id in run.get("signal_ids", [])
            if str(signal_id)
        }
        run_signals = [
            signal
            for signal in all_audit_signals
            if str(signal.get("run_id") or "") == run_id
            or str(signal.get("signal_id") or "") in listed_signal_ids
        ]
        research_contract = run.get("research_contract")
        if (
            isinstance(research_contract, dict)
            and int(research_contract.get("version") or 0) >= 1
            and (run.get("completed_at") or run.get("status") in {"success", "completed"})
        ):
            findings["research_coverage"].extend(
                evaluate_research_coverage(run, run_signals)
            )
        contract = run.get("signal_contract")
        if not isinstance(contract, dict) or int(contract.get("version") or 0) < 1:
            continue
        audit_contract = dict(contract)
        count_limited_research = (
            isinstance(run.get("research_contract"), dict)
            and run["research_contract"].get("mode") == "count_limited"
        )
        if (
            int(audit_contract.get("version") or 0) >= 2
            and (
                count_limited_research
                or (
                    not run.get("completed_at")
                    and run.get("status") not in {"success", "completed"}
                )
            )
        ):
            # A run can be audited while collection is still in progress. Keep the
            # source-bias checks active, but defer frequency and score-band vitality
            # checks until the run has been explicitly completed. Explicitly
            # count-limited runs never inherit full-monitoring volume quotas.
            audit_contract["version"] = 1
        findings["signal_portfolio"].extend(
            evaluate_run_signal_contract(
                run_id,
                [
                    signal
                    for signal in run_signals
                    if str(signal.get("signal_id") or "")
                    in {str(item) for item in contract.get("signal_ids", [])}
                ],
                audit_claims_by_id,
                audit_contract,
            )
        )

    for insight_id in sorted(set(insights) - referenced_insights):
        findings["signal_integrity"].append(
            f"{insight_id}: Insight is not referenced by any Signal"
        )
    for claim_id in sorted(active_claim_ids - published_claim_ids):
        findings["unpublished_claims"].append(
            f"{claim_id}: active Claim is not connected to a Signal"
        )
    for source_id in sorted(source_ids - published_source_ids):
        findings["unpublished_sources"].append(
            f"{source_id}: Source is not connected to a Signal"
        )
    analysis_items = [
        (insight_id, normalize_text(analysis))
        for insight_id, analysis in sorted(analysis_by_insight.items())
    ]
    for index, (insight_id, analysis) in enumerate(analysis_items):
        for other_id, other_analysis in analysis_items[index + 1 :]:
            matcher = SequenceMatcher(None, analysis, other_analysis)
            # real_quick_ratio() and quick_ratio() are upper bounds for ratio().
            # They preserve the 90% finding contract while avoiding an expensive
            # character-level comparison for clearly dissimilar long reports.
            if matcher.real_quick_ratio() < 0.9 or matcher.quick_ratio() < 0.9:
                continue
            similarity = matcher.ratio()
            if similarity >= 0.9:
                findings["signal_quality"].append(
                    f"{insight_id} / {other_id}: analyses are {similarity:.0%} similar"
                )

    for path, run in load_json_objects(root / RUNS_DIR):
        results = run.get("results") or {}
        new_claims = int(results.get("new_claims") or 0)
        new_signals = int(results.get("new_signals") or 0)
        if new_claims > 0 and new_signals < 1:
            findings["run_publication"].append(
                f"{run.get('run_id') or path.stem}: {new_claims} new claims but no published Signal"
            )

    pending_records = load_json_objects(root / PENDING_REVIEWS_DIR)
    for path, _ in pending_records:
        findings["pending_reviews"].append(path.stem)

    report_date = today()
    report_path = root / "reports" / "audits" / f"audit-{report_date}.md"
    lines = [
        "---",
        f"title: Market Sensing Intelligence Audit {report_date}",
        f"date: {report_date}",
        "---",
        "",
        f"# Market Sensing Intelligence Audit - {report_date}",
        "",
        "## Summary",
        "",
    ]
    categories = [
        "source_integrity",
        "source_schema",
        "risk_factor_schema",
        "risk_factor_integrity",
        "media_integrity",
        "media_schema",
        "claim_schema",
        "claim_evidence",
        "observation_schema",
        "event_schema",
        "evidence_integrity",
        "analytics_projection",
        "signal_schema",
        "signal_integrity",
        "signal_quality",
        "score_calibration",
        "research_coverage",
        "signal_portfolio",
        "unpublished_claims",
        "unpublished_sources",
        "run_publication",
        "stale_claims",
        "active_conflicts",
        "pending_reviews",
    ]
    for category in categories:
        lines.append(f"- {category}: {len(findings.get(category, []))}")
    for category in categories:
        values = findings.get(category, [])
        if not values:
            continue
        lines.extend(["", f"## {category}", ""])
        lines.extend(f"- {value}" for value in values)
    report_text = "\n".join(lines) + "\n"
    report_id = f"audit:{report_date}"
    put_artifact(
        root,
        report_id,
        "audit",
        f"Market Sensing Intelligence Audit {report_date}",
        markdown_text=report_text,
        metadata={"counts": {key: len(findings.get(key, [])) for key in categories}},
    )
    append_log(
        root,
        "audit",
        f"{sum(len(items) for items in findings.values())} findings. "
        f"Artifact: {report_id}",
    )
    return {
        "action": "audited",
        "report_artifact_id": report_id,
        "counts": {key: len(findings.get(key, [])) for key in categories},
    }


def brief(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    settings = effective_settings(root)
    sources_by_id = {
        str(record.get("source_id", "")): record
        for _, record in source_records(root)
        if record.get("source_id")
    }
    priority_order = {
        predicate: index
        for index, predicate in enumerate(settings.get("priority_predicates", []))
    }
    since = validate_date(args.since, "since")
    assert since is not None
    changes: list[dict[str, Any]] = []
    for _, claim in claim_records(root):
        for event in claim.get("history", []):
            event_date = event.get("date")
            if isinstance(event_date, str) and event_date > since:
                changes.append(
                    {
                        "date": event_date,
                        "claim_id": claim.get("claim_id"),
                        "subject_id": claim.get("subject_id"),
                        "predicate": claim.get("predicate"),
                        "value": claim.get("value"),
                        "status": claim.get("status"),
                        "action": event.get("action"),
                        "reason": event.get("reason", ""),
                        "source_ids": claim.get("source_ids", []),
                    }
                )
    changes.sort(
        key=lambda item: (
            item["date"],
            priority_order.get(str(item["predicate"]), len(priority_order)),
            item["subject_id"],
            item["predicate"],
        )
    )
    pending = sorted(path.stem for path, _ in load_json_objects(root / PENDING_REVIEWS_DIR))
    report_path = (
        root / "reports" / "briefs" / f"brief-{since}-to-{today()}.md"
    )
    lines = [
        "---",
        f"title: 포스코그룹 마켓센싱 브리프 · {since}–{today()}",
        f"date: {today()}",
        f"since: {since}",
        "---",
        "",
        "# 포스코그룹 마켓센싱 브리프",
        "",
        f"> 관찰 기간 **{since}–{today()}** · 마지막 기준일 이후 확인된 변화만 정리",
        "",
        '!!! abstract "한눈에 보기"',
        "",
        f"    **확인된 변화 {len(changes)}건** · **사람 검토 대기 {len(pending)}건**",
        "",
        "    사실과 근거를 먼저 제시하고, AI 분석은 별도 구역에서 구분합니다.",
        "",
        "## 확인된 변화",
        "",
    ]
    if changes:
        lines.extend(
            [
                "| 확인일 | 대상·항목 | 확인된 변화 |",
                "| --- | --- | --- |",
            ]
        )
        for item in changes:
            subject = reader_subject_name(str(item["subject_id"]), settings)
            predicate = str(item["predicate"])
            predicate_label = PREDICATE_LABELS.get(
                predicate,
                predicate.replace("_", " ").strip().capitalize(),
            )
            action_label = CLAIM_ACTION_LABELS.get(
                str(item["action"]),
                str(item["action"]),
            )
            status = CLAIM_STATUS_LABELS.get(
                str(item["status"]),
                str(item["status"]),
            )
            detail = (
                f"**{action_label}.** "
                f"{humanize_claim_value(item['value'])}"
            )
            if status != "현재 유효":
                detail += f" · 상태: {status}"
            reason = str(item["reason"]).strip()
            if reason:
                detail += f" · {reason}"
            detail += " " + claim_source_footnote_references(item)
            lines.append(
                f"| {markdown_cell(item['date'])} | "
                f"**{markdown_cell(subject)}** · {markdown_cell(predicate_label)} | "
                f"{markdown_cell(detail)} |"
            )
    else:
        lines.extend(
            [
                '!!! info "새로 확인된 변화 없음"',
                "",
                "    이 기간에 기록된 Claim 변화가 없습니다.",
            ]
        )
    lines.extend(["", "## 사람 검토", ""])
    if pending:
        lines.extend(
            [
                '!!! warning "판단 대기 항목 있음"',
                "",
                f"    **{len(pending)}건**이 사람의 판단을 기다리고 있습니다. "
                "[검토 대기 화면](../../REVIEW.md)에서 근거와 선택지를 확인하세요.",
            ]
        )
    else:
        lines.extend(
            [
                '!!! info "검토 대기 없음"',
                "",
                "    현재 사람의 판단을 기다리는 충돌 항목이 없습니다.",
            ]
        )
    lines.extend(
        [
            "",
            "## AI 분석",
            "",
            '!!! note "작성 전"',
            "",
            "    근거 원문을 다시 확인한 뒤 경쟁적 의미와 POSCO 관점의 시사점을 "
            "작성합니다.",
            "    사실과 추론을 섞지 않고 불확실성을 함께 표시합니다.",
            "",
            "## 후속 확인",
            "",
            '!!! note "추가 확인 항목"',
            "",
            "    추가 검증이 필요한 출처·프로젝트·주장을 여기에 정리합니다.",
        ]
    )
    cited_source_ids = sorted(
        {
            str(source_id)
            for item in changes
            for source_id in item.get("source_ids", [])
        }
    )
    if cited_source_ids:
        lines.extend(["", "## 근거 자료", ""])
        lines.extend(
            source_footnote_definition(source_id, sources_by_id)
            for source_id in cited_source_ids
        )
    report_text = "\n".join(lines) + "\n"
    report_id = f"brief:{since}:{today()}"
    html_text: str | None = None
    if getattr(args, "html", False):
        with tempfile.TemporaryDirectory() as temp_directory:
            temp_root = Path(temp_directory)
            markdown_path = temp_root / "brief.md"
            html_path = temp_root / "brief.html"
            atomic_write_text(markdown_path, report_text)
            render_report_html(root, markdown_path, html_path)
            html_text = html_path.read_text(encoding="utf-8")
    put_artifact(
        root,
        report_id,
        "brief",
        f"포스코그룹 마켓센싱 브리프 · {since}–{today()}",
        markdown_text=report_text,
        html_text=html_text,
        metadata={
            "since": since,
            "through": today(),
            "change_count": len(changes),
            "pending_review_count": len(pending),
        },
    )
    append_log(
        root,
        "brief",
        f"{len(changes)} changes since {since}. "
        f"Artifact: {report_id}" + ("; HTML stored" if html_text else ""),
    )
    result = {
        "action": "brief_created",
        "report_artifact_id": report_id,
        "change_count": len(changes),
        "pending_review_count": len(pending),
    }
    if html_text:
        result["html_stored"] = True
    return result


def render_report(args: argparse.Namespace) -> dict[str, Any]:
    root = require_store(Path(args.root))
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise ValueError(f"Markdown report does not exist: {input_path}")
    if input_path.suffix.casefold() != ".md":
        raise ValueError("render-report input must be a .md file")
    if args.output:
        raise ValueError("--output was retired; rendered HTML is stored in SQLite")
    with tempfile.TemporaryDirectory() as temp_directory:
        output_path = Path(temp_directory) / "report.html"
        rendered = render_report_html(root, input_path, output_path)
        html_text = output_path.read_text(encoding="utf-8")
    markdown_text = input_path.read_text(encoding="utf-8")
    report_id = f"report:{raw_sha256(markdown_text.encode('utf-8'))[:16]}"
    put_artifact(
        root,
        report_id,
        "report",
        input_path.stem,
        markdown_text=markdown_text,
        html_text=html_text,
        metadata={
            "source_count": rendered["source_count"],
            "missing_source_ids": rendered["missing_source_ids"],
        },
    )
    append_log(
        root,
        "render-report",
        f"{input_path.name} -> {report_id} "
        f"({rendered['source_count']} cited sources)",
    )
    return {
        "action": "html_report_stored",
        "report_artifact_id": report_id,
        "source_count": rendered["source_count"],
        "missing_source_ids": rendered["missing_source_ids"],
    }


def _nested_reference_ids(
    value: Any,
    singular_key: str,
    plural_key: str,
) -> set[str]:
    references: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key == singular_key and isinstance(child, str) and child.strip():
                    references.add(child.strip())
                elif key == plural_key and isinstance(child, list):
                    references.update(
                        item.strip()
                        for item in child
                        if isinstance(item, str) and item.strip()
                    )
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return references


def _signal_prune_plan(
    connection: Any, retained_signal_ids: set[str] | None = None
) -> dict[str, Any]:
    records: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in connection.execute(
        "SELECT collection, record_id, payload_json FROM wiki_records"
    ):
        records[str(row["collection"])][str(row["record_id"])] = json.loads(
            row["payload_json"]
        )

    all_signals = records.get("signals", {})
    if not all_signals:
        raise ValueError("prune-to-signals requires at least one stored Signal")
    if retained_signal_ids is not None:
        unknown = retained_signal_ids - set(all_signals)
        if unknown:
            raise ValueError(
                "Unknown retained Signal IDs: " + ", ".join(sorted(unknown))
            )
        if not retained_signal_ids:
            raise ValueError("At least one --signal-id must be retained")
        signals = {
            signal_id: all_signals[signal_id]
            for signal_id in sorted(retained_signal_ids)
        }
    else:
        signals = all_signals

    keep_insights: set[str] = set()
    keep_claims: set[str] = set()
    keep_sources: set[str] = set()
    keep_runs: set[str] = set()
    keep_signal_versions: set[str] = set()
    keep_observations: set[str] = set()
    keep_events: set[str] = set()
    keep_company_impacts: set[str] = set()
    keep_scenarios: set[str] = set()
    keep_risk_factors: set[str] = set()
    for signal in signals.values():
        keep_insights.update(
            _nested_reference_ids(signal, "insight_id", "insight_ids")
        )
        keep_claims.update(_nested_reference_ids(signal, "claim_id", "claim_ids"))
        keep_sources.update(_nested_reference_ids(signal, "source_id", "source_ids"))
        keep_risk_factors.update(str(item) for item in signal.get("risk_factor_ids", []))
        run_id = str(signal.get("run_id") or "").strip()
        if run_id and run_id in records.get("runs", {}):
            keep_runs.add(run_id)

    for version_id, version in records.get("signal_versions", {}).items():
        if str(version.get("signal_id") or "") in signals:
            keep_signal_versions.add(version_id)
            keep_company_impacts.update(
                str(item) for item in version.get("company_impact_version_ids", [])
            )
            keep_scenarios.update(str(item) for item in version.get("scenario_version_ids", []))
            keep_risk_factors.update(str(item) for item in version.get("risk_factor_ids", []))
            for evidence in version.get("evidence_refs", []):
                if not isinstance(evidence, dict):
                    continue
                kind = str(evidence.get("kind") or "")
                evidence_id = str(evidence.get("version_id") or "")
                if kind == "observation":
                    keep_observations.add(evidence_id)
                elif kind == "event":
                    keep_events.add(evidence_id)
                elif kind == "claim":
                    keep_claims.update(
                        claim_id
                        for claim_id, claim in records.get("claims", {}).items()
                        if claim.get("claim_version_id") == evidence_id
                    )
                keep_sources.update(str(item) for item in evidence.get("source_ids", []))

    for evidence_id in keep_observations:
        evidence = records.get("observations", {}).get(evidence_id, {})
        source_id = str(evidence.get("source_id") or "")
        if source_id:
            keep_sources.add(source_id)
        keep_risk_factors.update(str(item) for item in evidence.get("risk_factor_ids", []))
    for evidence_id in keep_events:
        evidence = records.get("events", {}).get(evidence_id, {})
        keep_sources.update(str(item) for item in evidence.get("source_ids", []))
        keep_risk_factors.update(str(item) for item in evidence.get("risk_factor_ids", []))

    missing_insights = keep_insights - set(records.get("insights", {}))
    if missing_insights:
        raise ValueError(
            "Cannot prune with missing Signal Insight references: "
            + ", ".join(sorted(missing_insights))
        )

    for insight_id in keep_insights:
        insight = records["insights"][insight_id]
        keep_claims.update(_nested_reference_ids(insight, "claim_id", "claim_ids"))
        keep_sources.update(_nested_reference_ids(insight, "source_id", "source_ids"))

    while True:
        before = len(keep_claims)
        for claim_id in tuple(keep_claims):
            claim = records.get("claims", {}).get(claim_id)
            if claim is None:
                continue
            keep_claims.update(_nested_reference_ids(claim, "claim_id", "claim_ids"))
            for relation_key in ("supersedes", "coexists_with"):
                relation_ids = claim.get(relation_key, [])
                if isinstance(relation_ids, list):
                    keep_claims.update(
                        item.strip()
                        for item in relation_ids
                        if isinstance(item, str) and item.strip()
                    )
            keep_sources.update(_nested_reference_ids(claim, "source_id", "source_ids"))
        if len(keep_claims) == before:
            break

    missing_claims = keep_claims - set(records.get("claims", {}))
    if missing_claims:
        raise ValueError(
            "Cannot prune with missing Signal Claim references: "
            + ", ".join(sorted(missing_claims))
        )

    while True:
        before = len(keep_sources)
        for source_id in tuple(keep_sources):
            source = records.get("sources", {}).get(source_id)
            if source is None:
                continue
            keep_sources.update(_nested_reference_ids(source, "source_id", "source_ids"))
            previous_version = source.get("previous_version")
            if isinstance(previous_version, str) and previous_version.strip():
                keep_sources.add(previous_version.strip())
        if len(keep_sources) == before:
            break

    missing_sources = keep_sources - set(records.get("sources", {}))
    if missing_sources:
        raise ValueError(
            "Cannot prune with missing Signal Source references: "
            + ", ".join(sorted(missing_sources))
        )

    while True:
        before = len(keep_risk_factors)
        for risk_factor_id in tuple(keep_risk_factors):
            parent = str(
                records.get("risk_factors", {})
                .get(risk_factor_id, {})
                .get("parent_risk_factor_id")
                or ""
            )
            if parent:
                keep_risk_factors.add(parent)
        if len(keep_risk_factors) == before:
            break

    keep_by_collection = {
        "signals": set(signals),
        "signal_versions": keep_signal_versions,
        "insights": keep_insights,
        "claims": keep_claims,
        "sources": keep_sources,
        "risk_factors": keep_risk_factors,
        "observations": keep_observations,
        "events": keep_events,
        "company_impacts": keep_company_impacts,
        "scenarios": keep_scenarios,
        "runs": keep_runs,
    }
    remove_by_collection = {
        collection: sorted(
            set(items) - keep_by_collection.get(collection, set())
        )
        for collection, items in records.items()
    }
    return {
        "keep_by_collection": keep_by_collection,
        "remove_by_collection": remove_by_collection,
        "artifact_count": connection.execute(
            "SELECT COUNT(*) FROM wiki_artifacts"
        ).fetchone()[0],
        "operation_log_count": connection.execute(
            "SELECT COUNT(*) FROM wiki_operation_log"
        ).fetchone()[0],
        "binary_asset_remove_count": connection.execute(
            "SELECT COUNT(*) FROM wiki_binary_assets"
        ).fetchone()[0]
        if not keep_sources
        else connection.execute(
            "SELECT COUNT(*) FROM wiki_binary_assets "
            f"WHERE source_id IS NULL OR source_id NOT IN ({','.join('?' * len(keep_sources))})",
            tuple(sorted(keep_sources)),
        ).fetchone()[0],
        "source_content_remove_count": connection.execute(
            "SELECT COUNT(*) FROM wiki_source_contents"
        ).fetchone()[0]
        if not keep_sources
        else connection.execute(
            "SELECT COUNT(*) FROM wiki_source_contents "
            f"WHERE source_id NOT IN ({','.join('?' * len(keep_sources))})",
            tuple(sorted(keep_sources)),
        ).fetchone()[0],
    }


def _public_signal_prune_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "preserved": {
            collection: len(record_ids)
            for collection, record_ids in plan["keep_by_collection"].items()
        },
        "removed": {
            **{
                collection: len(record_ids)
                for collection, record_ids in plan["remove_by_collection"].items()
                if record_ids
            },
            "artifacts": plan["artifact_count"],
            "operation_log": plan["operation_log_count"],
            "binary_assets": plan["binary_asset_remove_count"],
            "source_contents": plan["source_content_remove_count"],
        },
    }


def prune_to_signals(args: argparse.Namespace) -> dict[str, Any]:
    """Keep complete Signal evidence lineage and remove every unrelated dataset."""
    root = require_store(Path(args.root))
    dry_run = bool(getattr(args, "dry_run", False))
    requested = set(getattr(args, "signal_id", []) or []) or None
    with sqlite_connection_scope(root) as connection:
        plan = _signal_prune_plan(connection, requested)
    public_plan = _public_signal_prune_plan(plan)
    if dry_run:
        return {"action": "prune_to_signals_preview", **public_plan}

    backup_value = str(getattr(args, "backup_path", "") or "").strip()
    if not backup_value:
        raise ValueError("prune-to-signals requires --backup-path unless --dry-run is used")
    backup_path = Path(backup_value).expanduser().resolve()
    if backup_path == database_path(root):
        raise ValueError("Backup path must differ from the canonical database")
    if backup_path.exists():
        raise ValueError(f"Backup path already exists: {backup_path}")
    online_backup(root, backup_path)

    with sqlite_transaction(root) as connection:
        plan = _signal_prune_plan(connection, requested)
        keep = plan["keep_by_collection"]

        def delete_except(table: str, column: str, values: set[str]) -> None:
            if values:
                placeholders = ",".join("?" * len(values))
                connection.execute(
                    f"DELETE FROM {table} WHERE {column} NOT IN ({placeholders})",
                    tuple(sorted(values)),
                )
            else:
                connection.execute(f"DELETE FROM {table}")

        delete_except(
            "wiki_signal_versions", "signal_version_id", keep.get("signal_versions", set())
        )
        delete_except(
            "wiki_company_impact_versions",
            "company_impact_version_id",
            keep.get("company_impacts", set()),
        )
        delete_except(
            "wiki_scenario_versions", "scenario_version_id", keep.get("scenarios", set())
        )
        delete_except(
            "wiki_observation_versions",
            "observation_version_id",
            keep.get("observations", set()),
        )
        delete_except(
            "wiki_event_versions", "event_version_id", keep.get("events", set())
        )
        if keep.get("claims"):
            placeholders = ",".join("?" * len(keep["claims"]))
            connection.execute(
                f"DELETE FROM wiki_claim_versions WHERE claim_id NOT IN ({placeholders})",
                tuple(sorted(keep["claims"])),
            )
        else:
            connection.execute("DELETE FROM wiki_claim_versions")
        connection.execute("DELETE FROM wiki_risk_factor_links")
        delete_except("wiki_source_assets", "source_id", keep.get("sources", set()))
        delete_except(
            "wiki_risk_factors", "risk_factor_id", keep.get("risk_factors", set())
        )
        keep_sources = sorted(plan["keep_by_collection"]["sources"])
        if keep_sources:
            placeholders = ",".join("?" * len(keep_sources))
            connection.execute(
                "DELETE FROM wiki_binary_assets "
                f"WHERE source_id IS NULL OR source_id NOT IN ({placeholders})",
                tuple(keep_sources),
            )
            connection.execute(
                "DELETE FROM wiki_source_contents "
                f"WHERE source_id NOT IN ({placeholders})",
                tuple(keep_sources),
            )
        else:
            connection.execute("DELETE FROM wiki_binary_assets")
            connection.execute("DELETE FROM wiki_source_contents")

        for collection, record_ids in plan["remove_by_collection"].items():
            connection.executemany(
                "DELETE FROM wiki_records WHERE collection=? AND record_id=?",
                ((collection, record_id) for record_id in record_ids),
            )
        connection.execute("DELETE FROM wiki_artifacts")
        connection.execute("DELETE FROM wiki_operation_log")
        connection.execute(
            "DELETE FROM sqlite_sequence WHERE name='wiki_operation_log'"
        )

        for table, id_column, subject_kind in (
            ("wiki_claim_versions", "claim_version_id", "claim"),
            ("wiki_observation_versions", "observation_version_id", "observation"),
            ("wiki_event_versions", "event_version_id", "event"),
            ("wiki_signal_versions", "signal_version_id", "signal"),
        ):
            for row in connection.execute(
                f"SELECT {id_column}, payload_json FROM {table}"
            ):
                payload = json.loads(str(row["payload_json"]))
                for risk_factor_id in payload.get("risk_factor_ids", []):
                    connection.execute(
                        "INSERT OR IGNORE INTO wiki_risk_factor_links("
                        "risk_factor_id, subject_kind, subject_version_id, created_at"
                        ") VALUES (?, ?, ?, ?)",
                        (str(risk_factor_id), subject_kind, str(row[id_column]), timestamp()),
                    )

        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity_check failed after Signal-only pruning")
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise RuntimeError("SQLite foreign_key_check failed after Signal-only pruning")

    with sqlite_connection_scope(root) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("VACUUM")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    integrity = sqlite_integrity(root)
    return {
        "action": (
            "retained_selected_signal_lineage"
            if requested is not None
            else "pruned_to_signal_lineage"
        ),
        **_public_signal_prune_plan(plan),
        "backup": str(backup_path),
        "integrity_check": integrity["integrity_check"],
        "foreign_key_errors": len(integrity["foreign_key_check"]),
    }


def migrate_to_sqlite(args: argparse.Namespace) -> dict[str, Any]:
    """Losslessly import the legacy file store and optionally retire its data files."""
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise ValueError(f"Store root does not exist: {root}")

    legacy_records: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    collection_directories = {
        "sources": SOURCE_RECORDS_DIR,
        "source_candidates": SOURCE_CANDIDATES_DIR,
        "claims": CLAIMS_DIR,
        "signals": SIGNALS_DIR,
        "insights": INSIGHTS_DIR,
        "reviews_pending": PENDING_REVIEWS_DIR,
        "reviews_resolved": RESOLVED_REVIEWS_DIR,
        "runs": RUNS_DIR,
    }
    for collection, relative in collection_directories.items():
        records: list[tuple[Path, dict[str, Any]]] = []
        directory = root / relative
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                with path.open("r", encoding="utf-8") as handle:
                    value = json.load(handle)
                if not isinstance(value, dict):
                    raise ValueError(f"Expected JSON object: {path}")
                records.append((path, value))
        legacy_records[collection] = records

    db_path = database_path(root)
    backup_path: Path | None = None
    if db_path.is_file():
        backup_path = (
            db_path.parent
            / "backups"
            / f"market_sensing-before-file-migration-{datetime.now():%Y%m%dT%H%M%S}.db"
        )
        online_backup(root, backup_path)
    initialize_sqlite(root)

    imported_counts: dict[str, int] = {}
    raw_paths: list[Path] = []
    media_paths: list[Path] = []
    for collection, records in legacy_records.items():
        for path, original in records:
            record = json.loads(json.dumps(original, ensure_ascii=False))
            if collection == "sources":
                source_id = str(record.get("source_id") or path.stem)
                raw_value = str(record.get("raw_path") or "")
                raw_path = root / raw_value if raw_value else None
                if raw_path is None or not raw_path.is_file():
                    raise ValueError(f"{source_id}: legacy raw source is missing")
                raw_bytes = raw_path.read_bytes()
                expected = str(record.get("raw_sha256") or "")
                current = raw_sha256(raw_bytes)
                lf_current = raw_sha256(raw_bytes.replace(b"\r\n", b"\n"))
                if expected and expected not in {current, lf_current}:
                    raise ValueError(f"{source_id}: raw source hash mismatch")
                record.pop("raw_path", None)
                record["raw_ref"] = f"sqlite:wiki_source_contents:{source_id}"
                for media in record.get("images", []):
                    local_value = str(media.get("local_path") or "")
                    if not local_value:
                        continue
                    media_path = root / local_value
                    if not media_path.is_file():
                        raise ValueError(
                            f"{source_id}/{media.get('media_id')}: legacy image is missing"
                        )
                    media_bytes = media_path.read_bytes()
                    media_id = str(media.get("media_id") or "")
                    suffix = media_path.suffix.casefold()
                    media_type = {
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".gif": "image/gif",
                        ".webp": "image/webp",
                    }.get(suffix, "application/octet-stream")
                    put_binary_asset(
                        root,
                        media_id,
                        media_bytes,
                        source_id=source_id,
                        media_type=media_type,
                        metadata={"legacy_path": local_value},
                    )
                    media.pop("local_path", None)
                    media["local_ref"] = f"sqlite:wiki_binary_assets:{media_id}"
                    media_paths.append(media_path)
                write_json(path, record)
                put_source_content(
                    root,
                    source_id,
                    raw_bytes,
                    media_type=source_media_type(raw_bytes),
                )
                raw_paths.append(raw_path)
            else:
                write_json(path, record)
        imported_counts[collection] = len(records)

    watchlist_path = root / "config" / "watchlist.json"
    if watchlist_path.is_file():
        with watchlist_path.open("r", encoding="utf-8") as handle:
            settings = json.load(handle)
        if not isinstance(settings, dict):
            raise ValueError(f"Expected JSON object: {watchlist_path}")
        put_settings(root, "watchlist", settings)
    elif get_settings(root, "watchlist") is None:
        put_settings(root, "watchlist", default_watchlist())

    artifact_paths: list[Path] = []
    artifact_roots = [
        root / "events",
        root / "reports" / "briefs",
        root / "reports" / "audits",
    ]
    for directory in artifact_roots:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*")):
            if path.suffix.casefold() not in {".md", ".html"}:
                continue
            relative = path.relative_to(root).as_posix()
            existing = get_artifact(root, relative)
            markdown_text = existing.get("markdown_text") if existing else None
            html_text = existing.get("html_text") if existing else None
            text_value = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix.casefold() == ".md":
                markdown_text = text_value
            else:
                html_text = text_value
            put_artifact(
                root,
                relative,
                "legacy_report" if "reports/" in relative else "event",
                path.stem,
                markdown_text=markdown_text,
                html_text=html_text,
                metadata={"legacy_path": relative},
            )
            artifact_paths.append(path)

    for path, review in legacy_records.get("reviews_pending", []):
        candidate_path_value = str(review.get("candidate_path") or "")
        candidate_path = root / candidate_path_value if candidate_path_value else None
        if candidate_path and candidate_path.is_file():
            put_artifact(
                root,
                str(review.get("review_id") or path.stem),
                "source_candidate",
                str((review.get("candidate") or {}).get("title") or path.stem),
                markdown_text=candidate_path.read_text(encoding="utf-8", errors="replace"),
                metadata={"legacy_path": candidate_path_value},
            )
            artifact_paths.append(candidate_path)

    log_path = root / "log.md"
    if log_path.is_file():
        put_artifact(
            root,
            "legacy:operation-log",
            "legacy_log",
            "Legacy operation log",
            markdown_text=log_path.read_text(encoding="utf-8", errors="replace"),
        )
        artifact_paths.append(log_path)

    verification = sqlite_integrity(root)
    if verification["integrity_check"] != "ok" or verification["foreign_key_check"]:
        raise RuntimeError(f"SQLite verification failed: {verification}")

    if backup_path is None and getattr(args, "remove_legacy_files", False):
        backup_path = (
            db_path.parent
            / "backups"
            / f"market_sensing-after-file-import-{datetime.now():%Y%m%dT%H%M%S}.db"
        )
        online_backup(root, backup_path)

    removed: list[str] = []
    if getattr(args, "remove_legacy_files", False):
        generated_roots = [
            root / "companies",
            root / "technologies",
            root / "projects",
            root / "entities",
            root / "sources",
            root / "signals",
        ]
        generated_files = [
            path
            for directory in generated_roots
            if directory.is_dir()
            for path in directory.glob("*.md")
        ]
        generated_files.extend(
            path
            for path in (
                root / "index.md",
                root / "REVIEW.md",
                root / "recent-updates.md",
                root / "reports" / "index.md",
                watchlist_path,
            )
            if path.is_file()
        )
        record_files = [path for records in legacy_records.values() for path, _ in records]
        exact_targets = {
            path.resolve()
            for path in record_files
            + raw_paths
            + media_paths
            + artifact_paths
            + generated_files
            if path.is_file()
        }
        root_prefix = str(root) + os.sep
        for path in sorted(exact_targets):
            if not str(path).startswith(root_prefix):
                raise RuntimeError(f"Refusing to remove path outside store root: {path}")
            path.unlink()
            removed.append(path.relative_to(root).as_posix())

    append_log(
        root,
        "migrate-to-sqlite",
        f"Imported {sum(imported_counts.values())} records; removed {len(removed)} legacy files.",
    )
    return {
        "action": "migrated_to_sqlite",
        "database": str(db_path),
        "backup": str(backup_path) if backup_path else None,
        "imported": imported_counts,
        "verification": verification,
        "removed_legacy_files": len(removed),
        "storage": "sqlite",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage a source-grounded POSCO Group market sensing store."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scaffold_parser = subparsers.add_parser(
        "scaffold", help="Create a market sensing intelligence knowledge store."
    )
    scaffold_parser.add_argument("root")
    scaffold_parser.set_defaults(func=lambda args: scaffold(Path(args.root)))

    scout_parser = subparsers.add_parser(
        "scout",
        help=(
            "Initialize, update, or complete an adaptive research run only after "
            "every configured company/business-axis cell passes the coverage gate."
        ),
    )
    scout_parser.add_argument("root")
    scout_parser.add_argument("--run-id", required=True)
    scout_parser.add_argument("--date-from")
    scout_parser.add_argument("--date-to")
    scout_parser.add_argument(
        "--target-count",
        type=int,
        help=(
            "Use only when the user explicitly requests a result count, such as "
            "'find three'; completion then requires that many published Signals "
            "instead of full company/axis coverage."
        ),
    )
    scout_parser.add_argument(
        "--company-id",
        action="append",
        help=(
            "Explicit user-selected company scope; repeat for multiple companies. "
            "Without this option, default settings determine company coverage."
        ),
    )
    scout_parser.add_argument(
        "--business-axis",
        action="append",
        help=(
            "Explicit user-selected business-axis scope; repeat for multiple axes. "
            "Without this option, default settings determine axis coverage."
        ),
    )
    scout_parser.add_argument(
        "--user-scope",
        help="Record the user's explicit scope or method instruction in the frozen run contract.",
    )
    scout_parser.add_argument(
        "--coverage-file",
        help="JSON coverage ledger replacing the run's current coverage progress.",
    )
    scout_parser.add_argument(
        "--complete",
        action="store_true",
        help="Close the run only when its frozen default or user-directed contract passes.",
    )
    scout_parser.set_defaults(func=scout_run)

    migration_parser = subparsers.add_parser(
        "migrate-to-sqlite",
        help="Import the legacy JSON/Markdown store into one canonical SQLite file.",
    )
    migration_parser.add_argument("root")
    migration_parser.add_argument(
        "--remove-legacy-files",
        action="store_true",
        help="After hash and integrity verification, remove migrated data files and projections.",
    )
    migration_parser.set_defaults(func=migrate_to_sqlite)

    analytics_migration_parser = subparsers.add_parser(
        "migrate-analytics-contract",
        help=(
            "Upgrade legacy Source, Claim, Insight, and Signal rows to the current "
            "version-pinned analytics contract."
        ),
    )
    analytics_migration_parser.add_argument("root")
    analytics_migration_parser.add_argument(
        "--legacy-source-modality",
        choices=SOURCE_MODALITIES,
        default="DOCUMENT",
        help="Modality assigned only to legacy Sources that do not already declare one.",
    )
    analytics_migration_parser.set_defaults(func=migrate_analytics_contract)

    prune_parser = subparsers.add_parser(
        "prune-to-signals",
        help="Keep complete Signal/Insight/Claim/Source lineage and remove unrelated data.",
    )
    prune_parser.add_argument("root")
    prune_parser.add_argument(
        "--backup-path",
        help="Required recovery copy for destructive pruning.",
    )
    prune_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show preserved and removed counts without changing SQLite.",
    )
    prune_parser.add_argument(
        "--signal-id",
        action="append",
        help=(
            "Development-only retention set; repeat to keep only these Signals and "
            "their complete evidence lineage."
        ),
    )
    prune_parser.set_defaults(func=prune_to_signals)

    source_parser = subparsers.add_parser(
        "add-source", help="Register an immutable source with duplicate checks."
    )
    source_parser.add_argument("root")
    source_parser.add_argument("--content-file", required=True)
    source_parser.add_argument("--title", required=True)
    source_parser.add_argument("--url")
    source_parser.add_argument("--publisher", required=True)
    source_parser.add_argument("--published-at")
    source_parser.add_argument("--collected-at")
    source_parser.add_argument("--source-type", choices=sorted(SOURCE_TYPES), required=True)
    source_parser.add_argument(
        "--source-modality", choices=SOURCE_MODALITIES, required=True,
        help="Observation modality: MARKET, DOCUMENT, PHYSICAL, or ATTENTION.",
    )
    source_parser.add_argument("--language", required=True)
    source_parser.add_argument(
        "--reliability", choices=sorted(SOURCE_RELIABILITY), required=True
    )
    source_parser.add_argument(
        "--academic-kind",
        choices=sorted(ACADEMIC_KINDS),
        help="Required for source_type=academic.",
    )
    source_parser.add_argument(
        "--author",
        action="append",
        help="Academic author; repeat for multiple authors.",
    )
    source_parser.add_argument("--venue", help="Journal or proceedings title.")
    source_parser.add_argument("--doi")
    source_parser.add_argument("--conference-name")
    source_parser.add_argument("--conference-date")
    source_parser.add_argument("--conference-location")
    source_parser.add_argument(
        "--peer-review-status",
        choices=sorted(PEER_REVIEW_STATUSES),
    )
    source_parser.add_argument(
        "--supporting-of",
        help="Record this URL as a republication/supporting source without storing content.",
    )
    source_parser.add_argument(
        "--force",
        action="store_true",
        help="Accept a near-duplicate as an independent source after review.",
    )
    source_parser.set_defaults(func=add_source)

    academic_parser = subparsers.add_parser(
        "set-academic-metadata",
        help="Add or update verified bibliographic metadata on an academic source.",
    )
    academic_parser.add_argument("root")
    academic_parser.add_argument("--source-id", required=True)
    academic_parser.add_argument(
        "--academic-kind",
        choices=sorted(ACADEMIC_KINDS),
        required=True,
    )
    academic_parser.add_argument("--author", action="append")
    academic_parser.add_argument("--venue")
    academic_parser.add_argument("--doi")
    academic_parser.add_argument("--conference-name")
    academic_parser.add_argument("--conference-date")
    academic_parser.add_argument("--conference-location")
    academic_parser.add_argument("--published-at")
    academic_parser.add_argument(
        "--peer-review-status",
        choices=sorted(PEER_REVIEW_STATUSES),
    )
    academic_parser.set_defaults(func=set_academic_metadata)

    image_parser = subparsers.add_parser(
        "add-image",
        help="Attach an optional source-grounded technical image to an existing source.",
    )
    image_parser.add_argument("root")
    image_parser.add_argument("--source-id", required=True)
    image_input = image_parser.add_mutually_exclusive_group(required=True)
    image_input.add_argument("--image-file")
    image_input.add_argument("--image-url")
    image_parser.add_argument("--origin-url")
    image_parser.add_argument("--caption", required=True)
    image_parser.add_argument("--alt-text")
    image_parser.add_argument("--creator")
    image_parser.add_argument(
        "--display-width",
        choices=("compact", "detail"),
        help="Display ordinary photos compactly or technical diagrams at detail width.",
    )
    image_parser.add_argument(
        "--hero-priority",
        type=int,
        help="Lower values take precedence when selecting the representative image.",
    )
    image_parser.add_argument(
        "--subject-id",
        action="append",
        help="Limit display to an intended COM-, TEC-, PRJ-, FAC-, or POL- subject. Repeatable.",
    )
    image_parser.add_argument("--kind", choices=sorted(MEDIA_KINDS), required=True)
    image_parser.add_argument(
        "--rights-status", choices=sorted(MEDIA_RIGHTS), required=True
    )
    image_parser.add_argument("--rights-note", required=True)
    image_parser.set_defaults(func=add_image)

    risk_factor_parser = subparsers.add_parser(
        "add-risk-factor", help="Register a governed analytics risk-factor definition."
    )
    risk_factor_parser.add_argument("root")
    risk_factor_parser.add_argument("--risk-factor-id", required=True)
    risk_factor_parser.add_argument("--taxonomy-version", type=int, default=1)
    risk_factor_parser.add_argument("--name", required=True)
    risk_factor_parser.add_argument("--definition", required=True)
    risk_factor_parser.add_argument("--category", required=True)
    risk_factor_parser.add_argument("--parent-risk-factor-id")
    risk_factor_parser.add_argument("--alias", action="append")
    risk_factor_parser.add_argument("--status", choices=("active", "retired"), default="active")
    risk_factor_parser.add_argument("--valid-from")
    risk_factor_parser.add_argument("--valid-to")
    risk_factor_parser.set_defaults(func=add_risk_factor)

    observation_parser = subparsers.add_parser(
        "add-observation", help="Register a versioned structured market observation."
    )
    observation_parser.add_argument("root")
    observation_parser.add_argument("--observation-id", required=True)
    observation_parser.add_argument("--version-no", type=int, default=1)
    observation_parser.add_argument("--series-key", required=True)
    observation_parser.add_argument("--metric-kind", required=True)
    observation_parser.add_argument("--value", required=True)
    observation_parser.add_argument("--unit", required=True)
    observation_parser.add_argument("--observed-at", required=True)
    observation_parser.add_argument("--source-id", required=True)
    observation_parser.add_argument(
        "--modality", choices=("MARKET", "PHYSICAL", "ATTENTION"), required=True
    )
    observation_parser.add_argument("--risk-factor-id", action="append", required=True)
    observation_parser.add_argument(
        "--verification-status",
        choices=("verified", "partial", "unverified"),
        default="verified",
    )
    observation_parser.set_defaults(func=add_observation)

    event_parser = subparsers.add_parser(
        "add-event", help="Register a versioned evidence-grounded market event."
    )
    event_parser.add_argument("root")
    event_parser.add_argument("--event-id", required=True)
    event_parser.add_argument("--version-no", type=int, default=1)
    event_parser.add_argument("--event-type", required=True)
    event_parser.add_argument("--actor-ref", required=True)
    event_parser.add_argument("--target-ref", required=True)
    event_parser.add_argument("--observed-at", required=True)
    event_parser.add_argument("--effective-at")
    event_parser.add_argument("--before-value")
    event_parser.add_argument("--after-value")
    event_parser.add_argument("--unit")
    event_parser.add_argument("--source-id", action="append", required=True)
    event_parser.add_argument("--modality", choices=SOURCE_MODALITIES, required=True)
    event_parser.add_argument("--risk-factor-id", action="append", required=True)
    event_parser.add_argument(
        "--status",
        choices=("announced", "effective", "delayed", "cancelled", "completed", "disputed"),
        default="effective",
    )
    event_parser.set_defaults(func=add_event)

    systematic_parser = subparsers.add_parser(
        "run-systematic-analysis",
        help=(
            "Run version-pinned anomaly, relationship, network, entropy, and "
            "Risk Factor candidate calculations for an existing Signal."
        ),
    )
    systematic_parser.add_argument("root")
    systematic_parser.add_argument("--signal-id", required=True)
    systematic_parser.add_argument(
        "--spec-file",
        required=True,
        help="JSON method bundle and Observation-version series; never unversioned values.",
    )
    systematic_parser.set_defaults(func=run_systematic_signal_analysis)

    claim_parser = subparsers.add_parser(
        "add-claim", help="Create or verify an atomic claim."
    )
    claim_parser.add_argument("root")
    claim_parser.add_argument("--subject-id", required=True)
    claim_parser.add_argument("--predicate", required=True)
    claim_parser.add_argument("--value", required=True)
    claim_parser.add_argument("--source-id", action="append", required=True)
    claim_parser.add_argument("--risk-factor-id", action="append")
    claim_parser.add_argument(
        "--confidence", choices=sorted(CLAIM_CONFIDENCE), required=True
    )
    claim_parser.add_argument("--as-of")
    claim_parser.add_argument("--reason", required=True)
    claim_parser.set_defaults(func=add_claim)

    signal_parser = subparsers.add_parser(
        "add-signal",
        help="Create a canonical market-change version from version-pinned Evidence.",
    )
    signal_parser.add_argument("root")
    signal_parser.add_argument("--run-id", required=True)
    signal_parser.add_argument(
        "--canonical-key", required=True,
        help="Stable identity key for the canonical market change; never include assessment dates.",
    )
    signal_parser.add_argument("--risk-factor-id", action="append", required=True)
    signal_parser.add_argument("--observation-id", action="append")
    signal_parser.add_argument("--event-id", action="append")
    signal_parser.add_argument(
        "--title", required=True,
        help="Short factual title naming the observed external change.",
    )
    signal_parser.add_argument(
        "--sentence", required=True,
        help="Complete sentence stating the separate business implication.",
    )
    signal_parser.add_argument(
        "--signal-type", choices=SIGNAL_TYPES, required=True,
        help="Governed change-type classification shown separately from business axis.",
    )
    signal_parser.add_argument(
        "--signal-role", choices=SIGNAL_ROLES, required=True,
        help="core_market_signal for external sensing; execution_context for own execution.",
    )
    signal_parser.add_argument(
        "--signal-origin", choices=SIGNAL_ORIGINS, required=True,
        help="Where the observed change originated; must be compatible with signal-role.",
    )
    signal_parser.add_argument(
        "--baseline-assumption",
        help="Current business assumption challenged by a core market Signal.",
    )
    signal_parser.add_argument(
        "--observed-break",
        help="Verified observation that weakens the baseline assumption.",
    )
    signal_parser.add_argument(
        "--decision-change",
        help="Specific decision that should change if the observation persists.",
    )
    signal_parser.add_argument(
        "--surprise-pattern", choices=sorted(SURPRISE_PATTERNS),
        help="Controlled pattern used to diversify assumption-breaking discovery.",
    )
    signal_parser.add_argument("--surprise-score", type=int)
    signal_parser.add_argument(
        "--falsification-check",
        help="One concrete check that would weaken or reject this interpretation.",
    )
    signal_parser.add_argument("--paragraph", required=True)
    signal_parser.add_argument(
        "--document-path",
        help="Optional related report path; the inline analysis remains the primary document layer.",
    )
    signal_parser.add_argument(
        "--analysis-file", required=True,
        help="Reader-facing narrative Markdown stored beside the structured analysis.",
    )
    signal_parser.add_argument(
        "--structured-analysis-file", required=True,
        help="Validated UI-ready JSON stored in the Insight payload_json.",
    )
    signal_parser.add_argument(
        "--impact-estimate-file",
        help="Validated JSON model for the default interactive What-if simulator.",
    )
    signal_parser.add_argument(
        "--quantification-decision-file",
        help=(
            "Required not_applicable JSON only when no impact estimate can be "
            "provided; modeled decisions are derived from the estimate."
        ),
    )
    signal_parser.add_argument("--company-id", action="append", required=True)
    signal_parser.add_argument("--business-axis", required=True)
    signal_parser.add_argument("--claim-id", action="append", required=True)
    signal_parser.add_argument("--business-impact-score", type=int, required=True)
    signal_parser.add_argument("--business-impact-rationale", required=True)
    signal_parser.add_argument("--urgency-score", type=int, required=True)
    signal_parser.add_argument("--urgency-rationale", required=True)
    signal_parser.add_argument("--response-deadline")
    signal_parser.add_argument("--assessed-at")
    signal_parser.add_argument(
        "--assessment-confidence", choices=sorted(CLAIM_CONFIDENCE), required=True
    )
    signal_parser.set_defaults(func=add_signal)

    score_migration_parser = subparsers.add_parser(
        "migrate-signal-scores",
        help="Migrate schema-v2 Signal assessments from 1-5 to calibrated 1-10 anchors.",
    )
    score_migration_parser.add_argument("root")
    score_migration_parser.add_argument("--migrated-at")
    score_migration_parser.set_defaults(func=migrate_signal_scores)

    assessment_parser = subparsers.add_parser(
        "set-signal-assessment",
        help="Reassess an existing Signal on the 1-10 rubric while preserving claim history.",
    )
    assessment_parser.add_argument("root")
    assessment_parser.add_argument("--signal-id", required=True)
    assessment_parser.add_argument("--business-impact-score", type=int, required=True)
    assessment_parser.add_argument("--business-impact-rationale", required=True)
    assessment_parser.add_argument("--urgency-score", type=int, required=True)
    assessment_parser.add_argument("--urgency-rationale", required=True)
    assessment_parser.add_argument(
        "--assessment-confidence", choices=sorted(CLAIM_CONFIDENCE), required=True
    )
    assessment_parser.add_argument("--assessed-at")
    assessment_parser.add_argument("--reason", required=True)
    assessment_parser.add_argument("--enterprise-scope")
    assessment_parser.add_argument("--immediate-action")
    assessment_parser.add_argument("--delay-loss")
    assessment_parser.add_argument("--irreversibility")
    assessment_parser.set_defaults(func=set_signal_assessment)

    impact_parser = subparsers.add_parser(
        "set-impact-estimate",
        help="Attach or replace a validated What-if model on an existing Signal.",
    )
    impact_parser.add_argument("root")
    impact_parser.add_argument("--signal-id", required=True)
    impact_parser.add_argument("--estimate-file", required=True)
    impact_parser.set_defaults(func=set_impact_estimate)

    quantification_parser = subparsers.add_parser(
        "set-quantification-decision",
        help=(
            "Record the narrow not_applicable exception for a Signal without "
            "an impact model."
        ),
    )
    quantification_parser.add_argument("root")
    quantification_parser.add_argument("--signal-id", required=True)
    quantification_parser.add_argument("--decision-file", required=True)
    quantification_parser.set_defaults(func=set_quantification_decision)

    structured_analysis_parser = subparsers.add_parser(
        "set-structured-analysis",
        help="Attach or replace UI-ready JSON while preserving narrative Markdown.",
    )
    structured_analysis_parser.add_argument("root")
    structured_analysis_parser.add_argument("--signal-id", required=True)
    structured_analysis_parser.add_argument(
        "--structured-analysis-file", required=True
    )
    structured_analysis_parser.set_defaults(func=set_structured_analysis)

    signal_analysis_parser = subparsers.add_parser(
        "set-signal-analysis",
        help=(
            "Replace narrative analysis, optionally replace UI-ready JSON, and extend "
            "evidence lineage."
        ),
    )
    signal_analysis_parser.add_argument("root")
    signal_analysis_parser.add_argument("--signal-id", required=True)
    signal_analysis_parser.add_argument("--analysis-file", required=True)
    signal_analysis_parser.add_argument(
        "--structured-analysis-file",
        help="Omit to preserve the Signal's existing validated UI-ready JSON.",
    )
    signal_analysis_parser.add_argument("--claim-id", action="append", default=[])
    signal_analysis_parser.set_defaults(func=set_signal_analysis)

    report_headings_parser = subparsers.add_parser(
        "rewrite-signal-report-headings",
        help=(
            "Replace exact H2-H4 labels for selected Signals while preserving report "
            "prose, structured analysis, and evidence lineage."
        ),
    )
    report_headings_parser.add_argument("root")
    report_headings_parser.add_argument("--mapping-file", required=True)
    report_headings_parser.set_defaults(func=rewrite_signal_report_headings)

    trace_parser = subparsers.add_parser(
        "trace-signal", help="Traverse Signal to Insight, Claim, Source, and Archive."
    )
    trace_parser.add_argument("root")
    trace_parser.add_argument("--signal-id", required=True)
    trace_parser.add_argument("--depth", type=int, choices=range(1, 5), default=4)
    trace_parser.set_defaults(func=trace_signal)

    review_parser = subparsers.add_parser(
        "resolve-review", help="Apply a human decision to a claim conflict."
    )
    review_parser.add_argument("root")
    review_parser.add_argument("--review-id", required=True)
    review_parser.add_argument(
        "--decision",
        choices=[
            "supersede",
            "keep-existing",
            "coexist",
            "dispute",
            "supporting",
            "accept-new",
            "reject",
        ],
        required=True,
    )
    review_parser.add_argument("--rationale", required=True)
    review_parser.add_argument(
        "--related-source",
        help="Existing source ID selected when resolving a duplicate as supporting.",
    )
    review_parser.set_defaults(func=resolve_review)

    audit_parser = subparsers.add_parser(
        "audit", help="Check source and claim integrity without changing facts."
    )
    audit_parser.add_argument("root")
    audit_parser.add_argument("--stale-days", type=int)
    audit_parser.set_defaults(func=audit_store)

    brief_parser = subparsers.add_parser(
        "brief", help="Generate a change-only brief from claim history."
    )
    brief_parser.add_argument("root")
    brief_parser.add_argument("--since", required=True)
    brief_parser.add_argument(
        "--html",
        action="store_true",
        help="Also render a self-contained HTML report with source references.",
    )
    brief_parser.set_defaults(func=brief)

    render_parser = subparsers.add_parser(
        "render-report",
        help="Render any Markdown report as self-contained sourced HTML.",
    )
    render_parser.add_argument("root")
    render_parser.add_argument("--input", required=True)
    render_parser.add_argument("--output")
    render_parser.set_defaults(func=render_report)

    sync_parser = subparsers.add_parser(
        "sync-obsidian",
        help="Rebuild Obsidian Markdown projections and wikilinks.",
    )
    sync_parser.add_argument("root")
    sync_parser.set_defaults(func=sync_obsidian)

    settings_parser = subparsers.add_parser(
        "sync-settings",
        help="Sync the top-level Markdown settings into the JSON cache.",
    )
    settings_parser.add_argument("root")
    settings_parser.set_defaults(func=sync_settings)

    show_settings_parser = subparsers.add_parser(
        "show-settings",
        help="Show the effective human-editable Wiki settings.",
    )
    show_settings_parser.add_argument("root")
    show_settings_parser.set_defaults(func=show_settings)

    search_parser = subparsers.add_parser(
        "search",
        help="Rank local knowledge and follow Obsidian wikilinks once.",
    )
    search_parser.add_argument("root")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.set_defaults(func=search_store)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
