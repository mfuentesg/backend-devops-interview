# Backend/DevOps Engineer Interview

A small content service: users, posts, comments, tags. Django + Ninja + Postgres.

## Running it locally

Prereqs:

- [mise](https://mise.jdx.dev/) — manages the Python toolchain and uv.
- [Docker](https://docs.docker.com/get-docker/) with Compose — runs Postgres and pgAdmin.

Steps:

```sh
mise install
uv sync
cp .env.example .env                     # database config; defaults match docker-compose
docker compose up -d                     # Postgres on :5432, pgAdmin on :8080
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver
```

API docs at <http://localhost:8000/api/docs>. pgAdmin at <http://localhost:8080>
(`admin@example.com` / `postgres`), already connected to the local database.

### Configuration

`core/settings.py` reads its config from environment variables via `django-environ`,
loading a local `.env` file if one is present. Defaults match the `docker-compose.yml`
setup, so `.env` is optional for local work.

`.env` is git-ignored and never committed — it's your machine's copy. `.env.example` is
the tracked template; copy it (`cp .env.example .env`) and edit as needed.

| Variable            | Default                    |
| ------------------- | -------------------------- |
| `SECRET_KEY`        | an insecure dev key        |
| `LANGUAGE_CODE`     | `en-us`                    |
| `TIME_ZONE`         | `America/Santiago`         |
| `POSTGRES_DB`       | `backend_devops_interview` |
| `POSTGRES_USER`     | `postgres`                 |
| `POSTGRES_PASSWORD` | `postgres`                 |
| `POSTGRES_HOST`     | `localhost`                |
| `POSTGRES_PORT`     | `5432`                     |

Any real deployment must set its own `SECRET_KEY` (generate one with
`uv run python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`).

Seeding writes ~100k posts and ~500k comments. Expect a few minutes.

## What the API does

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET    | `/api/posts` | Published posts, newest first |
| GET    | `/api/posts/search?q=` | Full-text-ish search across title and body |
| GET    | `/api/posts/by-tag/{slug}` | Posts carrying a given tag |
| GET    | `/api/posts/{id}` | Post detail with comments |
| POST   | `/api/posts` | Create a post |
| POST   | `/api/posts/{id}/comments` | Add a comment to a post |
| GET    | `/api/users/{id}` | User profile with post and comment counts |
| GET    | `/api/users/find?email=` | Look up a user by email |

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
