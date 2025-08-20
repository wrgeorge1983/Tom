import logging
import re
from collections import defaultdict
from typing import List, Dict, Any, DefaultDict, Tuple, Optional
from urllib3 import disable_warnings

from orionsdk import SolarWinds


disable_warnings()
log = logging.getLogger(__name__)


class SolarWindsFilter:
    """Utility class for filtering SolarWinds nodes based on regex patterns."""
    
    def __init__(self, 
                 caption_pattern: Optional[str] = None,
                 vendor_pattern: Optional[str] = None, 
                 description_pattern: Optional[str] = None):
        """
        Initialize filter with regex patterns.
        
        :param caption_pattern: Regex pattern to match against node Caption (hostname)
        :param vendor_pattern: Regex pattern to match against node Vendor
        :param description_pattern: Regex pattern to match against node Description (OS/platform)
        """
        self.caption_regex = re.compile(caption_pattern, re.IGNORECASE) if caption_pattern else None
        self.vendor_regex = re.compile(vendor_pattern, re.IGNORECASE) if vendor_pattern else None
        self.description_regex = re.compile(description_pattern, re.IGNORECASE) if description_pattern else None
    
    def matches(self, node: Dict) -> bool:
        """Check if a node matches all configured filter patterns."""
        if self.caption_regex and not self.caption_regex.search(node.get("Caption", "")):
            return False
        if self.vendor_regex and not self.vendor_regex.search(node.get("Vendor", "")):
            return False
        if self.description_regex and not self.description_regex.search(node.get("Description", "")):
            return False
        return True
    
    @classmethod
    def switch_filter(cls) -> "SolarWindsFilter":
        """Pre-configured filter for common switch types."""
        return cls(
            vendor_pattern=r"(dell|arista|cisco)",
            description_pattern=r"(force10|s4048|z9100|DCS-|2960|4500)"
        )
    
    @classmethod  
    def router_filter(cls) -> "SolarWindsFilter":
        """Pre-configured filter for common router types."""
        return cls(
            vendor_pattern=r"(cisco|juniper)",
            description_pattern=r"(asr|mx)"
        )
    
    @classmethod
    def arista_exclusion_filter(cls) -> "SolarWindsFilter":
        """Filter to exclude specific Arista models."""
        return cls(
            vendor_pattern=r"arista",
            description_pattern=r"^(?!.*(DCS-7124SX|DCS-7150S)).*"
        )
    
    @classmethod
    def iosxe_filter(cls) -> "SolarWindsFilter":
        """Filter for Cisco IOS-XE devices (excludes Nexus, ASA, ISE, and ONS)."""
        return cls(
            vendor_pattern=r"cisco",
            description_pattern=r"^(?!.*(nexus|asa|ise|ons)).*"
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
            "iosxe": "Cisco IOS-XE devices (excludes Nexus and ASA)"
        }
    
    @staticmethod
    def get_filter(filter_name: str) -> SolarWindsFilter:
        """Get a predefined filter by name."""
        filters = {
            "switches": SolarWindsFilter.switch_filter,
            "routers": SolarWindsFilter.router_filter,
            "arista_exclusion": SolarWindsFilter.arista_exclusion_filter,
            "iosxe": SolarWindsFilter.iosxe_filter
        }
        
        if filter_name not in filters:
            available = ", ".join(filters.keys())
            raise ValueError(f"Unknown filter '{filter_name}'. Available: {available}")
        
        return filters[filter_name]()


class ModifiedSwisClient(SolarWinds):
    def __init__(self, hostname, username, password, *args, port=17774, **kwargs):
        connection_parameters = [hostname, username, password]
        if not all(connection_parameters):
            raise ValueError(
                f"Must provide valid connection parameters for solarwinds.  Got {connection_parameters=} "
            )

        super().__init__(hostname, username, password, *args, port=port, **kwargs)

    @classmethod
    def from_settings(cls, settings):
        log.info(f"Creating SolarWinds client for {settings.swapi_host}:{settings.swapi_port}")
        return cls(
            hostname=settings.swapi_host,
            username=settings.swapi_username,
            password=settings.swapi_password,
            port=settings.swapi_port,
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
        query = f"""
        SELECT s.SiteID, s.Name, s.IPAddress, s.NodeID, s.RegionID, n.Caption
        FROM Orion.Nodes n 
         JOIN Orion.IpSla.Sites s ON n.NodeID = s.NodeID
        """
        results = self.swis.query(query)
        return results


    def test(self):
        query = """
            SELECT TOP 1 NodeID
            FROM Orion.Nodes
        """
        log.info(f"Querying SWAPI...")
        import requests

        try:
            results = self.swis.query(query).get("results", [])
        except (AttributeError, requests.RequestException):
            return False
        return bool(results)  # empty results here also counts as failure




