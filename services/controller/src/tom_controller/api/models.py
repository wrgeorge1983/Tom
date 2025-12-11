from typing import Literal, Optional, Dict, Any, List, Union
import json

import saq
from pydantic import BaseModel, Field
from tom_shared.models import CommandExecutionResult


class JobResponse(BaseModel):
    job_id: str
    status: Literal[
        "NEW", "QUEUED", "ACTIVE", "COMPLETE", "FAILED", "ABORTED", "ABORTING"
    ]
    result: Optional[str | dict] = None
    group: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # Store job args for parsing
    attempts: int = 0
    error: Optional[str] = None

    @classmethod
    def from_job(cls, job) -> "JobResponse":
        if job is None:
            return cls(
                job_id="",
                status="NEW",
                result=None,
            )

        # Extract metadata from job kwargs if available
        metadata = None
        if hasattr(job, "kwargs") and job.kwargs:
            try:
                # job.kwargs contains our args as JSON string
                if "json" in job.kwargs:
                    metadata = json.loads(job.kwargs["json"])
            except (json.JSONDecodeError, KeyError):
                pass

        return cls(
            job_id=job.key,
            status=job.status.name,
            result=job.result,
            metadata=metadata,
            attempts=getattr(job, "attempts", 0),
            error=getattr(job, "error", None),
        )

    @classmethod
    async def from_job_id(cls, job_id: str, queue: saq.Queue) -> "JobResponse":
        job = await queue.job(job_id)
        return cls.from_job(job)

    @property
    def command_data(self) -> Optional[Dict[str, str]]:
        """Get command outputs from result."""
        if isinstance(self.result, dict) and "data" in self.result:
            return self.result["data"]
        return None

    @property
    def cache_metadata(self) -> Optional[dict]:
        """Get cache metadata if available."""
        if isinstance(self.result, dict) and "meta" in self.result:
            return self.result["meta"].get("cache")
        return None

    def get_command_output(self, command: str) -> Optional[str]:
        """Get output for a specific command."""
        data = self.command_data
        if data:
            return data.get(command)
        return None


class SendCommandRequest(BaseModel):
    """Request body for sending a single command to a device."""

    command: str = Field(..., description="The command to execute")
    wait: bool = Field(False, description="Wait for job completion")
    parse: bool = Field(False, description="Parse output using specified parser")
    parser: Literal["textfsm", "ttp"] = Field("textfsm", description="Parser to use")
    template: Optional[str] = Field(
        None, description="Explicit template name for parsing"
    )
    include_raw: bool = Field(False, description="Include raw output along with parsed")
    timeout: int = Field(10, description="Timeout in seconds")
    use_cache: bool = Field(False, description="Use cache for command results")
    cache_ttl: Optional[int] = Field(None, description="Cache TTL in seconds")
    cache_refresh: bool = Field(False, description="Force refresh cache")
    # Optional credentials override
    username: Optional[str] = Field(
        None, description="Override username (requires password)"
    )
    password: Optional[str] = Field(
        None, description="Override password (requires username)"
    )


class RawCommandRequest(BaseModel):
    """Request body for raw command endpoints (no inventory lookup)."""

    host: str = Field(..., description="Device hostname or IP")
    device_type: str = Field(
        ..., description="Device type (e.g., cisco_ios, arista_eos)"
    )
    command: str = Field(..., description="The command to execute")
    port: int = Field(22, description="SSH port")
    wait: bool = Field(False, description="Wait for job completion")
    # Credentials - must provide either credential_id or username+password
    credential_id: Optional[str] = Field(None, description="Stored credential ID")
    username: Optional[str] = Field(
        None, description="SSH username (requires password)"
    )
    password: Optional[str] = Field(
        None, description="SSH password (requires username)"
    )


class CommandSpec(BaseModel):
    """Specification for a single command with optional parsing configuration."""

    command: str = Field(..., description="The command to execute")
    parse: Optional[bool] = Field(
        None, description="Whether to parse this command's output"
    )
    parser: Optional[Literal["textfsm", "ttp"]] = Field(
        None, description="Parser to use for this command"
    )
    template: Optional[str] = Field(
        None, description="Explicit template to use for parsing this command"
    )
    include_raw: Optional[bool] = Field(
        None, description="Include raw output along with parsed result"
    )


class SendCommandsRequest(BaseModel):
    """Request body for sending multiple commands with per-command configuration."""

    commands: Union[List[str], List[CommandSpec]] = Field(
        ...,
        description="List of commands to execute. Can be strings for simple execution "
        "or CommandSpec objects for per-command configuration",
    )
    # Global defaults that can be overridden per command
    parse: bool = Field(False, description="Default: whether to parse command outputs")
    parser: Literal["textfsm", "ttp"] = Field(
        "textfsm", description="Default parser to use"
    )
    include_raw: bool = Field(
        False, description="Default: include raw output with parsed"
    )
    wait: bool = Field(False, description="Wait for job completion")
    timeout: int = Field(
        10, description="Timeout in seconds for device command execution"
    )
    retries: int = Field(
        3,
        description="Number of times to retry on transient failures (network errors, command timeouts, etc.). Does not affect semaphore acquisition attempts.",
    )
    max_queue_wait: int = Field(
        300,
        description="Maximum total seconds to wait for device semaphore acquisition across all retry attempts",
    )
    use_cache: bool = Field(True, description="Use cache for command results")
    cache_refresh: bool = Field(False, description="Force refresh cache")
    cache_ttl: Optional[int] = Field(None, description="Cache TTL in seconds")
    # Optional credentials override
    username: Optional[str] = Field(
        None, description="Override username (requires password)"
    )
    password: Optional[str] = Field(
        None, description="Override password (requires username)"
    )

    def get_normalized_commands(self) -> List[CommandSpec]:
        """Convert all commands to CommandSpec format with defaults applied."""
        normalized = []
        for cmd in self.commands:
            if isinstance(cmd, str):
                # Convert string to CommandSpec with request-level defaults
                normalized.append(
                    CommandSpec(
                        command=cmd,
                        parse=self.parse,
                        parser=self.parser,
                        include_raw=self.include_raw,
                    )
                )
            else:
                # Apply defaults to any unspecified fields in CommandSpec
                if cmd.parse is None:
                    cmd.parse = self.parse
                if cmd.parser is None:
                    cmd.parser = self.parser
                if cmd.include_raw is None:
                    cmd.include_raw = self.include_raw
                normalized.append(cmd)
        return normalized
