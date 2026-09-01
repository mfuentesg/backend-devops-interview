# Fintual Interview - Logbook

I'll use this document to cover two things:

1. Use it as context for the agent I'm working with (Claude).
2. Keep track of everything I found, changed, or still consider worth doing.

## Aspects that matter to me here

* Developer experience: giving a proper environment to other developers, making their work easier.
* Documentation: writing down as much as I can, so there are no black boxes for a future session.
* Automation: handy commands for the complex setups, including pipeline checks like linting and testing.
* Agents: preparing the repo so any agent harness has enough context to work with.
* Leave it in better condition than I found it.

## What I found

* Getting this running on a fresh laptop is harder than it should be: install PostgreSQL 16
  by hand, create the database yourself, bring `mise` and `uv`. Nothing is containerized.
* `seed.py` is slow, around 15-25 minutes. I gave the existing code a try, but after two
  minutes I preferred to fix it, nobody has the patience to wait that long just to get
  data in the db. Three things were hurting:
  1. `fake.sentence()` is called once per row, and there are 500k comments.
  2. `random.choices(weights=...)` rebuilds a 100k-element weight list on every call, ~600k times.
  3. The comments loop runs outside a transaction, so it's 500 separate autocommits.
* `seed.py` `handle()` is one long function, everything inline. Only a readability thing.
* `core/settings.py` had everything hardcoded: the DB connection, and a real `SECRET_KEY`
  committed to the repo. No way to change either per environment without editing the file.

## What I fixed and why

* Added `docker-compose.yml` for the database: `postgres:18.6-alpine` with a persistent
  volume and the db created on boot, plus `pgadmin` on `:8080` already wired through Docker
  `configs`. One command replaces the "install Postgres yourself" step.
* `core/settings.py` reads its config from env vars via `django-environ`: `SECRET_KEY`,
  `LANGUAGE_CODE`, `TIME_ZONE`, and the DB connection (`POSTGRES_DB`, `POSTGRES_USER`,
  `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`). Old values stay as defaults, so
  nothing breaks without a `.env`. Added `.env.example`; a local `.env` is read if present,
  real env vars still win. README updated with the table and the `docker compose` quickstart.
* Rotated `SECRET_KEY`. The old one was committed, so it's burned. The default now is a
  fresh insecure dev key, clearly marked, and any real deployment sets its own.
* `DEBUG` and `ALLOWED_HOSTS` now come from env. Defaults are `DEBUG=True` and
  `ALLOWED_HOSTS=[]`; with `DEBUG=True` Django already covers `.localhost`, `127.0.0.1`
  and `[::1]`, so local work needs nothing. Dropped the old `ALLOWED_HOSTS = ["*"]`.
  `.env.example` and the README table updated. The `DEBUG=False` security block still
  rides with the deploy work.
* `ruff` moved to `mise.toml`, pinned, instead of a `uv` dev dependency. It's a standalone
  binary and doesn't need the venv, and pinning means every machine and CI lint the same.
  Also excluded generated migrations from lint, so `ruff check .` is clean.
* `seed.py`: comment bodies come from a 10k pool instead of calling Faker per row, like
  posts already do for title and body. Those Faker calls were most of the loop.
* `seed.py`: precompute the cumulative weights once and draw a full batch per call (`k=n`),
  instead of `random.choices` rebuilding them every time. Removes ~600k O(n) passes.
* `seed.py`: wrapped the comments loop in a single `transaction.atomic()`, like the posts
  loop already is. 500 autocommits become 1.
* Seed goes from ~15-25 min to ~2 min. RNG stream changes, so rows differ but stay
  deterministic under `seed(42)`.
* Added `.github/workflows/ci.yml`: one `lint-test` job on push to `main` and on PRs,
  running `ruff check` and `pytest`. `jdx/mise-action` installs python, uv and ruff from
  `mise.toml`, so CI and local run the exact same pinned tools; uv venv is cached on
  `uv.lock`. A `build-and-push` job (GHCR image) is scaffolded but commented out until
  there's a `Dockerfile`.
* `blog/api.py` split into a `blog/api/` package: `posts`, `comments`, `users`, plus
  `responses.py` (envelope builder) and `helpers.py` (exception handlers, pagination,
  shared serializers). One file per entity, thin views, no service layer yet.
* Every routed API endpoint returns `{data, meta, status_code, errors}`. Ninja `ValidationError`
  and a small `ApiError` are reshaped into that envelope (400 / 404); `/api/docs` shows
  the wrapped shape via a generic `Envelope[T]` response schema.
* `GET /posts` takes `published`, `sort`, `query`, `slug`, `page`, `limit` (max 100),
  all validated. `select_related`/`prefetch_related` kill the author+tags N+1. Deleted
  `/posts/search` and `/posts/by-tag/{slug}` — folded into the filters.
* `GET /posts/{id}` gained `expand=comments`; comments are skipped unless asked for.
  `view_count` bump uses `update_fields=["view_count"]`.
* `POST /posts` sanitises title/body with `nh3`, validates author + tag slugs up front,
  returns 400 listing every bad value, 201 with the created post otherwise.
* Deleted `GET /users/find` — unauthenticated lookup by arbitrary email is an
  enumeration / DoS surface with no real use here.
* Added `requests/*.http` — runnable request files (JetBrains HTTP Client / VS Code
  REST Client) with every success and error scenario, so the API is explorable from
  the editor without curl.

## Self taste

* Docker Compose for local development, but only for Postgres and pgAdmin. One command, no
  cluster to manage. I considered skaffold + kind for native k8s manifests with autoreload,
  but I don't think it's needed at this moment. Maybe for a future iteration.
* `mise`, `uv` and the app run on the host, not in a container. Editor autocomplete and
  imports need the deps local, and the host disk beats a container bind mount (more on
  macOS). The app still needs an image for production, that's a separate concern.
* ruff for linting.
* Github Actions for CI, running lint and the smoke tests, tools installed via `mise`.
* Claude as the AI harness.

## Things I'll keep out

* Helm charts. Not too complex, but I don't think it's required right now, maybe later.
* Tracing tools. I consider this is too much for this project.
* `COPY`-based bulk load and splitting `handle()` in the seeder. Real rewrites for the last
  minute or so of seed time.
* A selector/service layer and a hexagonal layout — the package split is enough for now.

## What I'd do next

* Adopt `ruff format` repo-wide, 5 files currently diverge, then add a
  `ruff format --check` gate to CI. Left the format pass out for now to keep this
  diff focused.
* The `DEBUG=False` security block (SSL redirect, secure cookies, HSTS,
  `CSRF_TRUSTED_ORIGINS`) with the deploy work.
* A production server (gunicorn or uvicorn) and a multi-stage `Dockerfile`, then k8s
  manifests or an ECS task definition.
* Observability: Prometheus metrics endpoint, Grafana dashboards, Loki for the logs.
* Load testing for performance validation
* Race-safe view_count via F("view_count") + 1. Comma-separated expand values. Full-text
  index for the query filter.
* JSON 404/405/500 for the whole `/api/` prefix (resolver-level errors and unhandled
  exceptions still fall through to Django's HTML pages).
* Unknown query params on `GET /posts` are silently ignored — django-ninja filters params
  before schema validation, so `extra="forbid"` on the filter schema does nothing (verified).
  A stale `?q=` from the old `/posts/search` returns 200 + everything. Needs an explicit
  allow-list check against `request.GET`.
* `blog/api/helpers.py` is a grab-bag (serializers + `ApiError` + `paginate` + handler
  registration) — split `ApiError` into `errors.py`, move serializers to `serializers.py`.
* Error-item construction is duplicated (`responses._norm` vs the inline pydantic-`loc`
  mapping in `helpers`) — fold into one `_from_pydantic` helper and harden the
  `e["msg"]` / `e["message"]` bracket access to `.get()`.
* `GET /users/{id}` issues two `COUNT` queries — fold into
  `annotate(Count("posts"), Count("comments"))`.
* Deep `OFFSET` pagination scans discarded rows — move to keyset pagination on
  `(created_at, id)` at scale.
* Index `(-created_at, id)`, `is_published`, and the `query` `icontains` targets —
  currently sequential scans, run twice per request (count + page).
* Sanitisation is write-path only — the Django admin and the seeder bypass `nh3`.
* `paginate()` has no `page<1` / `limit<=0` guard (endpoint `Query(ge=1, le=100)` shields
  it today).
* Test fixtures `client` / `user` are redefined across all four test files — move to
  `blog/tests/conftest.py`.
