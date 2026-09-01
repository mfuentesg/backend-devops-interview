# HTTP request files

Runnable request collections for the endpoints in `blog/api/`.

- **JetBrains IDEs** (PyCharm, IntelliJ): open any `.http` file and click the gutter ▶.
- **VS Code**: install the "REST Client" extension (`humao.rest-client`), open a file,
  click "Send Request" above each `###` block.

Both pick variables from `http-client.env.json`. VS Code REST Client reads
`http-client.env.json` automatically; pick the `local` environment from its status-bar
env picker. JetBrains: choose `local` from the env dropdown at the top-right of the
`.http` editor. `local` points at `http://localhost:8000/api`.

Requests assume a seeded database — `author_id: 1` and `posts/1` exist after
`python manage.py seed`.
