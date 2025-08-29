from typing import Literal, Optional

import saq
from pydantic import BaseModel


class JobResponse(BaseModel):
    job_id: str
    status: Literal["NEW", "QUEUED", "ACTIVE", "COMPLETE", "FAILED", "ABORTED"]
    result: Optional[str | dict] = None
    group: Optional[str] = None

    @classmethod
    def from_job(cls, job: Optional[saq.job.Job]) -> "JobResponse":
        if job is None:
            return cls(
                job_id="",
                status="NEW",
                result=None,
            )
        return cls(
            job_id=job.key,
            status=job.status.name,
            result=job.result,
        )

    @classmethod
    async def from_job_id(cls, job_id: str, queue: saq.Queue) -> "JobResponse":
        job = await queue.job(job_id)
        return cls.from_job(job)
