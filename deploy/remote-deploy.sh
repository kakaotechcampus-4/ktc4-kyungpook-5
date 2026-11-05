#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?set AWS_REGION}"
: "${BACKEND_IMAGE:?set BACKEND_IMAGE}"
: "${FRONTEND_IMAGE:?set FRONTEND_IMAGE}"
: "${ACME_EMAIL:?set ACME_EMAIL}"

cd /opt/unyounghae
# Do not create a new store or overwrite an existing database configuration.
[[ -f api.env && -d api-storage ]] || {
  echo 'Missing /opt/unyounghae/api.env or existing api-storage directory' >&2
  exit 1
}

# Check the filesystem Docker actually uses before pulling or switching anything.
docker_root=$(docker info --format '{{.DockerRootDir}}')
available_kb=$(df -Pk "$docker_root" | awk 'NR == 2 {print $4}')
minimum_kb=$((2 * 1024 * 1024))
if [[ ! "$available_kb" =~ ^[0-9]+$ ]]; then
  echo "Cannot determine available disk space for Docker at $docker_root" >&2
  exit 1
fi
if (( available_kb < minimum_kb )); then
  echo "Insufficient disk space for deployment: Docker at $docker_root has ${available_kb} KiB available; at least ${minimum_kb} KiB (2 GiB) is required. See deploy/README.md for manual image cleanup." >&2
  exit 1
fi

# Shell variables override --env-file; the old deployment must use its own values.
previous_compose() (
  unset BACKEND_IMAGE FRONTEND_IMAGE SITE_ADDRESS ACME_EMAIL
  docker compose --env-file .env -f compose.yml "$@"
)

previous_images=''
current_images=$(printf '%s\n' "$BACKEND_IMAGE" "$FRONTEND_IMAGE" | sort -u)
cleanup_ready=true
if [[ -f .env && -f compose.yml ]]; then
  if ! previous_images=$(previous_compose config --images api web) \
    || [[ -z "$previous_images" ]]; then
    echo 'Warning: cannot read previous deployment images; image cleanup will be skipped.' >&2
    cleanup_ready=false
  else
    previous_images=$(printf '%s\n' "$previous_images" | sort -u)
    # Re-running the same release must not discard its rollback version.
    if [[ "$previous_images" == "$current_images" ]]; then
      if [[ ! -f .previous-images ]] || ! previous_images=$(cat .previous-images); then
        echo 'Warning: rollback image history is unavailable; image cleanup will be skipped.' >&2
        cleanup_ready=false
      fi
    fi
  fi
elif [[ -f .env || -f compose.yml ]]; then
  echo 'Warning: incomplete previous deployment configuration; image cleanup will be skipped.' >&2
  cleanup_ready=false
fi

registry="${BACKEND_IMAGE%%/*}"

cleanup_old_images() {
  [[ "$cleanup_ready" == true ]] || return 0
  local repository images image_repository tag image failed=0
  local keep_images
  # Keep this small rollback manifest across retries of the same commit. A
  # failure here is a cleanup failure, after the deployment is already committed.
  if ! printf '%s\n' "$previous_images" > .previous-images.next \
    || ! mv .previous-images.next .previous-images; then
    return 1
  fi
  keep_images=$(printf '%s\n' "$current_images" "$previous_images")
  echo "Retaining current and previous deployment images:"
  printf '%s\n' "$keep_images"

  # Delete explicit tags only from these two ECR repositories. Never prune the
  # host, force deletion, or remove untagged parents belonging to other images.
  for repository in "$registry/unyounghae-api" "$registry/unyounghae-web"; do
    if ! images=$(docker image ls --format '{{.Repository}} {{.Tag}}' "$repository"); then
      failed=1
      continue
    fi
    while read -r image_repository tag; do
      [[ "$image_repository" == "$repository" && -n "$tag" && "$tag" != '<none>' ]] || continue
      image="$image_repository:$tag"
      case $'\n'"$keep_images"$'\n' in
        *$'\n'"$image"$'\n'*) continue ;;
      esac
      if ! docker image rm --no-prune "$image"; then
        echo "Warning: could not remove old deployment image $image" >&2
        failed=1
      fi
    done <<< "$images"
  done
  return "$failed"
}

aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$registry"

printf 'BACKEND_IMAGE=%s\nFRONTEND_IMAGE=%s\nSITE_ADDRESS=%s\nACME_EMAIL=%s\n' \
  "$BACKEND_IMAGE" "$FRONTEND_IMAGE" "${SITE_ADDRESS:-:80}" "$ACME_EMAIL" > .env.next

docker compose --env-file .env.next -f compose.next.yml pull
# Read-only: the operator must inspect and migrate the selected DB beforehand.
docker compose --env-file .env.next -f compose.next.yml run --rm --no-deps api \
  uv run --no-sync python deployment_preflight.py
docker compose --env-file .env.next -f compose.next.yml up -d --remove-orphans

site_host="${SITE_ADDRESS:-:80}"
check_frontend() {
  if [[ "$site_host" == ":80" ]]; then
    curl --silent --fail --max-time 5 http://127.0.0.1/ >/dev/null
  else
    curl --silent --fail --max-time 5 \
      --resolve "$site_host:443:127.0.0.1" "https://$site_host/" >/dev/null \
      && curl --silent --fail --max-time 5 \
        --resolve "$site_host:443:127.0.0.1" \
        "https://$site_host/api/v1/healthz" >/dev/null
  fi
}

for attempt in {1..60}; do
  if curl --silent --fail http://127.0.0.1:8000/api/v1/healthz >/dev/null \
    && check_frontend; then
    mv compose.next.yml compose.yml
    mv .env.next .env
    if ! cleanup_old_images; then
      echo 'Warning: image cleanup failed; deployment remains successful. See deploy/README.md for manual image cleanup.' >&2
    fi
    exit 0
  fi
  sleep 2
done

docker compose --env-file .env.next -f compose.next.yml logs --tail 100 web >&2 || true
if [[ -f .env ]]; then
  previous_compose up -d --remove-orphans
fi
echo "Deployment health check failed; previous image configuration restored when available" >&2
exit 1
