"""Cache management API endpoints."""

import logging
from typing import Optional
from fastapi import Request, Depends, Query

from tom_controller.api.api import router
from tom_controller.api import do_auth
from tom_controller.api.auth import AuthResponse
from tom_controller.exceptions import TomException

logger = logging.getLogger(__name__)


@router.delete("/cache/{device_name}")
async def invalidate_device_cache(
    request: Request,
    device_name: str,
    auth: AuthResponse = Depends(do_auth)
) -> dict:
    """Invalidate all cache entries for a specific device.
    
    Args:
        device_name: Name of the device to invalidate cache for
        
    Returns:
        dict with count of invalidated entries
    """
    cache_manager = request.app.state.cache_manager
    
    if not cache_manager:
        raise TomException("Cache manager not available")
    
    deleted_count = await cache_manager.invalidate_device(device_name)
    
    logger.info(f"Invalidated {deleted_count} cache entries for device {device_name} by user {auth.get('user')}")
    
    return {
        "device": device_name,
        "deleted_count": deleted_count,
        "message": f"Invalidated {deleted_count} cache entries for {device_name}"
    }


@router.delete("/cache")
async def clear_all_cache(
    request: Request,
    auth: AuthResponse = Depends(do_auth)
) -> dict:
    """Clear all cache entries.
    
    Returns:
        dict with count of cleared entries
    """
    cache_manager = request.app.state.cache_manager
    
    if not cache_manager:
        raise TomException("Cache manager not available")
    
    deleted_count = await cache_manager.clear_all()
    
    logger.info(f"Cleared all cache: {deleted_count} entries deleted by user {auth.get('user')}")
    
    return {
        "deleted_count": deleted_count,
        "message": f"Cleared {deleted_count} cache entries"
    }


@router.get("/cache")
async def list_cache_keys(
    request: Request,
    device_name: Optional[str] = Query(None, description="Filter keys by device name"),
    auth: AuthResponse = Depends(do_auth)
) -> dict:
    """List all cache keys, optionally filtered by device.
    
    Args:
        device_name: Optional device name to filter by
        
    Returns:
        dict with list of cache keys
    """
    cache_manager = request.app.state.cache_manager
    
    if not cache_manager:
        raise TomException("Cache manager not available")
    
    keys = await cache_manager.list_keys(device_name=device_name)
    
    return {
        "device_filter": device_name,
        "count": len(keys),
        "keys": keys
    }


@router.get("/cache/stats")
async def get_cache_stats(
    request: Request,
    auth: AuthResponse = Depends(do_auth)
) -> dict:
    """Get cache statistics.
    
    Returns:
        dict with cache statistics
    """
    cache_manager = request.app.state.cache_manager
    
    if not cache_manager:
        raise TomException("Cache manager not available")
    
    # Get all keys to calculate stats
    all_keys = await cache_manager.list_keys()
    
    # Group by device (keys are like "device:command:hash")
    devices = {}
    for key in all_keys:
        parts = key.split(":", 1)
        if len(parts) >= 1:
            device = parts[0]
            devices[device] = devices.get(device, 0) + 1
    
    return {
        "enabled": request.app.state.settings.cache_enabled,
        "total_entries": len(all_keys),
        "devices_cached": len(devices),
        "entries_per_device": devices,
        "default_ttl": request.app.state.settings.cache_default_ttl,
        "max_ttl": request.app.state.settings.cache_max_ttl,
        "key_prefix": request.app.state.settings.cache_key_prefix
    }