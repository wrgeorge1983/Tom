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
        old_config = os.environ.get('TOM_CONFIG_FILE')
        os.environ['TOM_CONFIG_FILE'] = '/nonexistent/config.yaml'
        
        try:
            settings = NautobotSettings(
                url="https://nautobot.example.com",
                token="test-token-123",
            )
            
            assert settings.url == "https://nautobot.example.com"
            assert settings.token == "test-token-123"
            assert settings.credential_source == "custom_field"
            assert settings.credential_field == "credential_id"
            assert settings.credential_default == "default"
            assert settings.status_filter == []  # Now defaults to empty (no filter)
            assert settings.default_adapter == "netmiko"
            assert settings.default_driver == "cisco_ios"
        finally:
            if old_config:
                os.environ['TOM_CONFIG_FILE'] = old_config
            else:
                os.environ.pop('TOM_CONFIG_FILE', None)


class TestNautobotCredentialExtraction:
    """Test credential ID extraction from devices."""
    
    def test_custom_field_extraction(self):
        """Extract credential ID from custom field."""
        from tom_controller.Plugins.inventory.nautobot import NautobotSettings, NautobotInventoryPlugin
        from tom_controller.config import Settings
        
        # Create mock settings
        nb_settings = NautobotSettings(
            url="https://nautobot.example.com",
            token="test-token",
            credential_source="custom_field",
            credential_field="ssh_cred",
            credential_default="fallback",
        )
        main_settings = Settings()  # type: ignore[call-arg]
        
        # Mock the pynautobot import
        mock_pynautobot = MagicMock()
        mock_nb = MagicMock()
        mock_pynautobot.api.return_value = mock_nb
        
        import sys
        sys.modules['pynautobot'] = mock_pynautobot
        
        try:
            plugin = NautobotInventoryPlugin(nb_settings, main_settings)
            
            # Mock device with custom field
            device = Mock()
            device.custom_fields = {"ssh_cred": "datacenter_creds"}
            
            cred_id = plugin._get_credential_id(device)
            assert cred_id == "datacenter_creds"
            
            # Test fallback to default
            device.custom_fields = {}
            cred_id = plugin._get_credential_id(device)
            assert cred_id == "fallback"
        finally:
            del sys.modules['pynautobot']
    
    def test_config_context_extraction(self):
        """Extract credential ID from config context."""
        from tom_controller.Plugins.inventory.nautobot import NautobotSettings, NautobotInventoryPlugin
        from tom_controller.config import Settings
        
        nb_settings = NautobotSettings(
            url="https://nautobot.example.com",
            token="test-token",
            credential_source="config_context",
            credential_context_path="credential_id",
            credential_default="fallback",
        )
        main_settings = Settings()  # type: ignore[call-arg]
        
        # Mock pynautobot
        mock_pynautobot = MagicMock()
        mock_nb = MagicMock()
        mock_pynautobot.api.return_value = mock_nb
        
        import sys
        sys.modules['pynautobot'] = mock_pynautobot
        
        try:
            plugin = NautobotInventoryPlugin(nb_settings, main_settings)
            
            # Mock device with simple config context
            device = Mock()
            device.config_context = {"credential_id": "branch_creds"}
            
            cred_id = plugin._get_credential_id(device)
            assert cred_id == "branch_creds"
            
            # Test fallback to default
            device.config_context = {}
            cred_id = plugin._get_credential_id(device)
            assert cred_id == "fallback"
        finally:
            del sys.modules['pynautobot']
    
    def test_config_context_nested_path(self):
        """Extract credential ID from nested config context path."""
        from tom_controller.Plugins.inventory.nautobot import NautobotSettings, NautobotInventoryPlugin
        from tom_controller.config import Settings
        
        nb_settings = NautobotSettings(
            url="https://nautobot.example.com",
            token="test-token",
            credential_source="config_context",
            credential_context_path="tom.credentials.ssh",
            credential_default="fallback",
        )
        main_settings = Settings()  # type: ignore[call-arg]
        
        # Mock pynautobot
        mock_pynautobot = MagicMock()
        mock_nb = MagicMock()
        mock_pynautobot.api.return_value = mock_nb
        
        import sys
        sys.modules['pynautobot'] = mock_pynautobot
        
        try:
            plugin = NautobotInventoryPlugin(nb_settings, main_settings)
            
            # Mock device with nested config context
            device = Mock()
            device.config_context = {
                "tom": {
                    "credentials": {
                        "ssh": "nested_creds"
                    }
                }
            }
            
            cred_id = plugin._get_credential_id(device)
            assert cred_id == "nested_creds"
        finally:
            del sys.modules['pynautobot']


class TestPlatformDriverMapping:
    """Test platform to adapter/driver mapping."""
    
    def test_netmiko_device_type_preferred(self):
        """Use netmiko_device_type when available."""
        from tom_controller.Plugins.inventory.nautobot import NautobotSettings, NautobotInventoryPlugin
        from tom_controller.config import Settings
        
        nb_settings = NautobotSettings(
            url="https://nautobot.example.com",
            token="test-token",
        )
        main_settings = Settings()  # type: ignore[call-arg]
        
        # Mock pynautobot
        mock_pynautobot = MagicMock()
        mock_nb = MagicMock()
        mock_pynautobot.api.return_value = mock_nb
        
        import sys
        sys.modules['pynautobot'] = mock_pynautobot
        
        try:
            plugin = NautobotInventoryPlugin(nb_settings, main_settings)
            
            # Mock device with platform that has netmiko_device_type
            device = Mock()
            device.platform = Mock()
            device.platform.netmiko_device_type = "cisco_ios"
            device.platform.napalm_driver = "ios"
            
            adapter, driver = plugin._determine_adapter_and_driver(device)
            assert adapter == "netmiko"  # Uses default adapter
            assert driver == "cisco_ios"  # Uses platform's netmiko_device_type
        finally:
            del sys.modules['pynautobot']
    
    def test_scrapli_default_adapter(self):
        """Use scrapli when set as default adapter."""
        from tom_controller.Plugins.inventory.nautobot import NautobotSettings, NautobotInventoryPlugin
        from tom_controller.config import Settings
        
        nb_settings = NautobotSettings(
            url="https://nautobot.example.com",
            token="test-token",
            default_adapter="scrapli",
        )
        main_settings = Settings()  # type: ignore[call-arg]
        
        # Mock pynautobot
        mock_pynautobot = MagicMock()
        mock_nb = MagicMock()
        mock_pynautobot.api.return_value = mock_nb
        
        import sys
        sys.modules['pynautobot'] = mock_pynautobot
        
        try:
            plugin = NautobotInventoryPlugin(nb_settings, main_settings)
            
            # Mock device with platform
            device = Mock()
            device.platform = Mock()
            device.platform.netmiko_device_type = "cisco_iosxe"
            
            adapter, driver = plugin._determine_adapter_and_driver(device)
            assert adapter == "scrapli"  # Uses configured default adapter
            assert driver == "cisco_iosxe"  # Uses platform driver
        finally:
            del sys.modules['pynautobot']
    
    def test_fallback_when_no_platform(self):
        """Use default adapter/driver when device has no platform."""
        from tom_controller.Plugins.inventory.nautobot import NautobotSettings, NautobotInventoryPlugin
        from tom_controller.config import Settings
        
        nb_settings = NautobotSettings(
            url="https://nautobot.example.com",
            token="test-token",
        )
        main_settings = Settings()  # type: ignore[call-arg]
        
        # Mock pynautobot
        mock_pynautobot = MagicMock()
        mock_nb = MagicMock()
        mock_pynautobot.api.return_value = mock_nb
        
        import sys
        sys.modules['pynautobot'] = mock_pynautobot
        
        try:
            plugin = NautobotInventoryPlugin(nb_settings, main_settings)
            
            # Mock device with no platform
            device = Mock()
            device.platform = None
            
            adapter, driver = plugin._determine_adapter_and_driver(device)
            assert adapter == "netmiko"
            assert driver == "cisco_ios"
        finally:
            del sys.modules['pynautobot']


class TestIPExtraction:
    """Test IP address extraction from devices."""
    
    def test_primary_ip4(self):
        """Extract IPv4 address and strip prefix."""
        from tom_controller.Plugins.inventory.nautobot import NautobotSettings, NautobotInventoryPlugin
        from tom_controller.config import Settings
        
        nb_settings = NautobotSettings(
            url="https://nautobot.example.com",
            token="test-token",
        )
        main_settings = Settings()  # type: ignore[call-arg]
        
        # Mock pynautobot
        mock_pynautobot = MagicMock()
        mock_nb = MagicMock()
        mock_pynautobot.api.return_value = mock_nb
        
        import sys
        sys.modules['pynautobot'] = mock_pynautobot
        
        try:
            plugin = NautobotInventoryPlugin(nb_settings, main_settings)
            
            # Mock device with IPv4
            device = Mock()
            device.name = "router1"
            device.primary_ip4 = Mock()
            device.primary_ip4.address = "192.168.1.1/24"
            device.primary_ip6 = None
            
            host = plugin._get_host_ip(device)
            assert host == "192.168.1.1"
        finally:
            del sys.modules['pynautobot']
    
    def test_fallback_to_name(self):
        """Fall back to device name when no primary IP."""
        from tom_controller.Plugins.inventory.nautobot import NautobotSettings, NautobotInventoryPlugin
        from tom_controller.config import Settings
        
        nb_settings = NautobotSettings(
            url="https://nautobot.example.com",
            token="test-token",
        )
        main_settings = Settings()  # type: ignore[call-arg]
        
        # Mock pynautobot
        mock_pynautobot = MagicMock()
        mock_nb = MagicMock()
        mock_pynautobot.api.return_value = mock_nb
        
        import sys
        sys.modules['pynautobot'] = mock_pynautobot
        
        try:
            plugin = NautobotInventoryPlugin(nb_settings, main_settings)
            
            # Mock device with no IP
            device = Mock()
            device.name = "router-with-no-ip"
            device.primary_ip4 = None
            device.primary_ip6 = None
            
            host = plugin._get_host_ip(device)
            assert host == "router-with-no-ip"
        finally:
            del sys.modules['pynautobot']
