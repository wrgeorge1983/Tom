"""Tests for Nautobot inventory plugin."""

import pytest
from unittest.mock import MagicMock, Mock


class TestNautobotSettings:
    """Test Nautobot plugin settings."""

    def test_settings_with_defaults(self):
        """Nautobot settings apply defaults correctly."""
        import os
        from tom_controller.Plugins.inventory.nautobot import NautobotSettings

        # Set env var to non-existent file to prevent file loading
        old_config = os.environ.get("TOM_CONFIG_FILE")
        os.environ["TOM_CONFIG_FILE"] = "/nonexistent/config.yaml"

        try:
            settings = NautobotSettings(
                url="https://nautobot.example.com",
                token="test-token-123",
            )

            assert settings.url == "https://nautobot.example.com"
            assert settings.token == "test-token-123"
            # Credential settings
            assert settings.credential_source == "custom_field"
            assert settings.credential_field == "credential_id"
            assert settings.default_credential == "default"
            # Adapter settings
            assert settings.adapter_source == "custom_field"
            assert settings.adapter_field == ""
            assert settings.default_adapter == "netmiko"
            # Driver settings
            assert settings.driver_source == "custom_field"
            assert settings.driver_field == ""
            assert settings.default_driver == "cisco_ios"
            # Port
            assert settings.default_port == 22
            # Filters
            assert settings.status_filter == []
        finally:
            if old_config:
                os.environ["TOM_CONFIG_FILE"] = old_config
            else:
                os.environ.pop("TOM_CONFIG_FILE", None)


def _create_plugin(settings_overrides: dict):
    """Helper to create a plugin with mocked pynautobot."""
    from tom_controller.Plugins.inventory.nautobot import (
        NautobotSettings,
        NautobotInventoryPlugin,
    )
    from tom_controller.config import Settings

    nb_settings = NautobotSettings(
        url="https://nautobot.example.com",
        token="test-token",
        **settings_overrides,
    )
    main_settings = Settings()  # type: ignore[call-arg]

    # Mock the pynautobot import
    mock_pynautobot = MagicMock()
    mock_nb = MagicMock()
    mock_pynautobot.api.return_value = mock_nb

    import sys

    sys.modules["pynautobot"] = mock_pynautobot

    plugin = NautobotInventoryPlugin(nb_settings, main_settings)
    return plugin


def _cleanup_mock():
    """Remove mock from sys.modules."""
    import sys

    if "pynautobot" in sys.modules:
        del sys.modules["pynautobot"]


class TestCredentialExtraction:
    """Test credential_id extraction from different sources."""

    def test_from_custom_field(self):
        """Extract credential from custom field."""
        try:
            plugin = _create_plugin(
                {
                    "credential_source": "custom_field",
                    "credential_field": "my_cred_field",
                    "default_credential": "fallback",
                }
            )

            device = Mock()
            device.custom_fields = {"my_cred_field": "prod_creds"}

            assert plugin._get_credential_id(device) == "prod_creds"
        finally:
            _cleanup_mock()

    def test_from_config_context(self):
        """Extract credential from config context."""
        try:
            plugin = _create_plugin(
                {
                    "credential_source": "config_context",
                    "credential_field": "credential_id",
                    "default_credential": "fallback",
                }
            )

            device = Mock()
            device.custom_fields = {}
            device.config_context = {"credential_id": "ctx_creds"}

            assert plugin._get_credential_id(device) == "ctx_creds"
        finally:
            _cleanup_mock()

    def test_from_config_context_nested_path(self):
        """Extract credential from nested config context path."""
        try:
            plugin = _create_plugin(
                {
                    "credential_source": "config_context",
                    "credential_field": "tom.network.credential_id",
                    "default_credential": "fallback",
                }
            )

            device = Mock()
            device.custom_fields = {}
            device.config_context = {
                "tom": {"network": {"credential_id": "nested_creds"}}
            }

            assert plugin._get_credential_id(device) == "nested_creds"
        finally:
            _cleanup_mock()

    def test_fallback_to_default(self):
        """Use default when field not found."""
        try:
            plugin = _create_plugin(
                {
                    "credential_source": "custom_field",
                    "credential_field": "missing_field",
                    "default_credential": "fallback_cred",
                }
            )

            device = Mock()
            device.custom_fields = {}

            assert plugin._get_credential_id(device) == "fallback_cred"
        finally:
            _cleanup_mock()


class TestAdapterExtraction:
    """Test adapter extraction from different sources."""

    def test_from_custom_field(self):
        """Extract adapter from custom field."""
        try:
            plugin = _create_plugin(
                {
                    "adapter_source": "custom_field",
                    "adapter_field": "tom_adapter",
                    "default_adapter": "netmiko",
                }
            )

            device = Mock()
            device.custom_fields = {"tom_adapter": "scrapli"}
            device.config_context = {}

            assert plugin._get_adapter(device) == "scrapli"
        finally:
            _cleanup_mock()

    def test_from_config_context(self):
        """Extract adapter from config context."""
        try:
            plugin = _create_plugin(
                {
                    "adapter_source": "config_context",
                    "adapter_field": "tom.adapter",
                    "default_adapter": "netmiko",
                }
            )

            device = Mock()
            device.custom_fields = {}
            device.config_context = {"tom": {"adapter": "scrapli"}}

            assert plugin._get_adapter(device) == "scrapli"
        finally:
            _cleanup_mock()

    def test_fallback_to_default_when_field_empty(self):
        """Use default adapter when field is not configured."""
        try:
            plugin = _create_plugin(
                {
                    "adapter_source": "custom_field",
                    "adapter_field": "",  # Empty = use default
                    "default_adapter": "netmiko",
                }
            )

            device = Mock()
            device.custom_fields = {}
            device.config_context = {}

            assert plugin._get_adapter(device) == "netmiko"
        finally:
            _cleanup_mock()

    def test_invalid_adapter_falls_back_to_default(self):
        """Invalid adapter value falls back to default."""
        try:
            plugin = _create_plugin(
                {
                    "adapter_source": "custom_field",
                    "adapter_field": "tom_adapter",
                    "default_adapter": "netmiko",
                }
            )

            device = Mock()
            device.custom_fields = {"tom_adapter": "invalid_adapter"}
            device.config_context = {}

            assert plugin._get_adapter(device) == "netmiko"
        finally:
            _cleanup_mock()


class TestDriverExtraction:
    """Test driver extraction from different sources."""

    def test_from_custom_field(self):
        """Extract driver from custom field."""
        try:
            plugin = _create_plugin(
                {
                    "driver_source": "custom_field",
                    "driver_field": "tom_driver",
                    "default_driver": "cisco_ios",
                }
            )

            device = Mock()
            device.custom_fields = {"tom_driver": "arista_eos"}
            device.config_context = {}

            assert plugin._get_driver(device) == "arista_eos"
        finally:
            _cleanup_mock()

    def test_from_config_context(self):
        """Extract driver from config context."""
        try:
            plugin = _create_plugin(
                {
                    "driver_source": "config_context",
                    "driver_field": "tom.driver",
                    "default_driver": "cisco_ios",
                }
            )

            device = Mock()
            device.custom_fields = {}
            device.config_context = {"tom": {"driver": "juniper_junos"}}

            assert plugin._get_driver(device) == "juniper_junos"
        finally:
            _cleanup_mock()

    def test_fallback_to_default(self):
        """Use default driver when field not found."""
        try:
            plugin = _create_plugin(
                {
                    "driver_source": "custom_field",
                    "driver_field": "missing_field",
                    "default_driver": "cisco_ios",
                }
            )

            device = Mock()
            device.custom_fields = {}
            device.config_context = {}

            assert plugin._get_driver(device) == "cisco_ios"
        finally:
            _cleanup_mock()


class TestMixedSources:
    """Test using different sources for different fields."""

    def test_credential_from_custom_field_driver_from_config_context(self):
        """Credential from custom field, driver from config context."""
        try:
            plugin = _create_plugin(
                {
                    "credential_source": "custom_field",
                    "credential_field": "cred_id",
                    "default_credential": "default",
                    "driver_source": "config_context",
                    "driver_field": "tom.driver",
                    "default_driver": "cisco_ios",
                }
            )

            device = Mock()
            device.custom_fields = {"cred_id": "my_creds"}
            device.config_context = {"tom": {"driver": "arista_eos"}}

            assert plugin._get_credential_id(device) == "my_creds"
            assert plugin._get_driver(device) == "arista_eos"
        finally:
            _cleanup_mock()

    def test_all_from_config_context(self):
        """All fields from config context."""
        try:
            plugin = _create_plugin(
                {
                    "credential_source": "config_context",
                    "credential_field": "tom.credential_id",
                    "adapter_source": "config_context",
                    "adapter_field": "tom.adapter",
                    "driver_source": "config_context",
                    "driver_field": "tom.driver",
                }
            )

            device = Mock()
            device.custom_fields = {}
            device.config_context = {
                "tom": {
                    "credential_id": "ctx_creds",
                    "adapter": "scrapli",
                    "driver": "cisco_nxos",
                }
            }

            assert plugin._get_credential_id(device) == "ctx_creds"
            assert plugin._get_adapter(device) == "scrapli"
            assert plugin._get_driver(device) == "cisco_nxos"
        finally:
            _cleanup_mock()


class TestIPExtraction:
    """Test IP address extraction from devices."""

    def test_primary_ip4(self):
        """Extract IPv4 address and strip prefix."""
        try:
            plugin = _create_plugin({})

            device = Mock()
            device.name = "router1"
            device.primary_ip4 = Mock()
            device.primary_ip4.address = "192.168.1.1/24"
            device.primary_ip6 = None

            host = plugin._get_host_ip(device)
            assert host == "192.168.1.1"
        finally:
            _cleanup_mock()

    def test_fallback_to_name(self):
        """Fall back to device name when no primary IP."""
        try:
            plugin = _create_plugin({})

            device = Mock()
            device.name = "router-with-no-ip"
            device.primary_ip4 = None
            device.primary_ip6 = None

            host = plugin._get_host_ip(device)
            assert host == "router-with-no-ip"
        finally:
            _cleanup_mock()


class TestNeedsConfigContext:
    """Test _needs_config_context helper."""

    def test_no_config_context_needed(self):
        """No config context needed when all sources are custom_field."""
        try:
            plugin = _create_plugin(
                {
                    "credential_source": "custom_field",
                    "adapter_source": "custom_field",
                    "driver_source": "custom_field",
                }
            )

            assert plugin._needs_config_context() is False
        finally:
            _cleanup_mock()

    def test_config_context_needed_for_credential(self):
        """Config context needed when credential uses it."""
        try:
            plugin = _create_plugin(
                {
                    "credential_source": "config_context",
                    "adapter_source": "custom_field",
                    "driver_source": "custom_field",
                }
            )

            assert plugin._needs_config_context() is True
        finally:
            _cleanup_mock()

    def test_config_context_needed_for_driver(self):
        """Config context needed when driver uses it."""
        try:
            plugin = _create_plugin(
                {
                    "credential_source": "custom_field",
                    "adapter_source": "custom_field",
                    "driver_source": "config_context",
                }
            )

            assert plugin._needs_config_context() is True
        finally:
            _cleanup_mock()
