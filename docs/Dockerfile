FROM python:3.12-slim-trixie

# Create a non-root user
RUN useradd --create-home --shell /bin/bash mkdocs

# install uv
COPY --from=ghcr.io/astral-sh/uv:0.8.8 /uv /uvx /bin/

WORKDIR /app

# Change ownership
RUN chown mkdocs:mkdocs /app

# Switch to non-root user
USER mkdocs

# Copy pyproject.toml and uv.lock
COPY --chown=mkdocs:mkdocs pyproject.toml uv.lock ./

# Set venv path to avoid conflicts with mounted .venv
ENV UV_PROJECT_ENVIRONMENT_DIR=/tmp/venv

# Sync dependencies
RUN uv sync --frozen

# Copy docs source
COPY --chown=mkdocs:mkdocs . .

# Expose port
EXPOSE 8000

# Run mkdocs serve directly (shell form for proper signal handling)
CMD uv run mkdocs serve --dev-addr 0.0.0.0:8000