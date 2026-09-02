# Migrations on Docker

I've tried a few ways of handling migrations in containerized setups. Here migrations and
seeding are a local development concern, so the base `docker compose up` should stay
infra-only and not know anything about them.

For the production side, let's add a separate compose file (an opt-in overlay) with a
couple of extra services built from the same application image:

1. A `migrate` service that just runs the migrations, and that `web` waits on before
   starting.
2. A `seed` service that loads sample data, kept behind a profile so it doesn't run
   by default.

Both only change the command passed to the same image. That way we don't need a
dedicated image for migrations or seeding, and the app image stays free of any
migrate/seed commands baked in.

In a real deployment this would probably be a pipeline step instead. For now, keep it
simple: one production-only compose file with these services.
