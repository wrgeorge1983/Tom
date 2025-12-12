"""
Base classes for Tom Worker plugins.

This module provides the plugin infrastructure for the worker, including:
- PluginSettings: Base class for plugin-specific settings with prefix stripping
- CredentialPlugin: Abstract base class for credential store plugins
- CredentialPluginManager: Discovery, registration, and initialization of plugins
"""

import importlib
import os
from abc import ABC, abstractmethod
from logging import getLogger
from typing import Any, TYPE_CHECKING

from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from tom_shared.config import LoggingYamlConfigSettingsSource
from tom_worker.credentials.credentials import SSHCredentials

if TYPE_CHECKING:
    from tom_worker.config import Settings

logger = getLogger(__name__)


class StripPrefixEnvSettingsSource(EnvSettingsSource):
    """Environment settings source that strips plugin prefix from field names.

    For a plugin named "vault", this source will:
    - Look for env vars like TOM_WORKER_PLUGIN_VAULT_URL
    - Strip the prefix to populate the 'url' field
    """

    def __init__(
        self, settings_cls: type[BaseSettings], env_prefix: str, plugin_prefix: str
    ):
        """
        :param settings_cls: The settings class
        :param env_prefix: Base env prefix (e.g., "TOM_WORKER_")
        :param plugin_prefix: Plugin-specific prefix to strip (e.g., "PLUGIN_VAULT_")
        """
        # Call parent with empty prefix so it loads ALL env vars
        # We'll do the filtering ourselves in __call__
        super().__init__(settings_cls, env_prefix="")
        self.plugin_prefix = plugin_prefix.upper()
        self.full_prefix = (env_prefix + plugin_prefix).upper()

    def __call__(self) -> dict[str, Any]:
        d: dict[str, Any] = {}

        # Get all env vars that match our full prefix
        for env_name, env_value in self.env_vars.items():
            if env_name.upper().startswith(self.full_prefix):
                # Strip the full prefix to get the field name
                field_name = env_name[len(self.full_prefix) :].lower()
                d[field_name] = env_value

        return d


class StripPrefixYamlSettingsSource(LoggingYamlConfigSettingsSource):
    """YAML settings source that strips plugin prefix from field names.

    For a plugin named "vault", this source will:
    - Look for YAML keys like plugin_vault_url
    - Strip the prefix to populate the 'url' field
    """

    def __init__(self, settings_cls: type[BaseSettings], yaml_prefix: str):
        """
        :param settings_cls: The settings class
        :param yaml_prefix: Prefix to strip from YAML keys (e.g., "plugin_vault_")
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
                field_name = k_lower[len(self.yaml_prefix) :]
                result[field_name] = v
        return result


class PluginSettings(BaseSettings):
    """
    Base class for plugin-specific settings.

    Plugins should subclass this and set 'plugin_name' in model_config.
    This will automatically configure prefix stripping for both env vars and YAML.

    Example:
        class VaultSettings(PluginSettings):
            model_config = SettingsConfigDict(plugin_name="vault")

            url: str
            token: str = ""

    Config file uses: plugin_vault_url
    Env var uses: TOM_WORKER_PLUGIN_VAULT_URL
    Code uses: settings.url
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

        env_prefix = cls.model_config.get("env_prefix", "TOM_WORKER_")
        yaml_prefix = f"plugin_{plugin_name}_"
        env_plugin_prefix = f"PLUGIN_{plugin_name.upper()}_"

        return (
            init_settings,  # Highest priority: direct kwargs
            StripPrefixEnvSettingsSource(settings_cls, env_prefix, env_plugin_prefix),
            dotenv_settings,
            StripPrefixYamlSettingsSource(settings_cls, yaml_prefix),
        )

    model_config = SettingsConfigDict(
        env_prefix="TOM_WORKER_",
        env_file=os.getenv("TOM_WORKER_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_WORKER_CONFIG_FILE", "tom_worker_config.yaml"),
        case_sensitive=False,
        extra="forbid",
    )


class CredentialPlugin(ABC):
    """Base class for credential store plugins.

    Plugins should:
    1. Set 'name' class attribute (used for discovery)
    2. Set 'dependencies' class attribute (list of required packages)
    3. Set 'settings_class' class attribute (subclass of PluginSettings, or None)
    4. Implement __init__(plugin_settings, main_settings)
    5. Implement get_ssh_credentials(credential_id)
    6. Implement validate()
    """

    name: str
    dependencies: list[str] = []
    settings_class: type[PluginSettings] | None = None

    @abstractmethod
    def __init__(
        self, plugin_settings: PluginSettings | None, main_settings: "Settings"
    ):
        """
        Initialize the plugin with its specific settings.

        :param plugin_settings: Plugin-specific settings instance (None if no settings_class)
        :param main_settings: Main worker settings (for shared config like project_root)
        """
        pass

    @abstractmethod
    async def get_ssh_credentials(self, credential_id: str) -> SSHCredentials:
        """Retrieve SSH credentials by ID.

        :param credential_id: The credential identifier
        :return: SSHCredentials with username and password
        :raises TomException: If credential not found or retrieval fails
        """
        pass

    @abstractmethod
    async def validate(self) -> None:
        """Validate that the plugin is ready to serve credentials.

        This method should check connectivity, authentication, file existence, etc.
        It should raise TomException with a clear, actionable error message on failure.

        :raises TomException: If validation fails
        """
        pass


class CredentialPluginManager:
    """Manages loading and initialization of credential plugins.

    Unlike the controller's inventory plugin system which discovers all available
    plugins, this manager loads only the specific plugin that is configured.
    If that plugin cannot be loaded (missing module, missing dependencies, etc.),
    it fails immediately with a clear error message.
    """

    # Known credential plugins - add new ones here
    KNOWN_PLUGINS = ["yaml", "vault"]

    def __init__(self):
        self._loaded_plugin: type[CredentialPlugin] | None = None
        self._loaded_plugin_name: str | None = None

    def _check_dependencies(self, plugin_class: type[CredentialPlugin]) -> list[str]:
        """Check if a plugin's dependencies are satisfied.

        :param plugin_class: The plugin class to check
        :return: List of missing package names (empty if all satisfied)
        """
        missing_deps = []
        for pkg in plugin_class.dependencies:
            try:
                importlib.import_module(pkg)
            except (ImportError, ModuleNotFoundError):
                missing_deps.append(pkg)
        return missing_deps

    def _find_plugin_class_in_module(self, module) -> type[CredentialPlugin]:
        """Find the CredentialPlugin subclass in a module.

        :param module: The module to search
        :return: The CredentialPlugin subclass
        :raises ValueError: If no CredentialPlugin subclass found
        """
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, CredentialPlugin)
                and obj is not CredentialPlugin
            ):
                return obj
        raise ValueError("No CredentialPlugin subclass found in module")

    def load_plugin(self, plugin_name: str) -> type[CredentialPlugin]:
        """Load a specific credential plugin by name.

        This method attempts to import the plugin module, find the plugin class,
        and verify its dependencies are satisfied. If any step fails, it raises
        an exception with a clear error message.

        :param plugin_name: Name of the plugin to load (e.g., "yaml", "vault")
        :return: The plugin class (not instantiated)
        :raises ValueError: If plugin is unknown, cannot be imported, or has missing dependencies
        """
        if plugin_name not in self.KNOWN_PLUGINS:
            raise ValueError(
                f"Unknown credential plugin '{plugin_name}'. "
                f"Available plugins: {', '.join(self.KNOWN_PLUGINS)}"
            )

        # Try to import the plugin module
        module_path = f"tom_worker.Plugins.credentials.{plugin_name}"
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ValueError(
                f"Failed to import credential plugin '{plugin_name}': {e}\n"
                f"Module path: {module_path}"
            ) from e

        # Find the plugin class in the module
        try:
            plugin_class = self._find_plugin_class_in_module(module)
        except ValueError as e:
            raise ValueError(
                f"Credential plugin module '{plugin_name}' does not contain a valid plugin class: {e}"
            ) from e

        # Check dependencies (these are import names, not necessarily package names)
        missing_deps = self._check_dependencies(plugin_class)
        if missing_deps:
            raise ValueError(
                f"Credential plugin '{plugin_name}' has missing dependencies (import names): {missing_deps}\n"
                f"Note: package names may differ from import names (e.g., 'pyyaml' installs as 'yaml')"
            )

        logger.info(f"Loaded credential plugin '{plugin_name}'")
        self._loaded_plugin = plugin_class
        self._loaded_plugin_name = plugin_name
        return plugin_class

    def initialize_credential_plugin(
        self, plugin_name: str, settings: "Settings"
    ) -> CredentialPlugin:
        """Load and instantiate the specified credential plugin.

        This method combines loading (if not already loaded) and initialization.
        If the plugin cannot be loaded or instantiated, it raises an exception
        with a clear error message.

        :param plugin_name: Name of the plugin to initialize
        :param settings: Main worker settings
        :return: Initialized plugin instance
        :raises ValueError: If plugin cannot be loaded or initialized
        """
        # Load the plugin if not already loaded (or if a different plugin was loaded)
        if self._loaded_plugin is None or self._loaded_plugin_name != plugin_name:
            self.load_plugin(plugin_name)

        plugin_class = self._loaded_plugin
        assert plugin_class is not None  # load_plugin ensures this

        # Instantiate plugin-specific settings if the plugin has a settings_class
        if plugin_class.settings_class:
            logger.info(f"Loading plugin-specific settings for '{plugin_name}'")
            plugin_settings = plugin_class.settings_class()
            return plugin_class(plugin_settings, settings)
        else:
            logger.info(f"Plugin '{plugin_name}' has no settings class")
            return plugin_class(None, settings)
