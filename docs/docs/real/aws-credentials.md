# AWS Secrets Manager Credential Store

Store credentials in AWS Secrets Manager.

## Prerequisites

The `boto3` package is required. Install it with the `aws` extra:

```bash
uv add tom-worker[aws]
```

Or if building your own Docker image, include boto3 in your dependencies.

## Configuration

Set the credential plugin to `aws_secrets_manager` in your worker config:

```yaml
# tom_worker_config.yaml
credential_plugin: "aws_secrets_manager"

plugin_aws_secrets_manager_region: "us-east-1"
plugin_aws_secrets_manager_secret_prefix: "tom/credentials/"
```

Or via environment variables:

```bash
TOM_WORKER_CREDENTIAL_PLUGIN=aws_secrets_manager
TOM_WORKER_PLUGIN_AWS_SECRETS_MANAGER_REGION=us-east-1
TOM_WORKER_PLUGIN_AWS_SECRETS_MANAGER_SECRET_PREFIX=tom/credentials/
```

## AWS Authentication

AWS credentials are handled by boto3's standard credential chain. The plugin does not manage AWS authentication directly. Configure credentials using any of these methods:

1. **Environment variables** (recommended for containers):
   ```bash
   AWS_ACCESS_KEY_ID=AKIA...
   AWS_SECRET_ACCESS_KEY=...
   AWS_SESSION_TOKEN=...  # optional, for temporary credentials
   ```

2. **Shared credentials file** (`~/.aws/credentials`):
   ```ini
   [default]
   aws_access_key_id = AKIA...
   aws_secret_access_key = ...
   ```

3. **IAM instance profile** (recommended for EC2/ECS/Lambda):
   No configuration needed. The SDK automatically uses the instance's IAM role.

4. **ECS task role**:
   Set `AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` (ECS sets this automatically).

## Secret Structure

Credentials are stored in Secrets Manager at:

```
{secret_prefix}{credential_id}
```

With the default `secret_prefix` of `tom/credentials/`, a credential named `lab_creds` would be at:

```
tom/credentials/lab_creds
```

Each secret must be JSON containing `username` and `password` keys:

```json
{
  "username": "admin",
  "password": "your-password"
}
```

## Creating Secrets

Using the AWS CLI:

```bash
# Create a new secret
aws secretsmanager create-secret \
  --name tom/credentials/lab_creds \
  --secret-string '{"username": "admin", "password": "your-password"}'

# Update an existing secret
aws secretsmanager put-secret-value \
  --secret-id tom/credentials/lab_creds \
  --secret-string '{"username": "admin", "password": "new-password"}'

# List secrets
aws secretsmanager list-secrets --filter Key=name,Values=tom/credentials/
```

## IAM Permissions

The IAM principal (user, role, or instance profile) needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:ListSecrets"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:tom/credentials/*"
    }
  ]
}
```

Adjust the resource ARN to match your region, account, and secret prefix.

## Settings Reference

| Setting | Env Var | Required | Default |
|---------|---------|----------|---------|
| `plugin_aws_secrets_manager_region` | `TOM_WORKER_PLUGIN_AWS_SECRETS_MANAGER_REGION` | No | boto3 default |
| `plugin_aws_secrets_manager_secret_prefix` | `TOM_WORKER_PLUGIN_AWS_SECRETS_MANAGER_SECRET_PREFIX` | No | `"tom/credentials/"` |
| `plugin_aws_secrets_manager_endpoint_url` | `TOM_WORKER_PLUGIN_AWS_SECRETS_MANAGER_ENDPOINT_URL` | No | AWS default |

The `endpoint_url` setting is useful for local testing with LocalStack or other AWS-compatible services.
