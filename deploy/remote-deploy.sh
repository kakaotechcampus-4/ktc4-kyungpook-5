#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?set AWS_REGION}"
: "${BACKEND_IMAGE:?set BACKEND_IMAGE}"
: "${FRONTEND_IMAGE:?set FRONTEND_IMAGE}"

cd /opt/unyounghae
registry="${BACKEND_IMAGE%%/*}"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$registry"

printf 'BACKEND_IMAGE=%s\nFRONTEND_IMAGE=%s\nSITE_ADDRESS=%s\n' \
  "$BACKEND_IMAGE" "$FRONTEND_IMAGE" "${SITE_ADDRESS:-:80}" > .env.next

docker compose --env-file .env.next -f compose.yml pull
docker compose --env-file .env.next -f compose.yml up -d --remove-orphans

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
    mv .env.next .env
    exit 0
  fi
  sleep 2
done

docker compose --env-file .env.next -f compose.yml logs --tail 100 web >&2 || true
if [[ -f .env ]]; then
  docker compose --env-file .env -f compose.yml up -d --remove-orphans
fi
echo "Deployment health check failed; previous image configuration restored when available" >&2
exit 1
