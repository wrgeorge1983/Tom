import os
from abc import abstractmethod, ABC
from typing import Any
import importlib
from logging import getLogger

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, EnvSettingsSource

logger = getLogger(__name__)

from tom_controller.config import Settings
from tom_shared.config import LoggingYamlConfigSettingsSource


class StripPrefixEnvSettingsSource(EnvSettingsSource):
    """Environment settings source that strips plugin prefix from field names."""
    
    def __init__(self, settings_cls: type[BaseSettings], env_prefix: str, plugin_prefix: str):
        """
        :param settings_cls: The settings class
        :param env_prefix: Base env prefix (e.g., "TOM_")
        :param plugin_prefix: Plugin-specific prefix to strip (e.g., "PLUGIN_SOLARWINDS_")
        """
        super().__init__(settings_cls)
        self.plugin_prefix = plugin_prefix.upper()
        self.full_prefix = (env_prefix + plugin_prefix).upper()
    
    def prepare_field_value(self, field_name: str, field: Any, value: Any, value_is_complex: bool) -> Any:
        # Reconstruct the env var name with the plugin prefix
        env_name = self.full_prefix + field_name.upper()
        return super().prepare_field_value(field_name, field, value, value_is_complex)
    
    def __call__(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        
        # Get all env vars that match our full prefix
        for env_name, env_value in self.env_vars.items():
            if env_name.startswith(self.full_prefix):
                # Strip the full prefix to get the field name
                field_name = env_name[len(self.full_prefix):].lower()
                d[field_name] = env_value
        
        return d


class StripPrefixYamlSettingsSource(LoggingYamlConfigSettingsSource):
    """YAML settings source that strips plugin prefix from field names."""
    
    def __init__(self, settings_cls: type[BaseSettings], yaml_prefix: str):
        """
        :param settings_cls: The settings class
        :param yaml_prefix: Prefix to strip from YAML keys (e.g., "plugin_solarwinds_")
        """
        super().__init__(settings_cls)
        self.yaml_prefix = yaml_prefix.lower()
    
    def __call__(self) -> dict[str, Any]:
        d = super().__call__()
        # Extract only keys with our prefix, then strip it
        result = {}
        for k, v in d.items():
            k_lower = k.lower()
            if k_lower.startswith(self.yaml_prefix):
                field_name = k_lower[len(self.yaml_prefix):]
                result[field_name] = v
        return result


class PluginSettings(BaseSettings):
    """
    Base class for plugin-specific settings.
    
    Plugins should subclass this and set 'plugin_name' in model_config.
    This will automatically configure prefix stripping for both env vars and YAML.
    
    Example:
        class SolarwindsSettings(PluginSettings):
            model_config = SettingsConfigDict(plugin_name="solarwinds")
            
            host: str
            username: str
            password: str
    
    Config file uses: plugin_solarwinds_host
    Env var uses: TOM_PLUGIN_SOLARWINDS_HOST
    Code uses: settings.host
    """
    
    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        plugin_name = cls.model_config.get("plugin_name")
        if not plugin_name:
            raise ValueError(f"{cls.__name__} must set 'plugin_name' in model_config")
        
        env_prefix = cls.model_config.get("env_prefix", "TOM_")
        yaml_prefix = f"plugin_{plugin_name}_"
        env_plugin_prefix = f"PLUGIN_{plugin_name.upper()}_"
        
        return (
            StripPrefixEnvSettingsSource(settings_cls, env_prefix, env_plugin_prefix),
            dotenv_settings,
            StripPrefixYamlSettingsSource(settings_cls, yaml_prefix),
        )
    
    model_config = SettingsConfigDict(
        env_prefix="TOM_",
        env_file=os.getenv("TOM_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_CONFIG_FILE", "tom_config.yaml"),
        case_sensitive=False,
        extra="forbid",
    )


class ExampleTomPluginSettings(BaseSettings):
    """
    Tom Plugin Settings Base Class

    functions the same as the main Tom config, and in fact uses the same config file, sources, but will look for settings
    specific to each plugin.

    So variables will all have a prefix specific to the plugin.  Each plugins settings object will be processing the
    config file (and envvars, etc) and pulling out its own config and ignoring the others (and the base Tom settings)

    since the settings themselves will have a prefix built-in the 'env_prefix' etc will all stay the same as base tom

    precedence: ENVVARS > env_file > yaml_file > defaults


    """


    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            env_settings,
            dotenv_settings,
            LoggingYamlConfigSettingsSource(settings_cls),
        )

    model_config = SettingsConfigDict(
        env_prefix="TOM_",
        env_file=os.getenv("TOM_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_CONFIG_FILE", "tom_config.yaml"),
        case_sensitive=False,
        extra="forbid",
    )


class TomPlugin(ABC):
    """Base class for all Tom plugins.
    
    Plugins should:
    1. Set 'name' class attribute (used for discovery)
    2. Set 'dependencies' class attribute (list of required packages)
    3. Set 'settings_class' class attribute (subclass of PluginSettings)
    4. Implement __init__(plugin_settings, main_settings)
    """
    
    @abstractmethod
    def __init__(self, plugin_settings: PluginSettings | None, main_settings: Settings):
        """
        Initialize the plugin with its specific settings.
        
        :param plugin_settings: Plugin-specific settings instance (None for legacy plugins)
        :param main_settings: Main Tom settings (for shared config like Redis)
        """
        pass

    name: str
    dependencies: list[str] = []
    settings_class: type[PluginSettings] | None = None


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
        
        # Instantiate plugin-specific settings if the plugin has a settings_class
        if hasattr(plugin_class, 'settings_class') and plugin_class.settings_class:
            logger.info(f"Loading plugin-specific settings for {plugin_name}")
            plugin_settings = plugin_class.settings_class()
            plugin_instance = plugin_class(plugin_settings, settings)
        else:
            # Legacy plugins that don't use plugin-specific settings
            logger.info(f"Plugin {plugin_name} uses legacy settings approach")
            plugin_instance = plugin_class(None, settings)
        
        return plugin_instance

