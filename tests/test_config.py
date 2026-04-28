import importlib
import sys

import pytest


def test_config_raises_when_required_env_missing(monkeypatch):
    # Ensure at least one required var is missing so module import fails loudly.
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setenv("GCP_REGION", "asia-south1")

    # Clear cached module if present, then import.
    sys.modules.pop("services.shared.config", None)

    with pytest.raises(RuntimeError, match="Missing required env var: GCP_PROJECT_ID"):
        importlib.import_module("services.shared.config")

