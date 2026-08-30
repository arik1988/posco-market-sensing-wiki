"""Deterministic statistical evidence for canonical market Signals.

The calculations in this module narrow Risk Factor candidates.  They never
assert causality, forecast a market outcome, or replace source-backed facts.
Every result is derived only from version-pinned Observation records and an
explicit method bundle so the same inputs produce the same content digest.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from typing import Any


ANALYSIS_SCHEMA_VERSION = 1
METHOD_TYPES = (
    "robust_anomaly",
    "relationship_change",
    "network_change",
    "entropy_change",
    "risk_factor_contribution",
)
ANALYSIS_STATUSES = ("completed", "insufficient_data")


def _text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _round(value: float) -> float:
    return round(float(value), 8)


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean, right_mean = statistics.fmean(left), statistics.fmean(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_delta)
        * sum(value * value for value in right_delta)
    )
    if denominator == 0:
        return None
    return sum(a * b for a, b in zip(left_delta, right_delta, strict=True)) / denominator


def _entropy(values: list[float], minimum: float, maximum: float, bins: int) -> float:
    if minimum == maximum:
        return 0.0
    width = (maximum - minimum) / bins
    counts = [0] * bins
    for value in values:
        index = min(bins - 1, max(0, int((value - minimum) / width)))
        counts[index] += 1
    total = len(values)
    return -sum(
        (count / total) * math.log2(count / total) for count in counts if count
    )


def _series_payload(
    series_spec: dict[str, Any], observations: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    risk_factor_id = _text(series_spec.get("risk_factor_id"), "series.risk_factor_id")
    series_key = _text(series_spec.get("series_key"), "series.series_key")
    observation_ids = [
        _text(value, "series.observation_version_id")
        for value in series_spec.get("observation_version_ids", [])
    ]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError(f"{series_key}: observation_version_ids must be unique")
    points: list[dict[str, Any]] = []
    for observation_id in observation_ids:
        observation = observations.get(observation_id)
        if observation is None:
            raise ValueError(f"{series_key}: unknown Observation version {observation_id}")
        if str(observation.get("series_key")) != series_key:
            raise ValueError(f"{observation_id}: series_key does not match {series_key}")
        if risk_factor_id not in observation.get("risk_factor_ids", []):
            raise ValueError(f"{observation_id}: is not linked to {risk_factor_id}")
        if observation.get("verification_status") != "verified":
            raise ValueError(f"{observation_id}: only verified Observations may be calculated")
        raw_value = observation.get("value")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"{observation_id}: value must be numeric")
        value = float(raw_value)
        if not math.isfinite(value):
            raise ValueError(f"{observation_id}: value must be finite")
        points.append(
            {
                "observation_version_id": observation_id,
                "observed_at": _text(observation.get("observed_at"), "observed_at"),
                "value": value,
                "unit": _text(observation.get("unit"), "unit"),
            }
        )
    points.sort(key=lambda item: (item["observed_at"], item["observation_version_id"]))
    if len({item["observed_at"] for item in points}) != len(points):
        raise ValueError(f"{series_key}: one Observation per observed_at is required")
    units = {item["unit"] for item in points}
    if len(units) > 1:
        raise ValueError(f"{series_key}: all Observation units must match")
    unit = next(iter(units)) if units else _text(series_spec.get("unit"), "series.unit")
    return {
        "risk_factor_id": risk_factor_id,
        "series_key": series_key,
        "unit": unit,
        "points": points,
    }


def _window_values(series: dict[str, Any], previous: int, current: int) -> tuple[list[float], list[float]]:
    values = [float(point["value"]) for point in series["points"]]
    if len(values) < previous + current:
        return [], []
    return values[-(previous + current) : -current], values[-current:]


def _robust_anomaly(series: dict[str, Any], minimum_baseline: int) -> dict[str, Any]:
    values = [float(point["value"]) for point in series["points"]]
    if len(values) < minimum_baseline + 1:
        return {"status": "insufficient_data", "minimum_points": minimum_baseline + 1}
    baseline, latest = values[:-1], values[-1]
    median = statistics.median(baseline)
    mad = statistics.median(abs(value - median) for value in baseline)
    if mad == 0:
        return {
            "status": "insufficient_data",
            "reason": "zero_baseline_dispersion",
            "minimum_points": minimum_baseline + 1,
        }
    score = 0.6744897501960817 * (latest - median) / mad
    return {
        "status": "completed",
        "latest_value": _round(latest),
        "baseline_median": _round(median),
        "baseline_mad": _round(mad),
        "robust_z_score": _round(score),
        "direction": "increase" if score > 0 else "decrease" if score < 0 else "unchanged",
    }


def _aligned_windows(
    left: dict[str, Any], right: dict[str, Any], previous: int, current: int
) -> tuple[list[float], list[float], list[float], list[float]]:
    left_by_time = {point["observed_at"]: float(point["value"]) for point in left["points"]}
    right_by_time = {point["observed_at"]: float(point["value"]) for point in right["points"]}
    timestamps = sorted(set(left_by_time) & set(right_by_time))
    if len(timestamps) < previous + current:
        return [], [], [], []
    timestamps = timestamps[-(previous + current) :]
    old, new = timestamps[:-current], timestamps[-current:]
    return (
        [left_by_time[key] for key in old],
        [right_by_time[key] for key in old],
        [left_by_time[key] for key in new],
        [right_by_time[key] for key in new],
    )


def run_systematic_analysis(
    spec: dict[str, Any], observations: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Validate and execute the version-pinned deterministic analysis bundle."""

    if not isinstance(spec, dict):
        raise ValueError("analysis spec must be a JSON object")
    signal_version_id = _text(spec.get("signal_version_id"), "signal_version_id")
    if not signal_version_id.startswith("SIGV-"):
        raise ValueError("signal_version_id must use the SIGV- namespace")
    as_of = _text(spec.get("as_of"), "as_of")
    method_bundle = spec.get("method_bundle")
    if not isinstance(method_bundle, dict):
        raise ValueError("method_bundle must be an object")
    revisions = {
        key: _text(method_bundle.get(key), f"method_bundle.{key}")
        for key in (
            "formula_revision",
            "historical_window_policy_revision",
            "feature_set_revision",
            "normalization_revision",
        )
    }
    parameters = dict(method_bundle.get("parameters") or {})
    previous = int(parameters.get("previous_window_size", 8))
    current = int(parameters.get("current_window_size", 8))
    minimum_baseline = int(parameters.get("minimum_anomaly_baseline", 8))
    bins = int(parameters.get("entropy_bins", 4))
    threshold = float(parameters.get("network_correlation_threshold", 0.7))
    if previous < 4 or current < 4 or minimum_baseline < 5:
        raise ValueError("window sizes are below the governed minimum")
    if not 2 <= bins <= 20 or not 0 < threshold < 1:
        raise ValueError("entropy bins or network correlation threshold is invalid")

    raw_series = spec.get("series")
    if not isinstance(raw_series, list):
        raise ValueError("series must be an array")
    series = [_series_payload(dict(item), observations) for item in raw_series]
    if len({item["series_key"] for item in series}) != len(series):
        raise ValueError("series_key values must be unique")

    scope = dict(spec.get("analysis_scope") or {"kind": "atomic"})
    scope_kind = str(scope.get("kind") or "atomic")
    components = list(dict.fromkeys(scope.get("component_signal_version_ids", [])))
    if scope_kind not in {"atomic", "interaction"}:
        raise ValueError("analysis_scope.kind must be atomic or interaction")
    if scope_kind == "interaction" and len(components) < 2:
        raise ValueError("interaction analysis requires at least two component Signal versions")
    if scope_kind == "atomic" and components:
        raise ValueError("atomic analysis must not declare component Signal versions")
    scope = {"kind": scope_kind, "component_signal_version_ids": components}

    anomaly_results = [
        {
            "series_key": item["series_key"],
            "risk_factor_id": item["risk_factor_id"],
            **_robust_anomaly(item, minimum_baseline),
        }
        for item in series
    ]
    relationship_results: list[dict[str, Any]] = []
    for left_index, left in enumerate(series):
        for right in series[left_index + 1 :]:
            old_left, old_right, new_left, new_right = _aligned_windows(
                left, right, previous, current
            )
            old_corr, new_corr = _pearson(old_left, old_right), _pearson(new_left, new_right)
            result: dict[str, Any] = {
                "left_series_key": left["series_key"],
                "right_series_key": right["series_key"],
            }
            if old_corr is None or new_corr is None:
                result.update({"status": "insufficient_data", "minimum_aligned_points": previous + current})
            else:
                result.update(
                    {
                        "status": "completed",
                        "previous_correlation": _round(old_corr),
                        "current_correlation": _round(new_corr),
                        "absolute_change": _round(abs(new_corr - old_corr)),
                    }
                )
            relationship_results.append(result)

    entropy_results: list[dict[str, Any]] = []
    for item in series:
        old_values, new_values = _window_values(item, previous, current)
        result = {"series_key": item["series_key"], "risk_factor_id": item["risk_factor_id"]}
        if not old_values or not new_values:
            result.update({"status": "insufficient_data", "minimum_points": previous + current})
        else:
            combined = old_values + new_values
            old_entropy = _entropy(old_values, min(combined), max(combined), bins)
            new_entropy = _entropy(new_values, min(combined), max(combined), bins)
            result.update(
                {
                    "status": "completed",
                    "previous_entropy_bits": _round(old_entropy),
                    "current_entropy_bits": _round(new_entropy),
                    "change_bits": _round(new_entropy - old_entropy),
                }
            )
        entropy_results.append(result)

    completed_relationships = [item for item in relationship_results if item["status"] == "completed"]
    if len(series) < 3 or not completed_relationships:
        network_result: dict[str, Any] = {
            "status": "insufficient_data",
            "minimum_series": 3,
            "minimum_aligned_points": previous + current,
        }
    else:
        previous_edges = {
            tuple(sorted((item["left_series_key"], item["right_series_key"])))
            for item in completed_relationships
            if abs(float(item["previous_correlation"])) >= threshold
        }
        current_edges = {
            tuple(sorted((item["left_series_key"], item["right_series_key"])))
            for item in completed_relationships
            if abs(float(item["current_correlation"])) >= threshold
        }
        possible_edges = len(series) * (len(series) - 1) / 2
        network_result = {
            "status": "completed",
            "correlation_threshold": threshold,
            "previous_density": _round(len(previous_edges) / possible_edges),
            "current_density": _round(len(current_edges) / possible_edges),
            "added_edges": [list(edge) for edge in sorted(current_edges - previous_edges)],
            "removed_edges": [list(edge) for edge in sorted(previous_edges - current_edges)],
        }

    candidate_scores: dict[str, list[float]] = {item["risk_factor_id"]: [] for item in series}
    for item in anomaly_results:
        if item["status"] == "completed":
            candidate_scores[item["risk_factor_id"]].append(min(1.0, abs(float(item["robust_z_score"])) / 3))
    risk_by_series = {item["series_key"]: item["risk_factor_id"] for item in series}
    for item in completed_relationships:
        score = min(1.0, float(item["absolute_change"]))
        candidate_scores[risk_by_series[item["left_series_key"]]].append(score)
        candidate_scores[risk_by_series[item["right_series_key"]]].append(score)
    for item in entropy_results:
        if item["status"] == "completed":
            candidate_scores[item["risk_factor_id"]].append(min(1.0, abs(float(item["change_bits"]))))
    candidates = [
        {
            "risk_factor_id": risk_factor_id,
            "contribution_score": _round(statistics.fmean(scores)),
            "basis_count": len(scores),
            "interpretation": "구조변화 기여 후보이며 원인 또는 예측으로 확정하지 않습니다.",
        }
        for risk_factor_id, scores in candidate_scores.items()
        if scores
    ]
    candidates.sort(key=lambda item: (-item["contribution_score"], item["risk_factor_id"]))

    methods = {
        "robust_anomaly": anomaly_results,
        "relationship_change": relationship_results,
        "network_change": network_result,
        "entropy_change": entropy_results,
        "risk_factor_contribution": candidates,
    }
    completed_count = sum(
        any(item.get("status") == "completed" for item in value)
        if isinstance(value, list)
        else value.get("status") == "completed"
        for key, value in methods.items()
        if key != "risk_factor_contribution"
    )
    status = "completed" if completed_count else "insufficient_data"
    input_ids = [point["observation_version_id"] for item in series for point in item["points"]]
    analysis_identity = {
        "signal_version_id": signal_version_id,
        "analysis_scope": scope,
        "series_keys": sorted(item["series_key"] for item in series),
    }
    analysis_id = "SYSA-" + _sha256(analysis_identity)[:12].upper()
    semantic = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "version_no": int(spec.get("version_no", 1)),
        "signal_version_id": signal_version_id,
        "analysis_scope": scope,
        "status": status,
        "as_of": as_of,
        "method_bundle": {**revisions, "parameters": parameters},
        "method_types": list(METHOD_TYPES),
        "input_observation_version_ids": input_ids,
        "input_series": [
            {
                "risk_factor_id": item["risk_factor_id"],
                "series_key": item["series_key"],
                "unit": item["unit"],
                "observation_version_ids": [point["observation_version_id"] for point in item["points"]],
            }
            for item in series
        ],
        "results": methods,
        "limitations": list(
            dict.fromkeys(
                spec.get("limitations", [])
                or ["공개·등록된 관측 범위 밖의 변수와 실제 사내 계약·원가는 평가하지 않습니다."]
            )
        ),
    }
    if semantic["version_no"] < 1:
        raise ValueError("version_no must be at least 1")
    content_digest = "sha256:" + _sha256(semantic)
    return {
        **semantic,
        "analysis_result_version_id": "SYSAV-" + content_digest.removeprefix("sha256:")[:16].upper(),
        "content_digest": content_digest,
        "created_at": str(
            spec.get("created_at")
            or (f"{as_of}T00:00:00Z" if len(as_of) == 10 else as_of)
        ),
    }


def validate_systematic_analysis_result(
    value: dict[str, Any], observations: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Recalculate a stored result and reject drift or payload tampering."""

    spec = {
        "signal_version_id": value.get("signal_version_id"),
        "analysis_scope": value.get("analysis_scope"),
        "as_of": value.get("as_of"),
        "method_bundle": value.get("method_bundle"),
        "series": value.get("input_series"),
        "limitations": value.get("limitations"),
        "version_no": value.get("version_no"),
        "created_at": value.get("created_at"),
    }
    recalculated = run_systematic_analysis(spec, observations)
    if recalculated != value:
        raise ValueError("stored systematic analysis does not match recalculation")
    return value


__all__ = [
    "ANALYSIS_SCHEMA_VERSION",
    "ANALYSIS_STATUSES",
    "METHOD_TYPES",
    "run_systematic_analysis",
    "validate_systematic_analysis_result",
]
