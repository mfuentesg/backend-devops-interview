# Monitoring and observability

I've picked a set of tools for monitoring and observability. I'm most familiar with
Grafana, so everything stays in the same family and plugs together with little glue.

* **Grafana** for dashboards and log exploration. Keep it open to anonymous viewers so
  the dashboards are visible without an account, but only logged-in users get Explore and
  the editing features. Admin login from env vars.

* **Prometheus** as the metrics store and time series backend that feeds Grafana's
  dashboards and, later, alerts.

* **postgres-exporter** and the Django exporter to expose Postgres and app metrics for
  Prometheus to scrape.

* **Loki** for log aggregation. Emit structured logs as JSON and ship them with **Alloy**
  as the collector — tail the log file rather than pushing from the app, so the app
  doesn't care whether the logging stack is up.

* **pgAdmin** just as a handy UI for poking at the database and running queries.

Everything runs from Docker Compose alongside Postgres. Pin the image versions. Provision
the Grafana datasources and dashboards from files so a fresh `docker compose up` comes up
with working dashboards, no manual clicking.
