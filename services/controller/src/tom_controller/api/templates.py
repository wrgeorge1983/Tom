import csv
import logging
from io import StringIO
from pathlib import Path
from typing import Literal, Optional, List

import textfsm
from fastapi import APIRouter, Query
from pydantic import BaseModel
from starlette.requests import Request
from ttp import ttp

from tom_controller.exceptions import (
    TomNotFoundException,
    TomValidationException,
    TomException,
)
from tom_controller.inventory.inventory import InventoryStore
from tom_controller.parsing import TextFSMParser, TTPParser, parse_output

logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])


def _read_index(index_path: Path) -> List[dict]:
    """Read and parse the index file.

    Returns:
        List of index entries as dicts with keys: template, hostname, platform, command
    """
    if not index_path.exists():
        return []

    entries = []
    try:
        with open(index_path, "r") as f:
            lines = [
                line for line in f if line.strip() and not line.strip().startswith("#")
            ]
            if not lines:
                return []

            reader = csv.DictReader(lines, skipinitialspace=True)
            for row in reader:
                entry = {k.lower().strip(): v.strip() for k, v in row.items() if k}
                if entry:
                    entries.append(entry)
    except Exception as e:
        logger.warning(f"Error reading index file {index_path}: {e}")

    return entries


def _write_index(index_path: Path, entries: List[dict]) -> None:
    """Write entries to the index file.

    Args:
        index_path: Path to the index file
        entries: List of index entries as dicts
    """
    try:
        with open(index_path, "w", newline="") as f:
            # Write header
            f.write("Template, Hostname, Platform, Command\n")
            for entry in entries:
                template = entry.get("template", "")
                hostname = entry.get("hostname", ".*")
                platform = entry.get("platform", "")
                command = entry.get("command", "")
                f.write(f"{template}, {hostname}, {platform}, {command}\n")
    except Exception as e:
        logger.error(f"Error writing index file {index_path}: {e}")
        raise TomException(f"Cannot write index file: {e}")


def _add_to_index(
    index_path: Path,
    template_name: str,
    platform: str,
    command: str,
    hostname: str = ".*",
) -> None:
    """Add or update a template entry in the index file.

    Args:
        index_path: Path to the index file
        template_name: Name of the template file
        platform: Platform/device type (e.g., "cisco_ios")
        command: Command regex pattern (e.g., "show vlan")
        hostname: Hostname regex pattern (default: ".*")
    """
    entries = _read_index(index_path)

    # Remove any existing entry for this template
    entries = [e for e in entries if e.get("template") != template_name]

    # Add the new entry
    entries.append(
        {
            "template": template_name,
            "hostname": hostname,
            "platform": platform,
            "command": command,
        }
    )

    _write_index(index_path, entries)
    logger.info(f"Added/updated index entry for {template_name}")


def _remove_from_index(index_path: Path, template_name: str) -> bool:
    """Remove a template entry from the index file.

    Args:
        index_path: Path to the index file
        template_name: Name of the template to remove

    Returns:
        True if entry was found and removed, False otherwise
    """
    entries = _read_index(index_path)
    original_count = len(entries)

    entries = [e for e in entries if e.get("template") != template_name]

    if len(entries) < original_count:
        _write_index(index_path, entries)
        logger.info(f"Removed index entry for {template_name}")
        return True

    return False


class TemplateMatch(BaseModel):
    """Information about a matched template."""

    template_name: str
    source: str  # "custom", "ntc-templates", etc.
    parser: Literal["textfsm", "ttp"]


class TemplateMatchResponse(BaseModel):
    """Response for template match lookup."""

    device_type: str
    command: str
    matches: List[TemplateMatch]


class TemplateContent(BaseModel):
    """Full template information including content."""

    name: str
    parser: Literal["textfsm", "ttp"]
    source: str  # "custom", "ntc" (textfsm only)
    content: str


class TemplateCreateRequest(BaseModel):
    """Request to create a new template."""

    name: str
    content: str
    overwrite: bool = False
    # Index entry fields for auto-discovery
    platform: Optional[str] = None
    command: Optional[str] = None
    hostname: Optional[str] = None


class TemplateCreateResponse(BaseModel):
    """Response after creating a template."""

    name: str
    parser: Literal["textfsm", "ttp"]
    created: bool
    validation_warnings: Optional[List[str]] = None


class TemplateDeleteResponse(BaseModel):
    """Response after deleting a template."""

    name: str
    deleted: bool


class ParseTestRequest(BaseModel):
    """Request to test parsing raw output."""

    raw_output: str
    parser: Literal["textfsm", "ttp"] = "textfsm"
    template: Optional[str] = None
    template_source: Optional[str] = None
    device_type: Optional[str] = None
    command: Optional[str] = None
    include_raw: bool = False


@router.get("/templates/textfsm")
async def list_textfsm_templates(request: Request):
    """List all available TextFSM templates."""

    settings = request.app.state.settings
    template_dir = Path(settings.textfsm_template_dir)
    parser = TextFSMParser(custom_template_dir=template_dir)
    return parser.list_templates()


@router.get("/templates/match")
async def match_template(
    request: Request,
    command: str = Query(
        ..., description="Command to find template for (e.g., 'show version')"
    ),
    device_type: Optional[str] = Query(
        None,
        description="Device type/platform (e.g., 'cisco_ios'). Required if device not specified.",
    ),
    device: Optional[str] = Query(
        None,
        description="Inventory device name. If provided, device_type is looked up from inventory.",
    ),
    parser: Optional[Literal["textfsm", "ttp"]] = Query(
        None, description="Parser type to check. If not specified, checks both."
    ),
) -> TemplateMatchResponse:
    """Find which template(s) would be used to parse a command for a given device type.

    You must provide either `device_type` or `device` (inventory lookup).
    If both are provided, `device` takes precedence.

    Returns information about matching templates from both TextFSM and TTP parsers
    (or just one if `parser` is specified).
    """
    settings = request.app.state.settings

    # Resolve device_type from inventory if device name provided
    resolved_device_type = device_type
    if device:
        inventory_store: InventoryStore = request.app.state.inventory_store
        try:
            device_config = inventory_store.get_device_config(device)
            resolved_device_type = device_config.adapter_driver
        except KeyError:
            raise TomNotFoundException(f"Device '{device}' not found in inventory")

    if not resolved_device_type:
        raise TomValidationException(
            "Must provide either 'device_type' or 'device' parameter"
        )

    matches: List[TemplateMatch] = []

    # Check TextFSM templates
    if parser is None or parser == "textfsm":
        textfsm_parser = TextFSMParser(
            custom_template_dir=Path(settings.textfsm_template_dir)
        )
        template_path, source, template_name = textfsm_parser._discover_template(
            platform=resolved_device_type,
            command=command,
        )
        if template_name and source:
            matches.append(
                TemplateMatch(
                    template_name=template_name,
                    source=source,
                    parser="textfsm",
                )
            )

    # Check TTP templates
    if parser is None or parser == "ttp":
        ttp_parser = TTPParser(custom_template_dir=Path(settings.ttp_template_dir))
        ttp_template_path, ttp_source, ttp_template_name = ttp_parser.discover_template(
            platform=resolved_device_type,
            command=command,
        )
        if ttp_template_path and ttp_source and ttp_template_name:
            matches.append(
                TemplateMatch(
                    template_name=ttp_template_name,
                    source=ttp_source,
                    parser="ttp",
                )
            )

    return TemplateMatchResponse(
        device_type=resolved_device_type,
        command=command,
        matches=matches,
    )


@router.post("/parse/test")
async def test_parse(
    request: Request,
    body: ParseTestRequest,
):
    """Test parsing endpoint - parse raw text with a specified template.

    This is a convenience endpoint for testing templates without executing commands.

    You must provide either:
    - `template`: Explicit template name (e.g., "cisco_ios_show_version.textfsm")
    - `device_type` + `command`: For automatic template discovery

    Example request:
    ```json
    {
      "raw_output": "Cisco IOS Software, Version 15.1...",
      "parser": "textfsm",
      "template": "cisco_ios_show_version.textfsm"
    }
    ```
    """
    settings = request.app.state.settings

    return parse_output(
        raw_output=body.raw_output,
        settings=settings,
        device_type=body.device_type,
        command=body.command,
        template=body.template,
        template_source=body.template_source,
        include_raw=body.include_raw,
        parser_type=body.parser,
    )


@router.get("/templates/ttp")
async def list_ttp_templates(request: Request):
    """List all available TTP templates."""
    settings = request.app.state.settings
    template_dir = Path(settings.ttp_template_dir)
    parser = TTPParser(custom_template_dir=template_dir)
    return parser.list_templates()


@router.get("/templates/{parser_type}/{template_name}")
async def get_template(
    request: Request,
    parser_type: Literal["textfsm", "ttp"],
    template_name: str,
) -> TemplateContent:
    """Get the contents of a specific template.

    For TextFSM templates, both custom and ntc-templates can be retrieved.
    For TTP templates, only custom templates are available.
    """
    settings = request.app.state.settings

    if parser_type == "textfsm":
        template_dir = Path(settings.textfsm_template_dir)
        parser = TextFSMParser(custom_template_dir=template_dir)
        template_path, source = parser._find_template(template_name)

        if not template_path:
            raise TomNotFoundException(f"Template not found: {template_name}")

        content = template_path.read_text()
        return TemplateContent(
            name=template_path.name,
            parser="textfsm",
            source=source or "custom",
            content=content,
        )

    elif parser_type == "ttp":
        template_dir = Path(settings.ttp_template_dir)
        parser = TTPParser(custom_template_dir=template_dir)
        template_path, source = parser._find_template(template_name)

        if not template_path:
            raise TomNotFoundException(f"Template not found: {template_name}")

        content = template_path.read_text()
        return TemplateContent(
            name=template_path.name,
            parser="ttp",
            source=source or "custom",
            content=content,
        )

    else:
        raise TomValidationException(
            f"Parser type '{parser_type}' not supported. Use 'textfsm' or 'ttp'"
        )


@router.post("/templates/{parser_type}")
async def create_template(
    request: Request,
    parser_type: Literal["textfsm", "ttp"],
    body: TemplateCreateRequest,
) -> TemplateCreateResponse:
    """Create a new custom template.

    Templates are validated before saving:
    - TextFSM templates are compiled to check syntax
    - TTP templates are instantiated to catch any initialization errors

    If validation fails, the template is still created but warnings are returned.
    """
    settings = request.app.state.settings
    validation_warnings: List[str] = []

    # Determine template directory and validate extension
    if parser_type == "textfsm":
        template_dir = Path(settings.textfsm_template_dir)
        expected_ext = ".textfsm"
    elif parser_type == "ttp":
        template_dir = Path(settings.ttp_template_dir)
        expected_ext = ".ttp"
    else:
        raise TomValidationException(
            f"Parser type '{parser_type}' not supported. Use 'textfsm' or 'ttp'"
        )

    # Normalize template name
    template_name = body.name
    if not template_name.endswith(expected_ext):
        template_name += expected_ext

    # Security: prevent path traversal
    if "/" in template_name or "\\" in template_name or ".." in template_name:
        raise TomValidationException(
            "Template name cannot contain path separators or '..'"
        )

    template_path = template_dir / template_name

    # Check if template already exists
    if template_path.exists() and not body.overwrite:
        raise TomValidationException(
            f"Template '{template_name}' already exists. Set overwrite=true to replace."
        )

    # Validate template syntax
    if parser_type == "textfsm":
        try:
            fsm = textfsm.TextFSM(StringIO(body.content))
            logger.debug(f"TextFSM template validated, fields: {fsm.header}")
        except textfsm.TextFSMTemplateError as e:
            validation_warnings.append(f"TextFSM syntax error: {e}")
        except Exception as e:
            validation_warnings.append(f"Unexpected validation error: {e}")
    else:  # ttp
        try:
            parser = ttp(template=body.content)
            # TTP doesn't raise on most syntax errors, but try to catch what we can
        except Exception as e:
            validation_warnings.append(f"TTP initialization error: {e}")

    # Ensure directory exists
    try:
        template_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise TomException(f"Cannot create template directory: {e}")

    # Write template
    try:
        template_path.write_text(body.content)
    except OSError as e:
        raise TomException(f"Cannot write template file: {e}")

    # Add to index if platform and command are provided
    if body.platform and body.command:
        index_path = template_dir / "index"
        try:
            _add_to_index(
                index_path=index_path,
                template_name=template_name,
                platform=body.platform,
                command=body.command,
                hostname=body.hostname or ".*",
            )
        except Exception as e:
            validation_warnings.append(f"Failed to update index: {e}")

    return TemplateCreateResponse(
        name=template_name,
        parser=parser_type,
        created=True,
        validation_warnings=validation_warnings if validation_warnings else None,
    )


@router.delete("/templates/{parser_type}/{template_name}")
async def delete_template(
    request: Request,
    parser_type: Literal["textfsm", "ttp"],
    template_name: str,
) -> TemplateDeleteResponse:
    """Delete a custom template.

    Only custom templates can be deleted. Attempting to delete an ntc-template
    will return a 403 error.
    """
    settings = request.app.state.settings

    # Determine template directory
    if parser_type == "textfsm":
        template_dir = Path(settings.textfsm_template_dir)
        expected_ext = ".textfsm"
    elif parser_type == "ttp":
        template_dir = Path(settings.ttp_template_dir)
        expected_ext = ".ttp"
    else:
        raise TomValidationException(
            f"Parser type '{parser_type}' not supported. Use 'textfsm' or 'ttp'"
        )

    # Normalize template name
    if not template_name.endswith(expected_ext):
        template_name += expected_ext

    # Security: prevent path traversal
    if "/" in template_name or "\\" in template_name or ".." in template_name:
        raise TomValidationException(
            "Template name cannot contain path separators or '..'"
        )

    template_path = template_dir / template_name

    # Check if this is a custom template (in our template_dir)
    if not template_path.exists():
        # For TextFSM, check if it exists in ntc-templates
        if parser_type == "textfsm":
            parser = TextFSMParser(custom_template_dir=template_dir)
            ntc_path = parser.ntc_templates_dir / template_name
            if ntc_path.exists():
                raise TomValidationException(
                    f"Cannot delete ntc-template '{template_name}'. Only custom templates can be deleted."
                )
        raise TomNotFoundException(f"Template not found: {template_name}")

    # Delete the template
    try:
        template_path.unlink()
    except OSError as e:
        raise TomException(f"Cannot delete template file: {e}")

    # Remove from index if present
    index_path = template_dir / "index"
    if index_path.exists():
        try:
            _remove_from_index(index_path, template_name)
        except Exception as e:
            logger.warning(f"Failed to remove {template_name} from index: {e}")

    return TemplateDeleteResponse(name=template_name, deleted=True)
