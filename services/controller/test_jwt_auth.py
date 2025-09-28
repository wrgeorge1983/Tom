#!/usr/bin/env python3
"""Test script for JWT authentication.

This script creates mock JWTs for testing the JWT validation functionality.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from jose import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

# Add the controller source to path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from tom_controller.auth import get_jwt_validator
from tom_controller.exceptions import JWTValidationError


def create_rsa_keypair():
    """Create an RSA keypair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    public_key = private_key.public_key()

    # Export keys in PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return private_key, public_key, private_pem, public_pem


def create_test_jwt(
    private_key,
    issuer,
    audience,
    subject="test@example.com",
    expires_in_seconds=3600,
    additional_claims=None,
):
    """Create a test JWT token."""
    now = datetime.utcnow()

    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "email": subject if "@" in subject else f"{subject}@example.com",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in_seconds),
        "nbf": now - timedelta(seconds=10),
    }

    if additional_claims:
        claims.update(additional_claims)

    # Create token with RS256 algorithm
    token = jwt.encode(
        claims, private_key, algorithm="RS256", headers={"kid": "test-key-1"}
    )

    return token


class MockJWKSServer:
    """Mock JWKS server that returns our test public key."""

    def __init__(self, public_key):
        self.public_key = public_key
        self._jwks_data = None

    def get_jwks(self):
        """Get JWKS data with our public key."""
        if not self._jwks_data:
            from jose import jwk

            # Convert public key to JWK format
            key_data = jwk.construct(self.public_key, algorithm="RS256").to_dict()
            key_data["kid"] = "test-key-1"
            key_data["use"] = "sig"

            self._jwks_data = {"keys": [key_data]}

        return self._jwks_data


async def test_google_jwt():
    """Test Google JWT validation."""
    print("\n=== Testing Google JWT Validator ===")

    # Create test keypair
    private_key, public_key, _, _ = create_rsa_keypair()

    # Create test token
    token = create_test_jwt(
        private_key,
        issuer="https://accounts.google.com",
        audience="test-client-id",
        subject="user@gmail.com",
        additional_claims={
            "email_verified": True,
            "name": "Test User",
        },
    )

    # Create validator config
    config = {
        "name": "google",
        "enabled": True,
        "issuer": "https://accounts.google.com",
        "client_id": "test-client-id",
        "audience": "test-client-id",
    }

    # Note: In a real test, we'd need to mock the JWKS endpoint
    # For now, this will fail when trying to fetch the actual Google JWKS
    validator = get_jwt_validator(config)

    print(f"Created test token for Google")
    print(f"Token (first 50 chars): {token[:50]}...")

    # Decode without verification to show claims
    unverified_claims = jwt.get_unverified_claims(token)
    print(f"Token claims: {json.dumps(unverified_claims, indent=2)}")

    print("\nNote: Actual validation would require mocking the JWKS endpoint")

    await validator.close()


async def test_duo_jwt():
    """Test Duo JWT validation."""
    print("\n=== Testing Duo JWT Validator ===")

    # Create test keypair
    private_key, public_key, _, _ = create_rsa_keypair()

    # Create test token
    token = create_test_jwt(
        private_key,
        issuer="https://test-tenant.duosecurity.com",
        audience="test-api-audience",
        subject="testuser",
        additional_claims={
            "preferred_username": "testuser",
            "auth_time": int(time.time()),
        },
    )

    # Create validator config
    config = {
        "name": "duo",
        "enabled": True,
        "issuer": "https://test-tenant.duosecurity.com",
        "client_id": "test-client-id",
        "audience": "test-api-audience",
        "jwks_uri": "https://test-tenant.duosecurity.com/oauth/v1/keys",
    }

    validator = get_jwt_validator(config)

    print(f"Created test token for Duo")
    print(f"Token (first 50 chars): {token[:50]}...")

    # Decode without verification to show claims
    unverified_claims = jwt.get_unverified_claims(token)
    print(f"Token claims: {json.dumps(unverified_claims, indent=2)}")

    print("\nNote: Actual validation would require mocking the JWKS endpoint")

    await validator.close()


async def test_expired_jwt():
    """Test validation of expired JWT."""
    print("\n=== Testing Expired JWT ===")

    # Create test keypair
    private_key, public_key, _, _ = create_rsa_keypair()

    # Create expired token
    token = create_test_jwt(
        private_key,
        issuer="https://test.example.com",
        audience="test-audience",
        subject="test@example.com",
        expires_in_seconds=-3600,  # Expired 1 hour ago
    )

    print(f"Created expired token")

    # Decode without verification to show claims
    unverified_claims = jwt.get_unverified_claims(token)
    print(f"Token claims: {json.dumps(unverified_claims, indent=2)}")
    print(f"Token expired at: {datetime.fromtimestamp(unverified_claims['exp'])}")
    print(f"Current time: {datetime.utcnow()}")


async def test_invalid_signature():
    """Test validation with invalid signature."""
    print("\n=== Testing Invalid Signature ===")

    # Create two different keypairs
    private_key1, _, _, _ = create_rsa_keypair()
    private_key2, _, _, _ = create_rsa_keypair()

    # Create token with first key
    token = create_test_jwt(
        private_key1,
        issuer="https://test.example.com",
        audience="test-audience",
        subject="test@example.com",
    )

    # Tamper with the token (change one character in the signature)
    parts = token.split(".")
    signature = parts[2]
    if signature[0] == "A":
        tampered_signature = "B" + signature[1:]
    else:
        tampered_signature = "A" + signature[1:]
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_signature}"

    print(f"Created token with tampered signature")
    print(f"Original token (last 20 chars): ...{token[-20:]}")
    print(f"Tampered token (last 20 chars): ...{tampered_token[-20:]}")


async def main():
    """Run all tests."""
    print("JWT Authentication Test Suite")
    print("=" * 50)

    # Test different providers
    await test_google_jwt()
    await test_duo_jwt()

    # Test error conditions
    await test_expired_jwt()
    await test_invalid_signature()

    print("\n" + "=" * 50)
    print("Test suite completed")
    print("\nNote: These tests demonstrate token creation and structure.")
    print("Full integration testing would require:")
    print("1. Mocking JWKS endpoints")
    print("2. Setting up test OAuth providers")
    print("3. Running the full API with test configuration")


if __name__ == "__main__":
    asyncio.run(main())
