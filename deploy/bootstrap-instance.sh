#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  printf 'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' \
    "${UBUNTU_CODENAME:-$VERSION_CODENAME}" "$(dpkg --print-architecture)" \
    > /etc/apt/sources.list.d/docker.sources
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi

if ! command -v aws >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y curl unzip
  case "$(uname -m)" in
    x86_64) aws_arch=x86_64 ;;
    aarch64) aws_arch=aarch64 ;;
    *) echo 'Unsupported architecture for AWS CLI' >&2; exit 1 ;;
  esac
  installer_dir=$(mktemp -d)
  trap 'rm -rf "$installer_dir"' EXIT
  curl -fsSLo "$installer_dir/awscliv2.zip" \
    "https://awscli.amazonaws.com/awscli-exe-linux-${aws_arch}.zip"
  unzip -q "$installer_dir/awscliv2.zip" -d "$installer_dir"
  "$installer_dir/aws/install"
fi

docker compose version
aws --version
