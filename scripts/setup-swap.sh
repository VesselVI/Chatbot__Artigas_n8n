#!/usr/bin/env bash
# Create 2G swap if missing (recommended on KVM2 with Chatwoot)
set -euo pipefail
if swapon --show | grep -q .; then
  echo "Swap already configured."
  exit 0
fi
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo "2G swap enabled."
