# GitHub deploy secrets / environment

Configure once before automated production deploys.

## Environment

1. GitHub → Settings → Environments → create `production`
2. Required reviewers: owner
3. Deployment branches: `main` only

## Secrets (`production` environment or repository)

| Secret | Purpose |
|---|---|
| `DEPLOY_HOST` | VPS hostname/IP |
| `DEPLOY_USER` | SSH user |
| `DEPLOY_SSH_KEY` | Private key |
| `DEPLOY_PORT` | Optional, default 22 |

## Variables

| Variable | Purpose |
|---|---|
| `DEPLOY_PATH` | Optional, default `/opt/LeadHunter` |

## Prod `.env` must include

- `ADMIN_SECRET` (required, stable)
- `LLM_ENABLED=true`, `LLM_MODE=blocking`
- `SENTRY_DSN`
- Optional offsite: `S3_BUCKET`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`

> Admin bind lockdown (`127.0.0.1`) отложен — сейчас публичный `ADMIN_PUBLIC_PORT`
> по решению владельца до домена+TLS.
