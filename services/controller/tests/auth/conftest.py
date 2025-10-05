import json
from pathlib import Path
from typing import Dict, Any, Optional
import pytest


@pytest.fixture
def recordings_dir():
    """Path to recordings directory"""
    return Path(__file__).parent.parent / "fixtures" / "recordings"


@pytest.fixture
def load_recording(recordings_dir):
    """Load a recording by name
    
    Usage:
        recording = load_recording("google_id_token")
        
    Returns dict with:
        - token: JWT string
        - metadata: Recording metadata (provider, timestamps, etc.)
        - discovery_request/response: OIDC discovery (if present)
        - jwks_request/response: JWKS fetch (if present)
        - decoded_claims: Expected claims (if JWT)
    """
    def _load(recording_name: str) -> Dict[str, Any]:
        recording_dir = recordings_dir / recording_name
        
        if not recording_dir.exists():
            pytest.skip(f"Recording not found: {recording_name}. Run scripts/record_oauth_token.py to create it.")
        
        recording: Dict[str, Any] = {}
        
        # Load token (required)
        token_file = recording_dir / "token.txt"
        if not token_file.exists():
            pytest.fail(f"Recording {recording_name} missing token.txt")
        recording["token"] = token_file.read_text().strip()
        
        # Load metadata (required)
        metadata_file = recording_dir / "metadata.json"
        if not metadata_file.exists():
            pytest.fail(f"Recording {recording_name} missing metadata.json")
        recording["metadata"] = json.loads(metadata_file.read_text())
        
        # Load optional files
        if (recording_dir / "discovery_request.json").exists():
            recording["discovery_request"] = json.loads(
                (recording_dir / "discovery_request.json").read_text()
            )
            recording["discovery_response"] = json.loads(
                (recording_dir / "discovery_response.json").read_text()
            )
        
        if (recording_dir / "jwks_request.json").exists():
            recording["jwks_request"] = json.loads(
                (recording_dir / "jwks_request.json").read_text()
            )
            recording["jwks_response"] = json.loads(
                (recording_dir / "jwks_response.json").read_text()
            )
        
        if (recording_dir / "decoded_claims.json").exists():
            recording["decoded_claims"] = json.loads(
                (recording_dir / "decoded_claims.json").read_text()
            )
        else:
            recording["decoded_claims"] = None
        
        return recording
    
    return _load


@pytest.fixture
def list_recordings(recordings_dir):
    """List all available recordings"""
    def _list() -> list[str]:
        if not recordings_dir.exists():
            return []
        return [d.name for d in recordings_dir.iterdir() if d.is_dir()]
    return _list
