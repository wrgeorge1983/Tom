# Enqueue Error Handling Improvements

## Problem

When `wait=True` and the wait-for-result times out, the exception is caught by a
generic `except Exception` handler that labels it "Failed to enqueue job for {device}".
This is misleading -- the enqueue succeeded, the wait timed out. From logs alone it's
impossible to distinguish an actual infrastructure failure (Redis down, semaphore
starvation) from a slow job that didn't finish in time.

Additionally, all log lines from `enqueue_job` lack the device name, making it
impossible to correlate job IDs to devices without cross-referencing timestamps.

## Changes

### 1. New exception class in `services/controller/src/tom_controller/exceptions.py`

Add one new exception:

```python
class TomJobEnqueueError(TomException):
    """Failed to submit a job to the queue (Redis/SAQ failure)."""
    pass
```

The wait-timeout case will NOT be an exception (see #2 below).

### 2. Rework `enqueue_job` in `services/controller/src/tom_controller/api/helpers.py`

Add a `job_label` parameter (typically the device name) used in all log lines.

Separate the enqueue and wait phases:

- **Enqueue phase**: Wrap `queue.enqueue()` in a try/except. On failure, raise
  `TomJobEnqueueError` with a clear message including the job_label and cause.

- **Wait phase**: Wrap `job.refresh(until_complete=...)` in a try/except for
  `TimeoutError`. On timeout, log a warning and fall through to return the
  JobResponse as-is. The response will have a non-complete status (e.g. ACTIVE,
  QUEUED) which tells the caller the job isn't done. This is not an error -- the
  job was accepted, we just couldn't wait long enough.

Include `job_label` in all log lines. Include `job.id` in all log lines after
it's known (the existing completion/failure logging already does this, but error
paths should too).

```python
async def enqueue_job(
    queue: saq.Queue,
    function_name: str,
    args: BaseModel,
    wait: bool = False,
    timeout: int = 10,
    retries: int = 3,
    max_queue_wait: int = 300,
    job_label: str = "",
) -> JobResponse:
    label = f" for {job_label}" if job_label else ""

    logger.info(f"Enqueuing job{label}: {function_name}")

    try:
        job = await queue.enqueue(
            function_name,
            timeout=timeout,
            json=args.model_dump_json(),
            retries=retries,
            retry_delay=1.0,
            retry_backoff=True,
        )
    except Exception as e:
        logger.error(f"Failed to submit job to queue{label}: {e}")
        raise TomJobEnqueueError(
            f"Failed to submit job to queue{label}: {e}"
        ) from e

    logger.info(f"Enqueued job {job.id}{label} with retries={job.retries}")

    if wait:
        try:
            await job.refresh(until_complete=float(timeout))
        except TimeoutError:
            logger.warning(
                f"Job {job.id}{label} was enqueued but timed out after "
                f"{timeout}s waiting for result"
            )
            # Fall through -- return the job in whatever state it's in.
            # The caller sees a non-complete status and knows it's not done.
            job_response = JobResponse.from_job(job)
            return job_response

        if job.status == Status.COMPLETE:
            logger.info(
                f"Job {job.id}{label} completed successfully "
                f"after {job.attempts} attempt(s)"
            )
        elif job.status == Status.FAILED:
            error_summary = None
            if job.error:
                if "AuthenticationException" in job.error:
                    error_summary = "Authentication failed"
                elif "GatingException" in job.error:
                    error_summary = "Device busy"
                else:
                    error_lines = job.error.strip().split("\n")
                    if error_lines:
                        error_summary = error_lines[-1][:200]
            logger.error(
                f"Job {job.id}{label} FAILED after {job.attempts} "
                f"attempt(s) - {error_summary or 'Unknown error'}"
            )
        elif job.status == Status.ABORTED:
            logger.warning(
                f"Job {job.id}{label} was aborted after {job.attempts} attempt(s)"
            )
        else:
            logger.info(
                f"Job {job.id}{label} status: {job.status} "
                f"after {job.attempts} attempt(s)"
            )

    job_response = JobResponse.from_job(job)
    return job_response
```

### 3. Update callers in `services/controller/src/tom_controller/api/device.py`

In `_execute_device_job`, pass `job_label=device_name` and catch `TomJobEnqueueError`
specifically:

```python
try:
    response = await enqueue_job(
        params.queue,
        job_function,
        args,
        wait=params.wait,
        timeout=params.timeout,
        retries=params.retries,
        max_queue_wait=params.max_queue_wait,
        job_label=device_name,
    )
except TomJobEnqueueError as e:
    return _raise_or_plain(str(e), 500, raw_output)
```

No `except Exception` catch-all. If something unexpected happens it bubbles up to the
global handler in `app.py` which already catches `Exception` and returns 500.

### 4. Update callers in `services/controller/src/tom_controller/api/raw.py`

Same pattern as device.py. The raw endpoints at lines ~94 and ~190 have the same
`except Exception` wrapping `enqueue_job`. Change to catch `TomJobEnqueueError` and
pass an appropriate `job_label` (the host address).

### 5. Register handler in `services/controller/src/tom_controller/app.py`

`TomJobEnqueueError` is a subclass of `TomException`, so it's already caught by the
existing `TomException` handler (lines 349-361) which returns 500. No new handler
needed unless we want a different error label. Could optionally add an explicit handler
for clarity:

```python
@app.exception_handler(TomJobEnqueueError)
async def tom_job_enqueue_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "Job Enqueue Failed", "detail": str(exc)},
    )
```

This is optional -- the base `TomException` handler already covers it with a generic
"Internal Server Error" label.

### 6. Update endpoint docstrings

Add to the documented status codes for `send_commands`, `send_command`, and the raw
endpoints:

For the default (JSON) mode, document that:

- 200 may return a JobResponse with a non-complete status if `wait=True` and the wait
  timed out. The job was accepted and may still complete. Callers should check the
  `status` field rather than assuming a 200 means the job completed.

For `raw_output=true` mode:

- 500: Failed to submit job to queue (infrastructure error)

## Behavioral Summary

| Scenario | Before | After |
|---|---|---|
| Enqueue fails (Redis down, etc.) | 500 "Failed to enqueue job for X" | 500 "Failed to submit job to queue for X: {cause}" via TomJobEnqueueError |
| wait=True, wait times out | 500 "Failed to enqueue job for X" (misleading) | 200 with JobResponse showing non-complete status + warning log |
| wait=True, job completes | 200 with JobResponse | 200 with JobResponse (unchanged) |
| wait=False | 200 with QUEUED JobResponse | 200 with QUEUED JobResponse (unchanged) |

## Files to Modify

1. `services/controller/src/tom_controller/exceptions.py` -- add `TomJobEnqueueError`
2. `services/controller/src/tom_controller/api/helpers.py` -- rework `enqueue_job`
3. `services/controller/src/tom_controller/api/device.py` -- update `_execute_device_job`
4. `services/controller/src/tom_controller/api/raw.py` -- update both enqueue call sites
5. `services/controller/src/tom_controller/app.py` -- optionally add explicit handler
6. Endpoint docstrings in `device.py` and `raw.py`
