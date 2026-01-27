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
from tom_controller.inventory.inventory import InventoryService
from tom_controller.parsing import TextFSMParser, TTPParser, parse_output

logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])


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
        inventory_service: InventoryService = request.app.state.inventory_service
        try:
            device_config = inventory_service.get_device_config(device)
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
        ttp_template_path = ttp_parser._lookup_template_from_index(
            platform=resolved_device_type,
            command=command,
        )
        if ttp_template_path:
            matches.append(
                TemplateMatch(
                    template_name=ttp_template_path.name,
                    source="custom",
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
    raw_output: str,
    parser: str = Query("textfsm", description="Parser to use ('textfsm' or 'ttp')"),
    template: Optional[str] = Query(
        None, description="Template name (e.g., 'my_template.textfsm')"
    ),
    device_type: Optional[str] = Query(
        None, description="Device type for auto-discovery (e.g., 'cisco_ios')"
    ),
    command: Optional[str] = Query(
        None, description="Command for auto-discovery (e.g., 'show ip int brief')"
    ),
    include_raw: bool = Query(False, description="Include raw output in response"),
):
    """Test parsing endpoint - parse raw text with a specified template.

    This is a convenience endpoint for testing templates without executing commands.
    """

    if parser not in ["textfsm", "ttp"]:
        raise TomValidationException(
            f"Parser '{parser}' not supported. Use 'textfsm' or 'ttp'"
        )

    settings = request.app.state.settings

    return parse_output(
        raw_output=raw_output,
        settings=settings,
        device_type=device_type,
        command=command,
        template=template,
        include_raw=include_raw,
        parser_type=parser,
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
        template_path = parser._find_template(template_name)

        if not template_path:
            raise TomNotFoundException(f"Template not found: {template_name}")

        # Determine source
        if template_path.parent == template_dir:
            source = "custom"
        else:
            source = "ntc"

        content = template_path.read_text()
        return TemplateContent(
            name=template_path.name,
            parser="textfsm",
            source=source,
            content=content,
        )

    elif parser_type == "ttp":
        template_dir = Path(settings.ttp_template_dir)
        parser = TTPParser(custom_template_dir=template_dir)
        template_path = parser._find_template(template_name)

        if not template_path:
            raise TomNotFoundException(f"Template not found: {template_name}")

        content = template_path.read_text()
        return TemplateContent(
            name=template_path.name,
            parser="ttp",
            source="custom",
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

    return TemplateDeleteResponse(name=template_name, deleted=True)
