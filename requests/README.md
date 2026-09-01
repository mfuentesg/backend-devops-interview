# HTTP request files

Runnable request collections for the endpoints in `blog/api/`.

- **JetBrains IDEs** (PyCharm, IntelliJ): open any `.http` file and click the gutter ▶.
- **VS Code**: install the "REST Client" extension (`humao.rest-client`), open a file,
  click "Send Request" above each `###` block.

Both pick variables from `http-client.env.json`. Select the `local` environment
(JetBrains: env dropdown, top-right of the editor; REST Client: `rest-client.environmentVariables`
already reads this file). `local` points at `http://localhost:8000/api`.

Requests assume a seeded database — `author_id: 1` and `posts/1` exist after
`python manage.py seed`.
