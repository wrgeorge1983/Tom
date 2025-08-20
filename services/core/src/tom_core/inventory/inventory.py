from typing import Literal, Any, Annotated, Optional
import asyncio
import re
from concurrent.futures import ThreadPoolExecutor

import yaml
from pydantic import BaseModel, Field, RootModel

from tom_core.exceptions import TomException

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
            return await loop.run_in_executor(executor, self.get_device_config, device_name)
    
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
            raise TomException(f"Device {device_name} not found in {self.filename}")

        return DeviceConfig(**self.data[device_name])
    
    def list_all_nodes(self) -> list[dict]:
        """Return all nodes from YAML inventory as raw dict format."""
        return [{"Caption": name, **config} for name, config in self.data.items()]


class SwisInventoryStore(InventoryStore):
    def __init__(self, swis_client, settings):
        self.swis_client = swis_client
        self.settings = settings
        self.nodes = None
    
    def _load_nodes(self) -> list[dict]:
        """Load all nodes from SolarWinds on startup."""
        log.info("Starting SolarWinds node loading...")
        try:
            nodes = self.swis_client.list_nodes()
            log.info(f"Successfully loaded {len(nodes)} nodes from SolarWinds")
            return nodes
        except Exception as e:
            log.error(f"Failed to load nodes from SolarWinds: {e}")
            raise
    
    def _node_to_device_config(self, node: dict) -> DeviceConfig:
        """Convert SolarWinds node data to DeviceConfig format."""
        # TODO: Add proper mapping logic based on vendor/description
        # For now, default to netmiko cisco_ios
        return DeviceConfig(
            adapter="netmiko",
            adapter_driver="cisco_ios", 
            host=node["IPAddress"],
            port=22,
            credential_id=self.settings.swapi_default_cred_name
        )
    
    def get_device_config(self, device_name: str) -> DeviceConfig:
        """Find device by Caption (hostname) and return DeviceConfig."""
        log.info(f"Looking up device: {device_name}")
        
        if self.nodes is None:
            log.info("Nodes not loaded, loading from SolarWinds...")
            self.nodes = self._load_nodes()
            
        log.info(f"Searching through {len(self.nodes)} nodes for {device_name}")
        
        # Create filter to find device by caption (hostname)
        from tom_core.inventory.solarwinds import SolarWindsFilter
        device_filter = SolarWindsFilter(caption_pattern=f"^{re.escape(device_name)}$")
        
        for node in self.nodes:
            if device_filter.matches(node):
                log.info(f"Found device {device_name}")
                return self._node_to_device_config(node)
        
        log.warning(f"Device {device_name} not found in inventory")
        raise TomException(f"Device {device_name} not found in SolarWinds inventory")
    
    def list_all_nodes(self) -> list[dict]:
        """Return all nodes from SolarWinds inventory."""
        if self.nodes is None:
            log.info("Nodes not loaded, loading from SolarWinds...")
            self.nodes = self._load_nodes()
        return self.nodes
