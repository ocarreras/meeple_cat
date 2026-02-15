#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# EC2 user-data script: installs Docker on Ubuntu 24.04
# This runs automatically on first boot via cloud-init.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# Update system
apt-get update
apt-get upgrade -y

# Install Docker (official repo)
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Let ubuntu user use docker without sudo
usermod -aG docker ubuntu

# Create project directory
mkdir -p /opt/meeple
chown ubuntu:ubuntu /opt/meeple

# Enable Docker on boot
systemctl enable docker
systemctl start docker

# Basic firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "Server setup complete" > /opt/meeple/.setup-done
