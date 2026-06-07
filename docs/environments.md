# Environment Plan

Status: Provider selection pending
Updated: 2026-05-31

| Capability | Local | Staging | Production | Owner action |
| --- | --- | --- | --- | --- |
| PostgreSQL | Docker Compose PostgreSQL 16 | Select managed PostgreSQL | Select managed PostgreSQL | Record provider, region, backup policy, and credentials owner. |
| Redis | Docker Compose Redis 7 | Select managed Redis or host Redis | Select managed Redis or host Redis | Record provider and eviction policy. |
| Private media | Local Docker volume | Select private S3 bucket | Select private S3 bucket | Record bucket, region, lifecycle policy, and IAM owner. |
| SMTP | Console backend | Select transactional SMTP | Select transactional SMTP | Record provider, sender domain, and DNS verification state. |
| AI | Disabled until Anthropic credentials are provisioned | Anthropic API | Anthropic API | Record workspace owner and secret rotation policy. |

Secrets must live outside Git. Local development uses `.env`; staging and
production must inject environment variables through the deployment system.
Production startup fails fast when `DJANGO_SECRET_KEY` or
`DJANGO_ALLOWED_HOSTS` is missing. S3-backed private storage also requires an
explicit bucket name.
