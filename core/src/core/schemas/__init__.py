"""Re-exports all Pydantic v2 DTO schemas for SETU-DRR core."""

from core.schemas.common import (
    BaseSchema,
    PaginationParams,
    PaginatedResponse,
    BBoxQuery,
    PointGeometryDTO,
    PolygonGeometryDTO,
    MultiPolygonGeometryDTO,
    SCREENING_GRADE_NOTICE,
    ProvenanceMetadataDTO,
    ErrorDetail,
    ErrorEnvelope,
    ErrorResponse,
)
from core.schemas.zones import (
    HazardDetailDTO,
    ZoneCellSummary,
    ZoneCellDetail,
)
from core.schemas.hazard import (
    HazardCellDTO,
    HazardLayerLegendDTO,
    HazardLayerCoverageDTO,
    HazardLayerResponse,
    HazardLayerSummaryDTO,
    FloodDriverDTO,
    HazardCellDetailDTO,
)
from core.schemas.habitations import (
    LossEventDTO,
    VulnerabilityBreakdownDTO,
    HabitationListItem,
    HabitationRiskDossier,
)
from core.schemas.sites import (
    CapacityBreakdownDTO,
    AugmentedCapacityDTO,
    CandidateSiteItem,
    SiteCapacityOverrideRequest,
    SiteCapacityOverrideResponse,
)
from core.schemas.allocation import (
    AllocationPlanRequest,
    AllocationAssignmentDTO,
    AllocationPlanResponse,
)
from core.schemas.alerts import (
    ActiveAlertItem,
    ForecastAlertItem,
    ActiveAlertsResponse,
    ForecastAlertsResponse,
)
from core.schemas.scenario import (
    ScenarioWeightOverrideRequest,
    ScenarioAllocationParams,
    ScenarioHabitationItem,
    ScenarioAllocationSummaryDTO,
    ScenarioResponse,
)

from core.schemas.flood import (
    FloodSemanticType,
    CanonicalFloodRecord,
    ValidationReport,
    RowValidationError,
)
from core.schemas.auth import (
    JurisdictionDTO,
    LoginRequest,
    RegisterRequest,
    UserResponse,
    LogoutResponse,
)

from core.schemas.dynamic_triggers import (
    TriggerType,
    DataQuality,
    TriggerSource,
    CanonicalTriggerRecord,
    TriggerValidationReport,
)
from core.schemas.explanation import (
    FeatureContributionDTO,
    CanonicalExplanationRecord,
    ExplanationBatchDTO,
)

__all__ = [
    "BaseSchema",
    "PaginationParams",
    "PaginatedResponse",
    "BBoxQuery",
    "PointGeometryDTO",
    "PolygonGeometryDTO",
    "MultiPolygonGeometryDTO",
    "SCREENING_GRADE_NOTICE",
    "ProvenanceMetadataDTO",
    "ErrorDetail",
    "ErrorEnvelope",
    "ErrorResponse",
    "FeatureContributionDTO",
    "HazardDetailDTO",
    "ZoneCellSummary",
    "ZoneCellDetail",
    "HazardCellDTO",
    "HazardLayerLegendDTO",
    "HazardLayerCoverageDTO",
    "HazardLayerResponse",
    "HazardLayerSummaryDTO",
    "FloodDriverDTO",
    "HazardCellDetailDTO",
    "LossEventDTO",
    "VulnerabilityBreakdownDTO",
    "HabitationListItem",
    "HabitationRiskDossier",
    "CapacityBreakdownDTO",
    "AugmentedCapacityDTO",
    "CandidateSiteItem",
    "SiteCapacityOverrideRequest",
    "SiteCapacityOverrideResponse",
    "AllocationPlanRequest",
    "AllocationAssignmentDTO",
    "AllocationPlanResponse",
    "ActiveAlertItem",
    "ForecastAlertItem",
    "ActiveAlertsResponse",
    "ForecastAlertsResponse",
    "ScenarioWeightOverrideRequest",
    "ScenarioHabitationItem",
    "ScenarioResponse",
    "FloodSemanticType",
    "CanonicalFloodRecord",
    "ValidationReport",
    "RowValidationError",
    "TriggerType",
    "DataQuality",
    "TriggerSource",
    "CanonicalTriggerRecord",
    "TriggerValidationReport",
    "CanonicalExplanationRecord",
    "ExplanationBatchDTO",
    "JurisdictionDTO",
    "LoginRequest",
    "RegisterRequest",
    "UserResponse",
    "LogoutResponse",
]


