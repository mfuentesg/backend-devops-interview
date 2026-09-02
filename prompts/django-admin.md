# Administration interface

`/admin` is a well-known path, so it gets scanned and hammered constantly. Let's move it
somewhere else and put the whole thing behind environment variables, so it's easier to
protect and to disable entirely on production.

Two variables:

1. `ADMIN_ENABLED` — mounts the admin route or not. Default off.
2. `ADMIN_URL` — the path the admin lives on. Default to something that isn't `/admin/`.

Keep the change small: don't touch installed apps or middleware, just the route. Flipping
it on for a real environment should only need the env vars plus a superuser.

In the future we can revisit whether the admin should stay in the repo at all. For now
this is enough — off by default, on a non-obvious path, controlled from the environment.
