import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
import saq

from shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel
from tom_core.exceptions import TomException
from tom_core.inventory.inventory import (
    InventoryStore,
    DeviceConfig,
)

router = APIRouter()


def get_inventory_store(request: Request) -> InventoryStore:
    return request.app.state.inventory_store


class JobResponse(BaseModel):
    job_id: str
    status: Literal["NEW", "QUEUED", "ACTIVE", "COMPLETE", "FAILED", "ABORTED"]
    result: Optional[str | dict] = None

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


async def enqueue_job(
    queue: saq.Queue,
    function_name: str,
    args: BaseModel,
    wait: bool = False,
    timeout: int = 10,
) -> JobResponse:
    job = await queue.enqueue(
        function_name, timeout=timeout, json=args.model_dump_json()
    )
    if wait:
        await job.refresh(until_complete=float(timeout))

    job_response = JobResponse.from_job(job)
    return job_response


@router.get("/")
async def root():
    return {"message": "Hello World"}


@router.get("/foo")
async def foo(request: Request) -> JobResponse:
    queue: saq.Queue = request.app.state.queue
    return JobResponse.from_job(job)


@router.get("/job/{job_id}")
async def job(request: Request, job_id: str) -> JobResponse:
    queue: saq.Queue = request.app.state.queue
    return await JobResponse.from_job_id(job_id, queue)


@router.get("/raw/send_netmiko_command")
async def send_netmiko_command(
    request: Request,
    host: str,
    device_type: str,
    command: str,
    credential_id: str,
    port: int = 22,
    wait: bool = False,
) -> JobResponse:
    queue = request.app.state.queue

    args = NetmikoSendCommandModel(
        host=host,
        device_type=device_type,
        command=command,
        credential_id=credential_id,
        port=port,
    )
    return await enqueue_job(queue, "send_command_netmiko", args, wait=wait)


@router.get("/raw/send_scrapli_command")
async def send_scrapli_command(
    request: Request,
    host: str,
    device_type: str,
    command: str,
    credential_id: str,
    port: int = 22,
    wait: bool = False,
) -> JobResponse:
    queue = request.app.state.queue

    args = ScrapliSendCommandModel(
        host=host,
        device_type=device_type,
        command=command,
        credential_id=credential_id,
        port=port,
    )
    return await enqueue_job(queue, "send_command_scrapli", args, wait=wait)


@router.get("/inventory/{device_name}")
async def inventory(
    device_name: str, inventory_store: InventoryStore = Depends(get_inventory_store)
) -> DeviceConfig:
    return inventory_store.get_device_config(device_name)


@router.get("/device/{device_name}/send_command")
async def send_inventory_command(
    request: Request,
    device_name: str,
    command: str,
    inventory_store: InventoryStore = Depends(get_inventory_store),
    wait: bool = False,
    timeout: int = 10,
) -> JobResponse:
    device_config = inventory_store.get_device_config(device_name)

    queue: saq.Queue = request.app.state.queue

    if device_config.adapter == "netmiko":
        args = NetmikoSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            command=command,
            credential_id=device_config.credential_id,
            port=device_config.port,
        )
        response = await enqueue_job(
            queue, "send_command_netmiko", args, wait=wait, timeout=timeout
        )

    elif device_config.adapter == "scrapli":
        args = ScrapliSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            command=command,
            credential_id=device_config.credential_id,
            port=device_config.port,
        )
        response = await enqueue_job(
            queue, "send_command_scrapli", args, wait=wait, timeout=timeout
        )

    else:
        raise TomException(f"Unknown device type {type(device_config)}")

    return response
