import csv
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ttp import ttp
import ttp_templates

from tom_controller.exceptions import TomParsingException, TomTemplateNotFoundException

logger = logging.getLogger(__name__)

# Get the path to ttp_templates package
TTP_TEMPLATES_DIR = Path(ttp_templates.__file__).parent / "platform"


class TTPParser:
    def __init__(self, custom_template_dir: Optional[Path] = None):
        self.custom_template_dir = custom_template_dir
        self._index_cache = None

        if custom_template_dir and not custom_template_dir.exists():
            logger.warning(
                f"Custom template directory does not exist: {custom_template_dir}"
            )

    def parse(
        self,
        raw_output: str,
        template_name: Optional[str] = None,
        template_string: Optional[str] = None,
        platform: Optional[str] = None,
        command: Optional[str] = None,
        hostname: Optional[str] = None,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        # Initialize metadata tracking
        template_source = None
        matched_template = None

        # Mode 1: Explicit template name
        if template_name:
            template_path, source = self._find_template(template_name)

            if not template_path:
                raise TomTemplateNotFoundException(
                    f"Template not found: {template_name}"
                )

            with open(template_path) as f:
                template_content = f.read()

            matched_template = template_path.name
            template_source = source or "explicit"

            try:
                parser = ttp(data=raw_output, template=template_content)
                parser.parse()
                result = parser.result(structure="flat_list")
            except Exception as e:
                raise TomParsingException(f"TTP parsing failed: {e}") from e

        # Mode 2: Inline template string
        elif template_string:
            template_source = "inline"
            try:
                parser = ttp(data=raw_output, template=template_string)
                parser.parse()
                result = parser.result(structure="flat_list")
            except Exception as e:
                raise TomParsingException(f"TTP parsing failed: {e}") from e

        # Mode 3: Auto-discovery via custom index or ttp_templates
        elif platform and command:
            template_path, template_source, matched_template = self.discover_template(
                platform=platform, command=command, hostname=hostname
            )

            if not template_path:
                raise TomTemplateNotFoundException(
                    f"No template found for platform={platform}, command={command}"
                )

            with open(template_path) as f:
                template_content = f.read()

            logger.info(
                f"Using TTP template ({template_source}): {matched_template} for {platform}/{command}"
            )

            try:
                parser = ttp(data=raw_output, template=template_content)
                parser.parse()
                result = parser.result(structure="flat_list")
            except Exception as e:
                raise TomParsingException(f"TTP parsing failed: {e}") from e

        else:
            raise TomParsingException(
                "Either template_name, template_string, OR (platform + command) required for parsing"
            )

        response: Dict[str, Any] = {"parsed": result}
        if include_raw:
            response["raw"] = raw_output

        # Add metadata about template selection
        if template_source:
            response["_metadata"] = {"template_source": template_source}
            if matched_template:
                response["_metadata"]["template_name"] = matched_template

        return response

    def _find_template(
        self, template_name: str
    ) -> Tuple[Optional[Path], Optional[str]]:
        """Find template file, checking custom dir first, then ttp_templates package.

        Args:
            template_name: Name of template file

        Returns:
            Tuple of (path, source) where source is "custom" or "ttp_templates"
            Returns (None, None) if not found
        """
        # Handle both .ttp and .txt extensions (ttp_templates uses .txt)
        base_name = template_name
        if template_name.endswith(".ttp"):
            base_name = template_name[:-4]
        elif template_name.endswith(".txt"):
            base_name = template_name[:-4]

        # Check custom templates first (.ttp extension)
        if self.custom_template_dir:
            custom_path = self.custom_template_dir / f"{base_name}.ttp"
            if custom_path.exists():
                logger.debug(f"Using custom template: {custom_path}")
                return custom_path, "custom"

        # Fall back to ttp_templates package (.txt extension)
        if TTP_TEMPLATES_DIR.exists():
            ttp_templates_path = TTP_TEMPLATES_DIR / f"{base_name}.txt"
            if ttp_templates_path.exists():
                logger.debug(f"Using ttp_templates: {ttp_templates_path}")
                return ttp_templates_path, "ttp_templates"

        return None, None

    def list_templates(self) -> Dict[str, List[str]]:
        """List all available templates.

        Returns:
            Dict with 'custom' and 'ttp_templates' template lists
        """
        templates: Dict[str, List[str]] = {"custom": [], "ttp_templates": []}

        # List custom templates
        if self.custom_template_dir and self.custom_template_dir.exists():
            templates["custom"] = sorted(
                [f.name for f in self.custom_template_dir.glob("*.ttp")]
            )

        # List ttp_templates package templates
        if TTP_TEMPLATES_DIR.exists():
            templates["ttp_templates"] = sorted(
                [f.name for f in TTP_TEMPLATES_DIR.glob("*.txt")]
            )

        return templates

    def _load_index(self) -> List[Dict[str, str]]:
        """Load and parse the TTP template index file.

        Returns:
            List of index entries as dicts with keys: template, hostname, platform, command
        """
        if self._index_cache is not None:
            return self._index_cache

        if not self.custom_template_dir:
            return []

        index_file = self.custom_template_dir / "index"
        if not index_file.exists():
            logger.debug(f"No index file found at {index_file}")
            return []

        entries = []
        try:
            with open(index_file, "r") as f:
                # Filter out comment lines and empty lines
                lines = [
                    line
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                ]

                reader = csv.DictReader(lines, skipinitialspace=True)
                for row in reader:
                    # Normalize keys to lowercase and strip values
                    entry = {k.lower().strip(): v.strip() for k, v in row.items() if k}
                    if entry:  # Only add non-empty entries
                        entries.append(entry)

            self._index_cache = entries
            logger.debug(f"Loaded {len(entries)} entries from TTP index")
            return entries

        except Exception as e:
            logger.error(f"Failed to load TTP index: {e}")
            return []

    def _lookup_template_from_index(
        self, platform: str, command: str, hostname: Optional[str] = None
    ) -> Tuple[Optional[Path], Optional[str]]:
        """Look up a template from the custom index based on platform, command, and hostname.

        Args:
            platform: Device platform (e.g., 'cisco_ios')
            command: Command that was run (e.g., 'show version')
            hostname: Device hostname for hostname-based matching (optional)

        Returns:
            Tuple of (path, source) where source is "custom"
            Returns (None, None) if not found
        """
        entries = self._load_index()
        if not entries:
            return None, None

        hostname = hostname or ".*"

        # Find matching entry
        for entry in entries:
            try:
                # Check platform match
                if entry.get("platform") != platform:
                    continue

                # Check hostname regex match
                hostname_pattern = entry.get("hostname", ".*")
                if not re.match(hostname_pattern, hostname, re.IGNORECASE):
                    continue

                # Check command regex match
                command_pattern = entry.get("command", "")
                if not re.match(command_pattern, command, re.IGNORECASE):
                    continue

                # Found a match!
                template_name = entry.get("template")
                if not template_name:
                    continue

                template_path, source = self._find_template(template_name)
                if template_path and template_path.exists():
                    logger.debug(
                        f"Index matched: {template_name} for {platform}/{command}"
                    )
                    return template_path, source
                else:
                    logger.warning(f"Template in index not found: {template_name}")

            except re.error as e:
                logger.warning(f"Invalid regex in index entry: {e}")
                continue

        return None, None

    def _lookup_ttp_templates(
        self, platform: str, command: str
    ) -> Tuple[Optional[Path], Optional[str]]:
        """Look up a template from the ttp_templates package.

        Uses the same naming convention as ntc-templates:
        {platform}_{command_with_underscores}.txt

        Args:
            platform: Device platform (e.g., 'cisco_ios')
            command: Command that was run (e.g., 'show ip arp')

        Returns:
            Tuple of (path, source) where source is "ttp_templates"
            Returns (None, None) if not found
        """
        if not TTP_TEMPLATES_DIR.exists():
            return None, None

        # Build template name following ttp_templates convention
        # Command: "show ip arp" -> "show_ip_arp"
        # Pipe: "show run | sec interface" -> "show_run_pipe_sec_interface"
        normalized_command = command.lower()
        normalized_command = normalized_command.replace(" | ", "_pipe_")
        normalized_command = normalized_command.replace("|", "_pipe_")
        normalized_command = normalized_command.replace(" ", "_")
        normalized_command = normalized_command.replace("-", "_")

        template_name = f"{platform}_{normalized_command}.txt"
        template_path = TTP_TEMPLATES_DIR / template_name

        if template_path.exists():
            logger.debug(f"Found ttp_templates template: {template_path}")
            return template_path, "ttp_templates"

        return None, None

    def discover_template(
        self, platform: str, command: str, hostname: Optional[str] = None
    ) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
        """Discover which template to use for given platform/command.

        Checks custom index first, then ttp_templates package.

        Args:
            platform: Device platform (e.g., 'cisco_ios')
            command: Command to match (e.g., 'show version')
            hostname: Device hostname for matching (default: '.*')

        Returns:
            Tuple of (template_path, source, template_name)
            Returns (None, None, None) if no match found
        """
        # 1. Check custom index first
        template_path, source = self._lookup_template_from_index(
            platform=platform, command=command, hostname=hostname
        )
        if template_path:
            return template_path, source, template_path.name

        # 2. Fall back to ttp_templates package
        template_path, source = self._lookup_ttp_templates(
            platform=platform, command=command
        )
        if template_path:
            return template_path, source, template_path.name

        return None, None, None
