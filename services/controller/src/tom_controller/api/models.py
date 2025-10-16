from typing import Literal, Optional, Dict, Any
import json

import saq
from pydantic import BaseModel


class JobResponse(BaseModel):
    job_id: str
    status: Literal["NEW", "QUEUED", "ACTIVE", "COMPLETE", "FAILED", "ABORTED", "ABORTING"]
    result: Optional[str | dict] = None
    group: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # Store job args for parsing

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
        )

    @classmethod
    async def from_job_id(cls, job_id: str, queue: saq.Queue) -> "JobResponse":
        job = await queue.job(job_id)
        return cls.from_job(job)
