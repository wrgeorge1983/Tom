from typing import Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import yaml

from tom_controller.Plugins import InventoryPlugin
from tom_controller.config import Settings
from tom_controller.exceptions import TomNotFoundException
from tom_controller.inventory.inventory import DeviceConfig


class YamlInventoryPlugin(InventoryPlugin):
    """YAML file-based inventory plugin."""
    
    name = "yaml"
    dependencies = []  # No external dependencies
    
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.settings = settings
        self.filename = settings.inventory_path
        self.data: Optional[dict] = None
        self.priority = settings.get_inventory_plugin_priority("yaml")
        
        with open(self.filename, "r") as f:
            self.data = yaml.safe_load(f)
    
    def get_device_config(self, device_name: str) -> DeviceConfig:
        """Get device configuration from YAML inventory (sync version)."""
        if self.data is None:
            raise TomNotFoundException("YAML inventory not loaded")
        
        if device_name not in self.data:
            raise TomNotFoundException(
                f"Device {device_name} not found in {self.filename}"
            )
        
        return DeviceConfig(**self.data[device_name])
    
    async def aget_device_config(self, device_name: str) -> DeviceConfig:
        """Get device configuration from YAML inventory (async version)."""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(
                executor, self.get_device_config, device_name
            )
    
    def list_all_nodes(self) -> list[dict]:
        """Return all nodes from YAML inventory (sync version)."""
        if self.data is None:
            return []
        
        return [{"Caption": name, **config} for name, config in self.data.items()]
    
    async def alist_all_nodes(self) -> list[dict]:
        """Return all nodes from YAML inventory (async version)."""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self.list_all_nodes)
    
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
    
    def get_available_filters(self) -> dict[str, str]:
        """Return dict of filter_name -> description for named filters."""
        return {}
    
    def _node_to_device_config(self, node: dict) -> DeviceConfig:
        """Convert node dict to DeviceConfig."""
        return DeviceConfig(**node)
