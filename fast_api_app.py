"""Production ASGI entrypoint for ADK Web on Cloud Run."""

import os
from pathlib import Path

from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

PROJECT_ROOT = Path(__file__).resolve().parent

app: FastAPI = get_fast_api_app(
    agents_dir=str(PROJECT_ROOT),
    web=True,
    session_service_uri=os.getenv("SESSION_DATABASE_URL"),
    allow_origins=(
        os.getenv("ALLOW_ORIGINS", "").split(",")
        if os.getenv("ALLOW_ORIGINS")
        else None
    ),
    otel_to_cloud=os.getenv("OTEL_TO_CLOUD", "false").lower() == "true",
)
app.title = "Collections Intelligence Agent"
app.description = "Authenticated ADK interface for collections intelligence."
