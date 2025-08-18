FROM python:3.13-slim-trixie AS builder

# install uv
COPY --from=ghcr.io/astral-sh/uv:0.8.8 /uv /uvx /bin/


RUN mkdir -p /app/services/core
WORKDIR /app/services/core

COPY shared/ /app/shared/

COPY services/core/uv.lock .
COPY services/core/pyproject.toml .
# Install dependencies
RUN uv sync --locked --no-install-project --no-editable --no-dev

# Copy the rest of the project
COPY --chown=app:app services/core/ /app/services/core/
RUN uv sync --locked --no-editable --no-dev



# Final stage
FROM python:3.13-slim-trixie

# Copy installed environment only, not source code
COPY --from=builder --chown=app:app /app /app

WORKDIR /app/services/core

CMD [".venv/bin/fastapi", "run", "src/tom_core/main.py"]



