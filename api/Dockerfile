# Start from a small official image that already contains Python 3.12
FROM python:3.12-slim

# Copy the uv program into the image from Astral's official image.
# ("latest" is fine while learning; pin a version before sharing the project.)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# uv settings:
#   UV_COMPILE_BYTECODE=1    precompile Python files so the API starts faster
#   UV_LINK_MODE=copy        copy packages instead of linking (avoids warnings in Docker)
#   UV_PYTHON_DOWNLOADS=never  use the Python already in this image, never download another
# PATH: put the virtual environment first, so commands like "uvicorn" are found
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# All following commands run inside the /app folder of the image
WORKDIR /app

# Layer 1: copy ONLY the dependency files first.
# Docker caches this layer, so packages are not reinstalled when you only edit code.
COPY pyproject.toml uv.lock .python-version ./

# Install the packages exactly as pinned in uv.lock:
#   --locked            fail if uv.lock is out of date with pyproject.toml
#   --no-dev            skip ruff, pytest and httpx (not needed in the running API)
#   --no-install-project  install only the libraries, not our own code yet
# The cache mount keeps uv's download cache between builds, so rebuilds are faster.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Layer 2: copy your application code (changes often, so it comes last)
COPY app ./app

# Command that runs when the container starts:
#   app.main:app  = the "app" object inside app/main.py
#   --host 0.0.0.0  accept connections from outside the container
#   --port 8000   the port the API listens on
#   --reload      restart automatically when code changes (development only)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]