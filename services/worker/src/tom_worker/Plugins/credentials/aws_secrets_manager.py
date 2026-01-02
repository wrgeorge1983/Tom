"""AWS Secrets Manager credential store plugin."""

import json
import os
from logging import getLogger
from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from tom_worker.credentials.credentials import SSHCredentials
from tom_worker.exceptions import TomException
from tom_worker.Plugins.base import CredentialPlugin, PluginSettings

if TYPE_CHECKING:
    from tom_worker.config import Settings

logger = getLogger(__name__)


class AwsSecretsManagerSettings(PluginSettings):
    """
    AWS Secrets Manager Credential Plugin Settings.

    Config file uses prefixed keys: plugin_aws_secrets_manager_region, etc.
    Env vars use: TOM_WORKER_PLUGIN_AWS_SECRETS_MANAGER_REGION, etc.
    Code uses: settings.region, etc.

    Authentication:
    AWS credentials are handled by boto3's credential chain:
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    - Shared credentials file (~/.aws/credentials)
    - IAM role (when running on EC2/ECS/Lambda)

    Secret format:
    Secrets should be JSON with 'username' and 'password' keys:
    {"username": "admin", "password": "secret123"}
    """

    region: str = ""
    secret_prefix: str = "tom/credentials/"
    endpoint_url: str = ""

    model_config = SettingsConfigDict(
        env_prefix="TOM_WORKER_",
        env_file=os.getenv("TOM_WORKER_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_WORKER_CONFIG_FILE", "tom_worker_config.yaml"),
        case_sensitive=False,
        extra="forbid",
        plugin_name="aws_secrets_manager",  # type: ignore[typeddict-unknown-key]
    )


class AwsSecretsManagerPlugin(CredentialPlugin):
    """AWS Secrets Manager credential store plugin.

    Reads credentials from AWS Secrets Manager. Secrets are expected
    at path: {secret_prefix}{credential_id}

    Each secret must be JSON containing 'username' and 'password' keys:
    {"username": "admin", "password": "secret123"}

    AWS authentication is handled by boto3's standard credential chain:
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    - Shared credentials file (~/.aws/credentials)
    - IAM instance profile (EC2/ECS/Lambda)
    """

    name = "aws_secrets_manager"
    dependencies = ["boto3"]
    settings_class = AwsSecretsManagerSettings

    def __init__(
        self,
        plugin_settings: AwsSecretsManagerSettings,
        main_settings: "Settings",
    ):
        self.settings = plugin_settings
        self.main_settings = main_settings
        self._client = None

        logger.debug(
            f"AWS Secrets Manager credential plugin initialized "
            f"(region={plugin_settings.region or 'default'}, "
            f"prefix={plugin_settings.secret_prefix})"
        )

    def _get_client(self):
        """Get or create boto3 Secrets Manager client.

        :return: boto3 Secrets Manager client
        :raises TomException: If boto3 is not available
        """
        if self._client is not None:
            return self._client

        try:
            import boto3
        except ImportError:
            raise TomException(
                "boto3 is required for AWS Secrets Manager plugin. "
                "Install it with: uv add boto3"
            )

        client_kwargs = {}
        if self.settings.region:
            client_kwargs["region_name"] = self.settings.region
        if self.settings.endpoint_url:
            client_kwargs["endpoint_url"] = self.settings.endpoint_url

        self._client = boto3.client("secretsmanager", **client_kwargs)
        return self._client

    async def validate(self) -> None:
        """Validate AWS Secrets Manager connectivity and authentication.

        :raises TomException: If validation fails
        """
        client = self._get_client()

        try:
            client.list_secrets(MaxResults=1)
        except Exception as e:
            error_name = type(e).__name__
            raise TomException(
                f"AWS Secrets Manager validation failed: {error_name}: {e}\n"
                f"Ensure AWS credentials are configured and have secretsmanager:ListSecrets permission."
            ) from e

        region = self.settings.region or "default"
        logger.info(
            f"AWS Secrets Manager credential plugin validated: "
            f"connected to region '{region}' with prefix '{self.settings.secret_prefix}'"
        )

    async def get_ssh_credentials(self, credential_id: str) -> SSHCredentials:
        """Retrieve SSH credentials from AWS Secrets Manager.

        :param credential_id: The credential identifier
        :return: SSHCredentials with username and password
        :raises TomException: If credential not found or retrieval fails
        """
        client = self._get_client()
        secret_name = f"{self.settings.secret_prefix}{credential_id}"

        try:
            response = client.get_secret_value(SecretId=secret_name)
        except client.exceptions.ResourceNotFoundException:
            raise TomException(
                f"Secret not found: {secret_name}\n"
                f"Create it with: aws secretsmanager create-secret "
                f'--name {secret_name} --secret-string \'{{"username": "...", "password": "..."}}\''
            )
        except Exception as e:
            error_name = type(e).__name__
            raise TomException(
                f"Failed to retrieve secret '{secret_name}': {error_name}: {e}"
            ) from e

        secret_string = response.get("SecretString")
        if not secret_string:
            raise TomException(
                f"Secret '{secret_name}' has no SecretString value. "
                f"Binary secrets are not supported."
            )

        try:
            cred_data = json.loads(secret_string)
        except json.JSONDecodeError as e:
            raise TomException(
                f"Secret '{secret_name}' is not valid JSON: {e}\n"
                f'Expected format: {{"username": "...", "password": "..."}}'
            ) from e

        if not isinstance(cred_data, dict):
            raise TomException(
                f"Secret '{secret_name}' must be a JSON object, got {type(cred_data).__name__}"
            )

        if "username" not in cred_data:
            raise TomException(
                f"Secret '{secret_name}' is missing required 'username' field"
            )

        if "password" not in cred_data:
            raise TomException(
                f"Secret '{secret_name}' is missing required 'password' field"
            )

        return SSHCredentials(
            credential_id=credential_id,
            username=cred_data["username"],
            password=cred_data["password"],
        )

    async def list_credentials(self) -> list[str]:
        """List all available credential IDs from AWS Secrets Manager.

        :return: List of credential identifiers
        :raises TomException: If listing fails
        """
        client = self._get_client()
        prefix = self.settings.secret_prefix
        credential_ids = []

        try:
            paginator = client.get_paginator("list_secrets")
            for page in paginator.paginate(
                Filters=[{"Key": "name", "Values": [prefix]}]
            ):
                for secret in page.get("SecretList", []):
                    name = secret.get("Name", "")
                    if name.startswith(prefix):
                        # Strip the prefix to get the credential_id
                        credential_id = name[len(prefix) :]
                        if credential_id:  # Skip if empty after stripping
                            credential_ids.append(credential_id)
        except Exception as e:
            error_name = type(e).__name__
            raise TomException(
                f"Failed to list credentials from AWS Secrets Manager: {error_name}: {e}"
            ) from e

        return credential_ids
