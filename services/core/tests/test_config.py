import json
import os
import tempfile
from unittest import mock

import pytest

from tom_core.config import Settings


pytestDefaultValues = {
    "test_var_str": "pytestDefaultHost",
    "test_var_str2": "pytestDefaultHost2",
    "test_var_int": 1337,
    "test_var_list_str": ["a", "b"]

}

pytestEnvValues = {
    "TOM_CORE_TEST_VAR_STR": "pytestEnvVarHost",
    "TOM_CORE_TEST_VAR_INT": "138",
    "TOM_CORE_TEST_VAR_LIST_STR": json.dumps(["a", "b", "c"]),
}

pytestYamlDefaultValues = {
    "test_var_str": "pytestYamlDefaultHost",
    "test_var_str2": "pytestYamlDefaultHost2",
}


@pytest.fixture()
def clean_env():
    with mock.patch.dict(os.environ, clear=True):
        yield


@pytest.fixture()
def test_settings_class(clean_env):
    class TestSettings(Settings):
        test_var_str: str = pytestDefaultValues["test_var_str"]
        test_var_str2: str = pytestDefaultValues["test_var_str2"]
        test_var_int: int = pytestDefaultValues["test_var_int"]
        test_var_list_str: list[str] = pytestDefaultValues["test_var_list_str"]
        model_config = Settings.model_config.copy()
        model_config.update({
            "env_file": None,
            "yaml_file": None,
        })

    return TestSettings


@pytest.fixture()
def test_settings_yaml_file():
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(f"""
test_var_str2: {pytestYamlDefaultValues['test_var_str2']}  
test_var_str: {pytestYamlDefaultValues['test_var_str']} 
        """)
        f.flush()
    yield f.name
    os.remove(f.name)

@pytest.fixture()
def test_settings_file_with_env_vars(test_settings_yaml_file, test_settings_class):
    class TestSettings(test_settings_class):
        model_config = test_settings_class.model_config.copy()
        model_config.update({
            "env_file": None,
            "yaml_file": test_settings_yaml_file,
        })

    return TestSettings


def test_default_settings(test_settings_class):
    settings = test_settings_class()
    for key, value in pytestDefaultValues.items():
        assert getattr(settings, key) == value


def test_env_var_settings(test_settings_class):
    with mock.patch.dict(os.environ, pytestEnvValues):
        settings = test_settings_class()
        assert settings.test_var_str == pytestEnvValues["TOM_CORE_TEST_VAR_STR"]
        assert settings.test_var_int == int(pytestEnvValues["TOM_CORE_TEST_VAR_INT"])
        assert settings.test_var_list_str == json.loads(pytestEnvValues["TOM_CORE_TEST_VAR_LIST_STR"])


def test_settings_with_yaml_file(test_settings_file_with_env_vars):
    settings = test_settings_file_with_env_vars()
    assert settings.test_var_str == pytestYamlDefaultValues["test_var_str"]
    assert settings.test_var_str2 == pytestYamlDefaultValues["test_var_str2"]
    assert settings.test_var_int == pytestDefaultValues["test_var_int"]


def test_settings_with_env_and_yaml_file(test_settings_file_with_env_vars):
    with mock.patch.dict(os.environ, pytestEnvValues):
        settings = test_settings_file_with_env_vars()
        assert settings.test_var_int == int(pytestEnvValues["TOM_CORE_TEST_VAR_INT"]) # ENV
        assert settings.test_var_list_str == json.loads(pytestEnvValues["TOM_CORE_TEST_VAR_LIST_STR"]) # ENV
        assert settings.test_var_str2 == pytestYamlDefaultValues["test_var_str2"]  # YAML
        assert settings.test_var_str == pytestEnvValues["TOM_CORE_TEST_VAR_STR"]  # YAML overridden by env
