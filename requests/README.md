# HTTP request files

Runnable request collections for the endpoints in `blog/api/`.

- **JetBrains IDEs** (PyCharm, IntelliJ): open any `.http` file and click the gutter ▶.
- **VS Code**: install the "REST Client" extension (`humao.rest-client`), open a file,
  click "Send Request" above each `###` block.

Each file defines its own `@baseUrl` at the top (`http://localhost:8000/api`). Change
that one line to point at another environment.

Requests assume a seeded database — `author_id: 1` and `posts/1` exist after
`python manage.py seed`.
