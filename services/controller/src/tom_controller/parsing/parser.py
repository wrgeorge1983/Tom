"""Main parsing entry point for Tom Controller."""

from pathlib import Path
from typing import Any, Dict, Optional

from tom_controller.exceptions import TomValidationException
from tom_controller.parsing.textfsm_parser import TemplateSource, TextFSMParser
from tom_controller.parsing.ttp_parser import TTPParser, TTPTemplateSource


def parse_output(
    raw_output: str,
    settings,
    device_type: Optional[str] = None,
    command: Optional[str] = None,
    template: Optional[str] = None,
    template_source: Optional[str] = None,
    include_raw: bool = False,
    parser_type: str = "textfsm",
) -> Dict[str, Any]:
    """Parse network device output using the specified parser.

    This is the main entry point for parsing functionality.
    Can be called from any endpoint that needs to parse output.

    Args:
        raw_output: Raw text output from network device
        settings: Settings object containing template directory configuration
        device_type: Device platform for auto-discovery (e.g., "cisco_ios")
        command: Command for auto-discovery (e.g., "show ip int brief")
        template: Explicit template name (overrides auto-discovery)
        template_source: Where to load template from.
                        For textfsm: "custom" or "ntc"
                        For ttp: "custom" or "ttp_templates"
                        If None, checks custom first, then falls back to library.
        include_raw: If True, include raw output in response
        parser_type: Parser to use ("textfsm" or "ttp")

    Returns:
        Dict containing parsed data and optionally raw output.

    Raises:
        TomTemplateNotFoundException: If the specified template is not found
        TomParsingException: If parsing fails
        TomValidationException: If parser_type is not supported
    """
    if parser_type == "textfsm":
        template_dir = Path(settings.textfsm_template_dir)
        parser = TextFSMParser(custom_template_dir=template_dir)
        # Validate source for textfsm
        textfsm_source: Optional[TemplateSource] = None
        if template_source is not None:
            if template_source not in ("custom", "ntc"):
                raise TomValidationException(
                    f"Invalid template_source '{template_source}' for textfsm. "
                    "Use 'custom' or 'ntc'."
                )
            textfsm_source = template_source  # type: ignore
        return parser.parse(
            raw_output=raw_output,
            template_name=template,
            template_source=textfsm_source,
            platform=device_type,
            command=command,
            include_raw=include_raw,
        )
    elif parser_type == "ttp":
        template_dir = Path(settings.ttp_template_dir)
        parser = TTPParser(custom_template_dir=template_dir)
        # Validate source for ttp
        ttp_source: Optional[TTPTemplateSource] = None
        if template_source is not None:
            if template_source not in ("custom", "ttp_templates"):
                raise TomValidationException(
                    f"Invalid template_source '{template_source}' for ttp. "
                    "Use 'custom' or 'ttp_templates'."
                )
            ttp_source = template_source  # type: ignore
        return parser.parse(
            raw_output=raw_output,
            template_name=template,
            template_source=ttp_source,
            platform=device_type,
            command=command,
            include_raw=include_raw,
        )
    else:
        raise TomValidationException(
            f"Parser type '{parser_type}' not supported. Use 'textfsm' or 'ttp'."
        )
