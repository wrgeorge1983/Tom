from typing import Optional

import yaml

from tom_controller.config import Settings
from tom_controller.exceptions import TomNotFoundException
from tom_controller.inventory.inventory import InventoryStore, DeviceConfig


class YamlInventoryStore(InventoryStore):
    data: Optional[dict] = None

    def __init__(self, filename: str, settings: Settings):
        self.settings = settings
        self.priority = settings.get_inventory_plugin_priority("yaml")
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
