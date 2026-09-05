"""Central configuration: environment loading, score weights and thresholds.

All magic numbers for scoring live here so that engines and tests reference a single
source of truth. Secrets are read only by name from the environment; ``.env`` contents
are never inspected or displayed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a local .env if present. We never read or print its contents;
# we only look up the named variables below.
load_dotenv()

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"

# --- Health score weights (must sum to 1.0) ---
HEALTH_WEIGHTS: dict[str, float] = {
    "schedule_performance": 0.25,
    "milestone_readiness": 0.20,
    "task_execution": 0.15,
    "risk_exposure": 0.15,
    "dependency_status": 0.10,
    "resource_capacity": 0.10,
    "action_closure": 0.05,
}

# --- Confidence score weights (must sum to 1.0) ---
CONFIDENCE_WEIGHTS: dict[str, float] = {
    "data_freshness": 0.40,
    "data_completeness": 0.30,
    "ownership_coverage": 0.20,
    "source_reliability": 0.10,
}

# --- Band thresholds (lower inclusive bound) ---
HEALTH_BANDS: dict[str, float] = {"Green": 80.0, "Amber": 60.0, "Red": 0.0}
CONFIDENCE_BANDS: dict[str, float] = {"High": 80.0, "Medium": 60.0, "Low": 0.0}

AI_DISCLAIMER: str = "AI-generated decision-support draft; human review required."
AI_UNAVAILABLE_MESSAGE: str = (
    "AI capability is unavailable because Azure OpenAI configuration is missing. "
    "Core deterministic portfolio analysis remains available."
)


@dataclass(frozen=True)
class AzureOpenAISettings:
    """Azure OpenAI connection settings resolved from the environment."""

    api_key: str | None
    endpoint: str | None

    @property
    def is_configured(self) -> bool:
        """Return True only when both an API key and endpoint are present."""
        return bool(self.api_key) and bool(self.endpoint)


def get_azure_settings() -> AzureOpenAISettings:
    """Read Azure OpenAI settings from the environment without exposing secret values."""
    return AzureOpenAISettings(
        api_key=os.getenv("API_KEY"),
        endpoint=os.getenv("ENDPOINT"),
    )
