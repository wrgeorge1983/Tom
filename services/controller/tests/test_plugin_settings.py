"""
Test plugin settings behavior.

Tests focus on:
1. Plugin settings loading from shared config with prefix stripping
2. Main settings ignoring plugin-prefixed keys
3. Coexistence in shared config file
4. Field validation and defaults (using direct instantiation)
"""
import tempfile
from pathlib import Path

import pytest


# Fixture creates a shared config file for tests that need it
@pytest.fixture
def shared_config_file():
    """Create a shared config file with both main and plugin settings."""
    config_content = """
# Main controller settings
host: "0.0.0.0"
port: 8020
log_level: "INFO"
inventory_type: "solarwinds"

# SolarWinds plugin settings (with plugin_ prefix)
plugin_solarwinds_host: "sw.test.example.com"
plugin_solarwinds_username: "test_sw_user"
plugin_solarwinds_password: "test_sw_pass"
plugin_solarwinds_port: 17774
plugin_solarwinds_default_cred_name: "test_cred"

# Random other settings that plugins should ignore
redis_host: "localhost"
redis_port: 6379
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_content)
        temp_file = f.name
    
    yield temp_file
    
    # Cleanup
    Path(temp_file).unlink()


class TestSolarwindsSettingsDirectInstantiation:
    """Test SolarWinds settings with direct kwargs (no file interaction)."""
    
    def test_field_validation(self):
        """SolarWinds settings validates field types correctly."""
        import os
        from tom_controller.Plugins.inventory.solarwinds import SolarwindsSettings
        
        # Set env var to non-existent file to prevent file loading
        old_config = os.environ.get('TOM_CONFIG_FILE')
        os.environ['TOM_CONFIG_FILE'] = '/nonexistent/config.yaml'
        
        try:
            settings = SolarwindsSettings(
                host='test.example.com',
                username='testuser',
                password='testpass',
                port=12345,
            )
            
            assert settings.host == 'test.example.com'
            assert settings.username == 'testuser'
            assert settings.password == 'testpass'
            assert settings.port == 12345
        finally:
            if old_config:
                os.environ['TOM_CONFIG_FILE'] = old_config
            else:
                os.environ.pop('TOM_CONFIG_FILE', None)
    
    def test_defaults(self):
        """SolarWinds settings applies defaults correctly."""
        import os
        from tom_controller.Plugins.inventory.solarwinds import SolarwindsSettings
        
        # Set env var to non-existent file to prevent file loading
        old_config = os.environ.get('TOM_CONFIG_FILE')
        os.environ['TOM_CONFIG_FILE'] = '/nonexistent/config.yaml'
        
        try:
            settings = SolarwindsSettings(
                host='test.example.com',
                username='testuser',
                password='testpass',
            )
            
            # These should use defaults
            assert settings.port == 17774
            assert settings.default_cred_name == 'default'
            assert len(settings.device_mappings) == 1  # Default catch-all mapping
        finally:
            if old_config:
                os.environ['TOM_CONFIG_FILE'] = old_config
            else:
                os.environ.pop('TOM_CONFIG_FILE', None)


class TestSharedConfigInteraction:
    """Test that main and plugin settings can share a config file."""
    
    def test_plugin_loads_from_shared_yaml(self, shared_config_file):
        """Plugin settings load from shared YAML, stripping plugin_ prefix."""
        # Import here so we can reload with fresh config
        import importlib
        import sys
        import os
        
        # Set config file env var BEFORE importing
        os.environ['TOM_CONFIG_FILE'] = shared_config_file
        
        # Reload the module to pick up the env var
        if 'tom_controller.Plugins.inventory.solarwinds' in sys.modules:
            import tom_controller.Plugins.inventory.solarwinds
            importlib.reload(tom_controller.Plugins.inventory.solarwinds)
        
        from tom_controller.Plugins.inventory.solarwinds import SolarwindsSettings
        
        try:
            settings = SolarwindsSettings()  # type: ignore[call-arg]
            
            # Verify prefix was stripped and values loaded
            assert settings.host == "sw.test.example.com"
            assert settings.username == "test_sw_user"
            assert settings.password == "test_sw_pass"
            assert settings.port == 17774
            assert settings.default_cred_name == "test_cred"
        finally:
            # Cleanup
            os.environ.pop('TOM_CONFIG_FILE', None)
    
    def test_main_settings_ignores_plugin_keys(self, shared_config_file):
        """Main Settings ignores plugin_ prefixed keys (extra='ignore')."""
        import importlib
        import sys
        import os
        
        os.environ['TOM_CONFIG_FILE'] = shared_config_file
        
        if 'tom_controller.config' in sys.modules:
            import tom_controller.config
            importlib.reload(tom_controller.config)
        
        from tom_controller.config import Settings
        
        try:
            # This should not raise validation errors about unknown plugin_ keys
            settings = Settings()  # type: ignore[call-arg]
            
            # Main settings should load their own values
            assert settings.host == "0.0.0.0"
            assert settings.port == 8020
            assert settings.inventory_type == "solarwinds"
            
            # Plugin settings should not appear on main settings
            assert not hasattr(settings, 'plugin_solarwinds_host')
        finally:
            os.environ.pop('TOM_CONFIG_FILE', None)
    
    def test_both_coexist(self, shared_config_file):
        """Both main and plugin settings can load from the same file."""
        import importlib
        import sys
        import os
        
        os.environ['TOM_CONFIG_FILE'] = shared_config_file
        
        # Reload both modules
        if 'tom_controller.Plugins.inventory.solarwinds' in sys.modules:
            import tom_controller.Plugins.inventory.solarwinds
            importlib.reload(tom_controller.Plugins.inventory.solarwinds)
        if 'tom_controller.config' in sys.modules:
            import tom_controller.config
            importlib.reload(tom_controller.config)
        
        from tom_controller.Plugins.inventory.solarwinds import SolarwindsSettings
        from tom_controller.config import Settings
        
        try:
            # Both should load without errors
            sw_settings = SolarwindsSettings()  # type: ignore[call-arg]
            main_settings = Settings()  # type: ignore[call-arg]
            
            # Plugin settings should have stripped prefixes
            assert sw_settings.host == "sw.test.example.com"
            
            # Main settings should have their own values
            assert main_settings.host == "0.0.0.0"
            
            # Both should coexist peacefully
            assert sw_settings.host != main_settings.host
        finally:
            os.environ.pop('TOM_CONFIG_FILE', None)


class TestYamlPluginCoexistence:
    """Test YAML plugin works with new plugin settings."""
    
    def test_yaml_plugin_with_plugin_settings(self):
        """YAML plugin now uses proper plugin settings with prefix stripping."""
        import tempfile
        from pathlib import Path
        from tom_controller.Plugins.inventory.yaml import YamlInventoryPlugin, YamlSettings
        from tom_controller.config import Settings
        
        # Create a minimal inventory file for the YAML plugin
        inventory_content = """
test_device:
  host: "192.168.1.1"
  adapter: "netmiko"
  adapter_driver: "cisco_ios"
  credential_id: "default"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(inventory_content)
            temp_inventory = f.name
        
        try:
            # YAML plugin now has its own settings class
            yaml_settings = YamlSettings(
                inventory_file=temp_inventory,
            )
            # Main settings provides project_root (no duplication)
            main_settings = Settings(
                project_root=".",  # Use current dir for test
            )  # type: ignore[call-arg]
            
            # Should initialize without errors
            plugin = YamlInventoryPlugin(yaml_settings, main_settings)
            
            assert plugin.name == "yaml"
            assert plugin.settings == yaml_settings
            assert plugin.settings.inventory_file == temp_inventory
            # Verify it combined main_settings.project_root with plugin inventory_file
            assert plugin.filename == str(Path(".") / temp_inventory)
        finally:
            Path(temp_inventory).unlink()


class TestMissingPluginCrash:
    """Test that missing plugins cause appropriate errors at runtime."""
    
    def test_missing_plugin_raises_error(self):
        """Requesting a plugin that doesn't exist should raise ValueError at initialization."""
        from tom_controller.Plugins.base import PluginManager
        from tom_controller.config import Settings
        import pytest
        
        # inventory_type is now str (not Literal), so this is valid at Settings level
        settings = Settings(
            inventory_type="nonexistent",
            inventory_plugins={"yaml": 100}
        )  # type: ignore[call-arg]
        
        pm = PluginManager()
        pm.discover_plugins(settings)
        
        # Validation happens at plugin initialization, not Settings load
        # Should raise ValueError when trying to initialize non-existent plugin
        with pytest.raises(ValueError, match="Unknown inventory plugin 'nonexistent'"):
            pm.initialize_inventory_plugin("nonexistent", settings)
