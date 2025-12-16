#!/usr/bin/env python3
"""
Seed NetBox with sample data for Tom tutorial.

This script creates:
- Manufacturers (Cisco, Arista)
- Device Types
- Platforms with netmiko_device_type
- Sites
- Device Roles
- Custom field for credential mapping
- Sample devices with IPs

Usage:
    python seed_netbox.py [--netbox-url URL] [--token TOKEN]

Defaults:
    --netbox-url: http://localhost:8080
    --token: 0123456789abcdef0123456789abcdef01234567
"""

import argparse
import sys
import time

try:
    import pynetbox
except ImportError:
    print("Error: pynetbox is required. Install with: pip install pynetbox")
    sys.exit(1)


def wait_for_netbox(nb, max_retries=30, delay=5):
    """Wait for NetBox to be ready."""
    print("Waiting for NetBox to be ready...")
    for i in range(max_retries):
        try:
            nb.status()
            print("NetBox is ready!")
            return True
        except Exception as e:
            print(f"  Attempt {i + 1}/{max_retries}: NetBox not ready yet ({e})")
            time.sleep(delay)
    print("Error: NetBox did not become ready in time")
    return False


def get_or_create(endpoint, search_field, search_value, create_data):
    """Get existing object or create new one."""
    # Search for existing
    filter_kwargs = {search_field: search_value}
    existing = list(endpoint.filter(**filter_kwargs))
    if existing:
        print(f"  Found existing: {search_value}")
        return existing[0]

    # Create new
    print(f"  Creating: {search_value}")
    return endpoint.create(create_data)


def create_custom_field(nb, name, content_types, field_type="text", label=None):
    """Create a custom field if it doesn't exist."""
    existing = list(nb.extras.custom_fields.filter(name=name))
    if existing:
        print(f"  Found existing custom field: {name}")
        return existing[0]

    print(f"  Creating custom field: {name}")
    return nb.extras.custom_fields.create(
        {
            "name": name,
            "type": field_type,
            "content_types": content_types,
            "label": label or name.replace("_", " ").title(),
            "filter_logic": "loose",
        }
    )


def seed_netbox(netbox_url, token):
    """Seed NetBox with tutorial data."""
    print(f"\nConnecting to NetBox at {netbox_url}")
    nb = pynetbox.api(netbox_url, token=token)

    # Wait for NetBox to be ready
    if not wait_for_netbox(nb):
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Creating Manufacturers")
    print("=" * 60)

    cisco = get_or_create(
        nb.dcim.manufacturers, "name", "Cisco", {"name": "Cisco", "slug": "cisco"}
    )

    arista = get_or_create(
        nb.dcim.manufacturers, "name", "Arista", {"name": "Arista", "slug": "arista"}
    )

    print("\n" + "=" * 60)
    print("Creating Device Types")
    print("=" * 60)

    cisco_isr = get_or_create(
        nb.dcim.device_types,
        "model",
        "ISR 4331",
        {"manufacturer": cisco.id, "model": "ISR 4331", "slug": "isr-4331"},
    )

    cisco_catalyst = get_or_create(
        nb.dcim.device_types,
        "model",
        "Catalyst 9300",
        {"manufacturer": cisco.id, "model": "Catalyst 9300", "slug": "catalyst-9300"},
    )

    arista_7050 = get_or_create(
        nb.dcim.device_types,
        "model",
        "7050SX3-48YC12",
        {
            "manufacturer": arista.id,
            "model": "7050SX3-48YC12",
            "slug": "7050sx3-48yc12",
        },
    )

    print("\n" + "=" * 60)
    print("Creating Platforms")
    print("=" * 60)

    # Platforms with netmiko_device_type for Tom integration
    cisco_ios_platform = get_or_create(
        nb.dcim.platforms,
        "name",
        "Cisco IOS",
        {
            "name": "Cisco IOS",
            "slug": "cisco-ios",
            "manufacturer": cisco.id,
            "napalm_driver": "ios",
            # This is the key field Tom uses
            "description": "netmiko_device_type: cisco_ios",
        },
    )

    cisco_iosxe_platform = get_or_create(
        nb.dcim.platforms,
        "name",
        "Cisco IOS-XE",
        {
            "name": "Cisco IOS-XE",
            "slug": "cisco-iosxe",
            "manufacturer": cisco.id,
            "napalm_driver": "ios",
            "description": "netmiko_device_type: cisco_xe",
        },
    )

    arista_eos_platform = get_or_create(
        nb.dcim.platforms,
        "name",
        "Arista EOS",
        {
            "name": "Arista EOS",
            "slug": "arista-eos",
            "manufacturer": arista.id,
            "napalm_driver": "eos",
            "description": "netmiko_device_type: arista_eos",
        },
    )

    print("\n" + "=" * 60)
    print("Creating Sites")
    print("=" * 60)

    site_dc1 = get_or_create(
        nb.dcim.sites, "name", "DC1", {"name": "DC1", "slug": "dc1", "status": "active"}
    )

    site_dc2 = get_or_create(
        nb.dcim.sites, "name", "DC2", {"name": "DC2", "slug": "dc2", "status": "active"}
    )

    print("\n" + "=" * 60)
    print("Creating Device Roles")
    print("=" * 60)

    role_router = get_or_create(
        nb.dcim.device_roles,
        "name",
        "Router",
        {"name": "Router", "slug": "router", "color": "0000ff"},
    )

    role_switch = get_or_create(
        nb.dcim.device_roles,
        "name",
        "Switch",
        {"name": "Switch", "slug": "switch", "color": "00ff00"},
    )

    print("\n" + "=" * 60)
    print("Creating Custom Fields for Tom Integration")
    print("=" * 60)

    # Custom field for credential mapping
    cf_credential = create_custom_field(
        nb,
        name="tom_credential_id",
        content_types=["dcim.device"],
        field_type="text",
        label="Tom Credential ID",
    )

    # Custom fields for adapter/driver override (Tom uses defaults if not set)
    cf_adapter = create_custom_field(
        nb,
        name="tom_adapter",
        content_types=["dcim.device"],
        field_type="text",
        label="Tom Adapter (netmiko/scrapli)",
    )

    cf_driver = create_custom_field(
        nb,
        name="tom_driver",
        content_types=["dcim.device"],
        field_type="text",
        label="Tom Driver (e.g. cisco_ios)",
    )

    print("\n" + "=" * 60)
    print("Creating Devices")
    print("=" * 60)

    # Define sample devices
    # NOTE: These IPs should be replaced with actual device IPs for real testing
    # tom_adapter and tom_driver custom fields specify how Tom connects
    devices = [
        {
            "name": "dc1-rtr-01",
            "device_type": cisco_isr.id,
            "role": role_router.id,
            "site": site_dc1.id,
            "platform": cisco_ios_platform.id,
            "status": "active",
            "custom_fields": {
                "tom_credential_id": "lab_creds",
                "tom_adapter": "netmiko",
                "tom_driver": "cisco_ios",
            },
            "ip": "10.0.1.1/24",
        },
        {
            "name": "dc1-rtr-02",
            "device_type": cisco_isr.id,
            "role": role_router.id,
            "site": site_dc1.id,
            "platform": cisco_iosxe_platform.id,
            "status": "active",
            "custom_fields": {
                "tom_credential_id": "lab_creds",
                "tom_adapter": "scrapli",
                "tom_driver": "cisco_iosxe",
            },
            "ip": "10.0.1.2/24",
        },
        {
            "name": "dc1-sw-01",
            "device_type": cisco_catalyst.id,
            "role": role_switch.id,
            "site": site_dc1.id,
            "platform": cisco_iosxe_platform.id,
            "status": "active",
            "custom_fields": {
                "tom_credential_id": "lab_creds",
                "tom_adapter": "scrapli",
                "tom_driver": "cisco_iosxe",
            },
            "ip": "10.0.1.10/24",
        },
        {
            "name": "dc2-sw-01",
            "device_type": arista_7050.id,
            "role": role_switch.id,
            "site": site_dc2.id,
            "platform": arista_eos_platform.id,
            "status": "active",
            "custom_fields": {
                "tom_credential_id": "arista_creds",
                "tom_adapter": "scrapli",
                "tom_driver": "arista_eos",
            },
            "ip": "10.0.2.10/24",
        },
        {
            "name": "dc2-sw-02",
            "device_type": arista_7050.id,
            "role": role_switch.id,
            "site": site_dc2.id,
            "platform": arista_eos_platform.id,
            "status": "active",
            "custom_fields": {
                "tom_credential_id": "arista_creds",
                "tom_adapter": "scrapli",
                "tom_driver": "arista_eos",
            },
            "ip": "10.0.2.11/24",
        },
    ]

    for dev_data in devices:
        ip_addr = dev_data.pop("ip")

        # Create device
        device = get_or_create(nb.dcim.devices, "name", dev_data["name"], dev_data)

        # Create interface
        intf = get_or_create(
            nb.dcim.interfaces,
            "name",
            "Management0",
            {
                "device": device.id,
                "name": "Management0",
                "type": "virtual",
            },
        )

        # Create IP address
        existing_ips = list(nb.ipam.ip_addresses.filter(address=ip_addr))
        if existing_ips:
            ip = existing_ips[0]
            print(f"  Found existing IP: {ip_addr}")
        else:
            print(f"  Creating IP: {ip_addr}")
            ip = nb.ipam.ip_addresses.create(
                {
                    "address": ip_addr,
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": intf.id,
                }
            )

        # Set as primary IP
        device.primary_ip4 = ip.id
        device.save()

    print("\n" + "=" * 60)
    print("NetBox Seed Complete!")
    print("=" * 60)
    print(f"""
Summary:
  - 2 Manufacturers (Cisco, Arista)
  - 3 Device Types
  - 3 Platforms
  - 2 Sites (DC1, DC2)
  - 2 Device Roles (Router, Switch)
  - 3 Custom Fields (tom_credential_id, tom_adapter, tom_driver)
  - 5 Devices with management IPs and Tom connection settings

Next Steps:
  1. Access NetBox at {netbox_url}
     Username: admin
     Password: admin

  2. Store credentials in Vault (from the repo root directory):
     uv run credload.py put lab_creds -u admin -p yourpassword
     uv run credload.py put arista_creds -u admin -p yourpassword

  3. Update device IPs in NetBox to match your actual lab devices

  4. Test Tom:
     curl -X POST "http://localhost:8000/api/device/dc1-rtr-01/send_command" \\
       -H "X-API-Key: tutorial-api-key-replace-me" \\
       -H "Content-Type: application/json" \\
       -d '{{"command": "show version", "wait": true}}'
""")


def main():
    parser = argparse.ArgumentParser(description="Seed NetBox with Tom tutorial data")
    parser.add_argument(
        "--netbox-url",
        default="http://localhost:8080",
        help="NetBox URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--token",
        default="0123456789abcdef0123456789abcdef01234567",
        help="NetBox API token",
    )

    args = parser.parse_args()
    seed_netbox(args.netbox_url, args.token)


if __name__ == "__main__":
    main()
