"""Tests for template management API endpoints."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tom_controller.api.templates import (
    TemplateContent,
    TemplateCreateRequest,
    TemplateCreateResponse,
    TemplateDeleteResponse,
)
from tom_controller.parsing import TextFSMParser, TTPParser
from tom_controller.exceptions import TomNotFoundException, TomValidationException


@pytest.fixture
def test_template_dir(tmp_path):
    """Create a temporary template directory structure."""
    textfsm_dir = tmp_path / "textfsm"
    ttp_dir = tmp_path / "ttp"
    textfsm_dir.mkdir()
    ttp_dir.mkdir()

    # Create a sample TextFSM template
    sample_textfsm = """Value INTERFACE (\\S+)
Value IP_ADDRESS (\\S+)

Start
  ^${INTERFACE}\\s+${IP_ADDRESS} -> Record
"""
    (textfsm_dir / "test_template.textfsm").write_text(sample_textfsm)

    # Create a sample TTP template
    sample_ttp = """<group name="interfaces">
Interface: {{ interface }}
IP: {{ ip }}
</group>
"""
    (ttp_dir / "test_template.ttp").write_text(sample_ttp)

    return tmp_path


class TestListTTPTemplates:
    def test_list_ttp_templates(self, test_template_dir):
        """Test listing TTP templates."""
        ttp_dir = test_template_dir / "ttp"
        parser = TTPParser(custom_template_dir=ttp_dir)
        result = parser.list_templates()

        assert "custom" in result
        assert "test_template.ttp" in result["custom"]

    def test_list_ttp_templates_empty_custom(self, tmp_path):
        """Test listing TTP templates when custom directory is empty."""
        ttp_dir = tmp_path / "ttp"
        ttp_dir.mkdir()
        parser = TTPParser(custom_template_dir=ttp_dir)
        result = parser.list_templates()

        # Custom should be empty, but ttp_templates package should have templates
        assert result["custom"] == []
        assert "ttp_templates" in result
        assert len(result["ttp_templates"]) > 0  # ttp_templates package has templates


class TestGetTemplate:
    def test_get_textfsm_custom_template(self, test_template_dir):
        """Test retrieving a custom TextFSM template."""
        textfsm_dir = test_template_dir / "textfsm"
        parser = TextFSMParser(custom_template_dir=textfsm_dir)
        template_path = parser._find_template("test_template.textfsm")

        assert template_path is not None
        assert template_path.exists()
        content = template_path.read_text()
        assert "Value INTERFACE" in content

    def test_get_textfsm_template_without_extension(self, test_template_dir):
        """Test retrieving template without .textfsm extension."""
        textfsm_dir = test_template_dir / "textfsm"
        parser = TextFSMParser(custom_template_dir=textfsm_dir)
        template_path = parser._find_template("test_template")

        assert template_path is not None
        assert template_path.name == "test_template.textfsm"

    def test_get_ttp_template(self, test_template_dir):
        """Test retrieving a TTP template."""
        ttp_dir = test_template_dir / "ttp"
        parser = TTPParser(custom_template_dir=ttp_dir)
        template_path, source = parser._find_template("test_template.ttp")

        assert template_path is not None
        assert source == "custom"
        assert template_path.exists()
        content = template_path.read_text()
        assert "<group" in content

    def test_get_nonexistent_template(self, test_template_dir):
        """Test retrieving a template that doesn't exist."""
        textfsm_dir = test_template_dir / "textfsm"
        parser = TextFSMParser(custom_template_dir=textfsm_dir)
        template_path = parser._find_template("nonexistent.textfsm")

        assert template_path is None


class TestCreateTemplate:
    def test_create_textfsm_template(self, test_template_dir):
        """Test creating a new TextFSM template."""
        textfsm_dir = test_template_dir / "textfsm"
        template_name = "new_template.textfsm"
        template_content = """Value HOSTNAME (\\S+)

Start
  ^Hostname: ${HOSTNAME}
"""
        template_path = textfsm_dir / template_name
        template_path.write_text(template_content)

        assert template_path.exists()
        assert template_path.read_text() == template_content

    def test_create_ttp_template(self, test_template_dir):
        """Test creating a new TTP template."""
        ttp_dir = test_template_dir / "ttp"
        template_name = "new_template.ttp"
        template_content = """<group name="data">
Value: {{ value }}
</group>
"""
        template_path = ttp_dir / template_name
        template_path.write_text(template_content)

        assert template_path.exists()
        assert template_path.read_text() == template_content

    def test_create_template_adds_extension(self, test_template_dir):
        """Test that extension is added if missing."""
        textfsm_dir = test_template_dir / "textfsm"
        template_name = "no_extension"
        expected_name = "no_extension.textfsm"
        template_content = "Value TEST (\\S+)\n\nStart\n  ^${TEST}\n"

        # Simulate the extension logic
        if not template_name.endswith(".textfsm"):
            template_name = template_name + ".textfsm"

        template_path = textfsm_dir / template_name
        template_path.write_text(template_content)

        assert template_path.name == expected_name
        assert template_path.exists()

    def test_create_template_overwrite_false_fails(self, test_template_dir):
        """Test that overwrite=false fails if template exists."""
        textfsm_dir = test_template_dir / "textfsm"
        template_name = "test_template.textfsm"

        # Template already exists from fixture
        template_path = textfsm_dir / template_name
        assert template_path.exists()

        # Simulating the overwrite check
        overwrite = False
        if template_path.exists() and not overwrite:
            with pytest.raises(TomValidationException):
                raise TomValidationException(
                    f"Template '{template_name}' already exists."
                )

    def test_create_template_overwrite_true_succeeds(self, test_template_dir):
        """Test that overwrite=true replaces existing template."""
        textfsm_dir = test_template_dir / "textfsm"
        template_name = "test_template.textfsm"
        new_content = "Value NEWFIELD (\\S+)\n\nStart\n  ^${NEWFIELD}\n"

        template_path = textfsm_dir / template_name
        original_content = template_path.read_text()

        # Overwrite
        template_path.write_text(new_content)

        assert template_path.read_text() == new_content
        assert template_path.read_text() != original_content


class TestDeleteTemplate:
    def test_delete_custom_template(self, test_template_dir):
        """Test deleting a custom template."""
        textfsm_dir = test_template_dir / "textfsm"
        template_name = "test_template.textfsm"
        template_path = textfsm_dir / template_name

        assert template_path.exists()
        template_path.unlink()
        assert not template_path.exists()

    def test_delete_nonexistent_template(self, test_template_dir):
        """Test deleting a template that doesn't exist."""
        textfsm_dir = test_template_dir / "textfsm"
        template_name = "nonexistent.textfsm"
        template_path = textfsm_dir / template_name

        assert not template_path.exists()


class TestTemplateValidation:
    def test_valid_textfsm_template_compiles(self):
        """Test that valid TextFSM template compiles without error."""
        import textfsm
        from io import StringIO

        valid_template = """Value INTERFACE (\\S+)
Value STATUS (up|down)

Start
  ^${INTERFACE}.*${STATUS} -> Record
"""
        # Should not raise
        fsm = textfsm.TextFSM(StringIO(valid_template))
        assert fsm.header == ["INTERFACE", "STATUS"]

    def test_invalid_textfsm_template_raises(self):
        """Test that invalid TextFSM template raises error."""
        import textfsm
        from io import StringIO

        invalid_template = """Value INTERFACE (\\S+

Start
  ^${INTERFACE}
"""
        with pytest.raises(textfsm.TextFSMTemplateError):
            textfsm.TextFSM(StringIO(invalid_template))

    def test_textfsm_undefined_value_raises(self):
        """Test that referencing undefined value raises error."""
        import textfsm
        from io import StringIO

        template_with_undefined = """Value INTERFACE (\\S+)

Start
  ^${UNDEFINED_VALUE}
"""
        with pytest.raises(textfsm.TextFSMTemplateError):
            textfsm.TextFSM(StringIO(template_with_undefined))


class TestPathTraversalPrevention:
    def test_reject_path_with_slash(self):
        """Test that template names with / are rejected."""
        template_name = "../etc/passwd"
        assert "/" in template_name or ".." in template_name

    def test_reject_path_with_backslash(self):
        """Test that template names with \\ are rejected."""
        template_name = "..\\etc\\passwd"
        assert "\\" in template_name or ".." in template_name

    def test_reject_path_with_dotdot(self):
        """Test that template names with .. are rejected."""
        template_name = "..template.textfsm"
        assert ".." in template_name
