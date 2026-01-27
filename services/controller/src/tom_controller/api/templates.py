from pathlib import Path
from typing import Literal, Optional, List

from fastapi import APIRouter, Query
from pydantic import BaseModel
from starlette.requests import Request

from tom_controller.exceptions import TomNotFoundException, TomValidationException
from tom_controller.inventory.inventory import InventoryService
from tom_controller.parsing import TextFSMParser, TTPParser, parse_output

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
        if template_name:
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
