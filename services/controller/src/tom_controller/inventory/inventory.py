from typing import Literal, Any, Annotated, Optional, Dict
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re

import yaml
from pydantic import BaseModel, Field, RootModel

from tom_controller.exceptions import TomNotFoundException

import logging

log = logging.getLogger(__name__)


class InventoryFilter:
    """Generic filter for inventory nodes using regex patterns on any field."""
    
    def __init__(self, field_patterns: Dict[str, str]):
        """
        Initialize filter with field->regex pattern mappings.
        
        :param field_patterns: Dict mapping field names to regex patterns
        """
        self.filters = {}
        for field, pattern in field_patterns.items():
            if pattern:  # Only compile non-empty patterns
                try:
                    self.filters[field] = re.compile(pattern, re.IGNORECASE)
                except re.error as e:
                    log.warning(f"Invalid regex pattern for field {field}: {pattern} - {e}")
                    raise ValueError(f"Invalid regex pattern for field '{field}': {e}")
    
    def matches(self, node: Dict) -> bool:
        """Check if a node matches all configured filter patterns."""
        for field, regex in self.filters.items():
            value = node.get(field, "")
            if not regex.search(str(value)):
                return False
        return True


class DeviceConfig(BaseModel):
    adapter: Literal["netmiko", "scrapli"]
    adapter_driver: str
    adapter_options: dict[str, Any] = {}
    host: str
    port: int = 22
    credential_id: str


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

    def get_filterable_fields(self) -> dict[str, str]:
        """Return dict of field_name -> description for fields that can be filtered on."""
        raise NotImplementedError


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

    def get_filterable_fields(self) -> dict[str, str]:
        """Return available fields for YAML inventory filtering."""
        return {
            "Caption": "Device name (key in YAML)",
            "host": "IP address or hostname",
            "adapter": "Network adapter (netmiko or scrapli)",
            "adapter_driver": "Driver type (cisco_ios, arista_eos, etc.)",
            "credential_id": "Credential reference",
            "port": "SSH/Telnet port number"
        }
