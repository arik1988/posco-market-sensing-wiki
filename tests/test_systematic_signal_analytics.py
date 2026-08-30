import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "market-sensing-intelligence"
    / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))

import signal_analytics  # noqa: E402
import sqlite_store  # noqa: E402
import systematic_signal_analytics as systematic  # noqa: E402


def analysis_fixture(series_count: int = 3, points: int = 17):
    observations = {}
    series = []
    for series_index in range(series_count):
        risk_factor_id = f"RF-FACTOR-{series_index + 1}"
        series_key = f"series.{series_index + 1}"
        observation_ids = []
        for point_index in range(points):
            observation_id = f"OBSV-{series_index + 1:02d}{point_index + 1:03d}"
            observation_ids.append(observation_id)
            base = point_index * (series_index + 1)
            value = base + (12 if point_index == points - 1 and series_index == 0 else 0)
            observations[observation_id] = {
                "observation_version_id": observation_id,
                "series_key": series_key,
                "value": float(value),
                "unit": "index",
                "observed_at": f"2026-08-{point_index + 1:02d}",
                "risk_factor_ids": [risk_factor_id],
                "verification_status": "verified",
            }
        series.append(
            {
                "risk_factor_id": risk_factor_id,
                "series_key": series_key,
                "observation_version_ids": observation_ids,
            }
        )
    spec = {
        "signal_version_id": "SIGV-TEST000000000001",
        "version_no": 1,
        "as_of": "2026-08-29",
        "analysis_scope": {"kind": "atomic", "component_signal_version_ids": []},
        "method_bundle": {
            "formula_revision": "systematic-signal-analytics-v1",
            "historical_window_policy_revision": "two-fixed-windows-v1",
            "feature_set_revision": "verified-observations-v1",
            "normalization_revision": "native-unit-no-rescale-v1",
            "parameters": {
                "previous_window_size": 8,
                "current_window_size": 8,
                "minimum_anomaly_baseline": 8,
                "entropy_bins": 4,
                "network_correlation_threshold": 0.7,
            },
        },
        "series": series,
        "limitations": ["테스트 관측 범위 밖의 변수는 평가하지 않습니다."],
        "created_at": "2026-08-29T12:00:00+09:00",
    }
    return spec, observations


class SystematicSignalAnalyticsTests(unittest.TestCase):
    def test_same_versioned_inputs_and_method_produce_identical_result(self):
        spec, observations = analysis_fixture()
        first = systematic.run_systematic_analysis(spec, observations)
        second = systematic.run_systematic_analysis(spec, observations)
        self.assertEqual(first, second)
        self.assertEqual("completed", first["status"])
        self.assertTrue(first["results"]["risk_factor_contribution"])
        self.assertIn(
            first["results"]["network_change"]["status"],
            {"completed", "insufficient_data"},
        )
        systematic.validate_systematic_analysis_result(first, observations)
        spec_without_created_at = dict(spec)
        spec_without_created_at.pop("created_at")
        self.assertEqual(
            systematic.run_systematic_analysis(spec_without_created_at, observations),
            systematic.run_systematic_analysis(spec_without_created_at, observations),
        )

    def test_insufficient_data_is_explicit_instead_of_fabricating_metrics(self):
        spec, observations = analysis_fixture(series_count=1, points=4)
        result = systematic.run_systematic_analysis(spec, observations)
        self.assertEqual("insufficient_data", result["status"])
        self.assertEqual(
            "insufficient_data", result["results"]["robust_anomaly"][0]["status"]
        )
        self.assertEqual(
            "insufficient_data", result["results"]["network_change"]["status"]
        )
        self.assertEqual([], result["results"]["risk_factor_contribution"])

    def test_no_registered_time_series_can_be_audited_as_insufficient(self):
        spec, observations = analysis_fixture()
        spec["series"] = []
        result = systematic.run_systematic_analysis(spec, observations)
        self.assertEqual("insufficient_data", result["status"])
        self.assertEqual([], result["input_observation_version_ids"])
        self.assertEqual([], result["results"]["risk_factor_contribution"])

    def test_interaction_scope_requires_two_component_signal_versions(self):
        spec, observations = analysis_fixture()
        spec["analysis_scope"] = {
            "kind": "interaction",
            "component_signal_version_ids": ["SIGV-ONLY-ONE"],
        }
        with self.assertRaisesRegex(ValueError, "at least two component"):
            systematic.run_systematic_analysis(spec, observations)

    def test_result_and_input_lineage_are_normalized_in_sqlite(self):
        spec, observations = analysis_fixture()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index in range(3):
                risk_factor = signal_analytics.validate_risk_factor(
                    {
                        "risk_factor_id": f"RF-FACTOR-{index + 1}",
                        "name": f"요인 {index + 1}",
                        "definition": "정량 분석 테스트용 위험요인입니다.",
                        "category": "MARKET_FACTOR",
                    }
                )
                sqlite_store.put_risk_factor(root, risk_factor)
            source = {
                "schema_version": 2,
                "source_id": "SRC-ANALYTICS-001",
                "source_type": "other",
                "source_modality": "MARKET",
                "collected_at": "2026-08-29",
            }
            sqlite_store.upsert_record(root, "sources", source["source_id"], source)
            sqlite_store.put_source_asset(root, source)
            for value in observations.values():
                value.update(
                    {
                        "schema_version": 1,
                        "observation_id": value["observation_version_id"],
                        "version_no": 1,
                        "metric_kind": "index",
                        "source_id": source["source_id"],
                        "modality": "MARKET",
                        "created_at": "2026-08-29T12:00:00+09:00",
                    }
                )
                sqlite_store.upsert_record(
                    root, "observations", value["observation_version_id"], value
                )
                sqlite_store.put_observation_version(root, value)
            with sqlite_store.connection_scope(root) as connection:
                connection.execute(
                    "INSERT INTO wiki_signal_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        spec["signal_version_id"],
                        "SIG-TEST00000001",
                        1,
                        "test.systematic.analytics",
                        "{}",
                        "0" * 64,
                        "2026-08-29T12:00:00+09:00",
                    ),
                )
            result = systematic.run_systematic_analysis(spec, observations)
            sqlite_store.put_systematic_analysis(root, result)
            integrity = sqlite_store.integrity(root)
            self.assertEqual(
                1,
                integrity["analytics_counts"]["wiki_systematic_analysis_versions"],
            )
            self.assertEqual(
                51,
                integrity["analytics_counts"]["wiki_systematic_analysis_inputs"],
            )
            stored = sqlite_store.read_record(
                root, "systematic_analyses", result["analysis_result_version_id"]
            )
            self.assertEqual(result["content_digest"], stored["content_digest"])


if __name__ == "__main__":
    unittest.main()
