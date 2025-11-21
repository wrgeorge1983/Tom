from abc import ABC, abstractmethod
import importlib
from logging import getLogger

from tom_controller.config import Settings

logger = getLogger(__name__)


class TomPlugin(ABC):
    @abstractmethod
    def __init__(self, settings: Settings):
        """Plugins must take a Settings object and should find their config from there"""
        pass

    name: str
    dependencies: list[str] = []


class InventoryPlugin(TomPlugin):
    """Base class for inventory plugins.
    
    Provides same interface as old InventoryStore for compatibility.
    """
    
    priority: int = 1000
    
    @abstractmethod
    def get_device_config(self, device_name: str):
        """Get configuration for a specific device (sync)."""
        pass
    
    @abstractmethod
    async def aget_device_config(self, device_name: str):
        """Get configuration for a specific device (async)."""
        pass
    
    @abstractmethod
    def list_all_nodes(self) -> list[dict]:
        """Return all nodes from inventory (sync)."""
        pass
    
    @abstractmethod
    async def alist_all_nodes(self) -> list[dict]:
        """Return all nodes from inventory (async)."""
        pass
    
    @abstractmethod
    def get_filterable_fields(self) -> dict[str, str]:
        """Return dict of field_name -> description for fields that can be filtered on."""
        pass
    
    def get_available_filters(self) -> dict[str, str]:
        """Return dict of filter_name -> description for named filters.
        
        Default implementation returns empty dict.
        """
        return {}
    
    def get_filter(self, filter_name: str):
        """Get a named filter by name.
        
        Default implementation raises ValueError.
        """
        available = list(self.get_available_filters().keys())
        if available:
            raise ValueError(
                f"Unknown filter '{filter_name}'. Available: {', '.join(available)}"
            )
        else:
            raise ValueError(
                f"Named filters are not supported by this inventory source."
            )

class PluginManager:

    def __init__(self):
        self._plugins: dict[str, type[TomPlugin]] = {}
        self._inventory_plugins: dict[str, type[InventoryPlugin]] = {}

    @property
    def inventory_plugin_names(self):
        plugin_names = list(self._inventory_plugins.keys())
        return plugin_names

    def _register_inventory_plugin(self, plugin_class: type[InventoryPlugin]):
        name = plugin_class.name
        dependencies = plugin_class.dependencies
        missing_deps = []
        for pkg in dependencies:
            try:
                importlib.import_module(pkg)
            except (ImportError, ModuleNotFoundError):
                missing_deps.append(pkg)

        if missing_deps:
            logger.error(f"Cannot load inventory plugin {name} because it depends on missing packages: {missing_deps}")
            return

        self._inventory_plugins[name] = plugin_class

        logger.info(f"Registered inventory plugin {name}")

    def _find_plugin_class_in_module(self, module) -> type[InventoryPlugin]:
        for name in dir(module):
            obj = getattr(module, name)
            if (isinstance(obj, type) and issubclass(obj, InventoryPlugin) and obj is not InventoryPlugin):
                return obj
        raise ValueError("No InventoryPlugin subclass found in module")

    def discover_plugins(self, settings: Settings):
        for plugin_name in settings.inventory_plugins:
            try:
                module = importlib.import_module(f'tom_controller.Plugins.inventory.{plugin_name}')
            except (ImportError, ModuleNotFoundError):
                logger.error(f"Cannot load inventory plugin {plugin_name} because it cannot be imported")
                continue

            try:
                plugin_class = self._find_plugin_class_in_module(module)
                logger.info(f'found inventory plugin {plugin_name}, attempting to register')
                self._register_inventory_plugin(plugin_class)
            except ValueError as e:
                logger.error(f"Failed to find plugin class in module {plugin_name}: {e}")

    def initialize_inventory_plugin(self, plugin_name, settings: Settings):
        """Create an instance of the plugin with the given settings"""
        if plugin_name not in self._inventory_plugins:
            raise ValueError(f"Unknown inventory plugin '{plugin_name}'")

        plugin_class = self._inventory_plugins[plugin_name]
        plugin_instance = plugin_class(settings)
        return plugin_instance