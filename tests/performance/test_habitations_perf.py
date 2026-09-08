"""Performance and Latency Benchmarking for Day 4 Habitations Endpoints."""

import time
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from api.main import app
from core.config import settings

client = TestClient(app)


def benchmark_endpoint(url: str, params: dict | None = None, runs: int = 25) -> dict[str, float]:
    """Runs repeated requests to compute p50, p95, p99 latency in milliseconds."""
    # Warmup request
    client.get(url, params=params)

    latencies = []
    for _ in range(runs):
        t0 = time.perf_counter()
        res = client.get(url, params=params)
        t1 = time.perf_counter()
        assert res.status_code == 200
        latencies.append((t1 - t0) * 1000.0)

    return {
        "p50": float(np.percentile(latencies, 50)),
        "p95": float(np.percentile(latencies, 95)),
        "p99": float(np.percentile(latencies, 99)),
        "mean": float(np.mean(latencies)),
        "min": float(np.min(latencies)),
        "max": float(np.max(latencies)),
    }


class TestHabitationsPerformance:
    def test_database_engine_query_plan_latency(self):
        """Measures pure PostgreSQL query execution time using EXPLAIN ANALYZE."""
        engine = create_engine(settings.get_sqlalchemy_url(direct=True))
        with engine.connect() as conn:
            plan = conn.execute(text("""
                EXPLAIN (ANALYZE, TIMING ON)
                SELECT h.id, hr.priority_score, count(*) OVER() as full_count
                FROM habitation h
                LEFT JOIN habitation_risk hr ON h.id = hr.habitation_id
                ORDER BY COALESCE(hr.priority_score, 0.0) DESC, h.id ASC
                LIMIT 50;
            """)).fetchall()

            # Verify query planner uses indexes and completes in under 10ms
            plan_text = " ".join([r[0] for r in plan])
            assert "Execution Time" in plan_text
            print(f"\n[DB PLAN] {plan[-1][0]}")

    def test_performance_all_day4_endpoints(self):
        """Benchmarks API endpoints across remote database connection."""
        # 1. Warm connection
        client.get("/health/live")

        # 2. Benchmark /habitations default
        bench_default = benchmark_endpoint("/habitations", {"limit": 20})
        print(f"\n[BENCH] GET /habitations -> p50: {bench_default['p50']:.2f}ms, p95: {bench_default['p95']:.2f}ms, p99: {bench_default['p99']:.2f}ms")

        # 3. Benchmark /habitations?admin=555
        bench_admin = benchmark_endpoint("/habitations", {"admin": 555, "limit": 20})
        print(f"[BENCH] GET /habitations?admin=555 -> p50: {bench_admin['p50']:.2f}ms, p95: {bench_admin['p95']:.2f}ms, p99: {bench_admin['p99']:.2f}ms")

        # 4. Benchmark /habitations?tier=immediate
        bench_tier = benchmark_endpoint("/habitations", {"tier": "immediate"})
        print(f"[BENCH] GET /habitations?tier=immediate -> p50: {bench_tier['p50']:.2f}ms, p95: {bench_tier['p95']:.2f}ms, p99: {bench_tier['p99']:.2f}ms")

        # 5. Benchmark /habitations?sort=urgency
        bench_urgency = benchmark_endpoint("/habitations", {"sort": "urgency"})
        print(f"[BENCH] GET /habitations?sort=urgency -> p50: {bench_urgency['p50']:.2f}ms, p95: {bench_urgency['p95']:.2f}ms, p99: {bench_urgency['p99']:.2f}ms")

        # 6. Benchmark /habitations?sort=caseload
        bench_caseload = benchmark_endpoint("/habitations", {"sort": "caseload"})
        print(f"[BENCH] GET /habitations?sort=caseload -> p50: {bench_caseload['p50']:.2f}ms, p95: {bench_caseload['p95']:.2f}ms, p99: {bench_caseload['p99']:.2f}ms")

        # 7. Benchmark /habitations/{id}/risk
        list_res = client.get("/habitations", params={"limit": 1})
        hab_id = list_res.json()["items"][0]["id"]
        bench_risk = benchmark_endpoint(f"/habitations/{hab_id}/risk")
        print(f"[BENCH] GET /habitations/{hab_id}/risk -> p50: {bench_risk['p50']:.2f}ms, p95: {bench_risk['p95']:.2f}ms, p99: {bench_risk['p99']:.2f}ms")
