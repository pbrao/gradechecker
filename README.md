# Grade Checker

Automated assignment and grade monitoring for Home Access Center (HAC). It logs in headlessly, extracts live assignment data, analyzes it with an LLM, and optionally emails an HTML report. A minimal HTTP server exposes endpoints to trigger the workflow from a container.

Key files:

- [pydanticai_gradechecker.py](pydanticai_gradechecker.py)
- [basic_server.py](basic_server.py)
- [Dockerfile](Dockerfile)
- [.dockerignore](.dockerignore)

---

Features

- Headless HAC scraping

  - Hardened Chrome options for containers; nested iframe handling; explicit waits for assignment rows.
  - Strict mode: if 0 assignments are extracted, the run fails (no fallback) when invoked via HTTP.

- AI analysis (HTML report)

  - Model: gemini-2.5-flash (temperature 0).
  - Output normalized to pure HTML string for clean email rendering.

- Email delivery

  - Gmail SMTP with app password, multiple recipients supported.

- Scheduling

  - Optional daily run at 3:00 PM via CLI flag.

- Observability

  - Optional Logfire with token-based configuration and advanced options (base URL, service metadata).

- Security hardening
  - Token-required POST trigger (configurable).
  - Rate limiting and concurrency guarding.
  - Secure HTTP headers (CSP, X-Frame-Options, etc.) and reduced fingerprinting.
  - Safe logs and sanitized HTTP responses to avoid leaking PII.
  - Secrets are not baked into the image; non-root user in container; sensitive artifacts stored in /tmp.

---

Architecture Overview

- HTTP server

  - [basic_server.py](basic_server.py) serves:
    - GET /health
    - POST /run-grade-check: triggers a subprocess running [pydanticai_gradechecker.py](pydanticai_gradechecker.py) with email enabled
  - Adds security headers, optional authentication, rate limiting, and prevents concurrent runs.

- CLI workflow
  - [pydanticai_gradechecker.py](pydanticai_gradechecker.py):
    - Logs into HAC and extracts assignments.
    - Saves data to a file in /tmp (path configurable).
    - Performs LLM analysis and sends email.

---

Environment Variables

Core (required for full pipeline)

- HAC_URL: HAC login URL
- HAC_USERNAME: HAC username
- HAC_PASSWORD: HAC password
- GMAIL_SENDER: Sender email address
- GMAIL_APP_PASSWORD: Gmail app password
- GMAIL_RECEIVERS: Comma-separated list of recipients
- GEMINI_API_KEY or GOOGLE_API_KEY: Gemini API key (either var is supported)

Logfire (optional)

- LOGFIRE_TOKEN: Token for project auth
- LOGFIRE_BASE_URL: e.g. https://logfire-us.pydantic.dev
- LOGFIRE_SERVICE_NAME: e.g. gradechecker
- LOGFIRE_SERVICE_VERSION: e.g. 0.1.0
- ENVIRONMENT: e.g. production

Security and runtime (recommended)

- ENVIRONMENT: production/development (affects default auth requirements)
- SERVICE_AUTH_TOKEN: Token required to POST /run-grade-check (when enabled)
- REQUIRE_AUTH: true/false (default true in production)
- MIN_RUN_INTERVAL_SEC: Minimum seconds between accepted POST triggers (default 60)
- SAFE_HTTP_RESPONSE: true/false (when true, suppresses stdout/stderr in HTTP responses)
- SAFE_LOGS: true/false (when true, avoids printing the full HTML analysis to stdout; default true)
- ASSIGNMENTS_PATH: Path to store assignments data (default /tmp/assignments.txt)
- DISABLE_DEV_SHM_USAGE: true/false; set true in constrained containers to avoid Chrome using /dev/shm
- LOGFIRE_DISABLE: true/false; disable Logfire entirely
- DEBUG*SNAPSHOTS: true/false; when true, writes /tmp/hac*\_.png and /tmp/hac\_\_.html inside the container for debugging

---

Build and Run Locally (Podman)

1. Build the image

- The image contains Chrome and Chromedriver aligned for headless scraping.

  sudo podman build -t localhost/grade-checker-gcloud:latest .

2. Run the container

- Use your .env for credentials and set security controls.

  sudo podman run -d --name grade-checker-strict \
   -p 8080:8080 \
   --env-file .env \
   -e SERVICE_AUTH_TOKEN=dev \
   -e REQUIRE_AUTH=false \
   -e ENVIRONMENT=development \
   -e MIN_RUN_INTERVAL_SEC=5 \
   -e SAFE_HTTP_RESPONSE=true \
   -e SAFE_LOGS=true \
   -e ASSIGNMENTS_PATH=/tmp/assignments.txt \
   -e LOGFIRE_DISABLE=true \
   -e DISABLE_DEV_SHM_USAGE=true \
   --shm-size=1g \
   --tmpfs /tmp:rw,size=1g \
   localhost/grade-checker-gcloud:latest

Optional hardened runtime flags (validate first):

- --read-only
- --tmpfs /tmp:rw,size=1g
- --pids-limit=256
- --memory=1g --memory-swap=1g
- --cap-drop=ALL

3. Health and trigger

- Health:
  curl -i http://localhost:8080/health

- Trigger run (authenticated, production-style):
  curl -i -X POST -H 'X-Auth-Token: your-strong-token' http://localhost:8080/run-grade-check

- Development endpoint (bypasses auth when REQUIRE_AUTH=false or ENVIRONMENT!=production):

  - Local-file + email (uses baked-in assignments.txt for isolation):
    curl -i -X POST "http://localhost:8080/run-grade-check-dev?local=1"
  - Live scrape + email:
    curl -i -X POST "http://localhost:8080/run-grade-check-dev"

- Logs:
  sudo podman logs --tail 200 grade-checker-strict

4. Exec into the container (for direct CLI testing)

- Live scrape + email:
  sudo podman exec -it grade-checker-strict python pydanticai_gradechecker.py --email

- Local file + email (for flakiness isolation):
  sudo podman exec -it grade-checker-strict python pydanticai_gradechecker.py --local --email

---

HTTP API

- GET /

  - Basic service info.

- GET /health

  - Returns 200 OK with a JSON payload indicating health status.

- POST /run-grade-check

  - Triggers live scraping, LLM analysis, and email.
  - Strict mode: fails if 0 assignments extracted (no fallback).

  - Security:
    - Optional authentication with SERVICE_AUTH_TOKEN and REQUIRE_AUTH=true.
    - Rate limited via MIN_RUN_INTERVAL_SEC.
    - Concurrency: rejects overlapping runs with 409 conflict.
  - Responses:
    - With SAFE_HTTP_RESPONSE=true, suppresses potentially sensitive stdout/stderr in the JSON body.

- POST /run-grade-check-dev (development convenience)
  - Purpose: trigger the workflow during local development without setting up auth.
  - Behavior:
    - When ENVIRONMENT=production AND REQUIRE_AUTH=true, this endpoint is disabled (403).
    - When REQUIRE_AUTH=false or ENVIRONMENT!=production, this endpoint runs:
      - With live scraping by default.
      - With local file if you pass ?local=1 (no live scraping).
  - Examples:
    - curl -i -X POST "http://localhost:8080/run-grade-check-dev?local=1"
    - curl -i -X POST "http://localhost:8080/run-grade-check-dev"

See [basic_server.py](basic_server.py) for implementation details.

---

CLI Usage

From inside the container (or on your host if dependencies are installed):

- Run once (scrape → analyze):
  python pydanticai_gradechecker.py

- Use local file (skip scraping):
  python pydanticai_gradechecker.py --local

- Send email with analysis:
  python pydanticai_gradechecker.py --email

- Schedule daily at 3:00 PM:
  python pydanticai_gradechecker.py --schedule

Notes:

- The CLI writes assignment data to ASSIGNMENTS_PATH (default /tmp/assignments.txt) and sets file permissions to 600.
- When invoked through the HTTP endpoint, there is no fallback to local file and failures are surfaced.

---

Security Best Practices Applied

- Authentication on POST trigger (token-based, configurable) in [basic_server.py](basic_server.py)
- Rate limiting and single-flight concurrency guard to prevent abuse and overlap
- Strict CSP and other security headers; reduced Server fingerprint and suppressed default request logs
- SAFE_HTTP_RESPONSE=true prevents leaking stdout/stderr over HTTP
- SAFE_LOGS=true avoids printing full HTML analysis (PII)
- Secrets never baked into the image (see [Dockerfile](Dockerfile)); [.dockerignore](.dockerignore) excludes .env
- Subprocess environment uses least privilege: only whitelisted env vars passed through
- Non-root user in container
- Sensitive artifacts stored in /tmp; assignment file chmod to 600

---

LLM and Email

- LLM model: gemini-2.5-flash (temperature 0)
- Output normalized to a plain HTML string before email
- Email via Gmail SMTP SSL 465 with app passwords; supports multiple recipients

---

Troubleshooting

- 0 assignments extracted

  - Strict mode treats this as failure. Check login flow, iframe switching, and selectors. Retry or validate with the local file option to isolate scraping from email/LLM.

- Chrome/Chromedriver crashes

  - Set DISABLE_DEV_SHM_USAGE=true in the container environment.
  - Run with larger shared memory and tmpfs for /tmp:
    --shm-size=1g and --tmpfs /tmp:rw,size=1g
  - Ensure no conflicting Chrome processes; container restarts clean these up.
  - Enable DEBUG*SNAPSHOTS=true to capture /tmp/hac*\_.png and /tmp/hac\_\_.html for inspection.

- Logfire configuration

  - Use LOGFIRE_TOKEN and optionally LOGFIRE_BASE_URL. Service metadata can be set via LOGFIRE_SERVICE_NAME, LOGFIRE_SERVICE_VERSION, ENVIRONMENT.

- SMTP issues
  - Use an app password for Gmail. Verify sender is allowed and recipients are correct.

---

Deploy on Google Cloud (Cloud Run + Artifact Registry + Cloud Scheduler)

This project ships with Terraform to deploy a public Cloud Run service that receives scheduled triggers via Cloud Scheduler. The container image is stored in Artifact Registry. See [infra/main.tf](infra/main.tf:1) and the variables template [infra/terraform.tfvars](infra/terraform.tfvars:1). Optional CI is provided via [cloudbuild.yaml](cloudbuild.yaml:1), and a local push script via [build-and-push.sh](build-and-push.sh:1).

Prerequisites

- gcloud CLI (authenticated and configured):
  - gcloud auth login
  - gcloud auth application-default login
  - gcloud config set project YOUR_PROJECT_ID
  - gcloud config set run/region us-central1
- Terraform >= 1.5.x
- Billing enabled on the GCP project

1. Configure Terraform variables

- Edit [infra/terraform.tfvars](infra/terraform.tfvars:1) and set:
  - HAC credentials: hac_url, hac_username, hac_password
  - Gmail: gmail_sender, gmail_app_password, gmail_receivers
  - App security: service_auth_token (strong value)
  - LLM: gemini_api_key OR google_api_key (at least one)
  - Optional: project_id, region, environment, require_auth, logfire settings, disable_dev_shm_usage

2. Enable APIs and create Artifact Registry
   From the repo root:

```bash
cd infra
terraform init

# Create prerequisite services and the Artifact Registry repository first
terraform apply \
  -target=google_project_service.run \
  -target=google_project_service.artifactregistry \
  -target=google_project_service.scheduler \
  -target=google_artifact_registry_repository.repo
```

3. Build and push the container image to Artifact Registry
   Option A: Podman (recommended for local)

```bash
# From repo root
bash build-and-push.sh
```

Option B: Cloud Build

- Adjust [cloudbuild.yaml](cloudbuild.yaml:1) if you change project/region/repo.

```bash
gcloud builds submit --region=us-central1 --config cloudbuild.yaml .
```

4. Deploy Cloud Run + Scheduler with Terraform
   After the image is available in Artifact Registry:

```bash
cd infra
terraform apply
```

Terraform outputs

- service_url: the Cloud Run base URL
- artifact_registry_repo: registry path for images
- region and project_id helpers

Verification

- Health:

```bash
curl -i "$(terraform output -raw service_url)/health"
```

- Manual trigger (token required):

```bash
TOKEN="the-same-token-you-set-in-terraform.tfvars"
curl -i -X POST -H "X-Auth-Token: ${TOKEN}" "$(terraform output -raw service_url)/run-grade-check"
```

- Logs (stdout/stderr from revisions):

```bash
gcloud logs tail --project "$(terraform output -raw project_id 2>/dev/null || gcloud config get-value project)" --log-name=run.googleapis.com%2Fstdout
```

How the schedule works

- [infra/main.tf](infra/main.tf:88) creates google_cloud_scheduler_job with a daily schedule (default 3:00 PM America/Chicago).
- The Scheduler POSTs to ${service_url}/run-grade-check and includes the X-Auth-Token header set from service_auth_token.
- Adjust cron and time_zone in [infra/main.tf](infra/main.tf:88) to change schedule.

Security and runtime notes

- Keep REQUIRE_AUTH=true and set a strong SERVICE_AUTH_TOKEN for any non-dev environment.
- The Cloud Run service is configured for public invocation for simplicity; application-layer auth still requires the token. For stricter security, remove the allUsers IAM member and use Cloud Scheduler OIDC to invoke Cloud Run instead.
- Keep SAFE_HTTP_RESPONSE=true and SAFE_LOGS=true to prevent sensitive data exposure.
- Inject secrets via Terraform/vars or a secret manager; do not bake secrets into images.
- Prefer read-only filesystem with tmpfs for /tmp in production.
- Chrome stability flags (e.g., DISABLE_DEV_SHM_USAGE) are available via Terraform variables in [infra/main.tf](infra/main.tf:132).

Cloud Run support

- Cloud Run or similar platforms are supported by the current container image.

---

OpenTofu (Terraform-compatible) GCP Deployment

If you use OpenTofu instead of Terraform, the HCL in [infra/main.tf](infra/main.tf:1) and variables in [infra/terraform.tfvars](infra/terraform.tfvars:1) work unchanged. Replace terraform commands with tofu as shown below.

Prerequisites

- gcloud CLI authenticated and configured:
  - gcloud auth login
  - gcloud auth application-default login
  - gcloud config set project YOUR_PROJECT_ID
  - gcloud config set run/region us-central1
- OpenTofu installed (tofu >= 1.5.x)
- Billing enabled on your GCP project

1. Configure variables

- Edit [infra/terraform.tfvars](infra/terraform.tfvars:1) and set:
  - HAC: hac_url, hac_username, hac_password
  - Gmail: gmail_sender, gmail_app_password, gmail_receivers
  - App security: service_auth_token (strong value)
  - LLM: gemini_api_key OR google_api_key (at least one)
  - Optional overrides: project_id, region, environment, require_auth, logfire settings, disable_dev_shm_usage

2. Enable APIs and create Artifact Registry (first pass)
   From repo root:

```bash
cd infra
tofu init

# Create prerequisite services and the Artifact Registry repository first
tofu apply \
  -target=google_project_service.run \
  -target=google_project_service.artifactregistry \
  -target=google_project_service.scheduler \
  -target=google_artifact_registry_repository.repo
```

3. Build and push the image to Artifact Registry
   Option A: Podman (local)

```bash
# From repo root
bash build-and-push.sh
```

Option B: Cloud Build

- Adjust [cloudbuild.yaml](cloudbuild.yaml:1) if you change project/region/repo.

```bash
gcloud builds submit --region=us-central1 --config cloudbuild.yaml .
```

4. Deploy Cloud Run + Scheduler (second pass)
   After the image is available in Artifact Registry:

```bash
cd infra
tofu apply
```

Outputs

- Cloud Run URL:
  ```bash
  tofu output -raw service_url
  ```
- Helper outputs:
  ```bash
  tofu output -raw project_id
  tofu output -raw region
  ```

Verification

- Health:
  ```bash
  curl -i "$(tofu output -raw service_url)/health"
  ```
- Manual trigger (token required):
  ```bash
  TOKEN="the-same-token-you-set-in-terraform.tfvars"
  curl -i -X POST -H "X-Auth-Token: ${TOKEN}" "$(tofu output -raw service_url)/run-grade-check"
  ```

How the schedule works

- The daily job is provisioned by [infra/main.tf](infra/main.tf:88) using google_cloud_scheduler_job (defaults to 3:00 PM America/Chicago).
- Scheduler POSTs to ${service_url}/run-grade-check and includes X-Auth-Token from service_auth_token.

Notes

- State: OpenTofu uses the same state model; by default a local state file (terraform.tfstate) is created under infra/. Configure a remote backend (e.g., GCS) if desired.
- Security: Consider removing the allUsers invoker IAM and using Cloud Scheduler OIDC for strict invocation. The app still enforces SERVICE_AUTH_TOKEN at the HTTP layer.
- Stability: Chrome flags such as DISABLE_DEV_SHM_USAGE are available as variables in [infra/main.tf](infra/main.tf:132).

---

GCP Architecture Diagram

The following diagram illustrates the GCP deployment architecture for this project, including Artifact Registry, Cloud Run, and Cloud Scheduler triggering the service on a schedule. It also shows the runtime subprocess that performs scraping, LLM analysis, and email.

```mermaid
flowchart LR
  subgraph Developer_CI
    Podman["Podman build-and-push.sh"]
    CloudBuild["Cloud Build (optional)"]
  end

  subgraph Artifact_Registry
    AR["gradechecker-repo"]
  end

  Podman --> AR
  CloudBuild --> AR

  subgraph Cloud_Run_Service
    server["basic_server.py / HTTP"]
    worker["pydanticai_gradechecker.py / scraper + LLM + email"]
  end

  subgraph Cloud_Scheduler
    sched["Daily Trigger (3:00 PM America/Chicago)"]
  end

  sched -->| "POST /run-grade-check\nX-Auth-Token: SERVICE_AUTH_TOKEN" | server
  server -->| "subprocess" | worker

  worker -->| "Headless Chrome" | HAC["Home Access Center"]
  worker -->| "Gemini API" | Gemini["Gemini"]
  worker -->| "SMTP 465" | Gmail["Gmail"]
  worker -. optional .-> Logfire["Logfire"]

  classDef opt fill:#eee,stroke:#999,stroke-dasharray: 3 3;
  class Logfire opt;
```

Notes

- Image Source: Container images are built locally with Podman via [build-and-push.sh](build-and-push.sh:1) or by Cloud Build using [cloudbuild.yaml](cloudbuild.yaml:1), then pushed to Artifact Registry.
- Runtime: Cloud Run runs [basic_server.py](basic_server.py:1), which exposes HTTP endpoints and launches [pydanticai_gradechecker.py](pydanticai_gradechecker.py:1) as a subprocess for scraping, analysis, and email.
- Scheduling: Cloud Scheduler posts to the Cloud Run URL at the configured cron time. The request includes the X-Auth-Token header that must match SERVICE_AUTH_TOKEN configured in the service environment; see [infra/main.tf](infra/main.tf:88).
- Configuration: Environment variables are set by the service spec in [infra/main.tf](infra/main.tf:42) and documented in this README.
- Security: Keep REQUIRE_AUTH=true and set a strong SERVICE_AUTH_TOKEN in production; consider replacing public invoker IAM with Cloud Scheduler OIDC if stricter security is required.
