"""Pydantic models shared by the pipeline and the API.

These flow into FastAPI's OpenAPI document, which generates web/lib/api-types.ts
(`pnpm generate:types`). Changing a model here changes the frontend's types —
that is the point (§9.7, "prevents contract drift between tracks").
"""
