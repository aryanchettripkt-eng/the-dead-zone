"""Exports the FastAPI OpenAPI 3.1.0 schema to openapi.json in the repository root."""

import json
from pathlib import Path
from api.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = REPO_ROOT / "openapi.json"


def export_openapi() -> Path:
    """Generates the OpenAPI schema from the FastAPI app and writes it to openapi.json."""
    schema = app.openapi()
    OPENAPI_PATH.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"Exported OpenAPI schema to {OPENAPI_PATH} ({OPENAPI_PATH.stat().st_size} bytes)")
    return OPENAPI_PATH


if __name__ == "__main__":
    export_openapi()
