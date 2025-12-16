"""Core validation logic for Tom configuration files."""

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings


@dataclass
class ValidationResult:
    """Result of validating a configuration file."""

    config_file: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unknown_keys: list[str] = field(default_factory=list)
    loaded_values: dict[str, Any] = field(default_factory=dict)

    def print_report(self) -> None:
        """Print a human-readable validation report."""
        print(f"\nValidating: {self.config_file}")
        print("=" * 60)

        if self.errors:
            print("\nERRORS:")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print("\nWARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")

        if self.unknown_keys:
            print("\nUNKNOWN KEYS (will be ignored):")
            for key in self.unknown_keys:
                print(f"  - {key}")

        if self.loaded_values:
            print("\nLOADED VALUES:")
            for key, value in sorted(self.loaded_values.items()):
                # Mask sensitive values
                if any(s in key.lower() for s in ["password", "secret", "token"]):
                    display_value = "***" if value else "(empty)"
                else:
                    display_value = repr(value)
                print(f"  {key}: {display_value}")

        print()
        if self.valid:
            if self.warnings or self.unknown_keys:
                print("RESULT: VALID (with warnings)")
            else:
                print("RESULT: VALID")
        else:
            print("RESULT: INVALID")
        print()


def get_valid_keys_from_model(
    settings_class: type[BaseSettings], prefix: str = ""
) -> set[str]:
    """Extract valid YAML keys from a Pydantic settings class.

    :param settings_class: The Pydantic BaseSettings subclass
    :param prefix: Optional prefix to prepend to field names
    :return: Set of valid YAML key names
    """
    return {f"{prefix}{name}" for name in settings_class.model_fields.keys()}


def find_unknown_keys(raw_yaml: dict[str, Any], valid_keys: set[str]) -> list[str]:
    """Find keys in YAML that aren't in the valid set.

    :param raw_yaml: Dictionary of keys from the YAML file
    :param valid_keys: Set of valid key names
    :return: List of unknown key names
    """
    return [k for k in raw_yaml.keys() if k not in valid_keys]


def suggest_correction(
    unknown_key: str, valid_keys: set[str], cutoff: float = 0.6
) -> str | None:
    """Suggest a correction for an unknown key using fuzzy matching.

    :param unknown_key: The unknown key to find a match for
    :param valid_keys: Set of valid key names to match against
    :param cutoff: Minimum similarity ratio (0-1) to consider a match
    :return: Suggested correction or None if no good match
    """
    matches = difflib.get_close_matches(unknown_key, valid_keys, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def load_yaml_file(config_path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dictionary.

    :param config_path: Path to the YAML file
    :return: Dictionary of config values
    :raises FileNotFoundError: If file doesn't exist
    :raises yaml.YAMLError: If file is not valid YAML
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    # Handle empty files
    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ValueError(
            f"Config file must contain a YAML dictionary, got {type(data).__name__}"
        )

    return data


def validate_yaml_config(
    config_path: str | Path,
    main_settings_class: type[BaseSettings],
    plugin_settings: dict[str, type[BaseSettings]] | None = None,
    plugin_selector_field: str | None = None,
) -> ValidationResult:
    """Validate a YAML configuration file against Pydantic models.

    :param config_path: Path to the YAML config file
    :param main_settings_class: The main Settings class for the service
    :param plugin_settings: Dict mapping plugin name to its settings class
    :param plugin_selector_field: Field name that selects the active plugin (e.g., 'credential_plugin')
    :return: ValidationResult with errors, warnings, and loaded values
    """
    result = ValidationResult(config_file=str(config_path), valid=True)

    # Load raw YAML
    try:
        raw_yaml = load_yaml_file(config_path)
    except FileNotFoundError as e:
        result.valid = False
        result.errors.append(str(e))
        return result
    except yaml.YAMLError as e:
        result.valid = False
        result.errors.append(f"Invalid YAML: {e}")
        return result
    except ValueError as e:
        result.valid = False
        result.errors.append(str(e))
        return result

    # Build set of valid keys from main settings
    valid_keys = get_valid_keys_from_model(main_settings_class)

    # Add plugin keys for all known plugins
    if plugin_settings:
        for plugin_name, plugin_class in plugin_settings.items():
            # Get plugin_name from model_config if available, otherwise use dict key
            config_plugin_name = (
                getattr(plugin_class.model_config, "plugin_name", None) or plugin_name
            )
            prefix = f"plugin_{config_plugin_name}_"
            valid_keys |= get_valid_keys_from_model(plugin_class, prefix)

    # Find unknown keys
    unknown = find_unknown_keys(raw_yaml, valid_keys)

    for key in unknown:
        result.unknown_keys.append(key)
        suggestion = suggest_correction(key, valid_keys)
        if suggestion:
            result.warnings.append(
                f"Unknown key '{key}' - did you mean '{suggestion}'?"
            )
        else:
            result.warnings.append(f"Unknown key '{key}'")

    # Store loaded values (only the ones that are valid)
    for key, value in raw_yaml.items():
        if key in valid_keys:
            result.loaded_values[key] = value

    # Check which plugin is selected and warn about unused plugin configs
    if plugin_selector_field and plugin_settings:
        selected_plugin = raw_yaml.get(plugin_selector_field)
        if selected_plugin:
            # Find keys for non-selected plugins
            for plugin_name, plugin_class in plugin_settings.items():
                if plugin_name == selected_plugin:
                    continue
                config_plugin_name = (
                    getattr(plugin_class.model_config, "plugin_name", None)
                    or plugin_name
                )
                prefix = f"plugin_{config_plugin_name}_"
                for key in raw_yaml.keys():
                    if key.startswith(prefix):
                        result.warnings.append(
                            f"Key '{key}' is for plugin '{plugin_name}' but "
                            f"'{plugin_selector_field}' is set to '{selected_plugin}'"
                        )

    return result
