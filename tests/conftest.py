"""Shared fixtures for agentlimit tests."""

import fakeredis
import pytest


@pytest.fixture()
def redis_client():
    """Provide a fresh fakeredis instance for each test."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def redis_url():
    """Return a dummy Redis URL for UsageMeter init tests."""
    return "redis://localhost:6379"
