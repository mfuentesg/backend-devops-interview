# Logging pipeline design — Grafana Alloy + Loki

Date: 2026-09-01
Status: approved (brainstorming)

## Goal

The repo already ships a metrics stack (Prometheus, Grafana, `postgres-exporter`,
`django-prometheus`). Logs have no home: Django runs on `django.default` config —
plain text to the console, nothing collected. Add a log pipeline that fits the
existing monitoring stack:

- Structured (JSON) application logs from the host-run Django app.
- A collector (**Grafana Alloy**) that tails those logs and ships them to **Loki**.
- Loki wired into the same Grafana as a provisioned datasource, with a hand-built
  **Logs** dashboard alongside the existing PostgreSQL and Django ones.
- All infra in `docker-compose.yml`, images pinned, config under `monitoring/`.
- One command (`docker compose up -d`) still brings up everything.

## Non-goals for this pass (explicit)

- Collecting container logs (Postgres, Grafana, Prometheus, exporters, pgAdmin).
  Django app only.
- Trace / correlation IDs threaded through requests.
- Loki ruler / log-based alert rules.
- An S3-style Loki backend (MinIO). Single-binary + filesystem only.
- Promtail (deprecated in favour of Alloy).
- Shipping logs over the network from Django directly (no `loki.source.api`
  receiver, no `python-logging-loki` handler). File-tail only.
- Changing how the app is run — it stays a host process (`manage.py runserver`).

## Decisions locked during brainstorming

| Topic | Decision |
| --- | --- |
| Log sources | Django application only. |
| Transport | Django writes JSON lines to `logs/app.log`; that dir is bind-mounted read-only into the Alloy container; Alloy tails it with `loki.source.file`. No network coupling between the app and the stack. |
| Django logging | Human-readable plain text stays on the console (dev ergonomics). A JSON `RotatingFileHandler` is added, attached **only** when `LOG_JSON_FILE` is true. Stdlib only — a small custom `JsonFormatter`, no new dependency. |
| `LOG_LEVEL` default | Flat `"INFO"`. An explicit `LOG_LEVEL` env var overrides. (An earlier revision derived this from `DEBUG`; reverted — pointing the `django` logger at a DEBUG level turns on Django's internal DEBUG firehoses, see below.) |
| Django firehose loggers | `django.utils.autoreload` and `django.db.backends` are pinned to `INFO` regardless of `LOG_LEVEL` — at DEBUG they emit one line per watched file / per SQL query. A comment says to lower them by hand when debugging SQL. |
| Alignment guard | At settings load, `not DEBUG and LOG_LEVEL == "DEBUG"` emits a `warnings.warn(...)` — debug logging in a non-debug deployment is a perf / PII risk. Retained even though the default no longer follows `DEBUG`. |
| Loki deployment | Single-binary, `filesystem` object store, TSDB v13 index, `auth_enabled: false`, 168h (7d) retention with the compactor. No MinIO / rings. |
| Grafana surface | Provision the Loki datasource **and** a hand-built `logs.json` dashboard. |
| Alloy / Loki metrics | Added as Prometheus scrape targets (`/metrics`), consistent with the existing exporters. |
| `logs/` dir existence | Commit `logs/.gitkeep` so the bind-mount source exists with the developer's ownership before Compose can create it as root. |
| Label set | `job`, `service`, `level`, `logger` only — all bounded cardinality. Everything else stays log content, queried via `| json`. |

## Components

### `core/json_log.py` (new)

`JsonFormatter(logging.Formatter)`, ~30 lines, stdlib `json` + `logging`. Module
named `json_log`, not `logging`, to avoid any stdlib-shadow confusion.

Emits one JSON object per line:

| Field | Source |
| --- | --- |
| `timestamp` | `datetime.fromtimestamp(record.created, tz=UTC)`, ISO-8601 |
| `level` | `record.levelname` |
| `logger` | `record.name` |
| `message` | `record.getMessage()` |
| `module` | `record.module` |
| `funcName` | `record.funcName` |
| `lineno` | `record.lineno` |
| `process` | `record.process` |
| `thread` | `record.thread` |
| `exception` | `self.formatException(record.exc_info)` when `exc_info` is set, else omitted |

No attempt to serialize arbitrary `extra` in this pass (keeps the formatter
predictable); revisit if needed.

### `core/settings.py` (modified)

1. New env vars:

   | Var | Default | Notes |
   | --- | --- | --- |
   | `LOG_LEVEL` | `"INFO"` (schema entry `(str, "")`, resolved `env("LOG_LEVEL") or "INFO"`) | applies to `django`, `django.request`, `django.server`, `blog`, root |
   | `LOG_DIR` | `str(BASE_DIR / "logs")` | |
   | `LOG_JSON_FILE` | `False` | `.env` / `.env.example` ship `True` |

   `DEBUG` still needs to be resolved before the alignment guard runs; the existing
   `DEBUG = env("DEBUG")` line is enough (no reshuffle required now that the
   `LOG_LEVEL` default is static).

2. Alignment guard:

   ```python
   if not DEBUG and LOG_LEVEL == "DEBUG":
       warnings.warn(
           "LOG_LEVEL=DEBUG with DEBUG=False: debug logging in a non-debug "
           "deployment is a performance and PII-leak risk.",
           stacklevel=2,
       )
   ```

3. When `LOG_JSON_FILE`: `Path(LOG_DIR).mkdir(parents=True, exist_ok=True)`.

4. `LOGGING` dict:
   - `formatters`: `plain` (human console), `json` (`"()": "core.json_log.JsonFormatter"`)
   - `handlers`:
     - `console` — `logging.StreamHandler`, `plain` (always present)
     - `file` — `logging.handlers.RotatingFileHandler`, `${LOG_DIR}/app.log`,
       `json`, `maxBytes = 5 * 1024 * 1024`, `backupCount = 3`
       (only appended to logger `handlers` lists when `LOG_JSON_FILE`)
   - `loggers`: `django`, `django.request`, `django.server`, `blog` — each at
     `LOG_LEVEL`, handlers `["console"]` (+ `"file"` when `LOG_JSON_FILE`),
     `propagate: False` (so the `root` handlers don't re-emit them).
   - `loggers` (pinned): `django.db.backends` and `django.utils.autoreload` at a
     fixed `INFO`, same handlers, `propagate: False` — their DEBUG output is one
     line per SQL query / per watched file, never wanted just because
     `LOG_LEVEL=DEBUG`. Inline comment notes how to lower them for SQL debugging.
   - `root`: `LOG_LEVEL`, same handler list — catches every other logger once.
   - `disable_existing_loggers: False`.

### `monitoring/loki/loki-config.yml` (new)

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

Volume `loki_data:/loki`.

### `monitoring/alloy/config.alloy` (new)

```alloy
local.file_match "app" {
  path_targets = [{ __path__ = "/var/log/app/app.log", job = "django", service = "blog" }]
  sync_period  = "10s"
}

loki.source.file "app" {
  targets    = local.file_match.app.targets
  forward_to = [loki.process.app.receiver]
}

loki.process "app" {
  stage.json {
    expressions = { level = "level", logger = "logger", ts = "timestamp" }
  }
  stage.timestamp {
    source = "ts"
    # matched to the JsonFormatter output during implementation
    # (RFC3339Nano if isoformat() emits microseconds)
    format = "RFC3339Nano"
  }
  stage.labels {
    values = { level = "level", logger = "logger" }
  }
  forward_to = [loki.write.default.receiver]
}

loki.write "default" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
```

Alloy UI + `/metrics` on `:12345`. Storage path `/var/lib/alloy/data` on the
`alloy_data` volume (WAL + retry buffer).

### `docker-compose.yml` (modified)

Add:

- `loki` — pinned `grafana/loki:<stable>`, `-config.file=/etc/loki/loki-config.yml`,
  mount `./monitoring/loki/loki-config.yml`, volume `loki_data:/loki`, port
  `3100:3100`, `restart: unless-stopped`.
- `alloy` — pinned `grafana/alloy:<stable>`, command
  `run --server.http.listen-addr=0.0.0.0:12345 --storage.path=/var/lib/alloy/data /etc/alloy/config.alloy`,
  mounts `./monitoring/alloy/config.alloy:ro` and `./logs:/var/log/app:ro`, volume
  `alloy_data:/var/lib/alloy/data`, port `12345:12345`, `depends_on: [loki]`,
  `restart: unless-stopped`.
- `grafana` — add `loki` to `depends_on`.
- new named volumes: `loki_data`, `alloy_data`.

Exact image tags pinned to the current stable releases at implementation time and
verified with `docker compose config` + a boot.

### `monitoring/grafana/provisioning/datasources/datasource.yml` (modified)

Append:

```yaml
  - name: Loki
    uid: loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: false
```

### `monitoring/dashboards/logs.json` (new)

Hand-built **Logs** dashboard. Panels, every query checked against live series:

- Stat — total log lines over the range: `sum(count_over_time({job="django"} [$__range]))`
- Stat — error lines over the range: `sum(count_over_time({job="django", level="ERROR"} [$__range]))`
- Timeseries — volume by level: `sum by (level) (count_over_time({job="django"} [$__interval]))`
- Timeseries — warn/error rate: `sum by (level) (rate({job="django", level=~"WARNING|ERROR|CRITICAL"} [$__interval]))`
- Logs panel — `{job="django", level=~"$level"} |= "$search" | json` (empty `$search` → `|= ""`, matches all; `$level` = `.+` when the var is `All`)

Template vars:
- `level` — custom / dropdown: `All`, `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
  (multi-value → LogQL `level=~"$level"`)
- `search` — textbox, default empty, fed to `|=`

### `monitoring/prometheus.yml` (modified)

Add two `static_configs` scrape jobs:

- `loki` → `loki:3100`
- `alloy` → `alloy:12345`

### `.gitignore` (modified)

```
logs/*
!logs/.gitkeep
```

Commit `logs/.gitkeep`.

### `.env.example` / `.env` (modified)

Add:

```
# Structured JSON logs to logs/app.log for the Alloy -> Loki pipeline.
LOG_JSON_FILE=True
# Root/app log level. Defaults to INFO; set DEBUG for verbose app logs
# (django.db.backends and django.utils.autoreload stay at INFO regardless).
# LOG_LEVEL=INFO
```

`.env.example` ships no active `LOG_LEVEL` line so the `INFO` default shows through.

### `README.md` (modified)

- Loki + Alloy in the stack list and the port comment.
- A short **Logging** subsection: JSON to `logs/app.log`, tailed by Alloy into Loki,
  visible in Grafana; `runserver` with `LOG_JSON_FILE=True` feeds it.
- Config-table rows for `LOG_LEVEL` (default `INFO`), `LOG_DIR`, `LOG_JSON_FILE`.

### `NOTES.md` (modified)

Logbook framing — describe the added capability as design, not a fix narrative:

- New entry: the JSON logging config (INFO default, Django DEBUG firehoses pinned,
  the `DEBUG=False`+`LOG_LEVEL=DEBUG` guard), the Alloy → Loki pipeline, the
  provisioned datasource + Logs dashboard.
- Drop the "still want Loki for logs" line from "What I'd do next".
- Add follow-ups: container-log collection via `loki.source.docker`, correlation
  IDs, Loki ruler + log-based alerts, `extra`-field serialization in the formatter.
- "Self taste" / "Things I'll keep out": Alloy over Promtail; single-binary Loki
  over a MinIO backend; file-tail over network push.

## Data flow

```
Django (host process)
  └─ logging → RotatingFileHandler → logs/app.log   (JSON lines, 5MB x 3)
        │  bind mount ./logs → /var/log/app  (ro)
        ▼
Alloy container
  loki.source.file  (tail app.log)
   → loki.process   (stage.json → stage.timestamp → stage.labels: level, logger)
   → loki.write     → http://loki:3100/loki/api/v1/push
        ▼
Loki (single-binary, filesystem, 7d retention)   :3100
        ▲
Grafana  ── Loki datasource (uid: loki) ── Logs dashboard / Explore
Prometheus ── scrapes loki:3100/metrics, alloy:12345/metrics
```

## Error handling / edge cases

| Case | Behavior |
| --- | --- |
| `LOG_JSON_FILE=False` | No file handler, no `logs/` writes. Alloy's `local.file_match` polls the path every `sync_period` (10s) and attaches `loki.source.file` when the file appears — no `docker compose restart alloy` needed on a fresh checkout. |
| Log rotation | `RotatingFileHandler` renames; Alloy follows by inode and reopens the new file. |
| Loki down / restarting | Alloy buffers on the `alloy_data` volume (WAL) and retries. Django is unaffected — it only writes a file. |
| `logs/` owned by root (Compose created it) | Prevented by committing `logs/.gitkeep` so the dir pre-exists. |
| Label cardinality | Only `job`, `service`, `level`, `logger`. `message`, `module`, `funcName`, paths stay as content. |
| Event time vs ingest time | `stage.timestamp` parses the formatter's UTC timestamp so panels use event time. |
| Non-JSON lines in `app.log` (e.g. a stray traceback line) | `stage.json` fails that line's parse; it is still shipped, just without parsed labels. Acceptable. |
| Tests / CI | `LOG_JSON_FILE` defaults `False`; pytest writes no files, needs no stack. `conftest.py` also does `os.environ.setdefault("LOG_JSON_FILE", "False")` before Django is configured, so the suite still writes nothing after `cp .env.example .env` (which ships `LOG_JSON_FILE=True`). |

## Testing / verification

- `docker compose config` parses.
- `docker compose up -d loki alloy` → `curl -sf localhost:3100/ready`,
  `curl -sf localhost:12345/-/ready`.
- Run the app with `LOG_JSON_FILE=True`; exercise an endpoint and trigger a 404 and
  a 500; confirm `logs/app.log` contains matching JSON lines (including the
  `exception` field on the 500).
- `curl -G localhost:3100/loki/api/v1/query_range --data-urlencode 'query={job="django"}'`
  returns those lines with `level` / `logger` labels.
- Grafana → Explore → Loki → `{job="django"}` shows data; the **Logs** dashboard
  renders every panel with data; the `level` and `search` vars filter correctly.
- Prometheus `/targets` shows `loki` and `alloy` `up`.
- One unit test — `blog/tests/test_logging.py` (or `core/`): `JsonFormatter().format(record)`
  produces valid JSON with the expected keys; a record with `exc_info` includes
  `exception`.
- `ruff check .` clean.

## Rollout / ordering

1. `core/json_log.py` + settings `LOGGING` + env vars + alignment guard + unit test.
2. `.gitignore`, `logs/.gitkeep`, `.env.example` / `.env`.
3. `monitoring/loki/loki-config.yml`, `monitoring/alloy/config.alloy`.
4. `docker-compose.yml` services + volumes.
5. `datasource.yml` Loki entry, `prometheus.yml` scrape jobs.
6. `monitoring/dashboards/logs.json` — build against the live stack.
7. README + NOTES.
8. Full end-to-end verification pass.
