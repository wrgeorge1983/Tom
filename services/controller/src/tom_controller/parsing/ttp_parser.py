import csv
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ttp import ttp

logger = logging.getLogger(__name__)


class TTPParser:
    
    def __init__(self, custom_template_dir: Optional[Path] = None):
        self.custom_template_dir = custom_template_dir
        self._index_cache = None
        
        if custom_template_dir and not custom_template_dir.exists():
            logger.warning(f"Custom template directory does not exist: {custom_template_dir}")
    
    def parse(
        self, 
        raw_output: str, 
        template_name: Optional[str] = None,
        template_string: Optional[str] = None,
        platform: Optional[str] = None,
        command: Optional[str] = None,
        hostname: Optional[str] = None,
        include_raw: bool = False
    ) -> Dict[str, Any]:
        try:
            # Mode 1: Explicit template name
            if template_name:
                template_path = self._find_template(template_name)
                
                if not template_path:
                    error_msg = f"Template not found: {template_name}"
                    logger.error(error_msg)
                    return {
                        "error": error_msg,
                        "raw": raw_output if include_raw else None
                    }
                
                with open(template_path) as f:
                    template_content = f.read()
                
                parser = ttp(data=raw_output, template=template_content)
                parser.parse()
                result = parser.result(structure="flat_list")
            
            # Mode 2: Inline template string
            elif template_string:
                parser = ttp(data=raw_output, template=template_string)
                parser.parse()
                result = parser.result(structure="flat_list")
            
            # Mode 3: Auto-discovery via custom index
            elif platform and command:
                template_path = self._lookup_template_from_index(
                    platform=platform,
                    command=command,
                    hostname=hostname
                )
                
                if not template_path:
                    error_msg = f"No template found in index for platform={platform}, command={command}"
                    logger.error(error_msg)
                    return {
                        "error": error_msg,
                        "raw": raw_output if include_raw else None
                    }
                
                with open(template_path) as f:
                    template_content = f.read()
                
                logger.debug(f"Using template from index: {template_path.name}")
                parser = ttp(data=raw_output, template=template_content)
                parser.parse()
                result = parser.result(structure="flat_list")
                
            else:
                error_msg = "Either template_name, template_string, OR (platform + command) required"
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
        if not template_name.endswith('.ttp'):
            template_name += '.ttp'
        
        if self.custom_template_dir:
            custom_path = self.custom_template_dir / template_name
            if custom_path.exists():
                logger.debug(f"Using custom template: {custom_path}")
                return custom_path
        
        return None
    
    def list_templates(self) -> Dict[str, List[str]]:
        templates = {"custom": []}
        
        if self.custom_template_dir and self.custom_template_dir.exists():
            templates["custom"] = sorted([
                f.name for f in self.custom_template_dir.glob("*.ttp")
            ])
        
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
            with open(index_file, 'r') as f:
                # Filter out comment lines and empty lines
                lines = [line for line in f if line.strip() and not line.strip().startswith('#')]
                
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
        self,
        platform: str,
        command: str,
        hostname: Optional[str] = None
    ) -> Optional[Path]:
        """Look up a template from the index based on platform, command, and hostname.
        
        Args:
            platform: Device platform (e.g., 'cisco_ios')
            command: Command that was run (e.g., 'show version')
            hostname: Device hostname for hostname-based matching (optional)
            
        Returns:
            Path to template file if found, None otherwise
        """
        entries = self._load_index()
        if not entries:
            return None
        
        hostname = hostname or ".*"
        
        # Find matching entry
        for entry in entries:
            try:
                # Check platform match
                if entry.get('platform') != platform:
                    continue
                
                # Check hostname regex match
                hostname_pattern = entry.get('hostname', '.*')
                if not re.match(hostname_pattern, hostname, re.IGNORECASE):
                    continue
                
                # Check command regex match
                command_pattern = entry.get('command', '')
                if not re.match(command_pattern, command, re.IGNORECASE):
                    continue
                
                # Found a match!
                template_name = entry.get('template')
                if not template_name:
                    continue
                
                template_path = self._find_template(template_name)
                if template_path and template_path.exists():
                    logger.debug(f"Index matched: {template_name} for {platform}/{command}")
                    return template_path
                else:
                    logger.warning(f"Template in index not found: {template_name}")
                    
            except re.error as e:
                logger.warning(f"Invalid regex in index entry: {e}")
                continue
        
        return None
