from typing import Literal, Optional, Dict, Any
import json

import saq
from pydantic import BaseModel
from tom_shared.models import CommandExecutionResult


class JobResponse(BaseModel):
    job_id: str
    status: Literal["NEW", "QUEUED", "ACTIVE", "COMPLETE", "FAILED", "ABORTED", "ABORTING"]
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
        if hasattr(job, 'kwargs') and job.kwargs:
            try:
                # job.kwargs contains our args as JSON string
                if 'json' in job.kwargs:
                    metadata = json.loads(job.kwargs['json'])
            except (json.JSONDecodeError, KeyError):
                pass
        
        return cls(
            job_id=job.key,
            status=job.status.name,
            result=job.result,
            metadata=metadata,
            attempts=getattr(job, 'attempts', 0),
            error=getattr(job, 'error', None),
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
