from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from starlette.requests import Request

from tom_controller.exceptions import TomValidationException
from tom_controller.parsing import TextFSMParser, parse_output

router = APIRouter(tags=["templates"])


@router.get("/templates/textfsm")
async def list_textfsm_templates(request: Request):
    """List all available TextFSM templates."""

    settings = request.app.state.settings
    template_dir = Path(settings.textfsm_template_dir)
    parser = TextFSMParser(custom_template_dir=template_dir)
    return parser.list_templates()


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
