from typing import Optional

from fastapi import APIRouter, Depends, Query
from starlette.requests import Request

from tom_controller.inventory.inventory import (
    InventoryStore,
    DeviceConfig,
    InventoryFilter,
)


def get_inventory_store(request: Request) -> InventoryStore:
    return request.app.state.inventory_store


router = APIRouter(tags=["inventory"])


@router.get("/inventory/export")
async def export_inventory(
    request: Request,
    inventory_store: InventoryStore = Depends(get_inventory_store),
    filter_name: Optional[str] = Query(
        None,
        description="Optional named filter (switches, routers, iosxe, arista_exclusion, ospf_crawler_filter)",
    ),
) -> dict[str, DeviceConfig]:
    """Export all nodes from inventory in DeviceConfig format.

    Supports two filtering modes:
    1. Named filters: ?filter_name=switches
    2. Inline filters: ?Caption=router.*&Vendor=cisco

    If filter_name is provided, it takes precedence over inline filters.
    Use GET /api/inventory/fields to see available filterable fields.
    Use GET /api/inventory/filters to see available named filters.
    """
    import logging

    log = logging.getLogger(__name__)

    try:
        nodes = await inventory_store.alist_all_nodes()

        # Apply named filter if specified
        if filter_name:
            filter_obj = inventory_store.get_filter(filter_name)
            nodes = [node for node in nodes if filter_obj.matches(node)]
            log.info(
                f"Filtered to {len(nodes)} nodes using named filter '{filter_name}'"
            )
        else:
            # Get all query params as inline filter patterns
            filter_params = dict(request.query_params)

            # Apply inline filters if any field patterns provided
            if filter_params:
                filter_obj = InventoryFilter(filter_params)
                nodes = [node for node in nodes if filter_obj.matches(node)]
                log.info(
                    f"Filtered to {len(nodes)} nodes using inline filters: {filter_params}"
                )
            else:
                log.info(f"Exported {len(nodes)} nodes (no filter)")

        # Convert to DeviceConfig format
        device_configs = {}
        for node in nodes:
            caption = node.get("Caption")
            if caption:
                # For SWIS, convert node to DeviceConfig; for YAML, node is already in DeviceConfig format
                if hasattr(inventory_store, "_node_to_device_config"):
                    device_configs[caption] = inventory_store._node_to_device_config(
                        node
                    )
                else:
                    # YAML store - node already has DeviceConfig fields
                    device_configs[caption] = DeviceConfig(
                        **{k: v for k, v in node.items() if k != "Caption"}
                    )

        return device_configs
    except Exception as e:
        log.error(f"Failed to export inventory: {e}")
        raise


@router.get("/inventory/export/raw")
async def export_raw_inventory(
    request: Request,
    inventory_store: InventoryStore = Depends(get_inventory_store),
    filter_name: Optional[str] = Query(
        None,
        description="Optional named filter (switches, routers, iosxe, arista_exclusion, ospf_crawler_filter)",
    ),
) -> list[dict]:
    """Export raw nodes from inventory (SolarWinds format for SWIS, YAML format for YAML).

    Supports two filtering modes:
    1. Named filters: ?filter_name=switches
    2. Inline filters: ?Vendor=cisco&Description=asr.*

    If filter_name is provided, it takes precedence over inline filters.
    Use GET /api/inventory/fields to see available filterable fields.
    Use GET /api/inventory/filters to see available named filters.
    """
    import logging

    log = logging.getLogger(__name__)

    try:
        nodes = await inventory_store.alist_all_nodes()

        # Apply named filter if specified
        if filter_name:
            filter_obj = inventory_store.get_filter(filter_name)
            nodes = [node for node in nodes if filter_obj.matches(node)]
            log.info(
                f"Filtered to {len(nodes)} raw nodes using named filter '{filter_name}'"
            )
        else:
            # Get all query params as inline filter patterns
            filter_params = dict(request.query_params)

            # Apply inline filters if any field patterns provided
            if filter_params:
                filter_obj = InventoryFilter(filter_params)
                nodes = [node for node in nodes if filter_obj.matches(node)]
                log.info(
                    f"Filtered to {len(nodes)} raw nodes using inline filters: {filter_params}"
                )
            else:
                log.info(f"Exported {len(nodes)} raw nodes (no filter)")

        return nodes
    except Exception as e:
        log.error(f"Failed to export raw inventory: {e}")
        raise


@router.get("/inventory/fields")
async def get_inventory_fields(
    inventory_store: InventoryStore = Depends(get_inventory_store),
) -> dict[str, str]:
    """Get available filterable fields for the current inventory source."""
    return inventory_store.get_filterable_fields()


@router.get("/inventory/filters")
async def list_filters(
    inventory_store: InventoryStore = Depends(get_inventory_store),
) -> dict[str, str]:
    """List available named inventory filters for the current inventory source."""
    return inventory_store.get_available_filters()


@router.get("/inventory/{device_name}")
async def inventory(
    device_name: str, inventory_store: InventoryStore = Depends(get_inventory_store)
) -> DeviceConfig:
    import logging

    log = logging.getLogger(__name__)
    log.info(f"Inventory endpoint called for device: {device_name}")
    log.info(f"Inventory store type: {type(inventory_store)}")

    try:
        result = await inventory_store.aget_device_config(device_name)
        log.info(f"Successfully retrieved config for {device_name}")
        return result
    except Exception as e:
        log.error(f"Failed to get device config for {device_name}: {e}")
        raise
