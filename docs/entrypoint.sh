#!/bin/bash

# Prepare slop if enabled - copy to tmpfs to avoid mount permission issues
if [ "$INCLUDE_SLOP" = "true" ]; then
    # Copy existing docs first
    mkdir -p /tmp/docs/docs
    cp -r /app/docs/docs/* /tmp/docs/docs/ 2>/dev/null || true
    # Then copy slop contents into it
    mkdir -p /tmp/docs/docs/slop
    cp -r /app/slop/* /tmp/docs/docs/slop/
fi

# Select config file based on env var - use absolute paths
CONFIG_FILE="/app/mkdocs.yml"
if [ "$INCLUDE_SLOP" = "true" ]; then
    CONFIG_FILE="/app/mkdocs-slop.yml"
fi

# Run MkDocs serve with selected config
exec uv run mkdocs serve --dev-addr 0.0.0.0:8000 --config-file "$CONFIG_FILE"