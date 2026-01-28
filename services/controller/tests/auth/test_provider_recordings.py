"""
Tests for OAuth provider validation using recorded tokens.

These tests replay recorded OAuth interactions to verify:
1. Token validation logic works correctly
2. HTTP requests are formed correctly
3. Provider-specific quirks are preserved

To create recordings:
    python scripts/record_oauth_token.py google
    python scripts/record_oauth_token.py duo
"""

import pytest
from freezegun import freeze_time
from pytest_httpx import HTTPXMock

from tom_controller.auth.providers import GoogleJWTValidator, DuoJWTValidator
from tom_controller.auth.oidc_discovery import OIDCDiscovery
from tom_controller.exceptions import JWTExpiredError


class TestGoogleIDTokenValidation:
    """Test Google ID token validation against recorded interactions"""

    @pytest.mark.asyncio
    async def test_validate_recorded_google_id_token(
        self, load_recording, httpx_mock: HTTPXMock
    ):
        """Verify we can validate a recorded Google ID token"""
        recording = load_recording("google_id_token")

        if not recording.get("jwks_request"):
            pytest.skip("No JWKS recording available")

        # Mock HTTP to return recorded JWKS
        httpx_mock.add_response(
            url=recording["jwks_request"]["url"], json=recording["jwks_response"]
        )

        validator = GoogleJWTValidator(
            {
                "name": "google",
                "type": "google",
                "client_id": recording["metadata"]["client_id"],
                "issuer": recording["decoded_claims"]["iss"],
                "jwks_uri": recording["jwks_request"]["url"],
            }
        )

        # Mock time to when token was valid
        with freeze_time(recording["metadata"]["validation_time"]):
            claims = await validator.validate_token(recording["token"])

        # Verify outcome matches what we recorded
        assert claims["sub"] == recording["decoded_claims"]["sub"]
        assert claims["email"] == recording["decoded_claims"]["email"]
        assert claims["iss"] == recording["decoded_claims"]["iss"]

        await validator.close()

    @pytest.mark.asyncio
    async def test_google_discovery_request(
        self, load_recording, httpx_mock: HTTPXMock
    ):
        """Verify we make the correct discovery request for Google"""
        recording = load_recording("google_id_token")

        if not recording.get("discovery_request"):
            pytest.skip("No discovery recording available")

        httpx_mock.add_response(
            url=recording["discovery_request"]["url"],
            json=recording["discovery_response"],
        )

        discovery = OIDCDiscovery(recording["discovery_request"]["url"])
        doc = await discovery.discover()

        # Verify we parse the response correctly
        assert doc["issuer"] == recording["discovery_response"]["issuer"]
        assert doc["jwks_uri"] == recording["discovery_response"]["jwks_uri"]

        # Verify the request was made correctly
        request = httpx_mock.get_request()
        assert str(request.url) == recording["discovery_request"]["url"]
        assert request.method == recording["discovery_request"]["method"]

        await discovery.close()

    @pytest.mark.asyncio
    async def test_expired_google_token_rejected(
        self, load_recording, httpx_mock: HTTPXMock
    ):
        """Verify expired tokens fail validation"""
        recording = load_recording("google_id_token")

        if not recording.get("jwks_request"):
            pytest.skip("No JWKS recording available")

        httpx_mock.add_response(
            url=recording["jwks_request"]["url"], json=recording["jwks_response"]
        )

        validator = GoogleJWTValidator(
            {
                "name": "google",
                "type": "google",
                "client_id": recording["metadata"]["client_id"],
                "issuer": recording["decoded_claims"]["iss"],
                "jwks_uri": recording["jwks_request"]["url"],
            }
        )

        # Mock time to after expiration
        expired_time = recording["decoded_claims"]["exp"] + 100
        with freeze_time(expired_time):
            with pytest.raises(JWTExpiredError):
                await validator.validate_token(recording["token"])

        await validator.close()


class TestGoogleProviderQuirks:
    """Test Google-specific behavior documented in recordings"""

    def test_google_requires_client_secret(self, load_recording):
        """Verify Google recording documents client_secret requirement"""
        recording = load_recording("google_id_token")

        # This quirk should be documented in metadata
        assert recording["metadata"]["requires_client_secret"] is True
        assert "client_secret" in recording["metadata"]["notes"].lower()

    def test_google_access_token_is_opaque(self, load_recording):
        """Verify Google access tokens are documented as opaque"""
        try:
            recording = load_recording("google_access_token")
        except:
            pytest.skip("No Google access token recording available")

        # Should be documented as opaque (not a JWT)
        assert recording["metadata"]["is_jwt"] is False
        assert recording["metadata"]["token_type"] == "opaque"
        assert recording.get("decoded_claims") is None


class TestDuoIDTokenValidation:
    """Test Duo ID token validation against recorded interactions"""

    @pytest.mark.asyncio
    async def test_validate_recorded_duo_id_token(
        self, load_recording, httpx_mock: HTTPXMock
    ):
        """Verify we can validate a recorded Duo ID token"""
        recording = load_recording("duo_id_token")

        if not recording.get("jwks_request"):
            pytest.skip("No JWKS recording available")

        # Mock HTTP to return recorded JWKS
        httpx_mock.add_response(
            url=recording["jwks_request"]["url"], json=recording["jwks_response"]
        )

        validator = DuoJWTValidator(
            {
                "name": "duo",
                "type": "duo",
                "client_id": recording["metadata"]["client_id"],
                "issuer": recording["decoded_claims"]["iss"],
                "jwks_uri": recording["jwks_request"]["url"],
            }
        )

        # Mock time to when token was valid
        with freeze_time(recording["metadata"]["validation_time"]):
            claims = await validator.validate_token(recording["token"])

        # Verify outcome matches what we recorded
        assert claims["sub"] == recording["decoded_claims"]["sub"]
        assert claims["iss"] == recording["decoded_claims"]["iss"]

        await validator.close()

    @pytest.mark.asyncio
    async def test_duo_discovery_request(self, load_recording, httpx_mock: HTTPXMock):
        """Verify we make the correct discovery request for Duo"""
        recording = load_recording("duo_id_token")

        if not recording.get("discovery_request"):
            pytest.skip("No discovery recording available")

        httpx_mock.add_response(
            url=recording["discovery_request"]["url"],
            json=recording["discovery_response"],
        )

        discovery = OIDCDiscovery(recording["discovery_request"]["url"])
        doc = await discovery.discover()

        # Verify we parse the response correctly
        assert doc["issuer"] == recording["discovery_response"]["issuer"]
        assert doc["jwks_uri"] == recording["discovery_response"]["jwks_uri"]

        await discovery.close()


class TestDuoProviderQuirks:
    """Test Duo-specific behavior documented in recordings"""

    def test_duo_accepts_both_token_types_as_jwt(self, load_recording):
        """Verify Duo accepts both access and ID tokens as JWTs"""
        try:
            access_recording = load_recording("duo_access_token")
            id_recording = load_recording("duo_id_token")
        except:
            pytest.skip("Duo recordings not available")

        # Both should be JWTs
        assert access_recording["metadata"]["is_jwt"] is True
        assert id_recording["metadata"]["is_jwt"] is True

        # Both should have decoded claims
        assert access_recording["decoded_claims"] is not None
        assert id_recording["decoded_claims"] is not None


class TestJWKSCaching:
    """Test JWKS caching behavior"""

    @pytest.mark.asyncio
    async def test_jwks_cached_on_second_request(
        self, load_recording, httpx_mock: HTTPXMock
    ):
        """Verify JWKS responses are cached"""
        recording = load_recording("google_id_token")

        if not recording.get("jwks_request"):
            pytest.skip("No JWKS recording available")

        # Mock will only respond once - if cache doesn't work, second request will fail
        httpx_mock.add_response(
            url=recording["jwks_request"]["url"], json=recording["jwks_response"]
        )

        validator = GoogleJWTValidator(
            {
                "name": "google",
                "type": "google",
                "client_id": recording["metadata"]["client_id"],
                "issuer": recording["decoded_claims"]["iss"],
                "jwks_uri": recording["jwks_request"]["url"],
            }
        )

        with freeze_time(recording["metadata"]["validation_time"]):
            # First validation - should fetch JWKS
            await validator.validate_token(recording["token"])

            # Second validation - should use cache (no new HTTP request)
            await validator.validate_token(recording["token"])

        # Should only have made ONE request (cached the second time)
        requests = httpx_mock.get_requests()
        jwks_requests = [
            r for r in requests if "jwks" in str(r.url) or "keys" in str(r.url)
        ]
        assert len(jwks_requests) == 1, "JWKS should be cached after first request"

        await validator.close()
