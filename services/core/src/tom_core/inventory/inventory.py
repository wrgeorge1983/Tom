from typing import Literal, Any, Annotated, Optional

import yaml
from pydantic import BaseModel, Field, RootModel

from tom_core.exceptions import TomException


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


def _get_available_drivers():
    """Get all available drivers from actual adapter implementations"""
    from tom_core.adapters.scrapli_adapter import valid_async_drivers
    from netmiko.ssh_dispatcher import CLASS_MAPPER_BASE

    # Get actual netmiko drivers dynamically
    netmiko_drivers = list(CLASS_MAPPER_BASE.keys())

    return {
        "netmiko": {
            "drivers": sorted(netmiko_drivers),
            "note": "Netmiko drivers (all available drivers)",
        },
        "scrapli": {
            "drivers": sorted(valid_async_drivers.keys()),
            "note": "Scrapli async drivers",
        },
    }


def _dump_available_drivers():
    """Dump available drivers to stdout"""
    drivers = _get_available_drivers()

    print("# Available Adapter Drivers")
    print("# Use these values for 'adapter_driver' field in inventory.yml")
    print()

    for adapter_type, info in drivers.items():
        print(f"## {adapter_type}")
        print(f"# {info['note']}")
        for driver in info["drivers"]:
            print(f"  - {driver}")
        print()


if __name__ == "__main__":
    _dump_available_drivers()
