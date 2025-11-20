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

class PluginManager:

    def __init__(self):
        self._plugins: dict[str, type[TomPlugin]] = {}
        self._inventory_plugins: dict[str, type[TomPlugin]] = {}

    @property
    def inventory_plugin_names(self):
        plugin_names = list(self._inventory_plugins.keys())
        return plugin_names

    def _register_inventory_plugin(self, plugin_class: type[TomPlugin]):
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

        self._plugins[name] = plugin_class
        self._inventory_plugins[name] = plugin_class

        logger.info(f"Registered inventory plugin {name}")

    def _find_plugin_class_in_module(self, module):
        for name in dir(module):
            obj = getattr(module, name)
            if (isinstance(obj, type) and issubclass(obj, TomPlugin) and obj is not TomPlugin):
                return obj
        raise ValueError("No TomPlugin subclass found in module")

    def discover_plugins(self, settings: Settings):
        for plugin_name in settings.inventory_plugins:
            try:
                module = importlib.import_module(f'tom_controller.Plugins.inventory.{plugin_name}')
            except (ImportError, ModuleNotFoundError):
                logger.error(f"Cannot load inventory plugin {plugin_name} because it cannot be imported")
                continue

            plugin_class = self._find_plugin_class_in_module(module)
            logger.info(f'found inventory plugin {plugin_name}, attempting to import')
            self._register_inventory_plugin(plugin_class)

    def initialize_inventory_plugin(self, plugin_name, settings: Settings):
        """Create an instance of the plugin with the given settings"""
        if plugin_name not in self._inventory_plugins:
            raise ValueError(f"Unknown inventory plugin '{plugin_name}'")

        plugin_class = self._inventory_plugins[plugin_name]
        plugin_instance = plugin_class(settings)
        return plugin_instance