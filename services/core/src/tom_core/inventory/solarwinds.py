import logging
from collections import defaultdict
from typing import List, Dict, Any, DefaultDict, Tuple
from urllib3 import disable_warnings

from orionsdk import SolarWinds, SwisClient


disable_warnings()
log = logging.getLogger(__name__)


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
        # TODO: Add SolarWinds configuration to Settings class
        # For now, this method is a placeholder
        raise NotImplementedError("SolarWinds configuration not yet implemented in Settings")

    def get_nodes(
        self, keys: List[str] = ("NodeID", "Caption"), node_filter: str = None
    ):
        select_columns = ", ".join(f"n.{key}" for key in keys)
        if node_filter is None:
            node_filter = ""

        query = f"""
        SELECT {select_columns}

        FROM Orion.Nodes n
        {node_filter}
        """
        results = self.swis.query(query)
        return results

    def get_ipsla_nodes(self):
        query = f"""
        SELECT s.SiteID, s.Name, s.IPAddress, s.NodeID, s.RegionID, n.Caption
        FROM Orion.Nodes n 
         JOIN Orion.IpSla.Sites s ON n.NodeID = s.NodeID
        """
        results = self.swis.query(query)
        return results

    def query(self):
        pass

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


def list_nodes(hostname: str, username: str, password: str, alive_only=True) -> List[Dict]:
    client = SwisClient(
        hostname=hostname,
        username=username,
        password=password,
        port=17774,
    )
    rtr_query = """
    SELECT 
        NodeID, IPAddress, Uri, Caption, Description, Status, Vendor, DetailsUrl

    FROM Orion.Nodes n
    """

    if (
        alive_only
    ):  # only get nodes in 'UP' or 'WARNING' states, assume if Solarwinds can't reach/poll, neither can we.
        rtr_query += "\nWHERE Status in (1,3)\n"

    log.info(f"Querying SWAPI...")
    results = client.query(rtr_query).get("results", [])
    log.info(f" got {len(results)} results.")
    return results


def list_switches(hostname: str, username: str, password: str) -> List[Dict]:
    """
    :param hostname: SolarWinds hostname
    :param username: SolarWinds username  
    :param password: SolarWinds password
    :return: List of Dicts representing switches in SolarWinds
    """
    sw_nodes = list_nodes(hostname, username, password)
    return [sw_node for sw_node in sw_nodes if node_is_switch(sw_node)]


def list_routers(hostname: str, username: str, password: str) -> List[Dict]:
    """
    :param hostname: SolarWinds hostname
    :param username: SolarWinds username
    :param password: SolarWinds password  
    :return: List of Dicts representing routers in SolarWinds
    """
    sw_nodes = list_nodes(hostname, username, password)
    return [sw_node for sw_node in sw_nodes if node_is_router(sw_node)]


def node_is_arista(sw_node: Dict) -> bool:
    return "arista" in sw_node["Vendor"].lower() and (
        "DCS-7124SX" not in sw_node["Description"] and
        "DCS-7150S" not in sw_node["Description"]
    )


def node_is_force10(sw_node: Dict) -> bool:
    vendor, description = sw_node["Vendor"].lower(), sw_node["Description"].lower()
    # log.info(f'considering {vendor=}, {description=}')
    return "dell" in vendor and (
        "force10" in description or "s4048" in description or "z9100" in description
    )


def node_is_cisco_switch(sw_node: Dict) -> bool:
    vendor, description = sw_node["Vendor"].lower(), sw_node["Description"].lower()
    # log.info(f'considering {vendor=}, {description=}')
    return "cisco" in vendor and ("2960" in description or "4500" in description)


def node_is_cisco_router(sw_node: Dict) -> bool:
    vendor, description = sw_node["Vendor"].lower(), sw_node["Description"].lower()
    # log.info(f'considering {vendor=}, {description=}')
    return "cisco" in vendor and "asr" in description


def node_is_juniper_router(sw_node: Dict) -> bool:
    vendor, description = sw_node["Vendor"].lower(), sw_node["Description"].lower()
    # log.info(f'considering {vendor=}, {description=}')
    return "juniper" in vendor and "mx" in description


def node_is_switch(sw_node: Dict) -> bool:
    tests = [node_is_force10, node_is_arista, node_is_cisco_switch]
    return any(test(sw_node) for test in tests)


def node_is_router(sw_node: Dict) -> bool:
    tests = [node_is_juniper_router, node_is_cisco_router]
    return any(test(sw_node) for test in tests)


def get_solarwinds_vlans(hostname: str, username: str, password: str) -> DefaultDict[Any, list]:
    sw_client = ModifiedSwisClient(hostname, username, password)

    query = """
    SELECT NodeID, VlanId, VlanName, DisplayName, vlan.node.Caption, vlan.node.DetailsUrl, vlan.node.Description, vlan.node.Vendor
    FROM Orion.NodeVlans vlan
    """
    raw_vlan_data = sw_client.swis.query(query)["results"]

    data = defaultdict(list)

    for row in raw_vlan_data:
        v = data[str(row["VlanId"])]
        if node_is_switch(row):
            v.append({"hostname": row["Caption"], "name": row["DisplayName"]})

    return data
