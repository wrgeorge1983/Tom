"""Nautobot inventory plugin for Tom."""

import os
from typing import Literal, Optional, cast

from pydantic_settings import SettingsConfigDict

from tom_controller.Plugins.base import InventoryPlugin, PluginSettings
from tom_controller.config import Settings
from tom_controller.exceptions import TomNotFoundException
from tom_controller.inventory.inventory import DeviceConfig


class NautobotSettings(PluginSettings):
    """
    Nautobot Plugin Settings

    Config file uses: plugin_nautobot_url, plugin_nautobot_token, etc.
    Env vars use: TOM_PLUGIN_NAUTOBOT_URL, TOM_PLUGIN_NAUTOBOT_TOKEN, etc.
    Code accesses: settings.url, settings.token, etc.

    Supports two credential mapping strategies:
    1. Custom Field: Direct field on device (recommended, simpler)
    2. Config Context: Hierarchical JSON data (more complex, more flexible)
    """

    # Connection
    url: str
    token: str

    # Credential mapping - choose source
    credential_source: Literal["custom_field", "config_context"] = "custom_field"

    # For custom_field source
    credential_field: str = "credential_id"

    # For config_context source (can be nested like "tom.credentials.ssh")
    credential_context_path: str = "credential_id"

    # Default credential ID
    credential_default: str = "default"

    # Optional filters - use names as they appear in Nautobot
    # Leave empty to disable filtering
    status_filter: list[str] = []  # e.g., ["Active", "Planned"]
    role_filter: list[str] = []  # e.g., ["Edge Router", "Core Switch"]
    location_filter: list[str] = []  # e.g., ["NYC-DC1", "SFO-DC2"]
    tag_filter: list[str] = []  # e.g., ["production", "tom-managed"]

    # Defaults when platform's netmiko_device_type is not set
    default_adapter: Literal["netmiko", "scrapli"] = "netmiko"
    default_driver: str = "cisco_ios"

    model_config = SettingsConfigDict(
        env_prefix="TOM_",
        env_file=os.getenv("TOM_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_CONFIG_FILE", "tom_config.yaml"),
        case_sensitive=False,
        extra="forbid",
        plugin_name="nautobot",  # type: ignore[typeddict-unknown-key]
    )


class NautobotInventoryPlugin(InventoryPlugin):
    """Nautobot-based inventory plugin using pynautobot."""

    name = "nautobot"
    dependencies = ["pynautobot"]
    settings_class = NautobotSettings

    def __init__(self, plugin_settings: NautobotSettings, main_settings: Settings):
        super().__init__(plugin_settings, main_settings)
        self.settings = plugin_settings
        self.main_settings = main_settings
        self.priority = main_settings.get_inventory_plugin_priority("nautobot")

        # Initialize pynautobot client
        import pynautobot

        self.nb = pynautobot.api(url=plugin_settings.url, token=plugin_settings.token)

    def _get_credential_id(self, device) -> str:
        """
        Extract credential ID from device based on configured source.

        Supports:
        - custom_field: Direct field like device.custom_fields.credential_id
        - config_context: Nested JSON like device.config_context.tom.credential_id
        """
        if self.settings.credential_source == "custom_field":
            value = device.custom_fields.get(
                self.settings.credential_field, self.settings.credential_default
            )
            # Return value if it's a non-empty string, otherwise use default
            if isinstance(value, str) and value:
                return value
            return self.settings.credential_default
        elif self.settings.credential_source == "config_context":
            # Navigate nested config context path
            context = device.config_context
            for key in self.settings.credential_context_path.split("."):
                if isinstance(context, dict):
                    context = context.get(key, {})
                else:
                    context = {}
                    break

            # If we got a string, use it; otherwise use default
            if isinstance(context, str) and context:
                return context
            return self.settings.credential_default

        return self.settings.credential_default

    def _determine_adapter_and_driver(self, device) -> tuple[str, str]:
        """
        Determine adapter (netmiko/scrapli) and driver from device platform.

        Uses platform's built-in netmiko_device_type field if set,
        otherwise falls back to configured defaults.
        """
        if not device.platform:
            return (self.settings.default_adapter, self.settings.default_driver)

        # Use Nautobot's built-in netmiko_device_type field
        if (
            hasattr(device.platform, "netmiko_device_type")
            and device.platform.netmiko_device_type
        ):
            return (self.settings.default_adapter, device.platform.netmiko_device_type)

        return (self.settings.default_adapter, self.settings.default_driver)

    def _get_host_ip(self, device) -> str:
        """
        Extract host IP from device.

        Tries primary_ip4, then primary_ip6, falls back to device name.
        Strips /prefix notation from IPs.
        """
        if hasattr(device, "primary_ip4") and device.primary_ip4:
            # primary_ip4 is an object with .address attribute
            address = str(device.primary_ip4.address)
            return address.split("/")[0]

        if hasattr(device, "primary_ip6") and device.primary_ip6:
            address = str(device.primary_ip6.address)
            return address.split("/")[0]

        # Fallback to device name
        return device.name

    def _device_to_config(self, device) -> DeviceConfig:
        """Convert Nautobot device record to Tom DeviceConfig."""
        adapter, driver = self._determine_adapter_and_driver(device)

        return DeviceConfig(
            adapter=cast(Literal["netmiko", "scrapli"], adapter),
            adapter_driver=driver,
            host=self._get_host_ip(device),
            port=22,  # Could make configurable later
            credential_id=self._get_credential_id(device),
        )

    def _build_filter_params(self) -> dict:
        """Build query filter parameters from settings."""
        filters = {}

        if self.settings.status_filter:
            filters["status"] = self.settings.status_filter

        if self.settings.role_filter:
            filters["role"] = self.settings.role_filter

        if self.settings.location_filter:
            filters["location"] = self.settings.location_filter

        if self.settings.tag_filter:
            filters["tag"] = self.settings.tag_filter

        return filters

    def get_device(self, device_id: str) -> DeviceConfig | None:
        """
        Retrieve a single device by name from Nautobot.

        Returns None if device not found.
        """
        try:
            # Need to include config_context if using that source
            include = []
            if self.settings.credential_source == "config_context":
                include.append("config_context")

            include_param = ",".join(include) if include else None

            device = self.nb.dcim.devices.get(name=device_id, include=include_param)

            if not device:
                return None

            return self._device_to_config(device)

        except Exception as e:
            # Log error but don't crash
            print(f"Error fetching device {device_id} from Nautobot: {e}")
            return None

    def get_devices(
        self, filter_name: str | None = None
    ) -> list[tuple[str, DeviceConfig]]:
        """
        Retrieve all devices from Nautobot matching configured filters.

        Returns list of (device_name, DeviceConfig) tuples to preserve device names.
        filter_name parameter is ignored for now (could implement named filters later).
        """
        try:
            # Build filters from settings
            filters = self._build_filter_params()

            # Need to include config_context if using that source
            include = []
            if self.settings.credential_source == "config_context":
                include.append("config_context")

            include_param = ",".join(include) if include else None

            # Fetch all devices matching filters
            devices = self.nb.dcim.devices.filter(include=include_param, **filters)

            # Convert to (name, DeviceConfig) tuples to preserve device names
            return [
                (str(device.name), self._device_to_config(device)) for device in devices
            ]  # pyright: ignore [reportAttributeAccessIssue]

        except Exception as e:
            print(f"Error fetching devices from Nautobot: {e}")
            if "400" in str(e):
                print(
                    "Check your filter configuration (status/role/location/tag) - values must match what exists in your Nautobot instance, or set to [] to disable filtering."
                )
            return []

    # Implement abstract methods from InventoryPlugin

    def get_device_config(self, device_name: str):
        """Get configuration for a specific device (sync)."""
        return self.get_device(device_name)

    async def aget_device_config(self, device_name: str):
        """Get configuration for a specific device (async)."""
        # For now, wrap sync method (could use async pynautobot later)
        import asyncio

        return await asyncio.to_thread(self.get_device, device_name)

    def list_all_nodes(self) -> list[dict]:
        """Return all nodes from inventory (sync)."""
        try:
            # Build filters from settings
            filters = self._build_filter_params()

            # Need to include config_context if using that source
            include = []
            if self.settings.credential_source == "config_context":
                include.append("config_context")

            include_param = ",".join(include) if include else None

            # Fetch all devices matching filters - pynautobot returns list of Record objects
            devices = self.nb.dcim.devices.filter(include=include_param, **filters)

            # Convert to dict list, preserving device name as Caption
            result = []
            for device in devices:
                adapter, driver = self._determine_adapter_and_driver(device)
                result.append(
                    {
                        "Caption": device.name,  # pyright: ignore [reportAttributeAccessIssue]
                        "adapter": adapter,
                        "adapter_driver": driver,
                        "host": self._get_host_ip(device),
                        "port": 22,
                        "credential_id": self._get_credential_id(device),
                        "adapter_options": {},
                    }
                )

            return result

        except Exception as e:
            print(f"Error fetching devices from Nautobot: {e}")
            if "400" in str(e):
                print(
                    "Check your filter configuration (status/role/location/tag) - values must match what exists in your Nautobot instance, or set to [] to disable filtering."
                )
            return []

    async def alist_all_nodes(self) -> list[dict]:
        """Return all nodes from inventory (async)."""
        import asyncio

        return await asyncio.to_thread(self.list_all_nodes)

    def get_filterable_fields(self) -> dict[str, str]:
        """Return dict of field_name -> description for fields that can be filtered on."""
        return {
            "status": "Device status (e.g., active, staged)",
            "role": "Device role/function",
            "location": "Device location",
            "tag": "Device tags",
        }
