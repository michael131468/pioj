#!/bin/bash
# Install pioj as a systemd user service (native, no container)

set -e

SERVICE_NAME="pioj"
INSTALL_DIR="$HOME/bin/pioj"
ENV_FILE="$INSTALL_DIR/.env"
SYSTEMD_ENV_FILE="$HOME/.config/pioj/systemd.env"

echo "=== pioj systemd installer (native) ==="
echo "Install directory: $INSTALL_DIR"
echo "Env file: $ENV_FILE"
echo

# Create systemd env file directory
mkdir -p "$(dirname "$SYSTEMD_ENV_FILE")"

# Check if we should import from current environment
if [ -n "$JIRA_HOST" ] && [ -n "$JIRA_TOKEN" ]; then
    echo "Found JIRA variables in environment, creating systemd env file..."
    cat > "$SYSTEMD_ENV_FILE" <<EOF
# Environment variables for systemd service
# Auto-generated from current shell environment
JIRA_HOST=${JIRA_HOST}
JIRA_TOKEN=${JIRA_TOKEN}
JIRA_EMAIL=${JIRA_EMAIL:-}
EOF
    [ -n "$JIRA_ESTIMATION_FIELD" ] && echo "JIRA_ESTIMATION_FIELD=${JIRA_ESTIMATION_FIELD}" >> "$SYSTEMD_ENV_FILE"
    [ -n "$JIRA_SPRINT_FIELD" ] && echo "JIRA_SPRINT_FIELD=${JIRA_SPRINT_FIELD}" >> "$SYSTEMD_ENV_FILE"
    [ -n "$LLM_API_KEY" ] && echo "LLM_API_KEY=${LLM_API_KEY}" >> "$SYSTEMD_ENV_FILE"
    [ -n "$LLM_API_BASE" ] && echo "LLM_API_BASE=${LLM_API_BASE}" >> "$SYSTEMD_ENV_FILE"
    [ -n "$LLM_MODEL" ] && echo "LLM_MODEL=${LLM_MODEL}" >> "$SYSTEMD_ENV_FILE"

    chmod 600 "$SYSTEMD_ENV_FILE"
    echo "Created: $SYSTEMD_ENV_FILE"
elif [ -f "$ENV_FILE" ]; then
    echo "Using existing .env file: $ENV_FILE"
    SYSTEMD_ENV_FILE="$ENV_FILE"
else
    echo "⚠️  Warning: No environment variables found and no .env file exists"
    echo "Please either:"
    echo "  1. Create $ENV_FILE from .env.example"
    echo "  2. Set JIRA_HOST, JIRA_TOKEN, JIRA_EMAIL and re-run this script"
    echo
fi

# Create systemd user service
echo "Creating systemd service..."
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/${SERVICE_NAME}.service <<EOF
[Unit]
Description=pioj - JIRA Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$SYSTEMD_ENV_FILE
ExecStart=/usr/bin/env uv run server.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
EOF

# Reload systemd and enable service
echo "Enabling and starting service..."
systemctl --user daemon-reload
systemctl --user enable ${SERVICE_NAME}.service
systemctl --user start ${SERVICE_NAME}.service

# Enable lingering (so service starts on boot without login)
loginctl enable-linger "$USER"

echo
echo "✅ Installation complete!"
echo
echo "Service status:"
systemctl --user status ${SERVICE_NAME}.service --no-pager || true
echo
echo "Useful commands:"
echo "  systemctl --user status ${SERVICE_NAME}   # Check status"
echo "  systemctl --user restart ${SERVICE_NAME}  # Restart service"
echo "  systemctl --user stop ${SERVICE_NAME}     # Stop service"
echo "  systemctl --user disable ${SERVICE_NAME}  # Disable auto-start"
echo "  journalctl --user -u ${SERVICE_NAME} -f   # View logs"
echo
echo "Access pioj at: http://localhost:5000"
echo "Environment file: $SYSTEMD_ENV_FILE"
