"""Main parsing entry point for Tom Controller."""

from pathlib import Path
from typing import Any, Dict, Optional

from tom_controller.parsing.textfsm_parser import TextFSMParser
from tom_controller.parsing.ttp_parser import TTPParser


def parse_output(
    raw_output: str,
    settings,
    device_type: Optional[str] = None,
    command: Optional[str] = None,
    template: Optional[str] = None,
    include_raw: bool = False,
    parser_type: str = "textfsm"
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
        include_raw: If True, include raw output in response
        parser_type: Parser to use ("textfsm" or "ttp")
        
    Returns:
        Dict containing parsed data and optionally raw output.
        On error, returns error information with raw output.
    """
    if parser_type == "textfsm":
        template_dir = Path(settings.textfsm_template_dir)
        parser = TextFSMParser(custom_template_dir=template_dir)
        return parser.parse(
            raw_output=raw_output,
            template_name=template,
            platform=device_type,
            command=command,
            include_raw=include_raw
        )
    elif parser_type == "ttp":
        template_dir = Path(settings.ttp_template_dir)
        parser = TTPParser(custom_template_dir=template_dir)
        return parser.parse(
            raw_output=raw_output,
            template_name=template,
            platform=device_type,
            command=command,
            include_raw=include_raw
        )
    else:
        return {
            "error": f"Parser type '{parser_type}' not supported",
            "raw": raw_output if include_raw else None
        }
