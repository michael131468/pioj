# syntax=docker/dockerfile:1

FROM fedora:latest AS builder

# Install Python and uv
RUN dnf install -y python3.12 python3-pip && \
    dnf clean all

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Final stage
FROM fedora:latest

# Install Python
RUN dnf install -y python3.12 && \
    dnf clean all

# Set working directory
WORKDIR /app

# Copy uv and virtual environment from builder
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /app/.venv /app/.venv

# Copy application files
COPY server.py main.py ./
COPY index.html favicon.svg ./
COPY .env.example ./

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Create volume mount points for persistent data
VOLUME ["/app/data"]

# Run the application
CMD ["python3", "server.py"]
