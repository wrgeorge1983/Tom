from typing import Literal, Union, Optional, Any, Dict

from pydantic import BaseModel, Field


class StoredCredential(BaseModel):
    type: Literal["stored"] = "stored"
    credential_id: str


class InlineSSHCredential(BaseModel):
    type: Literal["inlineSSH"] = "inlineSSH"
    username: str
    password: str = Field(None, repr=False)


CredentialSource = StoredCredential | InlineSSHCredential


class NetmikoSendCommandModel(BaseModel):
    host: str
    port: int
    device_type: str
    commands: list[str]
    credential: CredentialSource = Field(discriminator="type")
    use_cache: bool = True
    cache_refresh: bool = False
    cache_ttl: Optional[int] = None


class ScrapliSendCommandModel(BaseModel):
    host: str
    port: int
    device_type: str
    commands: list[str]
    credential: CredentialSource = Field(discriminator="type")
    use_cache: bool = True
    cache_refresh: bool = False
    cache_ttl: Optional[int] = None


class CacheMetadata(BaseModel):
    """Metadata about cache usage for command execution."""
    cache_status: Literal["hit", "miss", "partial", "disabled"]
    commands: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-command cache information"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "cache_status": "partial",
                "commands": {
                    "show version": {
                        "cache_status": "hit",
                        "cached_at": "2024-01-01T10:00:00Z",
                        "age_seconds": 120.5,
                        "ttl": 300
                    },
                    "show interfaces": {
                        "cache_status": "miss"
                    }
                }
            }
        }


class CommandExecutionResult(BaseModel):
    """Result from executing commands on a network device.
    
    This model is used by workers to return structured results with metadata,
    and by the controller to parse and validate those results.
    """
    data: Dict[str, str] = Field(
        description="Command outputs keyed by command string"
    )
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about the execution (cache info, timing, etc.)"
    )
    
    @property
    def cache_metadata(self) -> Optional[CacheMetadata]:
        """Extract cache metadata if present."""
        cache_data = self.meta.get("cache")
        if cache_data:
            return CacheMetadata(**cache_data)
        return None
    
    @property
    def cache_status(self) -> str:
        """Get overall cache status."""
        cache_meta = self.cache_metadata
        return cache_meta.cache_status if cache_meta else "disabled"
    
    def get_command_output(self, command: str) -> Optional[str]:
        """Get output for a specific command."""
        return self.data.get(command)
    
    def was_cached(self, command: str) -> bool:
        """Check if a specific command result came from cache."""
        cache_meta = self.cache_metadata
        if not cache_meta:
            return False
        cmd_info = cache_meta.commands.get(command, {})
        return cmd_info.get("cache_status") == "hit"
    
    class Config:
        json_schema_extra = {
            "example": {
                "data": {
                    "show version": "Cisco IOS XE Software...",
                    "show interfaces": "GigabitEthernet0/0 is up..."
                },
                "meta": {
                    "cache": {
                        "cache_status": "partial",
                        "commands": {
                            "show version": {
                                "cache_status": "hit",
                                "cached_at": "2024-01-01T10:00:00Z",
                                "age_seconds": 120.5
                            },
                            "show interfaces": {
                                "cache_status": "miss"
                            }
                        }
                    },
                    "execution_time": 2.5,
                    "device": "router1"
                }
            }
        }
