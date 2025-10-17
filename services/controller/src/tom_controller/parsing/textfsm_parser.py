"""TextFSM parser implementation."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import textfsm
import ntc_templates

logger = logging.getLogger(__name__)

# Module-level parser instance (singleton)
_parser_instance = None

def get_parser(custom_template_dir: Optional[Path] = None) -> 'TextFSMParser':
    """Get or create the singleton parser instance.
    
    Args:
        custom_template_dir: Directory containing custom templates
        
    Returns:
        TextFSMParser instance
    """
    global _parser_instance
    if _parser_instance is None:
        if custom_template_dir is None:
            custom_dir = Path("/app/templates/textfsm")
            if custom_dir.exists():
                custom_template_dir = custom_dir
        _parser_instance = TextFSMParser(custom_template_dir)
    return _parser_instance


def parse_output(
    raw_output: str,
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
        parser = get_parser()
        return parser.parse(
            raw_output=raw_output,
            template_name=template,
            platform=device_type,
            command=command,
            include_raw=include_raw
        )
    elif parser_type == "ttp":
        from tom_controller.parsing import ttp_parser
        parser = ttp_parser.get_parser()
        return parser.parse(
            raw_output=raw_output,
            template_name=template,
            platform=device_type,
            include_raw=include_raw
        )
    else:
        return {
            "error": f"Parser type '{parser_type}' not supported",
            "raw": raw_output if include_raw else None
        }


class TextFSMParser:
    """TextFSM parser for network device output."""
    
    def __init__(self, custom_template_dir: Optional[Path] = None):
        """Initialize the TextFSM parser.
        
        Args:
            custom_template_dir: Directory containing custom TextFSM templates.
                                Templates here override ntc-templates.
        """
        self.custom_template_dir = custom_template_dir
        # Get the path to ntc-templates
        self.ntc_templates_dir = Path(ntc_templates.__file__).parent / "templates"
        
        if custom_template_dir and not custom_template_dir.exists():
            logger.warning(f"Custom template directory does not exist: {custom_template_dir}")
    
    def parse(
        self, 
        raw_output: str, 
        template_name: Optional[str] = None,
        platform: Optional[str] = None,
        command: Optional[str] = None,
        include_raw: bool = False
    ) -> Dict[str, Any]:
        """Parse raw output using TextFSM template.
        
        Args:
            raw_output: Raw text output from network device
            template_name: Explicit template name (e.g., "cisco_ios_show_ip_int_brief.textfsm")
            platform: Platform/device type for auto-discovery (e.g., "cisco_ios")
            command: Command for auto-discovery (e.g., "show ip int brief")
            include_raw: If True, include raw output in response
            
        Note: Either template_name OR (platform + command) must be provided.
              template_name takes precedence for explicit control.
            
        Returns:
            Dict containing parsed data and optionally raw output.
            On error, returns error information.
        """
        try:
            # Mode 1: Explicit template (highest priority)
            if template_name:
                template_path = self._find_template(template_name)
            
                if not template_path:
                    error_msg = f"Template not found: {template_name}"
                    logger.error(error_msg)
                    return {
                        "error": error_msg,
                        "raw": raw_output if include_raw else None
                    }
                
                # Parse with TextFSM
                with open(template_path) as f:
                    fsm = textfsm.TextFSM(f)
                    parsed_data = fsm.ParseText(raw_output)
                
                # Convert to list of dicts using header
                headers = [header.lower() for header in fsm.header]
                result = [dict(zip(headers, row)) for row in parsed_data]
                
            # Mode 2: Auto-discovery via ntc_templates
            elif platform and command:
                from ntc_templates.parse import parse_output
                
                try:
                    result = parse_output(
                        platform=platform,
                        command=command,
                        data=raw_output
                    )
                    # parse_output returns list of dicts already
                except Exception as e:
                    error_msg = f"Auto-discovery failed for {platform}/{command}: {str(e)}"
                    logger.error(error_msg)
                    return {
                        "error": error_msg,
                        "raw": raw_output if include_raw else None
                    }
            
            else:
                error_msg = "Either template_name OR (platform + command) required"
                logger.error(error_msg)
                return {
                    "error": error_msg,
                    "raw": raw_output if include_raw else None
                }
            
            response = {"parsed": result}
            if include_raw:
                response["raw"] = raw_output
                
            return response
            
        except Exception as e:
            error_msg = f"Parsing failed: {str(e)}"
            logger.error(error_msg)
            return {
                "error": error_msg,
                "raw": raw_output if include_raw else None
            }
    
    def _find_template(self, template_name: str) -> Optional[Path]:
        """Find template file, checking custom dir first, then ntc-templates.
        
        Args:
            template_name: Name of template file
            
        Returns:
            Path to template file, or None if not found
        """
        # Ensure .textfsm extension
        if not template_name.endswith('.textfsm'):
            template_name += '.textfsm'
        
        # Check custom templates first
        if self.custom_template_dir:
            custom_path = self.custom_template_dir / template_name
            if custom_path.exists():
                logger.debug(f"Using custom template: {custom_path}")
                return custom_path
        
        # Fall back to ntc-templates
        ntc_path = self.ntc_templates_dir / template_name
        if ntc_path.exists():
            logger.debug(f"Using ntc-template: {ntc_path}")
            return ntc_path
        
        return None
    
    def list_templates(self) -> Dict[str, List[str]]:
        """List all available templates.
        
        Returns:
            Dict with 'custom' and 'ntc' template lists
        """
        templates = {"custom": [], "ntc": []}
        
        # List custom templates
        if self.custom_template_dir and self.custom_template_dir.exists():
            templates["custom"] = sorted([
                f.name for f in self.custom_template_dir.glob("*.textfsm")
            ])
        
        # List ntc-templates  
        if self.ntc_templates_dir.exists():
            templates["ntc"] = sorted([
                f.name for f in self.ntc_templates_dir.glob("*.textfsm")
            ])
        
        return templates