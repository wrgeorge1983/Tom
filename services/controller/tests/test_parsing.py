import pytest
from pathlib import Path

from tom_controller.parsing.textfsm_parser import parse_output, TextFSMParser
from tom_controller.parsing.ttp_parser import TTPParser


@pytest.fixture
def test_template_dir():
    return Path(__file__).parent / "templates" / "textfsm"


@pytest.fixture
def test_fixtures_dir():
    return Path(__file__).parent / "fixtures" / "text_outputs"


@pytest.fixture
def sample_output(test_fixtures_dir):
    with open(test_fixtures_dir / "show_ip_int_brief.txt") as f:
        return f.read()


class TestTextFSMParser:

    def test_parse_with_explicit_template(self, sample_output, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        result = parser.parse(
            raw_output=sample_output,
            template_name="test_show_ip_int_brief.textfsm",
            include_raw=False
        )
        
        assert "parsed" in result
        assert "error" not in result
        assert len(result["parsed"]) == 4
        
        first_interface = result["parsed"][0]
        assert first_interface["interface"] == "GigabitEthernet0/0"
        assert first_interface["ip_address"] == "10.1.1.1"
        assert first_interface["status"] == "up"
        assert first_interface["protocol"] == "up"

    def test_parse_with_explicit_template_and_raw(self, sample_output, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        result = parser.parse(
            raw_output=sample_output,
            template_name="test_show_ip_int_brief.textfsm",
            include_raw=True
        )
        
        assert "parsed" in result
        assert "raw" in result
        assert result["raw"] == sample_output
        assert len(result["parsed"]) == 4

    def test_parse_with_missing_template(self, sample_output, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        result = parser.parse(
            raw_output=sample_output,
            template_name="nonexistent_template.textfsm",
            include_raw=True
        )
        
        assert "error" in result
        assert "Template not found" in result["error"]
        assert result["raw"] == sample_output

    def test_parse_without_template_or_platform(self, sample_output, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        result = parser.parse(
            raw_output=sample_output,
            include_raw=True
        )
        
        assert "error" in result
        assert "template_name OR (platform + command) required" in result["error"]
        assert result["raw"] == sample_output

    def test_parse_with_auto_discovery(self):
        sample_cisco_ios_output = """Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     10.1.1.1        YES NVRAM  up                    up
GigabitEthernet0/1     10.2.2.1        YES NVRAM  up                    up"""
        
        parser = TextFSMParser()
        result = parser.parse(
            raw_output=sample_cisco_ios_output,
            platform="cisco_ios",
            command="show ip interface brief",
            include_raw=False
        )
        
        assert "parsed" in result
        if "error" not in result:
            assert isinstance(result["parsed"], list)

    def test_parse_output_function(self, sample_output, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        
        from tom_controller.parsing import textfsm_parser
        original_instance = textfsm_parser._parser_instance
        try:
            textfsm_parser._parser_instance = parser
            
            result = parse_output(
                raw_output=sample_output,
                template="test_show_ip_int_brief.textfsm",
                include_raw=False,
                parser_type="textfsm"
            )
            
            assert "parsed" in result
            assert len(result["parsed"]) == 4
        finally:
            textfsm_parser._parser_instance = original_instance

    def test_parse_output_function_unsupported_parser(self, sample_output):
        result = parse_output(
            raw_output=sample_output,
            template="test.textfsm",
            parser_type="unsupported_parser"
        )
        
        assert "error" in result
        assert "not supported" in result["error"]

    def test_list_templates(self, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        templates = parser.list_templates()
        
        assert "custom" in templates
        assert "ntc" in templates
        assert "test_show_ip_int_brief.textfsm" in templates["custom"]
        assert isinstance(templates["ntc"], list)

    def test_find_template_with_extension(self, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        template_path = parser._find_template("test_show_ip_int_brief.textfsm")
        
        assert template_path is not None
        assert template_path.exists()
        assert template_path.name == "test_show_ip_int_brief.textfsm"

    def test_find_template_without_extension(self, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        template_path = parser._find_template("test_show_ip_int_brief")
        
        assert template_path is not None
        assert template_path.exists()
        assert template_path.name == "test_show_ip_int_brief.textfsm"


class TestParsingAPI:

    @pytest.fixture
    def mock_queue(self):
        import saq
        from unittest.mock import AsyncMock, MagicMock
        
        queue = MagicMock(spec=saq.Queue)
        job = MagicMock()
        job.id = "test-job-123"
        job.status = "complete"
        job.key = "test-job-123"
        job.result.return_value = {"show ip int brief": "GigabitEthernet0/0     10.1.1.1        YES NVRAM  up                    up"}
        
        async def mock_refresh(**kwargs):
            pass
        
        job.refresh = mock_refresh
        
        async def mock_enqueue(*args, **kwargs):
            return job
        
        queue.enqueue = mock_enqueue
        queue.job = AsyncMock(return_value=job)
        
        return queue

    @pytest.fixture
    def test_app(self, mock_queue, test_template_dir):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from tom_controller.api import api
        from tom_controller.config import Settings
        from tom_controller.inventory.inventory import YamlInventoryStore
        from unittest.mock import MagicMock
        import tempfile
        
        settings = Settings(
            auth_mode="none",
            redis_url="redis://localhost:6379",
            yaml_file=None,
        )
        
        app = FastAPI()
        app.state.settings = settings
        app.state.queue = mock_queue
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yml') as f:
            f.write("devices: {}")
        
        app.state.inventory_store = YamlInventoryStore(f.name)
        app.state.jwt_providers = []
        
        app.include_router(api.router, prefix="/api")
        
        from tom_controller.parsing import textfsm_parser
        original_parser = textfsm_parser._parser_instance
        textfsm_parser._parser_instance = TextFSMParser(custom_template_dir=test_template_dir)
        
        client = TestClient(app)
        
        yield client
        
        textfsm_parser._parser_instance = original_parser

    def test_list_templates_endpoint(self, test_app):
        response = test_app.get("/api/templates/textfsm")
        
        assert response.status_code == 200
        data = response.json()
        assert "custom" in data
        assert "ntc" in data
        assert "test_show_ip_int_brief.textfsm" in data["custom"]


class TestTTPParser:

    @pytest.fixture
    def test_template_dir(self):
        return Path(__file__).parent / "templates" / "ttp"

    @pytest.fixture
    def sample_output(self):
        return """Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     10.1.1.1        YES NVRAM  up                    up
GigabitEthernet0/1     10.2.2.1        YES NVRAM  up                    up
GigabitEthernet0/2     unassigned      YES NVRAM  administratively down down
Loopback0              192.168.1.1     YES NVRAM  up                    up"""

    def test_parse_with_explicit_template(self, sample_output, test_template_dir):
        parser = TTPParser(custom_template_dir=test_template_dir)
        result = parser.parse(
            raw_output=sample_output,
            template_name="test_show_ip_int_brief.ttp",
            include_raw=False
        )
        
        assert "parsed" in result
        assert "error" not in result
        assert len(result["parsed"]) > 0
        
        interfaces = result["parsed"][0]["interfaces"]
        assert len(interfaces) == 4

    def test_parse_with_template_string(self, sample_output):
        template = """<group name="interfaces">
{{ interface }} {{ ip_address }} YES {{ method }} {{ status }} {{ protocol }}
</group>"""
        
        parser = TTPParser()
        result = parser.parse(
            raw_output=sample_output,
            template_string=template,
            include_raw=False
        )
        
        assert "parsed" in result
        assert "error" not in result

    def test_parse_with_missing_template(self, sample_output, test_template_dir):
        parser = TTPParser(custom_template_dir=test_template_dir)
        result = parser.parse(
            raw_output=sample_output,
            template_name="nonexistent.ttp",
            include_raw=True
        )
        
        assert "error" in result
        assert "Template not found" in result["error"]
        assert result["raw"] == sample_output

    def test_parse_without_any_input(self, sample_output):
        parser = TTPParser()
        result = parser.parse(
            raw_output=sample_output,
            include_raw=True
        )
        
        assert "error" in result
        assert "required" in result["error"]

    def test_parse_output_function_ttp(self, sample_output):
        template = """<group name="interfaces">
{{ interface }} {{ ip_address }} YES {{ method }} {{ status }} {{ protocol }}
</group>"""
        
        result = parse_output(
            raw_output=sample_output,
            template=template,
            parser_type="ttp"
        )
        
        assert "parsed" in result or "error" in result

    def test_list_templates(self, test_template_dir):
        parser = TTPParser(custom_template_dir=test_template_dir)
        templates = parser.list_templates()
        
        assert "custom" in templates
        assert "test_show_ip_int_brief.ttp" in templates["custom"]
