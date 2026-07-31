# Cloud Run Private Demo Deployment

The deployable demonstration target is a private Cloud Run service protected by
IAP. ADK Web is a development interface, so this configuration is intended for
judging and controlled review rather than a customer-facing production UI.
Deployment is intentionally manual through the `production` GitHub environment
so a reviewer must authorize it after tests and ADK evaluations pass.

## Runtime Architecture

- `fast_api_app.py` serves ADK Web through FastAPI.
- `OTEL_TO_CLOUD=true` exports ADK traces to Cloud Trace.
- `DRAFT_DATABASE_URL` stores mutable drafts and approval audit fields in
  Postgres.
- `SESSION_DATABASE_URL` gives ADK persistent Cloud SQL sessions.
- the SQLite file contains deterministic synthetic reference data only;
  `scripts/ensure_data.py` creates it once when absent.
- IAP authenticates access to the Cloud Run UI.
- approval still uses a separate identity-bound credential from
  `APPROVER_CREDENTIALS_JSON`;
  IAP login alone does not grant approval.

## Required Secret Manager Secrets

Create these secret IDs without placing their values in GitHub:

| Secret ID | Runtime environment variable |
|---|---|
| `google-api-key` | `GOOGLE_API_KEY` |
| `draft-database-url` | `DRAFT_DATABASE_URL` |
| `session-database-url` | `SESSION_DATABASE_URL` |
| `approver-credentials-json` | `APPROVER_CREDENTIALS_JSON` |

Grant the runtime service account `roles/secretmanager.secretAccessor` and
database connectivity. Keep prompt/response content capture disabled; Cloud
Trace metadata and structured MCP events are sufficient for this demo.

## GitHub Configuration

Repository secrets:

- `WIF_PROVIDER`
- `DEPLOY_SERVICE_ACCOUNT`
- `RUNTIME_SERVICE_ACCOUNT`
- `GOOGLE_API_KEY` for the pre-deployment evaluation job

Repository variables:

- `GCP_PROJECT_ID`
- `GCP_REGION`
- `ARTIFACT_REPOSITORY`
Protect the GitHub `production` environment with required reviewers. The
workflow in `.github/workflows/deploy-cloud-run.yml` then performs:

1. deterministic seed and pytest;
2. full ADK evaluation generation and grading;
3. image build and Artifact Registry push;
4. private Cloud Run deployment with IAP and Secret Manager bindings.

No deployment has been executed by adding this configuration.
