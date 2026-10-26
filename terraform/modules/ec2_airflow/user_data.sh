#!/bin/bash
# Arranque del compadre: deja listo Docker, Compose, git y el cliente de MySQL.
# Cuando termine crea el archivo /var/lib/cloud/instance/compadre-listo.
set -euxo pipefail

dnf install -y docker git mariadb105 python3-pip
systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

touch /var/lib/cloud/instance/compadre-listo
