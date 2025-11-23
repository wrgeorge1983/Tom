from typing import Literal, Any, Dict
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re

from pydantic import BaseModel

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
    def __init__(self):
        self.priority = 1000

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

    def get_available_filters(self) -> dict[str, str]:
        """Return dict of filter_name -> description for named filters.
        
        Default implementation returns empty dict (no named filters).
        Inventory implementations can override to provide preset filters.
        """
        return {}

    def get_filter(self, filter_name: str) -> InventoryFilter:
        """Get a named filter by name.
        
        Default implementation raises ValueError since base class has no filters.
        Inventory implementations can override to provide preset filters.
        
        :param filter_name: Name of the filter to retrieve
        :return: InventoryFilter instance
        :raises ValueError: If filter_name is not available
        """
        available = list(self.get_available_filters().keys())
        if available:
            raise ValueError(
                f"Unknown filter '{filter_name}'. Available: {', '.join(available)}"
            )
        else:
            raise ValueError(
                f"Named filters are not supported by this inventory source. "
                f"Use inline filters with query parameters instead."
            )


class InventoryService:
    def __init__(self):
        self._inventory_stores: list[InventoryStore] = []

    def add_inventory_store(self, store: InventoryStore):
        self._inventory_stores.append(store)
        self._inventory_stores.sort(key=lambda store: store.priority)

    @property
    def default_inventory_store(self) -> InventoryStore:
        return self._inventory_stores[0]

    @property
    def inventory_stores(self) -> list[InventoryStore]:
        return self._inventory_stores

    def get_device_config(self, device_name: str) -> DeviceConfig:
        for store in self._inventory_stores:
            try:
                return store.get_device_config(device_name)
            except KeyError:
                continue
        raise KeyError(f"Device '{device_name}' not found in any inventory sources")

    async def alist_all_nodes(self) -> list[dict]:
        """List all nodes from all inventory sources."""
        results = []
        for store in self._inventory_stores:
            results.extend(await store.alist_all_nodes())
        return results

    def list_all_nodes(self) -> list[dict]:
        """List all nodes from all inventory sources."""
        results = []
        for store in self._inventory_stores:
            results.extend(store.list_all_nodes())
        return results



