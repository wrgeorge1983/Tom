from typing import Optional
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import yaml

from pydantic_settings import SettingsConfigDict

from tom_controller.Plugins.base import InventoryPlugin, PluginSettings
from tom_controller.config import Settings
from tom_controller.exceptions import TomNotFoundException
from tom_controller.inventory.inventory import DeviceConfig


class YamlSettings(PluginSettings):
    """
    YAML Plugin Settings
    
    Config file uses prefixed keys: plugin_yaml_inventory_file
    Env vars use: TOM_PLUGIN_YAML_INVENTORY_FILE
    Code accesses clean names: settings.inventory_file
    
    Note: Uses project_root from main Settings (not duplicated)
    
    Precedence: ENVVARS > env_file > yaml_file > defaults
    """
    
    # Clean field names - prefixes are added automatically for config/env lookup
    inventory_file: str = "defaultInventory.yml"
    
    model_config = SettingsConfigDict(
        env_prefix="TOM_",
        env_file=os.getenv("TOM_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_CONFIG_FILE", "tom_config.yaml"),
        case_sensitive=False,
        extra="forbid",
        plugin_name="yaml",  # type: ignore[typeddict-unknown-key]
    )


class YamlInventoryPlugin(InventoryPlugin):
    """YAML file-based inventory plugin."""
    
    name = "yaml"
    dependencies = []  # No external dependencies
    settings_class = YamlSettings
    
    def __init__(self, plugin_settings: YamlSettings, main_settings: Settings):
        super().__init__(plugin_settings, main_settings)
        self.settings = plugin_settings
        self.main_settings = main_settings
        # Compute inventory path using main_settings.project_root (no duplication)
        self.filename = str(Path(main_settings.project_root) / plugin_settings.inventory_file)
        self.data: Optional[dict] = None
        self.priority = main_settings.get_inventory_plugin_priority("yaml")
        
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
