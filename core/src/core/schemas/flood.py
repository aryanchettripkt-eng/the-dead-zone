"""Canonical Flood Domain Types & Ingestion Schemas (Day 3).

Provides normalized, transport-independent canonical representations for flood data
ingested from external Sentinel-1 artifacts.
"""

from enum import StrEnum
from typing import Optional, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator


class FloodSemanticType(StrEnum):
    """Semantic meaning of the flood observation.
    
    CRITICAL ARCHITECTURAL RULE:
    - STATIC_FREQUENCY: Represents historical inundation frequency / SAR water-mask occurrence (S_flood).
    - DYNAMIC_TRIGGER: Represents current event inundation observation / flood trigger (T_flood).
    """
    STATIC_FREQUENCY = "static_frequency"
    DYNAMIC_TRIGGER = "dynamic_trigger"


class CanonicalFloodRecord(BaseModel):
    """Normalized, transport-independent canonical flood record.
    
    Isolates external .txt artifact representations from core domain and database models.
    """
    h3_int: int = Field(description="H3 index as 64-bit integer.")
    h3_str: str = Field(description="H3 index as 15-character hexadecimal string.")
    res: int = Field(ge=6, le=10, description="H3 resolution level.")
    value: float = Field(description="Observed value (inundation frequency in [0,1] or dynamic trigger >= 0).")
    semantic_type: FloodSemanticType = Field(description="Semantic type: static_frequency or dynamic_trigger.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Observation or model confidence.")
    observation_count: int = Field(default=1, ge=1, description="Number of SAR scenes / observations aggregated.")
    valid_at: Optional[datetime] = Field(default=None, description="Timestamp of observation for dynamic triggers.")
    source: str = Field(default="sentinel1_rtc", description="Source identifier.")
    dataset_version: str = Field(default="s1-v1.0", description="Upstream dataset version.")
    raw_flags: Optional[str] = Field(default=None, description="Optional raw flags or quality indicators.")

    @field_validator("valid_at", mode="after")
    @classmethod
    def ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class RowValidationError(BaseModel):
    """Details of a rejected record during artifact parsing and validation."""
    row_number: int
    raw_content: str
    error_type: str
    message: str


class ValidationReport(BaseModel):
    """Structured report produced by artifact ingestion validation."""
    format_version: str = "1.0"
    semantic_type: FloodSemanticType = FloodSemanticType.STATIC_FREQUENCY
    dataset_version: str = "unknown"
    source: str = "sentinel1_rtc"
    total_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    errors: list[RowValidationError] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Artifact is valid if at least one row is accepted and no critical structural errors occurred."""
        return self.accepted_rows > 0 and (self.rejected_rows == 0 or (self.accepted_rows / self.total_rows >= 0.8))
