import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ttp import ttp

logger = logging.getLogger(__name__)


class TTPParser:
    
    def __init__(self, custom_template_dir: Optional[Path] = None):
        self.custom_template_dir = custom_template_dir
        
        if custom_template_dir and not custom_template_dir.exists():
            logger.warning(f"Custom template directory does not exist: {custom_template_dir}")
    
    def parse(
        self, 
        raw_output: str, 
        template_name: Optional[str] = None,
        template_string: Optional[str] = None,
        platform: Optional[str] = None,
        include_raw: bool = False
    ) -> Dict[str, Any]:
        try:
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
                
            elif template_string:
                parser = ttp(data=raw_output, template=template_string)
                parser.parse()
                result = parser.result(structure="flat_list")
                
            elif platform:
                parser = ttp(data=raw_output, platform=platform)
                parser.parse()
                result = parser.result(structure="flat_list")
                
            else:
                error_msg = "Either template_name, template_string, OR platform required"
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
