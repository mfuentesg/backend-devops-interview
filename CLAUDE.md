# Project rules

- Small commits, fully informative. Conventional Commits (`type(scope): summary`).
- No `Co-Authored-By: Claude` trailer.
- Focus on performance and developer experience.
- Keep @NOTES.md updated: first-person logbook, terse, found / fixed / kept out / next.

## Tooling

- `mise` for standalone tools (python, uv, ruff). Run `ruff check .` directly.
- `uv` dev group only for venv tools (pytest). A linter never goes in `uv add`.

## Config

- All settings from the environment via `django-environ`, defaults in the `Env(...)` schema.
- Keep `.env.example` in sync. Never commit real secrets; dev defaults stay obviously fake.

## Local dev

- Compose runs Postgres, pgAdmin, and the observability stack (Prometheus, Grafana,
  exporters, Loki, Alloy); the app and its deps still run on the host, on purpose.
- `Dockerfile` builds the production image; `compose.prod.yml` is an opt-in overlay
  that runs it (`web` + `migrate` + `seed`) — plain `docker compose up -d` never
  reads it.
