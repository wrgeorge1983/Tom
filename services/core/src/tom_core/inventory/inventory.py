from typing import Literal, Any, Annotated, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor

import yaml
from pydantic import BaseModel, Field, RootModel

from tom_core.exceptions import TomNotFoundException

import logging

log = logging.getLogger(__name__)


class DeviceConfig(BaseModel):
    adapter: Literal["netmiko", "scrapli"]
    adapter_driver: str
    adapter_options: dict[str, Any] = {}
    host: str
    port: int = 22
    credential_id: str


# these models are just for documentation purposes, they are not used in the code
class SchemaNetmikoDevice(DeviceConfig):
    adapter: Literal["netmiko"] = "netmiko"
    adapter_driver: Literal[
        "cisco_ios", "cisco_nxos", "arista_eos", "juniper_junos", "etc..."
    ]
    adapter_options: dict[str, Any] = {}


class SchemaScrapliDevice(DeviceConfig):
    adapter: Literal["scrapli"] = "scrapli"
    adapter_driver: Literal[
        "cisco_iosxe", "cisco_nxos", "cisco_iosxr", "arista_eos", "etc...."
    ]
    adapter_options: dict[str, Any] = {}


SchemaDeviceConfig = Annotated[
    SchemaNetmikoDevice | SchemaScrapliDevice, Field(discriminator="adapter")
]


# Wrapper model for schema generation
class InventorySchema(RootModel[dict[str, SchemaDeviceConfig]]):
    """Schema for inventory.yml - devices at root level"""

    root: dict[str, SchemaDeviceConfig] = Field(
        ..., description="Device configurations keyed by device name"
    )


class InventoryStore:
    def get_device_config(self, device_name: str) -> DeviceConfig:
        raise NotImplementedError

    async def aget_device_config(self, device_name: str) -> DeviceConfig:
        """Async version of get_device_config - default implementation calls sync version in threadpool."""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(
                executor, self.get_device_config, device_name
            )

    def list_all_nodes(self) -> list[dict]:
        """Return all nodes from inventory."""
        raise NotImplementedError

    async def alist_all_nodes(self) -> list[dict]:
        """Async version of list_all_nodes."""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self.list_all_nodes)


class YamlInventoryStore(InventoryStore):
    data: Optional[dict] = None

    def __init__(self, filename: str):
        self.filename = filename
        with open(filename, "r") as f:
            self.data = yaml.safe_load(f)

    def get_device_config(self, device_name: str) -> DeviceConfig:
        if device_name not in self.data:
            raise TomNotFoundException(
                f"Device {device_name} not found in {self.filename}"
            )

        return DeviceConfig(**self.data[device_name])

    def list_all_nodes(self) -> list[dict]:
        """Return all nodes from YAML inventory as raw dict format."""
        return [{"Caption": name, **config} for name, config in self.data.items()]
