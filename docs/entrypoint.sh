#!/bin/bash

# Simple entrypoint - slop is just a subdirectory now
exec uv run mkdocs serve --dev-addr 0.0.0.0:8000