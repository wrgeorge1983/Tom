#!/usr/bin/env python3
import argparse
import requests
import yaml
import sys


class VaultCredentialManager:
    def __init__(self, vault_addr: str, token: str, mount_point: str = "secret"):
        self.addr = vault_addr.rstrip("/")
        self.token = token
        self.mount_point = mount_point
        self.headers = {"X-Vault-Token": token}

    def load_creds(self, creds_file: str, path_prefix: str = "credentials"):
        """Load YAML credentials into Vault"""
        try:
            with open(creds_file, "r") as f:
                creds = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Error: File {creds_file} not found")
            return False
        except yaml.YAMLError as e:
            print(f"Error parsing YAML: {e}")
            return False

        success_count = 0
        for cred_id, cred_data in creds.items():
            if self._write_secret(f"{path_prefix}/{cred_id}", cred_data):
                print(f"✓ Loaded credential: {cred_id}")
                success_count += 1
            else:
                print(f"✗ Failed to load credential: {cred_id}")

        print(f"\nLoaded {success_count}/{len(creds)} credentials")
        return success_count == len(creds)

    def list_creds(self, path_prefix: str = "credentials"):
        """List all credential names"""
        secrets = self._list_secrets(path_prefix)
        if secrets is None:
            print(f"No credentials found at {path_prefix}/")
            return

        print(f"Credentials at {path_prefix}/:")
        for secret in sorted(secrets):
            print(f"  - {secret}")
        print(f"\nTotal: {len(secrets)} credentials")

    def delete_cred(self, cred_id: str, path_prefix: str = "credentials"):
        """Delete a specific credential"""
        path = f"{path_prefix}/{cred_id}"
        if self._delete_secret(path):
            print(f"✓ Deleted credential: {cred_id}")
            return True
        else:
            print(f"✗ Failed to delete credential: {cred_id}")
            return False

    def purge_creds(self, path_prefix: str = "credentials", confirm: bool = False):
        """Delete all credentials"""
        secrets = self._list_secrets(path_prefix)
        if not secrets:
            print(f"No credentials found at {path_prefix}/")
            return True

        if not confirm:
            print(f"Found {len(secrets)} credentials to delete:")
            for secret in sorted(secrets):
                print(f"  - {secret}")
            print("\nUse --confirm to actually delete them")
            return False

        success_count = 0
        for secret in secrets:
            if self._delete_secret(f"{path_prefix}/{secret}"):
                print(f"✓ Deleted: {secret}")
                success_count += 1
            else:
                print(f"✗ Failed to delete: {secret}")

        print(f"\nDeleted {success_count}/{len(secrets)} credentials")
        return success_count == len(secrets)

    def _write_secret(self, path: str, secret_data: dict) -> bool:
        """Write secret to KV v2 store"""
        url = f"{self.addr}/v1/{self.mount_point}/data/{path}"
        payload = {"data": secret_data}

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            print(f"  Error writing {path}: {e}")
            return False

    def _list_secrets(self, path: str) -> list | None:
        """List secrets at path"""
        url = f"{self.addr}/v1/{self.mount_point}/metadata/{path}"
        params = {"list": "true"}

        try:
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()["data"]["keys"]
        except requests.RequestException as e:
            print(f"Error listing {path}: {e}")
            return None

    def _delete_secret(self, path: str) -> bool:
        """Delete secret (metadata and all versions)"""
        url = f"{self.addr}/v1/{self.mount_point}/metadata/{path}"

        try:
            response = requests.delete(url, headers=self.headers)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            print(f"  Error deleting {path}: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Manage credentials in HashiCorp Vault"
    )
    parser.add_argument(
        "--vault-addr", default="http://localhost:8200", help="Vault address"
    )
    parser.add_argument("--token", default="myroot", help="Vault token")
    parser.add_argument("--mount", default="secret", help="KV mount point")
    parser.add_argument(
        "--path-prefix", default="credentials", help="Path prefix for credentials"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Load command
    load_parser = subparsers.add_parser("load", help="Load credentials from YAML file")
    load_parser.add_argument("file", help="YAML file to load")

    # List command
    list_parser = subparsers.add_parser("list", help="List all credential names")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a specific credential")
    delete_parser.add_argument("cred_id", help="Credential ID to delete")

    # Purge command
    purge_parser = subparsers.add_parser("purge", help="Delete all credentials")
    purge_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete (otherwise just show what would be deleted)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    vault = VaultCredentialManager(args.vault_addr, args.token, args.mount)

    if args.command == "load":
        success = vault.load_creds(args.file, args.path_prefix)
        sys.exit(0 if success else 1)

    elif args.command == "list":
        vault.list_creds(args.path_prefix)

    elif args.command == "delete":
        success = vault.delete_cred(args.cred_id, args.path_prefix)
        sys.exit(0 if success else 1)

    elif args.command == "purge":
        success = vault.purge_creds(args.path_prefix, args.confirm)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
