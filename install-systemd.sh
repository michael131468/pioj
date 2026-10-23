#!/bin/bash
# Install pioj as a systemd user service with Podman

set -e

# Configuration
IMAGE="${PIOJ_IMAGE:-ghcr.io/OWNER/REPO:latest}"
CONTAINER_NAME="pioj"
DATA_DIR="${PIOJ_DATA_DIR:-$HOME/.local/share/pioj}"
ENV_FILE="${PIOJ_ENV_FILE:-$HOME/.config/pioj/.env}"

echo "=== pioj systemd installer ==="
echo "Image: $IMAGE"
echo "Data directory: $DATA_DIR"
echo "Env file: $ENV_FILE"
echo

# Create directories
mkdir -p "$DATA_DIR"
mkdir -p "$(dirname "$ENV_FILE")"

# Create .env template if it doesn't exist
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating .env template at $ENV_FILE"
    cat > "$ENV_FILE" <<'EOF'
# JIRA Configuration (required)
JIRA_HOST=https://your-instance.atlassian.net
JIRA_TOKEN=your_token_here
JIRA_EMAIL=your@email.com

# Optional: Custom field overrides
#JIRA_ESTIMATION_FIELD=Custom Field Name
#JIRA_SPRINT_FIELD=Custom Sprint Field

# Optional: LLM integration for AI summaries
#LLM_API_KEY=your_api_key
#LLM_API_BASE=https://api.openai.com/v1
#LLM_MODEL=gpt-4o-mini
EOF
    echo "⚠️  Please edit $ENV_FILE with your JIRA credentials"
    echo
fi

# Pull the image
echo "Pulling image..."
podman pull "$IMAGE"

# Stop and remove existing container if present
if podman ps -a --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "Removing existing container..."
    podman rm -f "$CONTAINER_NAME" 2>/dev/null || true
fi

# Create the container (don't start it yet)
echo "Creating container..."
podman create \
    --name "$CONTAINER_NAME" \
    -p 5000:5000 \
    -v "$ENV_FILE:/app/.env:ro,Z" \
    -v "$DATA_DIR:/app/data:Z" \
    "$IMAGE"

# Generate systemd unit
echo "Generating systemd unit..."
mkdir -p ~/.config/systemd/user
podman generate systemd --new --name "$CONTAINER_NAME" \
    > ~/.config/systemd/user/${CONTAINER_NAME}.service

# Enable and start the service
echo "Enabling and starting service..."
systemctl --user daemon-reload
systemctl --user enable ${CONTAINER_NAME}.service
systemctl --user start ${CONTAINER_NAME}.service

# Enable lingering (so service starts on boot without login)
loginctl enable-linger "$USER"

echo
echo "✅ Installation complete!"
echo
echo "Service status:"
systemctl --user status ${CONTAINER_NAME}.service --no-pager
echo
echo "Useful commands:"
echo "  systemctl --user status ${CONTAINER_NAME}   # Check status"
echo "  systemctl --user restart ${CONTAINER_NAME}  # Restart service"
echo "  systemctl --user stop ${CONTAINER_NAME}     # Stop service"
echo "  systemctl --user disable ${CONTAINER_NAME}  # Disable auto-start"
echo "  journalctl --user -u ${CONTAINER_NAME} -f   # View logs"
echo
echo "Access pioj at: http://localhost:5000"
echo "Edit config: $ENV_FILE"
echo "Data location: $DATA_DIR"
