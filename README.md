# Pulsea

Pulsea is an internal agency platform for composing, scheduling, publishing, and
reviewing social content across client accounts.

## Local Setup

1. Copy `.env.example` to `.env` and replace placeholder values.
2. Start the local stack:

   ```powershell
   docker compose up --build
   ```

3. Run checks:

   ```powershell
   python -m pytest
   python -m ruff check .
   ```

The Compose stack starts Django, PostgreSQL, Redis, a Celery worker, and Celery
beat. Private local media is stored in the `private_media` Docker volume.

## Settings

- `config.settings.local` uses PostgreSQL and console email.
- `config.settings.test` uses SQLite and in-memory email for fast tests.
- `config.settings.production` requires production secrets and host settings.

See [docs/environments.md](docs/environments.md) and
[docs/integrations/platform-matrix.md](docs/integrations/platform-matrix.md)
before connecting any real platform accounts.

