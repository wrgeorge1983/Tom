FROM python:3.13-slim-trixie AS builder

# install uv
COPY --from=ghcr.io/astral-sh/uv:0.8.8 /uv /uvx /bin/

WORKDIR /app

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-install-workspace --no-editable

# Copy the rest of the project
ADD . /app

# Sync the whole project

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


# Final stage
FROM python:3.13-slim-trixie

# Copy installed environment only, not source code
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app /app

WORKDIR /app

CMD [".venv/bin/fastapi", "run", "src/tom_core/main.py"]



