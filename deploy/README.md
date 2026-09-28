# Team EC2 deployment

This deployment uses the existing Ubuntu 24.04 t3.medium instance in `ap-northeast-2`.
Do not launch another instance. The frontend is a static Vite build served by Caddy;
the API is a separate FastAPI container. Caddy sends `/api/*` to the API container.

## AWS setup

1. Keep inbound TCP 22 and 8000 closed. Allow TCP 80 for the initial IP-based demo.
   The API is bound only to `127.0.0.1:8000` on the instance.
2. Verify that Session Manager connects to the existing instance. Inspect the
   policies already attached to `ktc-ec2-ssm-role` for ECR pull access. Team
   accounts explicitly deny attaching policies to this managed role; if pull
   access is absent, request it from the infrastructure manager.
3. Create private ECR repositories `unyounghae-api` and `unyounghae-web` in Seoul.
4. Install Docker Engine, the Compose plugin, AWS CLI and `curl` on Ubuntu.
   Use the [official Docker Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
   Check with `sudo docker compose version` and `aws --version`.
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
It checks `http://127.0.0.1:8000/api/v1/healthz` and restores the previous image
configuration if that check fails. No SSH key or inbound port 22 is needed.

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
TCP 443. The public IP can
change after an EC2 stop/start, so update DNS after one.

The account's IAM deny on attaching policies to `ktc-ec2-ssm-role` is expected.
It does not imply that the preconfigured `ktc-github-deploy` OIDC role is broken.
