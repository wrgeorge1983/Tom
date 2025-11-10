FROM python:3.13-slim-trixie AS builder

# install uv
COPY --from=ghcr.io/astral-sh/uv:0.8.8 /uv /uvx /bin/

RUN mkdir -p /app/services/worker
WORKDIR /app/services/worker

COPY shared/ /app/shared/

# Install dependencies

COPY services/worker/uv.lock .
COPY services/worker/pyproject.toml .

RUN uv sync --locked --no-install-project --no-editable --no-dev && \
    find .venv -type d -name "ntc_templates" -exec sh -c 'cd {} && rm -rf templates && mkdir templates && touch templates/__init__.py' \; 2>/dev/null || true

# Copy the rest of the project
COPY --chown=app:app services/worker/ /app/services/worker
RUN  uv pip install --no-deps .

# Final stage
FROM python:3.13-slim-trixie

# Copy from builder
COPY --from=builder --chown=app:app /app /app

WORKDIR /app/services/worker

CMD [".venv/bin/python", "-m", "tom_worker.main"]



