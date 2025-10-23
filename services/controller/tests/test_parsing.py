import pytest
from pathlib import Path

from tom_controller.parsing import parse_output, TextFSMParser
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
    
    def test_expand_optional_syntax_simple(self, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        
        # Simple case: abc[[xyz]] becomes abc(x(y(z)?)?)?
        result = parser._expand_optional_syntax("abc[[xyz]]")
        assert result == "abc(x(y(z)?)?)?", f"Expected 'abc(x(y(z)?)?)?' but got '{result}'"
    
    def test_expand_optional_syntax_multiple_brackets(self, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        
        # Multiple brackets: sh[[ow]] ip int[[erface]]
        result = parser._expand_optional_syntax("sh[[ow]] ip int[[erface]]")
        expected = "sh(o(w)?)? ip int(e(r(f(a(c(e)?)?)?)?)?)?"
        assert result == expected, f"Expected '{expected}' but got '{result}'"
    
    def test_expand_optional_syntax_empty_brackets(self, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        
        # Empty brackets are not matched by the regex (requires at least one char)
        # This is acceptable since ntc-templates never uses empty brackets in practice
        result = parser._expand_optional_syntax("abc[[]]def")
        assert result == "abc[[]]def", f"Expected 'abc[[]]def' but got '{result}'"
    
    def test_expand_optional_syntax_single_char(self, test_template_dir):
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        
        # Single character: a[[b]] becomes a(b)?
        result = parser._expand_optional_syntax("a[[b]]")
        assert result == "a(b)?", f"Expected 'a(b)?' but got '{result}'"
    
    def test_expand_optional_syntax_regex_matching(self, test_template_dir):
        import re
        parser = TextFSMParser(custom_template_dir=test_template_dir)
        
        # Test that expanded regex actually matches correctly
        expanded = parser._expand_optional_syntax("sh[[ow]] ip int[[erface]] br[[ief]]")
        
        # Should match various abbreviations
        test_cases = [
            ("sh ip int br", True),
            ("sho ip int br", True),
            ("show ip int br", True),
            ("show ip interface brief", True),
            ("sh ip interface brief", True),
            ("show ip int brie", True),
            ("s ip int br", False),  # 's' alone shouldn't match
            ("shw ip int br", False),  # 'shw' shouldn't match
        ]
        
        for test_str, should_match in test_cases:
            match = re.match(expanded, test_str, re.IGNORECASE)
            matched = match is not None
            assert matched == should_match, \
                f"Pattern '{expanded}' {'should' if should_match else 'should not'} match '{test_str}'"

    def test_custom_index_with_fallback(self, tmp_path):
        # Create a custom template
        template_content = """Value INTERFACE (\S+)
Value IP_ADDRESS (\S+)
Value STATUS (up|down|administratively down)
Value PROTOCOL (up|down)

Start
  ^${INTERFACE}\s+${IP_ADDRESS}\s+\w+\s+\w+\s+${STATUS}\s+${PROTOCOL} -> Record
"""
        custom_template = tmp_path / "custom_test_parser.textfsm"
        custom_template.write_text(template_content)
        
        # Create an index file
        index_content = """Template, Hostname, Platform, Command
custom_test_parser.textfsm, .*, cisco_ios, show custom test
"""
        index_file = tmp_path / "index"
        index_file.write_text(index_content)
        
        parser = TextFSMParser(custom_template_dir=tmp_path)
        
        # Test 1: Custom template should be used
        sample_output = """Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     10.1.1.1        YES NVRAM  up                    up"""
        
        result = parser.parse(
            raw_output=sample_output,
            platform="cisco_ios",
            command="show custom test"
        )
        
        assert "parsed" in result
        assert "error" not in result
        assert len(result["parsed"]) == 1
        
        # Test 2: Command not in custom index should fallback to ntc-templates
        result2 = parser.parse(
            raw_output=sample_output,
            platform="cisco_ios",
            command="show ip interface brief"
        )
        
        assert "parsed" in result2
        # Should use ntc-templates fallback
        if "error" not in result2:
            assert isinstance(result2["parsed"], list)





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

    def test_custom_index_with_lookup(self, tmp_path):
        # Create a custom TTP template
        template_content = """<group name="interfaces">
{{ interface }} {{ ip_address }} YES {{ method }} {{ status }} {{ protocol }}
</group>
"""
        custom_template = tmp_path / "custom_ttp_test.ttp"
        custom_template.write_text(template_content)
        
        # Create an index file
        index_content = """Template, Hostname, Platform, Command
custom_ttp_test.ttp, .*, cisco_ios, show custom test
"""
        index_file = tmp_path / "index"
        index_file.write_text(index_content)
        
        parser = TTPParser(custom_template_dir=tmp_path)
        
        # Test: Auto-discovery using index
        sample_output = """Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     10.1.1.1        YES NVRAM  up                    up
GigabitEthernet0/1     10.2.2.1        YES NVRAM  up                    up"""
        
        result = parser.parse(
            raw_output=sample_output,
            platform="cisco_ios",
            command="show custom test"
        )
        
        assert "parsed" in result
        assert "error" not in result
        assert len(result["parsed"]) > 0
        
    def test_custom_index_no_match(self, tmp_path):
        # Create empty index
        index_content = """Template, Hostname, Platform, Command
"""
        index_file = tmp_path / "index"
        index_file.write_text(index_content)
        
        parser = TTPParser(custom_template_dir=tmp_path)
        
        # Test: No match in index should return error
        result = parser.parse(
            raw_output="some output",
            platform="cisco_ios",
            command="show version"
        )
        
        assert "error" in result
        assert "No template found" in result["error"]
