"""TextFSM parser implementation."""

import csv
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import textfsm
import ntc_templates

from tom_controller.exceptions import TomParsingException, TomTemplateNotFoundException

logger = logging.getLogger(__name__)


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
            logger.warning(
                f"Custom template directory does not exist: {custom_template_dir}"
            )

    def parse(
        self,
        raw_output: str,
        template_name: Optional[str] = None,
        platform: Optional[str] = None,
        command: Optional[str] = None,
        include_raw: bool = False,
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
        # Initialize metadata tracking
        template_source = None
        matched_template = None

        # Mode 1: Explicit template name
        if template_name:
            template_path = self._find_template(template_name)

            if not template_path:
                raise TomTemplateNotFoundException(
                    f"Template not found: {template_name}"
                )

            # Parse with TextFSM
            try:
                with open(template_path) as f:
                    fsm = textfsm.TextFSM(f)
                    parsed_data = fsm.ParseText(raw_output)
            except Exception as e:
                raise TomParsingException(f"TextFSM parsing failed: {e}") from e

            # Convert to list of dicts using header
            headers = [header.lower() for header in fsm.header]
            result = [dict(zip(headers, row)) for row in parsed_data]

        # Mode 2: Auto-discovery - find template ourselves
        elif platform and command:
            # Look up the template from our indexes
            template_path, template_source, matched_template = self._discover_template(
                platform=platform, command=command
            )

            if not template_path:
                raise TomTemplateNotFoundException(
                    f"No template found for platform={platform}, command={command}"
                )

            logger.info(
                f"Using {template_source} template: {matched_template} for {platform}/{command}"
            )

            # Parse with TextFSM directly
            try:
                with open(template_path) as f:
                    fsm = textfsm.TextFSM(f)
                    parsed_data = fsm.ParseText(raw_output)
            except Exception as e:
                raise TomParsingException(f"TextFSM parsing failed: {e}") from e

            # Convert to list of dicts using header
            headers = [header.lower() for header in fsm.header]
            result = [dict(zip(headers, row)) for row in parsed_data]

        else:
            raise TomParsingException(
                "Either template_name OR (platform + command) required for parsing"
            )

        response: Dict[str, Any] = {"parsed": result}
        if include_raw:
            response["raw"] = raw_output

        # Add metadata about template selection (if available)
        if template_source:
            response["_metadata"] = {"template_source": template_source}
            if matched_template:
                response["_metadata"]["template_name"] = matched_template

        return response

    def _find_template(self, template_name: str) -> Optional[Path]:
        """Find template file, checking custom dir first, then ntc-templates.

        Args:
            template_name: Name of template file

        Returns:
            Path to template file, or None if not found
        """
        # Ensure .textfsm extension
        if not template_name.endswith(".textfsm"):
            template_name += ".textfsm"

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
            templates["custom"] = sorted(
                [f.name for f in self.custom_template_dir.glob("*.textfsm")]
            )

        # List ntc-templates
        if self.ntc_templates_dir.exists():
            templates["ntc"] = sorted(
                [f.name for f in self.ntc_templates_dir.glob("*.textfsm")]
            )

        return templates

    def _discover_template(
        self, platform: str, command: str, hostname: str = ".*"
    ) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
        """Discover which template to use for given platform/command.

        Checks custom index first, then ntc-templates index.

        Args:
            platform: Device platform (e.g., 'cisco_ios')
            command: Command to match (e.g., 'show version')
            hostname: Device hostname for matching (default: '.*')

        Returns:
            Tuple of (template_path, source, template_name)
            - template_path: Full path to template file
            - source: "custom" or "ntc-templates"
            - template_name: Name of the template file
            Returns (None, None, None) if no match found
        """
        # 1. Check custom index first
        if self.custom_template_dir:
            custom_index = self.custom_template_dir / "index"
            if custom_index.exists():
                match = self._lookup_in_index(
                    index_file=custom_index,
                    platform=platform,
                    command=command,
                    hostname=hostname,
                )
                if match:
                    template_path = self.custom_template_dir / match
                    if template_path.exists():
                        return (template_path, "custom", match)
                    else:
                        logger.warning(f"Custom template in index not found: {match}")

        # 2. Check ntc-templates index
        ntc_index = self.ntc_templates_dir / "index"
        if ntc_index.exists():
            match = self._lookup_in_index(
                index_file=ntc_index,
                platform=platform,
                command=command,
                hostname=hostname,
            )
            if match:
                template_path = self.ntc_templates_dir / match
                if template_path.exists():
                    return (template_path, "ntc-templates", match)

        return (None, None, None)

    def _lookup_in_index(
        self, index_file: Path, platform: str, command: str, hostname: str = ".*"
    ) -> Optional[str]:
        """Look up a template in a specific index file.

        Args:
            index_file: Path to index file
            platform: Device platform
            command: Command to match
            hostname: Device hostname for matching

        Returns:
            Template name if found, None otherwise
        """
        try:
            with open(index_file, "r") as f:
                # Filter out comments and empty lines
                lines = [
                    line
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                ]

                reader = csv.DictReader(lines, skipinitialspace=True)
                for row in reader:
                    # Normalize keys
                    entry = {k.lower().strip(): v.strip() for k, v in row.items() if k}

                    # Check platform match (exact match)
                    if entry.get("platform") != platform:
                        continue

                    # Check hostname regex match
                    hostname_pattern = entry.get("hostname", ".*")
                    try:
                        if not re.match(hostname_pattern, hostname, re.IGNORECASE):
                            continue
                    except re.error as e:
                        logger.warning(
                            f"Invalid hostname regex in index: {hostname_pattern}"
                        )
                        continue

                    # Check command regex match
                    # ntc-templates uses special [[]] syntax for optional parts
                    command_pattern = entry.get("command", "")
                    command_pattern = self._expand_optional_syntax(command_pattern)

                    try:
                        if re.match(command_pattern, command, re.IGNORECASE):
                            return entry.get("template")
                    except re.error as e:
                        logger.warning(
                            f"Invalid command regex in index: {command_pattern}"
                        )
                        continue

            return None

        except Exception as e:
            logger.warning(f"Error reading index {index_file}: {e}")
            return None

    def _expand_optional_syntax(self, pattern: str) -> str:
        """Expand ntc-templates [[]] optional syntax to standard regex.

        abc[[xyz]] becomes abc(x(y(z)?)?)?

        Args:
            pattern: Pattern with [[]] syntax

        Returns:
            Standard regex pattern
        """

        def replace_bracket(match):
            content = match.group(1)
            if not content:
                return ""
            # Build nested optional groups from right to left
            # xyz becomes (x(y(z)?)?)?
            result = content[-1]
            for char in reversed(content[:-1]):
                result = f"{char}({result})?"
            return f"({result})?"

        # Replace [[...]] with optional regex
        expanded = re.sub(r"\[\[([^\]]+)\]\]", replace_bracket, pattern)
        return expanded
