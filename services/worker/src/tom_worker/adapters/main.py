

def _get_available_drivers():
    """Get all available drivers from actual adapter implementations"""
    from tom_worker.adapters.scrapli_adapter import valid_async_drivers
    from netmiko.ssh_dispatcher import CLASS_MAPPER_BASE

    # Get actual netmiko drivers dynamically
    netmiko_drivers = list(CLASS_MAPPER_BASE.keys())

    return {
        "netmiko": {
            "drivers": sorted(netmiko_drivers),
            "note": "Netmiko drivers (all available drivers)",
        },
        "scrapli": {
            "drivers": sorted(valid_async_drivers.keys()),
            "note": "Scrapli async drivers",
        },
    }


def _dump_available_drivers():
    """Dump available drivers to stdout"""
    drivers = _get_available_drivers()

    print("# Available Adapter Drivers")
    print("# Use these values for 'adapter_driver' field in inventory.yml")
    print()

    for adapter_type, info in drivers.items():
        print(f"## {adapter_type}")
        print(f"# {info['note']}")
        for driver in info["drivers"]:
            print(f"  - {driver}")
        print()


if __name__ == "__main__":
    _dump_available_drivers()
