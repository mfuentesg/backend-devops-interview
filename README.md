# Backend/DevOps Engineer Interview

A small content service: users, posts, comments, tags. Django + Ninja + Postgres.

## Running it locally

Prereqs:

- [mise](https://mise.jdx.dev/) — manages the Python toolchain, uv and ruff.
- [Docker](https://docs.docker.com/get-docker/) with Compose — runs Postgres, pgAdmin
  and the monitoring stack (Prometheus, Grafana, postgres-exporter, Loki, Alloy).

Steps:

```sh
mise install
uv sync
cp .env.example .env                     # config; defaults match docker-compose
docker compose up -d                     # the observability + DB stack — see below
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver        # the app runs on the host, not in Compose
```

API docs at <http://localhost:8000/api/docs>.

### The Compose stack

`docker compose up -d` brings up seven containers; the Django app itself stays on
the host (`runserver`, `:8000`), on purpose (editor imports, faster disk).

| Service      | Port    | What it does |
| ------------ | ------- | ------------ |
| `postgres`   | `5432`  | App database (`POSTGRES_PORT` maps the host port). |
| `pgadmin`    | `8080`  | DB admin UI at <http://localhost:8080>, pre-connected to `postgres` (`admin@example.com` / `postgres`). |
| `prometheus` | `9090`  | Scrapes `pgexporter`, the app's `/metrics`, Loki and Alloy. |
| `grafana`    | `3000`  | Dashboards at <http://localhost:3000> — **PostgreSQL**, **Django**, **Logs**. Anonymous view; edit as `admin` / `admin`. |
| `pgexporter` | `9187`  | Postgres metrics for Prometheus. |
| `loki`       | `3100`  | Log store (bound to `127.0.0.1`). |
| `alloy`      | `12345` | Tails `logs/app.log` → Loki (bound to `127.0.0.1`). |

Prometheus and the **Django** dashboard only report once `runserver` is up.

**Logging.** The Django app writes structured JSON to `logs/app.log` when
`LOG_JSON_FILE=True` (the `.env.example` default). Grafana Alloy tails that file and
ships it to Loki; the provisioned **Logs** dashboard and Explore query it. `runserver`
must be up for lines to appear — Alloy polls for the file every 10s and attaches when
it shows up, so the order you start things in doesn't matter. `LOG_LEVEL` defaults to
`INFO`; set `DEBUG` for verbose app logs — `django.db.backends`,
`django.utils.autoreload` and `django.template` stay at `INFO` either way.

Lint and tests:

```sh
ruff check .
uv run pytest
```

### Configuration

`core/settings.py` reads its config from environment variables via `django-environ`,
loading a local `.env` file if one is present. Defaults match the `docker-compose.yml`
setup, so `.env` is optional for local work.

`.env` is git-ignored and never committed — it's your machine's copy. `.env.example` is
the tracked template; copy it (`cp .env.example .env`) and edit as needed.

| Variable            | Default                               |
| ------------------- | ------------------------------------- |
| `SECRET_KEY`        | an insecure dev key                   |
| `DEBUG`             | `True`                                |
| `ALLOWED_HOSTS`     | `*` (dev; narrow for prod)            |
| `LANGUAGE_CODE`     | `en-us`                               |
| `TIME_ZONE`         | `America/Santiago`                    |
| `POSTGRES_DB`       | `backend_devops_interview`            |
| `POSTGRES_USER`     | `postgres`                            |
| `POSTGRES_PASSWORD` | `postgres`                            |
| `POSTGRES_HOST`     | `localhost`                           |
| `POSTGRES_PORT`     | `5432`                                |
| `LOG_LEVEL`         | `INFO`                                |
| `LOG_DIR`           | `<repo>/logs`                         |
| `LOG_JSON_FILE`     | `False` (`.env.example` ships `True`) |

`ALLOWED_HOSTS` ships `*` so the Prometheus container can scrape the host-run app
via `host.docker.internal`; set explicit hostnames for any real deployment.

`docker-compose.yml` also reads `.env`: `POSTGRES_DB` / `POSTGRES_USER` /
`POSTGRES_PASSWORD` seed the Postgres container plus pgAdmin's pre-registered
connection (`servers.json` + `pgpass`), `POSTGRES_PORT` maps the published host
port, and `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_DEFAULT_PASSWORD` (defaults
`admin@example.com` / `postgres`) are the pgAdmin login. pgAdmin reaches Postgres
over the Compose network as `postgres:5432` regardless of the host settings.
`postgres-exporter` uses the same `POSTGRES_*` credentials; Grafana's login is
`GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` (defaults `admin` / `admin`) and it
publishes on `GRAFANA_PORT` (default `3000`).

Any real deployment must set its own `SECRET_KEY` (generate one with
`uv run python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`).

Seeding writes ~100k posts and ~500k comments. Expect a few minutes.

## What the API does

Every `/api/` response is one envelope: `{ "data": …, "meta": … | null, "status_code": …, "errors": [ { "field", "message" } ] }` —
including unknown paths and wrong-method requests (a middleware wraps those 404/405s). Only an unhandled 500 still
falls through to Django's HTML page. `meta` carries `page`, `limit`, `total`, `total_pages` on list endpoints.

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET    | `/api/posts` | List posts. Query params: `published` (`true`/`false`/omit=all), `sort` (`asc`/`desc` on `created_at`), `query` (matches title or body), `slug` (posts carrying that tag slug), `page` (≥1), `limit` (1–100, default 20). |
| GET    | `/api/posts/{id}` | Post detail. `expand=comments` to include comments (omitted → `[]`). |
| POST   | `/api/posts` | Create a post. Title/body are HTML-sanitised; unknown `author_id` or `tag_slugs` → 400. Returns 201 with the post in detail shape. |
| POST   | `/api/posts/{id}/comments` | Add a comment. Returns 201 with the comment. |
| GET    | `/api/users/{id}` | User profile with post and comment counts. |

Ready-to-run requests for every scenario live in `requests/*.http` (JetBrains HTTP
Client or the VS Code REST Client extension) — see `requests/README.md`.

## The assignment

We want to see how you take a working prototype and turn it into something a team can develop on and operate. Pick the changes that give the strongest signal about how you'd improve this codebase if you owned it. There are three areas we care about:

1. **Developer experience.** Getting this running on a fresh laptop is harder than it should be. Make it easier.
2. **Performance.** Once the database is seeded, exercise the endpoints. Some of them are slow. Find out why and fix what you can.
3. **Production readiness.** This service is a long way from something you'd put behind a load balancer. Move it closer — pick whichever deployment target you'd reach for at work (Helm chart, ECS task def, K8s manifests, Fly, Render, plain Docker + systemd — your call).

**Depth beats breadth.** Pick 2–3 things and go deep rather than touching ten things shallowly. Write a short `NOTES.md` covering:

- What you did and why.
- What you deliberately *didn't* do.
- What you'd do next if you had another day.

## Non-goals

- **Authentication / authorization** is intentionally absent. If you want to suggest a direction in `NOTES.md`, great — but no need to implement anything.
- **Test coverage** is not what we're grading. The smoke tests are there so you have something to wire into CI.
- **Reshaping the domain model** isn't expected. Adjust it if a perf fix needs it; otherwise leave it.

## Time

Soft cap of 2–6 hours, depending on your experience and what tooling you have available (AI agents are fine — say so in `NOTES.md` and include chat transcripts). We're looking at signal, not hours.

## Deliverable

Whatever's easy for you to share: a GitHub link, a [gitfront](https://gitfront.io) link, a git bundle, even `git format-patch`. Please don't open a PR against this repo.
