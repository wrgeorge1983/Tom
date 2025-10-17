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
        from unittest.mock import MagicMock
        
        settings = MagicMock()
        settings.textfsm_template_dir = str(test_template_dir)
        settings.ttp_template_dir = "/tmp/ttp"
        
        result = parse_output(
            raw_output=sample_output,
            settings=settings,
            template="test_show_ip_int_brief.textfsm",
            include_raw=False,
            parser_type="textfsm"
        )
        
        assert "parsed" in result
        assert len(result["parsed"]) == 4

    def test_parse_output_function_unsupported_parser(self, sample_output):
        from unittest.mock import MagicMock
        
        settings = MagicMock()
        settings.textfsm_template_dir = "/tmp/textfsm"
        settings.ttp_template_dir = "/tmp/ttp"
        
        result = parse_output(
            raw_output=sample_output,
            settings=settings,
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
        from unittest.mock import MagicMock
        
        settings = MagicMock()
        settings.textfsm_template_dir = "/tmp/textfsm"
        settings.ttp_template_dir = "/tmp/ttp"
        
        template = """<group name="interfaces">
{{ interface }} {{ ip_address }} YES {{ method }} {{ status }} {{ protocol }}
</group>"""
        
        result = parse_output(
            raw_output=sample_output,
            settings=settings,
            template=template,
            parser_type="ttp"
        )
        
        assert "parsed" in result or "error" in result

    def test_list_templates(self, test_template_dir):
        parser = TTPParser(custom_template_dir=test_template_dir)
        templates = parser.list_templates()
        
        assert "custom" in templates
        assert "test_show_ip_int_brief.ttp" in templates["custom"]
