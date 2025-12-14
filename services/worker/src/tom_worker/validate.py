"""Configuration validator for Tom Worker.

Usage:
    python -m tom_worker.validate [config_file]

    If no config_file is specified, uses TOM_WORKER_CONFIG_FILE env var
    or defaults to tom_worker_config.yaml
"""

import argparse
import os
import sys

from tom_shared.validation import validate_yaml_config

from tom_worker.config import Settings
from tom_worker.Plugins.credentials.yaml import YamlCredentialSettings
from tom_worker.Plugins.credentials.vault import VaultCredentialSettings


# Map of credential plugin names to their settings classes
CREDENTIAL_PLUGIN_SETTINGS = {
    "yaml": YamlCredentialSettings,
    "vault": VaultCredentialSettings,
}


def get_default_config_path() -> str:
    """Get the default config file path from env or default."""
    return os.getenv("TOM_WORKER_CONFIG_FILE", "tom_worker_config.yaml")


def validate_worker_config(config_path: str | None = None) -> int:
    """Validate a worker configuration file.

    :param config_path: Path to config file, or None to use default
    :return: Exit code (0 = valid, 1 = invalid)
    """
    if config_path is None:
        config_path = get_default_config_path()

    print(f"Tom Worker Configuration Validator")
    print(f"Config file: {config_path}")

    result = validate_yaml_config(
        config_path=config_path,
        main_settings_class=Settings,
        plugin_settings=CREDENTIAL_PLUGIN_SETTINGS,
        plugin_selector_field="credential_plugin",
    )

    result.print_report()

    return 0 if result.valid else 1


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate Tom Worker configuration file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                           # Use default config path
    %(prog)s tom_worker_config.yaml    # Validate specific file
    %(prog)s /path/to/config.yaml      # Validate file at path
        """,
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        help=f"Config file to validate (default: $TOM_WORKER_CONFIG_FILE or tom_worker_config.yaml)",
    )

    args = parser.parse_args()

    sys.exit(validate_worker_config(args.config_file))


if __name__ == "__main__":
    main()
