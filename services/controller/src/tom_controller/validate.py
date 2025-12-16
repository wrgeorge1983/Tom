"""Configuration validator for Tom Controller.

Usage:
    python -m tom_controller.validate [config_file]

    If no config_file is specified, uses TOM_CONFIG_FILE env var
    or defaults to tom_controller_config.yaml
"""

import argparse
import os
import sys

from tom_shared.validation import validate_yaml_config

from tom_controller.config import Settings
from tom_controller.Plugins.inventory.yaml import YamlSettings as YamlInventorySettings
from tom_controller.Plugins.inventory.solarwinds import SolarwindsSettings
from tom_controller.Plugins.inventory.nautobot import NautobotSettings
from tom_controller.Plugins.inventory.netbox import NetBoxSettings


# Map of inventory plugin names to their settings classes
INVENTORY_PLUGIN_SETTINGS = {
    "yaml": YamlInventorySettings,
    "solarwinds": SolarwindsSettings,
    "nautobot": NautobotSettings,
    "netbox": NetBoxSettings,
}


def get_default_config_path() -> str:
    """Get the default config file path from env or default."""
    return os.getenv("TOM_CONFIG_FILE", "tom_controller_config.yaml")


def validate_controller_config(config_path: str | None = None) -> int:
    """Validate a controller configuration file.

    :param config_path: Path to config file, or None to use default
    :return: Exit code (0 = valid, 1 = invalid)
    """
    if config_path is None:
        config_path = get_default_config_path()

    print(f"Tom Controller Configuration Validator")
    print(f"Config file: {config_path}")

    result = validate_yaml_config(
        config_path=config_path,
        main_settings_class=Settings,
        plugin_settings=INVENTORY_PLUGIN_SETTINGS,
        plugin_selector_field="inventory_type",
    )

    result.print_report()

    return 0 if result.valid else 1


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate Tom Controller configuration file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                                # Use default config path
    %(prog)s tom_controller_config.yaml     # Validate specific file
    %(prog)s /path/to/config.yaml           # Validate file at path
        """,
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        help=f"Config file to validate (default: $TOM_CONFIG_FILE or tom_controller_config.yaml)",
    )

    args = parser.parse_args()

    sys.exit(validate_controller_config(args.config_file))


if __name__ == "__main__":
    main()
