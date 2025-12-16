"""Credential models for Tom Worker."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SSHCredentials:
    """SSH credentials for connecting to network devices."""

    credential_id: str
    username: Optional[str] = None
    password: Optional[str] = None
