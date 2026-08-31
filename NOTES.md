# Fintual Interview - Logbook

I'll write this document to cover two things.

1. Use it as context for the Agent I will use (Claude)
2. Detail all the stuff I believe that should be considered, implemented or fixed.

I would like to cover some important aspects to me:

* Developer experience: Giving a proper environment to other developers making its work easier.
* Documentation: Include as much details as possible, to avoid black boxes that nobody could understand in future development sessions
* Automation: Keep some handy commands to cover complex setups, including pipeline validations like linting or testing
* Agents: Prepare as much as possible this repo to give sufficient information for working with agents on any harness.
* Leave it better condition that you found it

## Self taste

* I'll use (skaffold)[https://github.com/GoogleContainerTools/skaffold] for local k8s development with autoreload support on code change, and other stuff. I have considered `docker compose` for this, but skaffold helps to have native k8s manifests and easy access to k8s workload.
* [kind](https://github.com/kubernetes-sigs/kind) for creating k8s nodes as docker containers
* Docker as container runtime
* Will include grafana for visualizing data using prometheus source, prometheus for collecting metrics and loki for logging
* [ruff](https://github.com/astral-sh/ruff) for linting
* Github actions for CI
* Claude as AI harness

## Code analysis

* blog/management/commands/seed.py
- `handle()` is one long function; could be split into per-entity steps (users / tags / posts / comments).
- Performance: the FK ordering (users -> tags -> posts -> post_tags -> comments) is inherent and cheap
  (parent IDs are already in memory before child inserts). The real bottlenecks were:
  1. `fake.sentence()` called per row for 500k comments -> now drawn from a 10k `comment_pool`,
     like posts already do for title/body.
  2. `random.choices(..., weights=...)` was re-accumulating a 100k-element weight list on every
     single draw (~600k calls) -> precompute `cum_weights` once and draw a full batch per call (`k=n`).
  3. Comments loop had no surrounding transaction (500 autocommits) -> wrapped in one
     `transaction.atomic()`, matching the posts loop.
- Estimated effect: ~15-25 min -> ~2 min, roughly 10-15x; almost all of it is item 2.
  RNG stream changes, so the seeded rows differ but stay deterministic under `seed(42)`.
- Not done: `COPY`-based bulk load (would shave the final ~1-2 min to ~30s but is a real rewrite
  away from the Django idiom), and splitting `handle()`.

## Things I will keep out

* Helm charts, is not too complex, but I don't is required at this moment, maybe for future improvements.
* Tracing tools, I consider this is too much for this project