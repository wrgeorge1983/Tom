"""Tests for enqueue_job in tom_controller.api.helpers.

These tests verify the three key behavioral paths:
1. Enqueue failure (Redis/SAQ down) -> raises TomJobEnqueueError
2. Wait timeout (job enqueued but result not ready in time) -> returns 200 with non-complete status
3. Normal success paths (wait=True completed, wait=False queued)
"""

from unittest.mock import AsyncMock

import pytest
import saq
from pydantic import BaseModel
from saq import Status

from tom_controller.api.helpers import enqueue_job
from tom_controller.exceptions import TomJobEnqueueError


class FakeArgs(BaseModel):
    host: str = "10.0.0.1"
    command: str = "show version"


def _make_queue() -> AsyncMock:
    """Create a mock SAQ Queue with a working job_id method.

    SAQ's Job.id property calls self.queue.job_id(self.key), so the mock
    queue must have a real job_id method (not an AsyncMock).
    """
    queue = AsyncMock()
    queue.job_id = lambda key: key
    return queue


def _make_job(queue: AsyncMock, status: Status = Status.NEW, **kwargs) -> saq.Job:
    """Create a real SAQ Job associated with a mock queue.

    Also sets up queue.job() to return a copy of this job (as SAQ's
    RedisQueue.job() would), so that _wait_for_job's polling guard works
    correctly with mock objects.
    """
    defaults = {
        "function": "send_commands_netmiko",
        "key": "saq:job:test-job-id",
        "retries": 3,
        "attempts": 1,
        "status": status,
        "result": None,
        "error": None,
        "queue": queue,
    }
    defaults.update(kwargs)
    job = saq.Job(**defaults)

    # queue.job() is called by the polling guard in _wait_for_job.
    # Return a snapshot of the job (same status) by default. Tests that need
    # different behavior can override queue.job after calling _make_job.
    async def _fake_queue_job(key):
        snapshot = saq.Job(
            function=job.function,
            key=job.key,
            retries=job.retries,
            attempts=job.attempts,
            status=job.status,
            result=job.result,
            error=job.error,
            completed=job.completed,
            queue=queue,
        )
        return snapshot

    queue.job = _fake_queue_job

    return job


class TestEnqueueSuccess:
    """Tests for the happy path: enqueue succeeds."""

    @pytest.mark.asyncio
    async def test_wait_false_returns_queued_job(self):
        """When wait=False, return immediately after enqueuing."""
        queue = _make_queue()
        job = _make_job(queue, status=Status.QUEUED)
        queue.enqueue = AsyncMock(return_value=job)

        response = await enqueue_job(
            queue, "send_commands_netmiko", FakeArgs(), wait=False, job_label="router1"
        )

        assert response.status == "QUEUED"
        assert response.job_id == "saq:job:test-job-id"
        queue.enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wait_true_complete(self):
        """When wait=True and job completes, return COMPLETE response."""
        queue = _make_queue()
        job = _make_job(queue, status=Status.QUEUED)

        async def fake_refresh(until_complete=None):
            job.status = Status.COMPLETE
            job.result = {"data": {"show version": "IOS 15.1"}, "meta": {}}
            job.attempts = 1

        job.refresh = AsyncMock(side_effect=fake_refresh)
        queue.enqueue = AsyncMock(return_value=job)

        response = await enqueue_job(
            queue,
            "send_commands_netmiko",
            FakeArgs(),
            wait=True,
            timeout=30,
            job_label="router1",
        )

        assert response.status == "COMPLETE"
        job.refresh.assert_awaited_once_with(until_complete=30.0)

    @pytest.mark.asyncio
    async def test_wait_true_failed_job(self):
        """When wait=True and job fails on the worker, return FAILED response (not an exception)."""
        queue = _make_queue()
        job = _make_job(queue, status=Status.QUEUED)

        async def fake_refresh(until_complete=None):
            job.status = Status.FAILED
            job.error = "Traceback ...\nAuthenticationException: bad password"
            job.attempts = 3

        job.refresh = AsyncMock(side_effect=fake_refresh)
        queue.enqueue = AsyncMock(return_value=job)

        response = await enqueue_job(
            queue,
            "send_commands_netmiko",
            FakeArgs(),
            wait=True,
            timeout=10,
            job_label="router1",
        )

        assert response.status == "FAILED"
        assert response.error is not None
        assert "AuthenticationException" in response.error

    @pytest.mark.asyncio
    async def test_wait_true_aborted_job(self):
        """When wait=True and job is aborted, return ABORTED response."""
        queue = _make_queue()
        job = _make_job(queue, status=Status.QUEUED)

        async def fake_refresh(until_complete=None):
            job.status = Status.ABORTED
            job.attempts = 1

        job.refresh = AsyncMock(side_effect=fake_refresh)
        queue.enqueue = AsyncMock(return_value=job)

        response = await enqueue_job(
            queue,
            "send_commands_netmiko",
            FakeArgs(),
            wait=True,
            timeout=10,
            job_label="router1",
        )

        assert response.status == "ABORTED"


class TestEnqueueFailure:
    """Tests for when queue.enqueue() itself fails (Redis down, etc.)."""

    @pytest.mark.asyncio
    async def test_enqueue_raises_tom_job_enqueue_error(self):
        """When queue.enqueue() raises, wrap in TomJobEnqueueError."""
        queue = _make_queue()
        queue.enqueue = AsyncMock(
            side_effect=ConnectionError("Redis connection refused")
        )

        with pytest.raises(TomJobEnqueueError) as exc_info:
            await enqueue_job(
                queue,
                "send_commands_netmiko",
                FakeArgs(),
                wait=False,
                job_label="router1",
            )

        assert "Failed to submit job to queue" in str(exc_info.value)
        assert "router1" in str(exc_info.value)
        assert "Redis connection refused" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_enqueue_failure_preserves_cause(self):
        """The original exception is chained via __cause__."""
        original = ConnectionError("Redis connection refused")
        queue = _make_queue()
        queue.enqueue = AsyncMock(side_effect=original)

        with pytest.raises(TomJobEnqueueError) as exc_info:
            await enqueue_job(
                queue, "send_commands_netmiko", FakeArgs(), job_label="switch1"
            )

        assert exc_info.value.__cause__ is original

    @pytest.mark.asyncio
    async def test_enqueue_failure_without_label(self):
        """Error message works without a job_label."""
        queue = _make_queue()
        queue.enqueue = AsyncMock(side_effect=RuntimeError("queue full"))

        with pytest.raises(TomJobEnqueueError) as exc_info:
            await enqueue_job(queue, "send_commands_netmiko", FakeArgs())

        msg = str(exc_info.value)
        assert "Failed to submit job to queue" in msg
        assert "queue full" in msg
        # No " for " label when job_label is empty
        assert " for " not in msg


class TestWaitTimeout:
    """Tests for when wait=True but the refresh times out."""

    @pytest.mark.asyncio
    async def test_timeout_returns_non_complete_response(self):
        """When refresh raises TimeoutError, return the job in its current state."""
        queue = _make_queue()
        job = _make_job(queue, status=Status.ACTIVE, attempts=0)
        job.refresh = AsyncMock(side_effect=TimeoutError())
        queue.enqueue = AsyncMock(return_value=job)

        response = await enqueue_job(
            queue,
            "send_commands_netmiko",
            FakeArgs(),
            wait=True,
            timeout=10,
            job_label="router1",
        )

        # Should return 200-equivalent (no exception), with non-complete status
        assert response.status == "ACTIVE"
        assert response.job_id == "saq:job:test-job-id"

    @pytest.mark.asyncio
    async def test_timeout_does_not_raise(self):
        """Timeout should NOT raise TomJobEnqueueError or any other exception."""
        queue = _make_queue()
        job = _make_job(queue, status=Status.QUEUED, attempts=0)
        job.refresh = AsyncMock(side_effect=TimeoutError())
        queue.enqueue = AsyncMock(return_value=job)

        # Should not raise
        response = await enqueue_job(
            queue,
            "send_commands_netmiko",
            FakeArgs(),
            wait=True,
            timeout=5,
            job_label="router1",
        )

        assert response.status == "QUEUED"

    @pytest.mark.asyncio
    async def test_timeout_logs_warning(self, caplog):
        """Timeout should log a warning with job ID and label."""
        import logging

        queue = _make_queue()
        job = _make_job(queue, status=Status.ACTIVE, attempts=0)
        job.refresh = AsyncMock(side_effect=TimeoutError())
        queue.enqueue = AsyncMock(return_value=job)

        with caplog.at_level(logging.WARNING):
            await enqueue_job(
                queue,
                "send_commands_netmiko",
                FakeArgs(),
                wait=True,
                timeout=10,
                job_label="router1",
            )

        assert any("timed out" in record.message for record in caplog.records)
        assert any("router1" in record.message for record in caplog.records)


class TestJobLabel:
    """Tests for job_label appearing in log output."""

    @pytest.mark.asyncio
    async def test_label_in_enqueue_log(self, caplog):
        """job_label should appear in the enqueuing log line."""
        import logging

        queue = _make_queue()
        job = _make_job(queue, status=Status.QUEUED)
        queue.enqueue = AsyncMock(return_value=job)

        with caplog.at_level(logging.INFO):
            await enqueue_job(
                queue,
                "send_commands_netmiko",
                FakeArgs(),
                wait=False,
                job_label="core-rtr-01",
            )

        enqueue_msgs = [r.message for r in caplog.records if "Enqueuing" in r.message]
        assert len(enqueue_msgs) >= 1
        assert "core-rtr-01" in enqueue_msgs[0]

    @pytest.mark.asyncio
    async def test_no_label_when_empty(self, caplog):
        """When job_label is empty, log lines should not contain ' for '."""
        import logging

        queue = _make_queue()
        job = _make_job(queue, status=Status.QUEUED)
        queue.enqueue = AsyncMock(return_value=job)

        with caplog.at_level(logging.INFO):
            await enqueue_job(
                queue, "send_commands_netmiko", FakeArgs(), wait=False, job_label=""
            )

        enqueue_msg = [r.message for r in caplog.records if "Enqueuing" in r.message][0]
        assert " for " not in enqueue_msg
