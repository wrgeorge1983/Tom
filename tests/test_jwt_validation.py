"""Tests for JWT validation against recorded tokens from real providers.

These tests use recorded JWTs from actual OAuth providers (Google, Duo, Entra)
to ensure we correctly validate tokens and extract claims consistently over time.
"""
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from typing import List

import pytest
from freezegun import freeze_time

from tom_controller.auth import get_jwt_validator
from tom_controller.auth.jwt_validator import JWTValidationError
from tom_controller.exceptions import JWTExpiredError, JWTInvalidClaimsError


def collect_fixtures(pattern: str) -> List[str]:
    """Collect fixture files matching glob pattern.
    
    Args:
        pattern: Glob pattern like "google_valid_*.yaml"
    
    Returns:
        List of fixture filenames (sorted)
    """
    fixtures_dir = Path(__file__).parent / "fixtures" / "jwt"
    if not fixtures_dir.exists():
        return []
    return [f.name for f in sorted(fixtures_dir.glob(pattern))]


@pytest.mark.jwt
@pytest.mark.asyncio
class TestJWTValidation:
    """Test JWT validation with recorded fixtures."""
    
    @pytest.mark.parametrize("fixture_name", collect_fixtures("google_valid_*.yaml"))
    async def test_google_valid_tokens(self, load_jwt_fixture, fixture_name):
        """Test validating real Google JWTs extract correct claims."""
        if not fixture_name:
            pytest.skip("No Google valid fixtures found")
        
        fixture = load_jwt_fixture(fixture_name)
        
        with freeze_time(fixture["validation_time"]):
            validator = get_jwt_validator(fixture["provider_config"])
            await validator._ensure_discovery()
            
            claims = await validator.validate_token(fixture["jwt"])
            
            assert claims["iss"] == fixture["expected"]["claims"]["iss"]
            assert claims["sub"] == fixture["expected"]["claims"]["sub"]
            assert claims["email"] == fixture["expected"]["claims"]["email"]
            assert claims["aud"] == fixture["expected"]["claims"]["aud"]
            
            user = validator.get_user_identifier(claims)
            assert user == fixture["expected"]["user"]
            
            await validator.close()
    
    @pytest.mark.parametrize("fixture_name", collect_fixtures("duo_valid_*.yaml"))
    async def test_duo_valid_tokens(self, load_jwt_fixture, fixture_name):
        """Test validating real Duo JWTs extract correct claims."""
        if not fixture_name:
            pytest.skip("No Duo valid fixtures found")
        
        fixture = load_jwt_fixture(fixture_name)
        
        with freeze_time(fixture["validation_time"]):
            validator = get_jwt_validator(fixture["provider_config"])
            await validator._ensure_discovery()
            
            claims = await validator.validate_token(fixture["jwt"])
            
            assert claims["iss"] == fixture["expected"]["claims"]["iss"]
            assert claims["sub"] == fixture["expected"]["claims"]["sub"]
            assert claims["aud"] == fixture["expected"]["claims"]["aud"]
            
            user = validator.get_user_identifier(claims)
            assert user == fixture["expected"]["user"]
            
            await validator.close()
    
    @pytest.mark.parametrize("fixture_name", collect_fixtures("entra_valid_*.yaml"))
    async def test_entra_valid_tokens(self, load_jwt_fixture, fixture_name):
        """Test validating real Entra JWTs extract correct claims."""
        if not fixture_name:
            pytest.skip("No Entra valid fixtures found")
        
        fixture = load_jwt_fixture(fixture_name)
        
        with freeze_time(fixture["validation_time"]):
            validator = get_jwt_validator(fixture["provider_config"])
            await validator._ensure_discovery()
            
            claims = await validator.validate_token(fixture["jwt"])
            
            assert claims["iss"] == fixture["expected"]["claims"]["iss"]
            assert claims["sub"] == fixture["expected"]["claims"]["sub"]
            assert claims["aud"] == fixture["expected"]["claims"]["aud"]
            
            if "tid" in fixture["expected"]["claims"]:
                assert claims["tid"] == fixture["expected"]["claims"]["tid"]
            
            user = validator.get_user_identifier(claims)
            assert user == fixture["expected"]["user"]
            
            await validator.close()
    
    @pytest.mark.parametrize("fixture_name", collect_fixtures("*_valid_*.yaml"))
    async def test_expired_tokens(self, load_jwt_fixture, fixture_name):
        """Test that expired tokens are rejected."""
        if not fixture_name:
            pytest.skip("No valid fixtures found for expiration test")
        
        fixture = load_jwt_fixture(fixture_name)
        
        expired_time = fixture.get("expiration_time")
        if not expired_time:
            pytest.skip(f"No expiration_time in {fixture_name}")
        
        expired_dt = datetime.fromisoformat(expired_time.replace("Z", "+00:00"))
        expired_plus_hour = expired_dt + timedelta(hours=1)
        with freeze_time(expired_plus_hour):
            validator = get_jwt_validator(fixture["provider_config"])
            await validator._ensure_discovery()
            
            with pytest.raises(JWTExpiredError):
                await validator.validate_token(fixture["jwt"])
            
            await validator.close()
    
    async def test_provider_mismatch(self, load_jwt_fixture):
        """Test that a token is rejected if issuer doesn't match provider."""
        google_fixtures = collect_fixtures("google_valid_*.yaml")
        duo_fixtures = collect_fixtures("duo_valid_*.yaml")
        
        if not google_fixtures or not duo_fixtures:
            pytest.skip("Need both Google and Duo fixtures for mismatch test")
        
        google_fixture = load_jwt_fixture(google_fixtures[0])
        duo_fixture = load_jwt_fixture(duo_fixtures[0])
        
        with freeze_time(google_fixture["validation_time"]):
            validator = get_jwt_validator(duo_fixture["provider_config"])
            await validator._ensure_discovery()
            
            with pytest.raises(JWTValidationError):
                await validator.validate_token(google_fixture["jwt"])
            
            await validator.close()


@pytest.mark.jwt
@pytest.mark.asyncio
class TestProviderSpecificValidation:
    """Test provider-specific validation rules."""
    
    @pytest.mark.parametrize("fixture_name", collect_fixtures("google_valid_*.yaml"))
    async def test_google_email_verified(self, load_jwt_fixture, fixture_name):
        """Test that Google validates email_verified claim."""
        if not fixture_name:
            pytest.skip("No Google valid fixtures found")
        
        fixture = load_jwt_fixture(fixture_name)
        
        with freeze_time(fixture["validation_time"]):
            validator = get_jwt_validator(fixture["provider_config"])
            await validator._ensure_discovery()
            
            claims = await validator.validate_token(fixture["jwt"])
            
            assert "email" in claims
            assert "email_verified" in claims
            assert claims["email_verified"] is True
            
            await validator.close()
    
    @pytest.mark.parametrize("fixture_name", collect_fixtures("entra_valid_*.yaml"))
    async def test_entra_tenant_validation(self, load_jwt_fixture, fixture_name):
        """Test that Entra validates tenant_id matches."""
        if not fixture_name:
            pytest.skip("No Entra valid fixtures found")
        
        fixture = load_jwt_fixture(fixture_name)
        
        if "tenant_id" not in fixture["provider_config"]:
            pytest.skip(f"No tenant_id in {fixture_name} provider config")
        
        with freeze_time(fixture["validation_time"]):
            validator = get_jwt_validator(fixture["provider_config"])
            await validator._ensure_discovery()
            
            claims = await validator.validate_token(fixture["jwt"])
            
            if "tid" in claims:
                config_tenant = fixture["provider_config"]["tenant_id"]
                assert claims["tid"] == config_tenant
            
            await validator.close()


@pytest.mark.jwt
def test_fixture_structure():
    """Verify all JWT fixtures have required structure."""
    fixtures_dir = Path(__file__).parent / "fixtures" / "jwt"
    fixture_files = list(fixtures_dir.glob("*.yaml"))
    
    assert len(fixture_files) > 0, "No JWT fixtures found"
    
    for fixture_file in fixture_files:
        with open(fixture_file) as f:
            fixture = yaml.safe_load(f)
        
        # Required top-level fields
        assert "provider" in fixture, f"{fixture_file.name}: missing 'provider'"
        assert "jwt" in fixture, f"{fixture_file.name}: missing 'jwt'"
        assert "expected" in fixture, f"{fixture_file.name}: missing 'expected'"
        assert "provider_config" in fixture, f"{fixture_file.name}: missing 'provider_config'"
        
        # Required in expected
        assert "valid" in fixture["expected"], f"{fixture_file.name}: missing 'expected.valid'"
        
        # If valid, must have user and claims
        if fixture["expected"]["valid"]:
            assert "user" in fixture["expected"], f"{fixture_file.name}: missing 'expected.user'"
            assert "claims" in fixture["expected"], f"{fixture_file.name}: missing 'expected.claims'"
            assert "validation_time" in fixture, f"{fixture_file.name}: missing 'validation_time'"
