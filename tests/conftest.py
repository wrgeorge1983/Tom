"""Pytest configuration and shared fixtures for Tom tests."""
import os
import pytest
import yaml
from pathlib import Path
from typing import Dict, Any


# Set test environment variables
os.environ["TOM_ENV"] = "test"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def jwt_fixtures_dir(fixtures_dir) -> Path:
    """Return the path to the JWT fixtures directory."""
    return fixtures_dir / "jwt"


def load_fixture(fixture_path: Path) -> Dict[str, Any]:
    """Load a YAML fixture file.
    
    Args:
        fixture_path: Path to the fixture file
        
    Returns:
        Dictionary containing fixture data
    """
    with open(fixture_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def load_jwt_fixture(jwt_fixtures_dir):
    """Fixture factory to load JWT test fixtures by name.
    
    Usage:
        def test_something(load_jwt_fixture):
            fixture = load_jwt_fixture("google_valid_1759709058.yaml")
    """
    def _load(filename: str) -> Dict[str, Any]:
        fixture_path = jwt_fixtures_dir / filename
        return load_fixture(fixture_path)
    
    return _load


# VCR configuration for recording HTTP interactions
@pytest.fixture(scope="module")
def vcr_config():
    """VCR configuration for pytest-recording."""
    return {
        "filter_headers": [
            ("authorization", "REDACTED"),
            ("cookie", "REDACTED"),
        ],
        "record_mode": "once",  # Record once, then replay
        "match_on": ["uri", "method"],
        "cassette_library_dir": "tests/cassettes",
    }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "vcr: mark test to use VCR cassettes for HTTP recording"
    )
    config.addinivalue_line(
        "markers", "jwt: mark test as JWT validation test"
    )
    config.addinivalue_line(
        "markers", "discovery: mark test as OIDC discovery test"
    )
