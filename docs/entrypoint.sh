#!/bin/bash

# Prepare slop if enabled - copy to tmpfs to avoid mount permission issues
if [ "$INCLUDE_SLOP" = "true" ]; then
    # Copy existing docs first (exclude slop symlink)
    mkdir -p /tmp/docs/docs
    (cd /app/docs/docs && find . -maxdepth 1 ! -name slop ! -name . -exec cp -r {} /tmp/docs/docs/ \;)
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