"""Unit tests for M3: Demo Data Honesty & Provenance Classification.

Section refs: docs/PRD1.md §1.3, §6.3, §14.1
M3 Requirements:
1. Synthetic demo triggers are classified as DataQuality.SYNTHETIC.
2. Synthetic data does NOT claim a real provider (e.g. NASA, ECMWF, IMD, CWC).
3. Existing real/source-derived data is NOT accidentally relabelled synthetic (preserves DataQuality.VALID).
4. API response DTOs preserve synthetic classification where data_quality/source is exposed.
5. Re-running the demo seed or parser does not change the classification unexpectedly.
"""

from datetime import datetime, timezone
import pytest

from core.enums import DataQuality, Tier
from core.schemas.dynamic_triggers import (
    CanonicalTriggerRecord,
    TriggerType,
    TriggerValidationReport,
)
from core.schemas.habitations import HabitationRiskDossier, VulnerabilityBreakdownDTO
from core.schemas.scenario import ScenarioResponse
from core.schemas.alerts import ActiveAlertItem
from pipeline.adapters.trigger_adapter import TriggerParserV1


class TestM3DemoDataHonesty:
    """Validates that synthetic and demo records are explicitly and honestly classified."""

    def test_synthetic_demo_trigger_is_classified_as_synthetic(self):
        """1. Synthetic demo trigger is classified as DataQuality.SYNTHETIC."""
        record = CanonicalTriggerRecord(
            h3="8860064989fffff",
            h3_int=614205562723631103,
            hazard_type="landslide",
            trigger_type=TriggerType.OBSERVED,
            trigger_value=1.25,
            valid_at=datetime.now(timezone.utc),
            source="SYNTHETIC_DEMO",
            provider="SYNTHETIC",
            data_quality=DataQuality.SYNTHETIC,
        )
        assert record.data_quality == DataQuality.SYNTHETIC
        assert record.source == "SYNTHETIC_DEMO"

    def test_synthetic_trigger_does_not_claim_real_provider(self):
        """2. Synthetic data does NOT claim a real provider (NASA, ECMWF, IMD, CWC)."""
        # If someone attempts to pass a real provider to a synthetic source:
        record = CanonicalTriggerRecord(
            h3="8860064989fffff",
            h3_int=614205562723631103,
            hazard_type="landslide",
            trigger_type=TriggerType.OBSERVED,
            trigger_value=1.25,
            valid_at=datetime.now(timezone.utc),
            source="SYNTHETIC_DEMO",
            provider="NASA/JAXA",  # Real provider falsely claimed
            data_quality=DataQuality.VALID,  # Falsely claimed as VALID
        )
        # Validator must intercept and correct to honest synthetic representation
        assert record.data_quality == DataQuality.SYNTHETIC
        assert record.provider == "SYNTHETIC"
        assert record.provider not in ("NASA/JAXA", "NASA", "ECMWF", "IMD", "CWC")

    def test_parser_enforces_synthetic_honesty_on_demo_csv(self):
        """Parser translates SYNTHETIC_DEMO rows into honest synthetic records."""
        csv_data = """# source: SYNTHETIC_DEMO
# provider: NASA/JAXA
h3,trigger_value,hazard_type,valid_at
8860064989fffff,1.25,landslide,2026-08-30T06:00:00Z
"""
        parser = TriggerParserV1()
        records, report = parser.parse(csv_data)

        assert len(records) == 1
        r = records[0]
        assert r.source == "SYNTHETIC_DEMO"
        assert r.data_quality == DataQuality.SYNTHETIC
        assert r.provider == "SYNTHETIC"
        assert report.data_quality == DataQuality.SYNTHETIC

    def test_real_source_derived_data_is_not_relabelled_synthetic(self):
        """3. Real provider feeds (IMERG_EARLY, ECMWF_OPEN) remain DataQuality.VALID with real providers."""
        csv_data = """# source: IMERG_EARLY
# provider: NASA/JAXA
h3,trigger_value,hazard_type,valid_at
8860064989fffff,0.85,landslide,2026-08-30T06:00:00Z
"""
        parser = TriggerParserV1()
        records, report = parser.parse(csv_data)

        assert len(records) == 1
        r = records[0]
        assert r.source == "IMERG_EARLY"
        assert r.provider == "NASA/JAXA"
        assert r.data_quality == DataQuality.VALID
        assert report.data_quality == DataQuality.VALID

    def test_api_schema_preserves_synthetic_classification(self):
        """4. API response DTOs preserve synthetic classification."""
        # HabitationRiskDossier defaults to synthetic
        dossier = HabitationRiskDossier(
            id=1,
            name="Demo Village",
            admin_id=555,
            admin_name="Wayanad",
            population=500,
            households=110,
            centroid=[76.12, 11.55],
            priority_score=0.45,
            caseload_score=225.0,
            tier=Tier.SHORT_TERM,
            triage_rationale="Demo rationale",
            prz_overlap_pct=45.0,
            hazard_intensity=0.85,
            decayed_loss_score=0.20,
            vulnerability=VulnerabilityBreakdownDTO(
                v_demographic=0.5,
                v_structural=0.5,
                v_access=0.5,
                v_economic=0.5,
                v_index=0.5,
            ),
        )
        assert dossier.data_quality == "synthetic"
        assert dossier.data_quality != "observed"

        # ScenarioResponse defaults to synthetic
        scenario = ScenarioResponse(
            scenario_id="scen-123",
            applied_weights={"landslide": 1.2},
            applied_gamma=0.6,
            sort_mode="urgency",
            total_habitations_evaluated=10,
            total_tier_shifts=2,
        )
        assert scenario.data_quality == DataQuality.SYNTHETIC
        assert scenario.data_quality != DataQuality.VALID

        # ActiveAlertItem preserves synthetic trigger_source and quality
        alert = ActiveAlertItem(
            h3="8860064989fffff",
            h3_int=614205562723631103,
            res=8,
            mhi_live=0.90,
            mhi_static=0.40,
            dominant_hazard="landslide",
            trigger_source="SYNTHETIC_DEMO",
            data_quality=DataQuality.SYNTHETIC,
            centroid=[76.12, 11.55],
        )
        assert alert.data_quality == DataQuality.SYNTHETIC
        assert alert.trigger_source == "SYNTHETIC_DEMO"

    def test_idempotent_re_parsing_does_not_mutate_classification(self):
        """5. Re-parsing the same synthetic or real trigger yields consistent classification."""
        parser = TriggerParserV1()
        csv_demo = "h3,value,source\n8860064989fffff,1.25,SYNTHETIC_DEMO\n"

        recs1, rep1 = parser.parse(csv_demo)
        recs2, rep2 = parser.parse(csv_demo)

        assert recs1[0].data_quality == recs2[0].data_quality == DataQuality.SYNTHETIC
        assert recs1[0].provider == recs2[0].provider == "SYNTHETIC"
        assert rep1.data_quality == rep2.data_quality == DataQuality.SYNTHETIC
