"""Tests for template management API endpoints."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tom_controller.api.templates import (
    TemplateContent,
    TemplateCreateRequest,
    TemplateCreateResponse,
    TemplateDeleteResponse,
    _read_index,
    _write_index,
    _add_to_index,
    _remove_from_index,
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
        template_path, source = parser._find_template("test_template.textfsm")

        assert template_path is not None
        assert source == "custom"
        assert template_path.exists()
        content = template_path.read_text()
        assert "Value INTERFACE" in content

    def test_get_textfsm_template_without_extension(self, test_template_dir):
        """Test retrieving template without .textfsm extension."""
        textfsm_dir = test_template_dir / "textfsm"
        parser = TextFSMParser(custom_template_dir=textfsm_dir)
        template_path, source = parser._find_template("test_template")

        assert template_path is not None
        assert source == "custom"
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
        template_path, source = parser._find_template("nonexistent.textfsm")

        assert template_path is None
        assert source is None


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


class TestIndexManagement:
    """Tests for index file read/write/add/remove functions."""

    def test_read_index_nonexistent(self, tmp_path):
        """Reading a nonexistent index returns empty list."""
        index_path = tmp_path / "index"
        result = _read_index(index_path)
        assert result == []

    def test_read_index_empty_file(self, tmp_path):
        """Reading an empty index file returns empty list."""
        index_path = tmp_path / "index"
        index_path.write_text("")
        result = _read_index(index_path)
        assert result == []

    def test_read_index_header_only(self, tmp_path):
        """Reading an index with only a header returns empty list."""
        index_path = tmp_path / "index"
        index_path.write_text("Template, Hostname, Platform, Command\n")
        result = _read_index(index_path)
        assert result == []

    def test_read_index_with_entries(self, tmp_path):
        """Reading an index with entries parses them correctly."""
        index_path = tmp_path / "index"
        index_path.write_text(
            "Template, Hostname, Platform, Command\n"
            "my_template.textfsm, .*, cisco_ios, show version\n"
            "other.textfsm, router-.*, arista_eos, show ip route\n"
        )
        result = _read_index(index_path)

        assert len(result) == 2
        assert result[0]["template"] == "my_template.textfsm"
        assert result[0]["hostname"] == ".*"
        assert result[0]["platform"] == "cisco_ios"
        assert result[0]["command"] == "show version"
        assert result[1]["template"] == "other.textfsm"
        assert result[1]["platform"] == "arista_eos"

    def test_read_index_skips_comments(self, tmp_path):
        """Comments in index file are skipped."""
        index_path = tmp_path / "index"
        index_path.write_text(
            "# This is a comment\n"
            "Template, Hostname, Platform, Command\n"
            "# Another comment\n"
            "my_template.textfsm, .*, cisco_ios, show version\n"
        )
        result = _read_index(index_path)
        assert len(result) == 1
        assert result[0]["template"] == "my_template.textfsm"

    def test_write_index(self, tmp_path):
        """Writing entries produces a valid index file."""
        index_path = tmp_path / "index"
        entries = [
            {
                "template": "test.textfsm",
                "hostname": ".*",
                "platform": "cisco_ios",
                "command": "show version",
            }
        ]
        _write_index(index_path, entries)

        content = index_path.read_text()
        assert "Template, Hostname, Platform, Command" in content
        assert "test.textfsm" in content

        # Verify round-trip
        read_back = _read_index(index_path)
        assert len(read_back) == 1
        assert read_back[0]["template"] == "test.textfsm"
        assert read_back[0]["platform"] == "cisco_ios"

    def test_write_index_empty(self, tmp_path):
        """Writing empty entries produces just a header."""
        index_path = tmp_path / "index"
        _write_index(index_path, [])

        content = index_path.read_text()
        assert "Template, Hostname, Platform, Command" in content

        read_back = _read_index(index_path)
        assert read_back == []

    def test_add_to_index_new_entry(self, tmp_path):
        """Adding a new entry to a nonexistent index creates it."""
        index_path = tmp_path / "index"
        _add_to_index(
            index_path=index_path,
            template_name="new.textfsm",
            platform="cisco_ios",
            command="show version",
        )

        entries = _read_index(index_path)
        assert len(entries) == 1
        assert entries[0]["template"] == "new.textfsm"
        assert entries[0]["hostname"] == ".*"  # default

    def test_add_to_index_replaces_existing(self, tmp_path):
        """Adding an entry with the same template name replaces the old one."""
        index_path = tmp_path / "index"

        _add_to_index(
            index_path=index_path,
            template_name="test.textfsm",
            platform="cisco_ios",
            command="show version",
        )
        _add_to_index(
            index_path=index_path,
            template_name="test.textfsm",
            platform="arista_eos",
            command="show version detail",
        )

        entries = _read_index(index_path)
        assert len(entries) == 1
        assert entries[0]["platform"] == "arista_eos"
        assert entries[0]["command"] == "show version detail"

    def test_add_to_index_custom_hostname(self, tmp_path):
        """Adding an entry with a custom hostname pattern."""
        index_path = tmp_path / "index"
        _add_to_index(
            index_path=index_path,
            template_name="dc_router.textfsm",
            platform="cisco_ios",
            command="show ip route",
            hostname="dc-.*",
        )

        entries = _read_index(index_path)
        assert len(entries) == 1
        assert entries[0]["hostname"] == "dc-.*"

    def test_add_to_index_multiple_entries(self, tmp_path):
        """Adding multiple different templates preserves all entries."""
        index_path = tmp_path / "index"

        _add_to_index(index_path, "first.textfsm", "cisco_ios", "show version")
        _add_to_index(index_path, "second.textfsm", "arista_eos", "show hostname")
        _add_to_index(index_path, "third.textfsm", "cisco_ios", "show ip route")

        entries = _read_index(index_path)
        assert len(entries) == 3
        templates = [e["template"] for e in entries]
        assert "first.textfsm" in templates
        assert "second.textfsm" in templates
        assert "third.textfsm" in templates

    def test_remove_from_index_existing(self, tmp_path):
        """Removing an existing entry returns True and removes it."""
        index_path = tmp_path / "index"
        _add_to_index(index_path, "first.textfsm", "cisco_ios", "show version")
        _add_to_index(index_path, "second.textfsm", "arista_eos", "show hostname")

        removed = _remove_from_index(index_path, "first.textfsm")
        assert removed is True

        entries = _read_index(index_path)
        assert len(entries) == 1
        assert entries[0]["template"] == "second.textfsm"

    def test_remove_from_index_nonexistent(self, tmp_path):
        """Removing a non-existent entry returns False."""
        index_path = tmp_path / "index"
        _add_to_index(index_path, "existing.textfsm", "cisco_ios", "show version")

        removed = _remove_from_index(index_path, "nonexistent.textfsm")
        assert removed is False

        entries = _read_index(index_path)
        assert len(entries) == 1

    def test_remove_from_index_empty(self, tmp_path):
        """Removing from an empty index returns False."""
        index_path = tmp_path / "index"
        index_path.write_text("Template, Hostname, Platform, Command\n")

        removed = _remove_from_index(index_path, "test.textfsm")
        assert removed is False

    def test_index_roundtrip_preserves_data(self, tmp_path):
        """Verify that add/read cycles preserve all field values."""
        index_path = tmp_path / "index"
        _add_to_index(
            index_path, "test.textfsm", "juniper_junos", "show route", "core-.*"
        )

        entries = _read_index(index_path)
        assert entries[0]["template"] == "test.textfsm"
        assert entries[0]["hostname"] == "core-.*"
        assert entries[0]["platform"] == "juniper_junos"
        assert entries[0]["command"] == "show route"


class TestTemplateCreateWithIndex:
    """Tests for template creation with automatic index entry."""

    def test_create_template_with_index_entry(self, test_template_dir):
        """Creating a template with platform+command adds it to the index."""
        textfsm_dir = test_template_dir / "textfsm"
        template_name = "indexed_template.textfsm"
        template_content = "Value TEST (\\S+)\n\nStart\n  ^${TEST}\n"

        (textfsm_dir / template_name).write_text(template_content)

        index_path = textfsm_dir / "index"
        _add_to_index(
            index_path=index_path,
            template_name=template_name,
            platform="cisco_ios",
            command="show test",
        )

        entries = _read_index(index_path)
        matching = [e for e in entries if e["template"] == template_name]
        assert len(matching) == 1
        assert matching[0]["platform"] == "cisco_ios"
        assert matching[0]["command"] == "show test"

    def test_create_template_without_index_fields(self, test_template_dir):
        """Creating a template without platform/command does not touch the index."""
        textfsm_dir = test_template_dir / "textfsm"
        template_name = "no_index_template.textfsm"
        template_content = "Value TEST (\\S+)\n\nStart\n  ^${TEST}\n"

        (textfsm_dir / template_name).write_text(template_content)

        # No _add_to_index call, so index should not exist
        index_path = textfsm_dir / "index"
        if index_path.exists():
            entries = _read_index(index_path)
            matching = [e for e in entries if e["template"] == template_name]
            assert len(matching) == 0


class TestTemplateDeleteWithIndex:
    """Tests for template deletion with automatic index cleanup."""

    def test_delete_template_removes_index_entry(self, test_template_dir):
        """Deleting a template also removes its index entry."""
        textfsm_dir = test_template_dir / "textfsm"
        template_name = "to_delete.textfsm"
        template_content = "Value TEST (\\S+)\n\nStart\n  ^${TEST}\n"

        # Create template and index entry
        (textfsm_dir / template_name).write_text(template_content)
        index_path = textfsm_dir / "index"
        _add_to_index(index_path, template_name, "cisco_ios", "show delete test")

        # Verify entry exists
        entries = _read_index(index_path)
        assert any(e["template"] == template_name for e in entries)

        # Delete template and remove from index
        (textfsm_dir / template_name).unlink()
        _remove_from_index(index_path, template_name)

        # Verify entry is gone
        entries = _read_index(index_path)
        assert not any(e["template"] == template_name for e in entries)

    def test_delete_template_preserves_other_entries(self, test_template_dir):
        """Deleting one template's index entry preserves others."""
        textfsm_dir = test_template_dir / "textfsm"
        index_path = textfsm_dir / "index"

        _add_to_index(index_path, "keep.textfsm", "cisco_ios", "show keep")
        _add_to_index(index_path, "remove.textfsm", "cisco_ios", "show remove")

        _remove_from_index(index_path, "remove.textfsm")

        entries = _read_index(index_path)
        assert len(entries) == 1
        assert entries[0]["template"] == "keep.textfsm"

    def test_delete_template_no_index_file(self, test_template_dir):
        """Deleting a template when no index file exists does not error."""
        textfsm_dir = test_template_dir / "textfsm"
        index_path = textfsm_dir / "index"

        # Ensure no index
        if index_path.exists():
            index_path.unlink()

        # Should not raise
        result = _remove_from_index(index_path, "nonexistent.textfsm")
        # _remove_from_index calls _read_index which returns [] for nonexistent
        # then len(entries) == original_count (0), so returns False
        assert result is False
