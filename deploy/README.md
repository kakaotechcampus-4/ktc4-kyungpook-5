# Team EC2 deployment

This deployment uses the existing Ubuntu 24.04 t3.medium instance in `ap-northeast-2`.
Do not launch another instance. The frontend is a static Vite build served by Caddy;
the API is a separate FastAPI container. Caddy sends `/api/*` to the API container.

## AWS setup

1. Keep inbound TCP 22 and 8000 closed. Allow TCP 80 for the initial IP-based demo.
   The API is bound only to `127.0.0.1:8000` on the instance.

## API database and file storage prerequisites

Before deploying this meeting-enabled image, inspect the existing instance and
database first. The old deployment has no declared API database or file volume;
that does not establish whether another database or storage already exists.
Identify the intended PostgreSQL database and existing uploaded files, preserve
and back them up, and confirm the database supports the pgvector extension.
Do not point the application at a new empty database as a substitute for existing
data. Do not copy secrets into Git, workflow variables or logs.

The operator must provide `/opt/unyounghae/api.env` (restricted permissions)
with `DATABASE_URL` and the required provider settings, and explicitly provision
`/opt/unyounghae/api-storage` with any existing uploaded files. The container
mounts that directory at `/app/var/storage`; it is not created by deployment.
`REMINDER_DISPATCHER_ENABLED` should remain false until Push configuration and
recipient behavior have been verified. STT and AI provider settings are separate.
The database must be attached to the separately managed external Docker network
`unyounghae-db` (override with `DB_NETWORK`). Compose does not create or remove
the database container or its persistent volume; do not publish its port.

The image contains Alembic files. Inspect the existing database revision and
backup before running `uv run --no-sync alembic upgrade head` against the selected
database using this image and the private environment. This migration is an
explicit operator step; deploy never automatically initializes or migrates a DB.
The PostgreSQL user must have permission for the migration and `vector` extension.

The deploy script refuses to switch containers unless the private env file and
storage directory exist and a read-only preflight confirms database connectivity,
the expected Alembic head and pgvector. This does not verify actual AI, STT, Push,
backups or the identity of the database; those remain separate operator checks.
The candidate compose file is staged separately so a preflight failure does not
overwrite the last deployed compose configuration.
2. Verify that Session Manager connects to the existing instance. Inspect the
   policies already attached to `ktc-ec2-ssm-role` for ECR pull access. Team
   accounts explicitly deny attaching policies to this managed role; if pull
   access is absent, request it from the infrastructure manager.
3. Create private ECR repositories `unyounghae-api` and `unyounghae-web` in Seoul.
4. On its first run, the SSM deployment installs Docker Engine, the Compose
   plugin, AWS CLI and `curl` on Ubuntu if missing. It uses the official Docker
   apt repository and AWS CLI installer. Later runs reuse the installation.
5. The team account already has the OIDC deployment role `ktc-github-deploy`.
   Do not create another role or an access key. First set only the GitHub
   repository Actions variable `AWS_ACCOUNT_ID` (the 12-digit team account ID).
   The ECR publish job can run now; the EC2 deployment job stays skipped while
   `EC2_INSTANCE_ID` is unset.
6. Run the `OIDC connection test` workflow manually on `develop`. Confirm that
   `aws sts get-caller-identity` reports `assumed-role/ktc-github-deploy`.
   The account guide confirms the role exists, but does not list its ECR push
   or SSM Run Command permissions. The first publish run checks ECR access in
   practice; request missing permissions from the infrastructure manager if it
   fails. Once the instance is ready, set the `EC2_INSTANCE_ID` Actions variable
   to enable automatic deployment. Leave `SITE_ADDRESS` unset for the IP-based
   HTTP demo.

## Initial deployment

Push the deployment files to `develop`. The workflow tests the frontend and
backend, builds both images in GitHub-hosted runners, pushes them to ECR with the
commit SHA as tag, then uses SSM Run Command to update the existing instance.
Pull requests targeting `develop` run verification only. Manual workflow runs also
run verification only; only a push to `develop` can publish images or deploy.
Pushes to `MVP` do not trigger this workflow.
It checks the local API and, when a domain is configured, validates the public
HTTPS certificate and API proxy. It restores the previous image configuration
if health checks fail. No SSH key or inbound port 22 is needed.

After the first run, check the Actions result and on the instance run:

```bash
sudo docker compose --env-file /opt/unyounghae/.env -f /opt/unyounghae/compose.yml ps
curl -fsS http://127.0.0.1:8000/api/v1/healthz
curl -I http://127.0.0.1/
```

Then browse to `http://<instance-public-ip>/`. Port 80 is HTTP. Do not use
real credentials or sensitive uploads in this demo until a domain and HTTPS are
configured. When a domain is available, point it at the current public IP,
set the GitHub Actions variable `SITE_ADDRESS` to the domain and open inbound
TCP 443. If the instance uses an Elastic IP, keep it associated with that
instance; otherwise, the public IP can change after a stop/start.

The account's IAM deny on attaching policies to `ktc-ec2-ssm-role` is expected.
It does not imply that the preconfigured `ktc-github-deploy` OIDC role is broken.

## Disk space and deployment image retention (#243)

Before ECR login or image pulls, `remote-deploy.sh` checks the filesystem at
Docker's `DockerRootDir`. It stops if less than **2 GiB (2,097,152 KiB)** is
available, reporting the path, available space and required space. It leaves the
running containers and deployed configuration in place. This is a minimum for
pulling about two image sets, not a reservation of space or a guarantee that a
larger future image will fit.

After the API/frontend health checks pass and `compose.next.yml` and `.env.next`
replace the deployed files, cleanup removes old tags from exactly these ECR
repositories in the deployment registry: `unyounghae-api` and `unyounghae-web`.
It keeps the new images and the images from the preceding successful deployment,
read from the saved Compose configuration **before** it is replaced. Image build
time is not used, so deploying an older commit also preserves the correct
rollback version. Shell image/site variables are cleared when reading the old
configuration or restoring it after a failed health check, so they cannot
override the saved `.env` values.

The previous image references are saved to `/opt/unyounghae/.previous-images`;
the retained references are also printed in the deployment command output.
Re-running the same commit retains this rollback history. On the first deployment
there is no previous version to retain. If the previous configuration or required
history cannot be read, cleanup is skipped with a warning. A failed cleanup or
history write also emits a warning and **does not fail or roll back a successful
deployment**. Pull, preflight or health-check failures never run image cleanup.

Deletion uses individual image tags with `docker image rm --no-prune`, without
`--force`. Images still required by containers may remain when Docker refuses to
delete them. PostgreSQL/pgvector images, other repositories, unidentifiable
dangling images, containers, networks, volumes, `api-storage/` and `backups/` are
not cleanup targets. ECR images remain available for pulling older versions.
See Docker's [image removal reference](https://docs.docker.com/reference/cli/docker/image/rm/)
and [Compose variable precedence](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/#ways-to-set-variables-with-interpolation)
for the underlying CLI behavior.

### Inspect and clean images manually

Use Session Manager on the existing instance. Inspect disk usage, current image
references and the rollback manifest before choosing any old tags to remove:

```bash
cd /opt/unyounghae
docker_root=$(sudo docker info --format '{{.DockerRootDir}}')
df -h "$docker_root"
sudo docker system df
sudo env -u BACKEND_IMAGE -u FRONTEND_IMAGE -u SITE_ADDRESS -u ACME_EMAIL \
  docker compose --env-file .env -f compose.yml config --images api web
sudo cat .previous-images  # absent until the first cleanup with known history
sudo docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
sudo docker image ls --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}'
```

If `.previous-images` is absent (for example, before this change is first
deployed), identify the previous successful deployment's SHA from GitHub Actions
and preserve its API and web tags as well as the current tags. Do not infer the
previous deployment from image creation time.

Remove only specific older API/web tags after inspecting the list, replacing
the account and SHA placeholders below. These are explicit examples to edit,
not a command to prune the host:

```bash
registry='<AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com'
old_sha='<SHA_OLDER_THAN_CURRENT_AND_PREVIOUS>'
sudo docker image rm --no-prune "$registry/unyounghae-api:$old_sha"
sudo docker image rm --no-prune "$registry/unyounghae-web:$old_sha"
df -h "$docker_root"
sudo docker system df
```

Do not use `docker system prune`, `docker image prune -a`, volume prune commands,
`--force`, or delete files under `api-storage/` or `backups/` for this task.
If Docker reports an image is still in use, inspect the container; automatic
cleanup intentionally leaves it alone. Once at least 2 GiB is free, retry the
deployment. Older removed tags can be pulled from ECR if needed.

### Deployment regression checks

Run from the repository root (also included in the CI `verify` job):

```bash
bash -n deploy/remote-deploy.sh
python3 -m unittest discover -s deploy/tests -v
```

The tests execute the shell script with isolated, stateful Docker/AWS/disk/HTTP
doubles. They cover two consecutive releases, same-release retries, repository
scope, disk thresholds, rollback, skipped cleanup and non-fatal cleanup errors;
they do not connect to the production instance or remove real images. After
deploying two distinct commits on the instance, verify that each app repository
has only the current and previous tags (unless Docker refused an in-use image),
and check the API health endpoint again.
