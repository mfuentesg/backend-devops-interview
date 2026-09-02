# Alloy + Loki Logging Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the host-run Django app structured JSON logging and ship those logs through Grafana Alloy into Loki, surfaced in the existing Grafana.

**Architecture:** Django writes JSON lines to `logs/app.log` (rotating) only when `LOG_JSON_FILE` is set. That directory is bind-mounted read-only into a new Alloy container, which tails the file, parses each line, promotes `level`/`logger` to labels, and pushes to a new single-binary Loki. Grafana gets a provisioned Loki datasource and a hand-built Logs dashboard. Prometheus scrapes Loki and Alloy `/metrics`.

**Tech Stack:** Django 5.2 `LOGGING` + stdlib `logging`/`json`, `grafana/loki:3.7.7` (single-binary, filesystem store), `grafana/alloy:v1.19.2`, Docker Compose, Grafana provisioning, Prometheus.

**Spec:** `docs/superpowers/specs/2026-09-01-loki-alloy-logging-design.md`

## Global Constraints

- Conventional Commits (`type(scope): summary`). No `Co-Authored-By: Claude` trailer.
- All settings come from the environment via `django-environ`; static defaults live in the `Env(...)` schema. `LOG_LEVEL` is the one exception — its default is derived from `DEBUG`, so its schema entry is `(str, "")` with the derived fallback applied in code.
- Keep `.env.example` in sync with any new env var. Dev defaults stay obviously fake. Never commit a real `.env` (it is git-ignored).
- Compose runs infra only; the Django app and its deps run on the host. Do not containerize the app.
- All container images pinned to an exact tag. No `latest`.
- `ruff check .` must stay clean (`select = ["E", "F", "I", "UP", "B"]`, line-length 100, target py314). Migrations are excluded; nothing else is.
- Tests run with `uv run pytest`; test files are `blog/tests/test_*.py` (pytest-django, `DJANGO_SETTINGS_MODULE = core.settings`).
- `NOTES.md` is a first-person logbook. Describe added capability as design, not as a fix narrative. Convert relative dates to absolute.
- Monitoring config lives under `monitoring/`. Grafana dashboards are hand-built and every query is checked against live series.

---

## File Structure

**Created:**
- `core/json_log.py` — the `JsonFormatter` (LogRecord → one-line JSON). Stdlib only.
- `blog/tests/test_logging.py` — unit tests for `JsonFormatter`.
- `logs/.gitkeep` — keeps the bind-mount source dir in the repo with the developer's ownership.
- `monitoring/loki/loki-config.yml` — Loki single-binary config.
- `monitoring/alloy/config.alloy` — Alloy pipeline (file tail → process → write).
- `monitoring/dashboards/logs.json` — Grafana "Logs" dashboard.

**Modified:**
- `core/settings.py` — resolve `DEBUG` early; add `LOG_LEVEL` / `LOG_DIR` / `LOG_JSON_FILE`; alignment guard; `LOGGING` dict.
- `.gitignore` — ignore `logs/*` except `.gitkeep`.
- `.env.example` — document `LOG_JSON_FILE` and the derived `LOG_LEVEL`.
- `docker-compose.yml` — `loki` + `alloy` services, `loki_data` + `alloy_data` volumes, `grafana` `depends_on`.
- `monitoring/grafana/provisioning/datasources/datasource.yml` — Loki datasource.
- `monitoring/prometheus.yml` — `loki` and `alloy` scrape jobs.
- `README.md` — stack list, Logging subsection, config-table rows.
- `NOTES.md` — new logbook entry, drop the "Loki for logs" next-step, add follow-ups.

**Locally edited, not committed:**
- `.env` — set `LOG_JSON_FILE=True` for local verification.

---

## Task 1: JSON log formatter + Django logging config

**Files:**
- Create: `core/json_log.py`
- Create: `blog/tests/test_logging.py`
- Modify: `core/settings.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `core.json_log.JsonFormatter` — `logging.Formatter` subclass; `.format(record: logging.LogRecord) -> str` returns a single-line JSON string with keys `timestamp, level, logger, message, module, funcName, lineno, process, thread` and, when `record.exc_info` is set, `exception`.
  - `core.settings.LOG_LEVEL: str`, `core.settings.LOG_DIR: str`, `core.settings.LOG_JSON_FILE: bool`, `core.settings.LOGGING: dict`.

- [ ] **Step 1: Write the failing test**

Create `blog/tests/test_logging.py`:

```python
import json
import logging
import sys

from core.json_log import JsonFormatter


def _record(**overrides):
    kwargs = dict(
        name="blog.api",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="hello %s",
        args=("world",),
        exc_info=None,
        func="do_thing",
    )
    kwargs.update(overrides)
    return logging.LogRecord(**kwargs)


def test_format_emits_valid_json_with_expected_keys():
    data = json.loads(JsonFormatter().format(_record()))
    assert data["level"] == "INFO"
    assert data["logger"] == "blog.api"
    assert data["message"] == "hello world"
    assert data["lineno"] == 42
    assert data["funcName"] == "do_thing"
    assert data["timestamp"].endswith("+00:00")
    assert "exception" not in data


def test_format_includes_exception_when_exc_info_present():
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record(exc_info=sys.exc_info())
    data = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in data["exception"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest blog/tests/test_logging.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.json_log'`

- [ ] **Step 3: Write the formatter**

Create `core/json_log.py`:

```python
import datetime
import json
import logging


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as one line of JSON for Loki ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created, tz=datetime.UTC
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest blog/tests/test_logging.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Wire the logging config into settings**

In `core/settings.py`:

Add `import warnings` to the imports at the top (keep import order ruff-clean: `datetime`/`pathlib`/`warnings` are stdlib, `environ` is third-party).

Add three entries to the `Env(...)` schema, after `POSTGRES_PORT`:

```python
    LOG_DIR=(str, str(BASE_DIR / "logs")),
    LOG_JSON_FILE=(bool, False),
    LOG_LEVEL=(str, ""),  # blank → derived from DEBUG below
```

After the existing `DEBUG = env("DEBUG")` line, add:

```python
LOG_LEVEL = env("LOG_LEVEL") or ("DEBUG" if DEBUG else "INFO")
LOG_DIR = env("LOG_DIR")
LOG_JSON_FILE = env("LOG_JSON_FILE")

if not DEBUG and LOG_LEVEL == "DEBUG":
    warnings.warn(
        "LOG_LEVEL=DEBUG with DEBUG=False: debug-level logging in a non-debug "
        "deployment is a performance and PII-leak risk.",
        stacklevel=2,
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
        "json": {"()": "core.json_log.JsonFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "loggers": {
        name: {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False}
        for name in ("django", "django.request", "django.server", "blog")
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}

if LOG_JSON_FILE:
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    LOGGING["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(Path(LOG_DIR) / "app.log"),
        "formatter": "json",
        "maxBytes": 5 * 1024 * 1024,
        "backupCount": 3,
    }
    for logger in LOGGING["loggers"].values():
        logger["handlers"].append("file")
    LOGGING["root"]["handlers"].append("file")
```

(`Path` is already imported at the top of the file.)

- [ ] **Step 6: Verify the whole suite + lint + a manual smoke**

Run: `uv run pytest -q`
Expected: PASS (all existing tests + the 2 new ones)

Run: `ruff check .`
Expected: clean

Run: `LOG_JSON_FILE=True uv run python -c "import django,logging; django.setup(); logging.getLogger('blog').warning('smoke test'); print(open('logs/app.log').read())"`
Expected: one JSON line with `"message": "smoke test"`, `"level": "WARNING"`, `"logger": "blog"`.

Then delete the stray file: `rm -rf logs/app.log`

- [ ] **Step 7: Commit**

```bash
git add core/json_log.py blog/tests/test_logging.py core/settings.py
git commit -m "feat(logging): structured JSON logging with a DEBUG-aligned level"
```

---

## Task 2: Repo scaffolding for the log directory and env

**Files:**
- Create: `logs/.gitkeep`
- Modify: `.gitignore`
- Modify: `.env.example`
- Locally edit (do not commit): `.env`

**Interfaces:**
- Consumes: `LOG_JSON_FILE` from Task 1.
- Produces: a committed empty `logs/` dir; `.env.example` documenting the new vars.

- [ ] **Step 1: Add the gitkeep and ignore rule**

```bash
mkdir -p logs
touch logs/.gitkeep
```

Append to `.gitignore` (after the existing `.env` line):

```
logs/*
!logs/.gitkeep
```

- [ ] **Step 2: Verify the ignore rule**

Run: `touch logs/app.log && git status --porcelain logs/`
Expected: shows `?? logs/.gitkeep` only (not `logs/app.log`).
Then: `rm logs/app.log`

- [ ] **Step 3: Document the env vars in `.env.example`**

Add, after the `TIME_ZONE` block (keep the file's comment style):

```
# Structured JSON logs to logs/app.log, tailed by Alloy into Loki.
LOG_JSON_FILE=True
# LOG_LEVEL follows DEBUG (True -> DEBUG, False -> INFO) unless set explicitly.
# LOG_LEVEL=INFO
```

- [ ] **Step 4: Mirror the change into the local `.env` (not committed)**

Add `LOG_JSON_FILE=True` to your local `.env` so the rest of the plan's verification steps produce logs.

- [ ] **Step 5: Commit**

```bash
git add .gitignore .env.example logs/.gitkeep
git commit -m "chore(logging): track logs/ dir and document LOG_JSON_FILE"
```

---

## Task 3: Stand up Loki + Alloy and prove logs flow end to end

**Files:**
- Create: `monitoring/loki/loki-config.yml`
- Create: `monitoring/alloy/config.alloy`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: `logs/app.log` produced by the host app (Task 1 + local `.env` from Task 2).
- Produces: Loki reachable at `localhost:3100`, Alloy at `localhost:12345`, `{job="django"}` streams queryable in Loki with `level` and `logger` labels.

- [ ] **Step 1: Write the Loki config**

Create `monitoring/loki/loki-config.yml`:

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  log_level: warn

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  retention_period: 168h
  reject_old_samples: true
  reject_old_samples_max_age: 168h

compactor:
  working_directory: /loki/compactor
  retention_enabled: true
  delete_request_store: filesystem
```

- [ ] **Step 2: Write the Alloy config**

Create `monitoring/alloy/config.alloy`:

```alloy
loki.source.file "app" {
  targets = [
    { __path__ = "/var/log/app/app.log", job = "django", service = "blog" },
  ]
  forward_to = [loki.process.app.receiver]
}

loki.process "app" {
  stage.json {
    expressions = {
      level  = "level",
      logger = "logger",
      ts     = "timestamp",
    }
  }

  stage.timestamp {
    source = "ts"
    format = "RFC3339Nano"
  }

  stage.labels {
    values = {
      level  = "level",
      logger = "logger",
    }
  }

  forward_to = [loki.write.default.receiver]
}

loki.write "default" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
```

- [ ] **Step 3: Add the services to `docker-compose.yml`**

Add these two services (place them after `prometheus`, before `grafana`):

```yaml
  loki:
    image: grafana/loki:3.7.7
    command: -config.file=/etc/loki/loki-config.yml
    ports:
      - "3100:3100"
    volumes:
      - ./monitoring/loki/loki-config.yml:/etc/loki/loki-config.yml
      - loki_data:/loki
    restart: unless-stopped

  alloy:
    image: grafana/alloy:v1.19.2
    command:
      - run
      - --server.http.listen-addr=0.0.0.0:12345
      - --storage.path=/var/lib/alloy/data
      - /etc/alloy/config.alloy
    ports:
      - "12345:12345"
    volumes:
      - ./monitoring/alloy/config.alloy:/etc/alloy/config.alloy:ro
      - ./logs:/var/log/app:ro
      - alloy_data:/var/lib/alloy/data
    depends_on:
      - loki
    restart: unless-stopped
```

Add `loki` to the `grafana` service's `depends_on` list (currently `[prometheus]` → `[prometheus, loki]`).

Add to the top-level `volumes:` block:

```yaml
  loki_data:
  alloy_data:
```

- [ ] **Step 4: Verify Compose parses and the image tags exist**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK`, no error.

Run: `docker compose pull loki alloy`
Expected: both images pull. If a tag 404s, check https://github.com/grafana/loki/releases and https://github.com/grafana/alloy/releases for the current stable tag, update the image line, and note the change.

- [ ] **Step 5: Boot the pipeline and check readiness**

```bash
docker compose up -d loki alloy
sleep 5
curl -sf localhost:3100/ready && echo " loki-ready"
curl -sf localhost:12345/-/ready && echo " alloy-ready"
```

Expected: both print `ready` / `Alloy is ready.` (Loki may take ~15s on first boot — retry the curl if it 503s.)

- [ ] **Step 6: Generate logs and confirm they land in Loki**

With the local `.env` carrying `LOG_JSON_FILE=True`:

```bash
uv run python manage.py runserver &
SERVER_PID=$!
sleep 3
curl -s localhost:8000/api/posts?limit=1 >/dev/null
curl -s localhost:8000/api/nonexistent >/dev/null   # 404 path
sleep 3
curl -sG localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={job="django"}' | python -m json.tool | head -40
kill $SERVER_PID
```

Expected: the JSON response `data.result` contains at least one stream; its `stream` object includes `job="django"`, `service="blog"`, and a `level` label; `values` carry the raw JSON log lines.

- [ ] **Step 7: Commit**

```bash
git add monitoring/loki/loki-config.yml monitoring/alloy/config.alloy docker-compose.yml
git commit -m "feat(monitoring): ship Django logs to Loki via Alloy"
```

---

## Task 4: Provision the Loki datasource and scrape Loki + Alloy metrics

**Files:**
- Modify: `monitoring/grafana/provisioning/datasources/datasource.yml`
- Modify: `monitoring/prometheus.yml`

**Interfaces:**
- Consumes: `loki` and `alloy` services from Task 3.
- Produces: a Grafana datasource with `uid: loki`; Prometheus targets `loki` and `alloy` reporting `up`.

- [ ] **Step 1: Add the Loki datasource**

Append to `monitoring/grafana/provisioning/datasources/datasource.yml` (under `datasources:`, matching the existing indentation):

```yaml
  - name: Loki
    uid: loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: false
    editable: false
```

- [ ] **Step 2: Add the Prometheus scrape jobs**

Append to `scrape_configs:` in `monitoring/prometheus.yml`:

```yaml
  - job_name: 'loki'
    static_configs:
      - targets: ['loki:3100']

  - job_name: 'alloy'
    static_configs:
      - targets: ['alloy:12345']
```

- [ ] **Step 3: Verify**

```bash
docker compose up -d
sleep 10
curl -sG localhost:9090/api/v1/targets | python -m json.tool \
  | grep -E '"job"|"health"'
```

Expected: `loki` and `alloy` jobs both show `"health": "up"`.

Open `http://localhost:3000` → Connections → Data sources → confirm **Loki** is listed and "Test" succeeds. Explore → Loki → `{job="django"}` returns lines (run the app first if none appear).

- [ ] **Step 4: Commit**

```bash
git add monitoring/grafana/provisioning/datasources/datasource.yml monitoring/prometheus.yml
git commit -m "feat(monitoring): provision Loki datasource and scrape loki/alloy metrics"
```

---

## Task 5: Logs dashboard

**Files:**
- Create: `monitoring/dashboards/logs.json`

**Interfaces:**
- Consumes: the `loki` datasource (`uid: loki`) from Task 4; the existing dashboard provider `monitoring/grafana/provisioning/dashboards/dashboards.yml` (already mounts `monitoring/dashboards/`).
- Produces: a provisioned **Logs** dashboard.

- [ ] **Step 1: Build the dashboard in Grafana against live data**

Ensure the app has produced a spread of log lines first:

```bash
uv run python manage.py runserver &
for i in $(seq 1 20); do curl -s "localhost:8000/api/posts?limit=1" >/dev/null; done
curl -s localhost:8000/api/nope >/dev/null
```

In Grafana (`http://localhost:3000`, log in as admin) create a new dashboard titled **Logs** with:

1. **Stat** — "Log lines (range)": Loki, query `sum(count_over_time({job="django"}[$__range]))`, instant.
2. **Stat** — "Errors (range)": query `sum(count_over_time({job="django", level="ERROR"}[$__range]))`, instant, thresholds red > 0.
3. **Time series** — "Volume by level": query `sum by (level) (count_over_time({job="django"}[$__auto]))`.
4. **Time series** — "Warn/error rate": query `sum by (level) (rate({job="django", level=~"WARNING|ERROR|CRITICAL"}[$__auto]))`.
5. **Logs** panel — "Stream": query `{job="django", level=~"$level"} |= "$search" | json`, show time + unique labels, newest first.

Template variables:
- `level` — Custom, values `All,DEBUG,INFO,WARNING,ERROR,CRITICAL`, multi-value on, "All" value `.+`, include-all on.
- `search` — Textbox, default empty.

Verify every panel renders with data and that changing `level` / typing in `search` filters the Stream panel.

- [ ] **Step 2: Export and save the JSON**

Dashboard settings → JSON Model → copy. Save to `monitoring/dashboards/logs.json`. Normalize it the same way the existing dashboards are:
- top-level `"uid"`: `"logs"`
- every panel `datasource` and every `targets[].datasource`: `{"type": "loki", "uid": "loki"}`
- `"id": null`, strip `"version"` churn and `__inputs`/`__requires` if present

Cross-check formatting against `monitoring/dashboards/django.json`.

- [ ] **Step 3: Verify provisioning picks it up**

```bash
docker compose restart grafana
sleep 8
curl -sf "localhost:3000/api/dashboards/uid/logs" | python -m json.tool | head -5
```

Expected: returns the dashboard (not 404). Open it in the browser — all five panels show data, both template vars work.

- [ ] **Step 4: Commit**

```bash
git add monitoring/dashboards/logs.json
git commit -m "feat(monitoring): hand-built Logs dashboard on Loki"
```

---

## Task 6: Documentation

**Files:**
- Modify: `README.md`
- Modify: `NOTES.md`

**Interfaces:**
- Consumes: everything above.
- Produces: docs in sync with the shipped pipeline.

- [ ] **Step 1: README**

- In the Docker prereq line and the `docker compose up -d` comment, add Loki (`:3100`) and Alloy (`:12345`) to the listed services.
- Under the Grafana paragraph, add a short **Logging** note:

  > The Django app writes structured JSON to `logs/app.log` when `LOG_JSON_FILE=True`
  > (the `.env.example` default). Grafana Alloy tails that file and ships it to Loki;
  > the provisioned **Logs** dashboard and Explore query it. `runserver` must be up
  > for lines to appear. `LOG_LEVEL` follows `DEBUG` (→ `DEBUG` when `DEBUG=True`,
  > else `INFO`) unless set explicitly.

- Add rows to the config table:

  | `LOG_LEVEL`     | follows `DEBUG` (`DEBUG`/`INFO`) |
  | `LOG_DIR`       | `<repo>/logs`                    |
  | `LOG_JSON_FILE` | `False` (`.env.example` ships `True`) |

- [ ] **Step 2: NOTES.md**

- Add an entry under "What I fixed and why" (logbook voice, design framing), e.g.:

  > * Structured logging: `core/json_log.py` renders each `LogRecord` as one JSON
  >   line; a `RotatingFileHandler` writes `logs/app.log` only when `LOG_JSON_FILE`
  >   is set, so tests and bare checkouts stay file-free. `LOG_LEVEL` derives from
  >   `DEBUG` (`DEBUG`→`DEBUG`, else `INFO`); an explicit value overrides, and
  >   `DEBUG=False` + `LOG_LEVEL=DEBUG` warns.
  > * Log pipeline in `docker-compose.yml`: `grafana/alloy:v1.19.2` tails the
  >   bind-mounted `logs/app.log`, parses the JSON, promotes `level`/`logger` to
  >   labels, and pushes to `grafana/loki:3.7.7` (single-binary, filesystem store,
  >   7-day retention). Grafana gets a provisioned Loki datasource and a hand-built
  >   **Logs** dashboard; Prometheus scrapes both new `/metrics` endpoints.

- Remove the "still want Loki for logs" clause from the observability bullet under "What I'd do next".
- Add follow-ups under "What I'd do next":

  > * Collect container logs too (`loki.source.docker` in Alloy) — right now only
  >   the app is covered.
  > * Correlation/request IDs threaded into the log context.
  > * Loki ruler + alert rules on log-based metrics (error-rate spike).
  > * `JsonFormatter` ignores `extra=` fields; serialize them if structured context
  >   becomes useful.

- Add to "Things I'll keep out": Promtail (Alloy supersedes it); a MinIO/S3 Loki backend (filesystem is fine at this scale); network log push from Django (file-tail decouples the app from the stack being up).

- [ ] **Step 3: Commit**

```bash
git add README.md NOTES.md
git commit -m "docs(logging): document the Alloy + Loki pipeline"
```

---

## Task 7: Full-stack verification pass

**Files:** none (verification only; fixes go back to the relevant task's files).

- [ ] **Step 1: Clean boot**

```bash
docker compose down
docker compose up -d
sleep 15
docker compose ps
```

Expected: `postgres`, `pgexporter`, `prometheus`, `grafana`, `pgadmin`, `loki`, `alloy` all `Up`.

- [ ] **Step 2: Readiness + targets**

```bash
curl -sf localhost:3100/ready && echo " loki"
curl -sf localhost:12345/-/ready && echo " alloy"
curl -sG localhost:9090/api/v1/targets | python -m json.tool | grep -E '"job"|"health"'
```

Expected: loki + alloy ready; all Prometheus targets `up` (the `django-exporter` one only once `runserver` is up).

- [ ] **Step 3: End-to-end log path**

```bash
uv run python manage.py migrate
uv run python manage.py runserver &
SERVER_PID=$!
sleep 3
for i in $(seq 1 10); do curl -s "localhost:8000/api/posts?limit=1" >/dev/null; done
curl -s localhost:8000/api/definitely-not-a-route >/dev/null
sleep 3
curl -sG localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query=sum(count_over_time({job="django"}[5m]))' \
  | python -m json.tool
kill $SERVER_PID
```

Expected: a non-zero scalar/vector result.

- [ ] **Step 4: Grafana**

Browser: `http://localhost:3000` → **Logs** dashboard renders all five panels with data; `level` and `search` vars filter the Stream panel. Existing **PostgreSQL** and **Django** dashboards still render (no datasource regression).

- [ ] **Step 5: Toggle-off behavior**

```bash
LOG_JSON_FILE=False uv run python -c "import django; django.setup(); import logging; logging.getLogger('blog').info('x')"
ls logs/
```

Expected: no `app.log` created; only `.gitkeep` present.

- [ ] **Step 6: Lint + tests + tree state**

```bash
ruff check .
uv run pytest -q
git status
```

Expected: ruff clean; all tests pass; working tree clean (no stray `logs/app.log`, no uncommitted plan-related changes).

- [ ] **Step 7: Fast-forward to main**

Per the repo workflow — fast-forward `main` to the topic branch (do **not** push unless asked):

```bash
git checkout main && git merge --ff-only feat/loki-alloy-logging && git checkout feat/loki-alloy-logging
```

---

## Self-Review

**1. Spec coverage:**
- JSON formatter (`core/json_log.py`) → Task 1. ✓
- `DEBUG`-derived `LOG_LEVEL` + alignment guard → Task 1. ✓
- `LOG_DIR` / `LOG_JSON_FILE` / `LOGGING` dict, file handler only when enabled → Task 1. ✓
- `.gitignore` + `logs/.gitkeep` + `.env.example` → Task 2. ✓
- Loki single-binary config → Task 3. ✓
- Alloy file-tail → process (json/timestamp/labels) → write → Task 3. ✓
- Compose services, volumes, pinned images, `grafana` depends_on → Task 3. ✓
- Loki datasource provisioning → Task 4. ✓
- Prometheus scrape of loki + alloy → Task 4. ✓
- Logs dashboard, panels + template vars → Task 5. ✓
- README + NOTES → Task 6. ✓
- Error-handling / edge cases (toggle-off, rotation, Loki-down buffering, label cardinality, event vs ingest time) → covered by config choices in Tasks 1/3 and verified in Tasks 3/7. ✓
- Testing/verification list from spec → Tasks 3, 4, 5, 7. ✓

**2. Placeholder scan:** No TBD/TODO. Image tags are concrete (`grafana/loki:3.7.7`, `grafana/alloy:v1.19.2`) with a fallback check step. The dashboard task references live Grafana UI steps rather than a full 300-line JSON blob — acceptable because the JSON is machine-exported and normalized against an existing checked-in example (`django.json`); every panel query is spelled out verbatim.

**3. Type consistency:** `JsonFormatter` — same name and `.format()` signature in Task 1's test, implementation, and the settings `"()"` reference. Label names `job`/`service`/`level`/`logger` consistent across Alloy config (Task 3), dashboard queries (Task 5), and verification queries (Tasks 3/7). Datasource `uid: loki` consistent between Task 4 and Task 5. Volume names `loki_data`/`alloy_data` consistent within Task 3.
