import logging
import os
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional

from pydantic import BaseModel
from pydantic_settings import SettingsConfigDict
from urllib3 import disable_warnings

from orionsdk import SolarWinds

from tom_controller.Plugins.base import InventoryPlugin, PluginSettings
from tom_controller.config import Settings
from tom_controller.exceptions import TomNotFoundException
from tom_controller.inventory.inventory import DeviceConfig, InventoryFilter

disable_warnings()
log = logging.getLogger(__name__)


class SolarWindsFilter(InventoryFilter):
    """Utility class for filtering SolarWinds nodes based on regex patterns.
    
    This is a convenience wrapper around InventoryFilter that provides named parameters
    for the common SolarWinds fields: Caption, Vendor, and Description.
    """

    def __init__(
        self,
        caption_pattern: Optional[str] = None,
        vendor_pattern: Optional[str] = None,
        description_pattern: Optional[str] = None,
    ):
        """
        Initialize filter with regex patterns for SolarWinds-specific fields.

        :param caption_pattern: Regex pattern to match against node Caption (hostname)
        :param vendor_pattern: Regex pattern to match against node Vendor
        :param description_pattern: Regex pattern to match against node Description (OS/platform)
        """
        field_patterns = {}
        if caption_pattern:
            field_patterns["Caption"] = caption_pattern
        if vendor_pattern:
            field_patterns["Vendor"] = vendor_pattern
        if description_pattern:
            field_patterns["Description"] = description_pattern
        
        super().__init__(field_patterns)

    @classmethod
    def switch_filter(cls) -> "SolarWindsFilter":
        """Pre-configured filter for common switch types."""
        return cls(
            vendor_pattern=r"(dell|arista|cisco)",
            description_pattern=r"(force10|s4048|z9100|DCS-|2960|4500)",
        )

    @classmethod
    def router_filter(cls) -> "SolarWindsFilter":
        """Pre-configured filter for common router types."""
        return cls(vendor_pattern=r"(cisco|juniper)", description_pattern=r"(asr|mx)")

    @classmethod
    def ospf_crawler_filter(cls) -> "SolarWindsFilter":
        """Filter for devices used by ospf_crawler: Cisco ASR, Cisco 29xx, Juniper MX104."""
        return cls(
            vendor_pattern=r"(?i)(cisco|juniper)",
            description_pattern=r"(?i)(asr|29\d{2}|mx104)",
        )

    @classmethod
    def arista_exclusion_filter(cls) -> "SolarWindsFilter":
        """Filter to exclude specific Arista models."""
        return cls(
            vendor_pattern=r"arista",
            description_pattern=r"^(?!.*(DCS-7124SX|DCS-7150S)).*",
        )

    @classmethod
    def iosxe_filter(cls) -> "SolarWindsFilter":
        """Filter for Cisco IOS-XE devices (excludes Nexus, ASA, ISE, and ONS)."""
        return cls(
            vendor_pattern=r"cisco", description_pattern=r"^(?!.*(nexus|asa|ise|ons)).*"
        )


class FilterRegistry:
    """Registry of predefined SolarWinds filters."""

    @staticmethod
    def get_available_filters() -> dict[str, str]:
        """Return dict of filter_name -> description."""
        return {
            "switches": "Common switch types (Dell, Arista, Cisco)",
            "routers": "Common router types (Cisco ASR, Juniper MX)",
            "arista_exclusion": "Arista devices excluding specific models",
            "iosxe": "Cisco IOS-XE devices (excludes Nexus and ASA)",
            "ospf_crawler_filter": "Filter for devices used by ospf_crawler",
        }

    @staticmethod
    def get_filter(filter_name: str) -> SolarWindsFilter:
        """Get a predefined filter by name."""
        filters = {
            "switches": SolarWindsFilter.switch_filter,
            "routers": SolarWindsFilter.router_filter,
            "arista_exclusion": SolarWindsFilter.arista_exclusion_filter,
            "iosxe": SolarWindsFilter.iosxe_filter,
            "ospf_crawler_filter": SolarWindsFilter.ospf_crawler_filter,
        }

        if filter_name not in filters:
            available = ", ".join(filters.keys())
            raise ValueError(f"Unknown filter '{filter_name}'. Available: {available}")

        return filters[filter_name]()


class ModifiedSwisClient(SolarWinds):
    """Extended SolarWinds client with additional query methods."""
    
    def __init__(self, hostname, username, password, *args, port=17774, **kwargs):
        connection_parameters = [hostname, username, password]
        if not all(connection_parameters):
            raise ValueError(
                f"Must provide valid connection parameters for solarwinds.  Got {connection_parameters=} "
            )

        super().__init__(hostname, username, password, *args, port=port, **kwargs)

    @classmethod
    def from_settings(cls, settings: "SolarwindsSettings"):
        log.info(
            f"Creating SolarWinds client for {settings.host}:{settings.port}"
        )
        return cls(
            hostname=settings.host,
            username=settings.username,
            password=settings.password,
            port=settings.port,
        )

    def list_nodes(self, alive_only=True) -> List[Dict]:
        query = """
        SELECT 
            NodeID, IPAddress, Uri, Caption, Description, Status, Vendor, DetailsUrl

        FROM Orion.Nodes n
        """

        if alive_only:
            query += "\nWHERE Status in (1,3)\n"

        log.info(f"Querying SWAPI with query: {query.strip()}")
        try:
            results = self.swis.query(query).get("results", [])
            log.info(f"Got {len(results)} results from SolarWinds")
            return results
        except Exception as e:
            log.error(f"SolarWinds query failed: {e}")
            raise

    def list_switches(self) -> List[Dict]:
        """Return list of switches from SolarWinds."""
        nodes = self.list_nodes()
        switch_filter = SolarWindsFilter.switch_filter()
        return [node for node in nodes if switch_filter.matches(node)]

    def list_routers(self) -> List[Dict]:
        """Return list of routers from SolarWinds."""
        nodes = self.list_nodes()
        router_filter = SolarWindsFilter.router_filter()
        return [node for node in nodes if router_filter.matches(node)]

    def list_filtered_nodes(self, filter_obj: SolarWindsFilter) -> List[Dict]:
        """Return list of nodes matching a custom filter."""
        nodes = self.list_nodes()
        return [node for node in nodes if filter_obj.matches(node)]

    def get_ipsla_nodes(self):
        query = """
        SELECT s.SiteID, s.Name, s.IPAddress, s.NodeID, s.RegionID, n.Caption
        FROM Orion.Nodes n 
         JOIN Orion.IpSla.Sites s ON n.NodeID = s.NodeID
        """
        results = self.swis.query(query)
        return results


class SolarWindsMatchCriteria(BaseModel):
    """Match criteria for SolarWinds devices."""

    vendor: Optional[str] = None
    description: Optional[str] = None
    caption: Optional[str] = None


class SolarWindsDeviceAction(BaseModel):
    """Action to take when a device matches criteria."""

    adapter: str
    adapter_driver: str
    credential_id: Optional[str] = None
    port: int = 22


class SolarWindsMapping(BaseModel):
    """A single match/action rule for SolarWinds devices."""

    match: SolarWindsMatchCriteria
    action: SolarWindsDeviceAction


class SolarwindsSettings(PluginSettings):
    """
    SolarWinds Plugin Settings
    
    Config file uses prefixed keys: plugin_solarwinds_host, plugin_solarwinds_username, etc.
    Env vars use: TOM_PLUGIN_SOLARWINDS_HOST, TOM_PLUGIN_SOLARWINDS_USERNAME, etc.
    Code accesses clean names: settings.host, settings.username, etc.
    
    Precedence: ENVVARS > env_file > yaml_file > defaults
    """
    
    # Clean field names - prefixes are added automatically for config/env lookup
    host: str
    username: str
    password: str
    port: int = 17774
    default_cred_name: str = 'default'  # default cred name attached to solarwinds inventory objects
    device_mappings: list[SolarWindsMapping] = [
        SolarWindsMapping(
            match=SolarWindsMatchCriteria(vendor=".*"),
            action=SolarWindsDeviceAction(
                adapter="netmiko",
                adapter_driver="cisco_ios",
                credential_id="default",
            )
        )
    ]
    
    model_config = SettingsConfigDict(
        env_prefix="TOM_",
        env_file=os.getenv("TOM_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_CONFIG_FILE", "tom_config.yaml"),
        case_sensitive=False,
        extra="forbid",
        plugin_name="solarwinds",  # type: ignore[typeddict-unknown-key]
    )


class SolarWindsInventoryPlugin(InventoryPlugin):
    """SolarWinds SWIS-based inventory plugin."""
    
    name = "solarwinds"
    dependencies = ["orionsdk"]
    settings_class = SolarwindsSettings
    
    def __init__(self, plugin_settings: SolarwindsSettings, main_settings: Settings):
        super().__init__(plugin_settings, main_settings)
        self.settings = plugin_settings
        self.main_settings = main_settings
        self.priority = main_settings.get_inventory_plugin_priority("solarwinds")
        self.nodes: Optional[List[Dict]] = None
        
        # Create SWIS client
        self.swis_client = ModifiedSwisClient.from_settings(plugin_settings)

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
        """Convert SolarWinds node data to DeviceConfig format using configured mappings."""
        # Try each mapping rule in order until we find a match
        for mapping in self.settings.device_mappings:
            # Create a filter from the match criteria
            filter_obj = SolarWindsFilter(
                caption_pattern=mapping.match.caption,
                vendor_pattern=mapping.match.vendor,
                description_pattern=mapping.match.description,
            )

            if filter_obj.matches(node):
                # Use the credential_id from the action, or fall back to default
                credential_id = (
                    mapping.action.credential_id
                    or self.settings.default_cred_name
                )

                return DeviceConfig(
                    adapter=mapping.action.adapter,
                    adapter_driver=mapping.action.adapter_driver,
                    host=node["IPAddress"],
                    port=mapping.action.port,
                    credential_id=credential_id,
                )

        # If no mapping matched, this shouldn't happen with the default ".*" rule
        # But provide a fallback just in case
        return DeviceConfig(
            adapter="netmiko",
            adapter_driver="cisco_ios",
            host=node["IPAddress"],
            port=22,
            credential_id=self.settings.default_cred_name,
        )

    def get_device_config(self, device_name: str) -> DeviceConfig:
        """Find device by Caption (hostname) and return DeviceConfig (sync)."""
        log.info(f"Looking up device: {device_name}")

        if self.nodes is None:
            log.info("Nodes not loaded, loading from SolarWinds...")
            self.nodes = self._load_nodes()

        log.info(f"Searching through {len(self.nodes)} nodes for {device_name}")

        # Create filter to find device by caption (hostname)
        device_filter = SolarWindsFilter(caption_pattern=f"^{re.escape(device_name)}$")

        for node in self.nodes:
            if device_filter.matches(node):
                log.info(f"Found device {device_name}")
                return self._node_to_device_config(node)

        log.warning(f"Device {device_name} not found in inventory")
        raise TomNotFoundException(
            f"Device {device_name} not found in SolarWinds inventory"
        )

    async def aget_device_config(self, device_name: str) -> DeviceConfig:
        """Find device by Caption (hostname) and return DeviceConfig (async)."""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(
                executor, self.get_device_config, device_name
            )

    def list_all_nodes(self) -> list[dict]:
        """Return all nodes from SolarWinds inventory (sync)."""
        if self.nodes is None:
            log.info("Nodes not loaded, loading from SolarWinds...")
            self.nodes = self._load_nodes()
        return self.nodes

    async def alist_all_nodes(self) -> list[dict]:
        """Return all nodes from SolarWinds inventory (async)."""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self.list_all_nodes)

    def get_filterable_fields(self) -> dict[str, str]:
        """Return available fields from SolarWinds for filtering."""
        return {
            "NodeID": "SolarWinds node ID",
            "IPAddress": "Device IP address",
            "Uri": "SolarWinds URI",
            "Caption": "Device hostname",
            "Description": "Device description/OS info",
            "Status": "Node status code",
            "Vendor": "Device vendor",
            "DetailsUrl": "SolarWinds details URL"
        }

    def get_available_filters(self) -> dict[str, str]:
        """Return available named filters for SolarWinds inventory."""
        return FilterRegistry.get_available_filters()

    def get_filter(self, filter_name: str) -> SolarWindsFilter:
        """Get a named SolarWinds filter by name."""
        return FilterRegistry.get_filter(filter_name)
