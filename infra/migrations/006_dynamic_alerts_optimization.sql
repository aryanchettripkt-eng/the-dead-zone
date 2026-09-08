-- 006_dynamic_alerts_optimization.sql
-- Optimisation indexes for Active Alert Zones, Forecast Alert Zones, and dynamic snapshot queries (Day 6)

CREATE INDEX IF NOT EXISTS idx_mhi_snapshot_active_alerts 
ON mhi_snapshot (mhi_live DESC, mhi_static ASC) 
WHERE mhi_live >= 0.75;

CREATE INDEX IF NOT EXISTS idx_mhi_snapshot_forecast_alerts 
ON mhi_snapshot (mhi_fcst DESC, mhi_static ASC) 
WHERE mhi_fcst >= 0.75;

CREATE INDEX IF NOT EXISTS idx_hazard_dynamic_h3_valid 
ON hazard_dynamic (h3, valid_at DESC);
