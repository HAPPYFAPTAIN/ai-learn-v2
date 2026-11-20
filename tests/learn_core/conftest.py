"""Existing core regressions exercise the explicitly supported gateway mode.

Personal-provider tests override this setting to exercise the new default.
"""
import pytest
from learn_core.config import get_settings


@pytest.fixture(autouse=True)
def gateway_regression_mode(monkeypatch):
    monkeypatch.setenv('LEARN_MODEL_SOURCE', 'gateway')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
