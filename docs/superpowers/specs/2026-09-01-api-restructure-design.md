# API restructure design — `blog/api.py`

Date: 2026-09-01
Status: approved (brainstorming)
Source prompt: `prompts/api.md`

## Goal

Take the single-file prototype API (`blog/api.py`, 8 endpoints, hand-rolled dict
serializers, no validation) and turn it into something a team can extend and operate:

- Split responsibilities into a small package, one module per entity.
- Give every endpoint a common response envelope, documented in `/api/docs`.
- Add real input validation, pagination, filtering and sorting to the list endpoint.
- Add expansion control and safe writes to the detail and create endpoints.
- Remove an endpoint that is a privacy / abuse risk.

Non-goals for this pass (explicit): full hexagonal / ports-and-adapters layout, a
selector/service layer, Postgres full-text or trigram indexes, query-string-level SQL
injection hardening (the ORM already parameterizes), comment expansion in the list
endpoint, adding a real `slug` field to `Post`.

## Decisions locked during brainstorming

| Topic | Decision |
| --- | --- |
| Module structure | "Just split the file": `blog/api/` package, one module per entity, shared glue in `helpers.py` + `responses.py`. No service layer. |
| Pagination metadata | Top-level `meta` key in the envelope: `{page, limit, total, total_pages}`. `null` on non-list endpoints. |
| Error item shape | `{field: str | null, message: str}`. No machine-readable code. |
| Envelope mechanism | Generic `Envelope[T]` Pydantic schema declared as `response=` (approach B), so `/api/docs` shows the real wrapped shape. Built through a single `ApiResponse` "template" object, used by views and exception handlers alike. Renderer approach rejected (breaks docs). |
| `?slug=` filter | Matches **tag** slug, same logic as the old `/posts/by-tag/{slug}`. Unknown tag → empty list + 200 (list endpoints never 404). |
| `/posts/search`, `/posts/by-tag/{slug}` | Deleted — folded into `/posts` query params. |
| `/users/find` | Deleted (route + handler). |
| List item shape | Minimal, unchanged `PostListOut`: `id, title, author, tags, view_count, created_at`. No `body`, no `comments`. |
| Default page size | `limit=20`, max `100`, min `1`. `page` min `1`. |
| POST /posts sanitization | Normalize (strip, non-empty, length) **and** strip HTML via `nh3`. New dependency. |
| POST /posts validation | Unknown `author_id` or any unknown `tag_slug` → `400` listing every bad value at once, nothing created (single `transaction.atomic()`). Success → `201` with the post in detail shape, `comments: []`. |
| `view_count` bump | `post.view_count += 1; post.save(update_fields=["view_count"])` (literal to the prompt). `F("view_count") + 1` noted as a race-safe follow-up, not done here. |
| Comment create response | Return the created comment in `CommentOut` shape (was bare `{id}`), `201`. |

## Response envelope

Every endpoint — success and error — returns this shape:

```json
{
  "data": null,
  "meta": null,
  "status_code": 200,
  "errors": []
}
```

- `data`: the typed payload (object or list), or `null` on error.
- `meta`: `{page, limit, total, total_pages}` on list endpoints only; `null` otherwise.
- `status_code`: mirrors the HTTP status (kept in the body per the prompt).
- `errors`: list of `{field, message}`; empty on success.

### Schemas (`blog/schemas.py`)

```python
T = TypeVar("T")

class ErrorItem(Schema):
    field: str | None = None
    message: str

class Meta(Schema):
    page: int
    limit: int
    total: int
    total_pages: int

class Envelope(Schema, Generic[T]):
    data: T | None = None
    meta: Meta | None = None
    status_code: int
    errors: list[ErrorItem] = []
```

If Ninja 1.6 does not render `Envelope[T]` cleanly into OpenAPI, fall back to explicit
subclasses (`PostListEnvelope(Envelope)` with `data: list[PostListOut] | None`, etc.).
Same docs output, more boilerplate.

### Response template (`blog/api/responses.py`)

```python
class ApiResponse:
    @staticmethod
    def success(data, *, status=200, meta=None) -> tuple[int, dict]: ...
    @staticmethod
    def paginated(items, *, page, limit, total) -> tuple[int, dict]: ...
    @staticmethod
    def error(errors: list[dict | ErrorItem], *, status=400) -> tuple[int, dict]: ...
```

Returns `(status, body)` tuples so Ninja sets the HTTP status and the body `status_code`
stays in sync. The exception handlers call `ApiResponse.error(...)`.

## Module layout

`blog/api.py` becomes `blog/api/` (import path `from blog.api import router` preserved):

```
blog/api/
  __init__.py     # Router(); include posts/comments/users routers; nothing else public
  posts.py        # GET /posts, GET /posts/{id}, POST /posts
  comments.py     # POST /posts/{id}/comments
  users.py        # GET /users/{id}
  responses.py    # ApiResponse template
  helpers.py      # exception handlers, paginate(), shared _serialize_author/_serialize_tag
```

Exception handlers are registered on the `NinjaAPI` instance in `core/urls.py` (that is
where the `NinjaAPI()` object lives). `helpers.register_exception_handlers(api)` is called
there.

`blog/schemas.py` stays a single module; gains `Envelope`, `Meta`, `ErrorItem`,
`PostFilters`, `SortOrder`, `Expandable`.

## Exception handlers (`blog/api/helpers.py`)

| Exception | HTTP | Body |
| --- | --- | --- |
| `ninja.errors.ValidationError` (query + body) | 400 | one `ErrorItem` per Pydantic error: `field` from `loc[-1]`, `message` from `msg` |
| `django.http.Http404` / custom `NotFound` | 404 | single item, e.g. `{field: "post_id", message: "No post with id 999"}` |
| custom `ApiError(status, errors)` | `status` | the provided `errors` |
| `Exception` (fallback) | 500 | `[{field: null, message: "Internal server error"}]`, only when `DEBUG=False`; in debug, re-raise so Ninja's default traceback page shows |

## Endpoints

### `GET /posts` — list, filter, sort, paginate

```python
class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"

class PostFilters(Schema):
    published: bool | None = None      # true=published, false=drafts, omitted=all
    sort: SortOrder = SortOrder.desc   # created_at only
    query: str | None = None           # icontains over title OR body
    slug: str | None = None            # tag slug; unknown => empty list
```

Handler:

```python
@router.get("/posts", response={200: Envelope[list[PostListOut]], 400: Envelope[None]})
def list_posts(request, filters: Query[PostFilters],
               page: int = Query(1, ge=1),
               limit: int = Query(20, ge=1, le=100)):
```

- Base queryset: `Post.objects.select_related("author").prefetch_related("tags")`
  (removes the current per-row author + tags N+1).
- Apply filters conditionally, all via ORM kwargs (parameterized):
  - `published is not None` → `.filter(is_published=filters.published)`
  - `query` → `.filter(Q(title__icontains=q) | Q(body__icontains=q))`
  - `slug` → `.filter(tags__slug=filters.slug)`
- `.order_by("created_at" if sort is asc else "-created_at")`
- Paginate: `total = qs.count()`, `items = list(qs[offset:offset + limit])`,
  `total_pages = ceil(total / limit)` (0 when total is 0).
- `limit=101` (or `page=0`) → `ValidationError` → 400 envelope.
- Returns `ApiResponse.paginated(...)`.

Old `/posts/search` and `/posts/by-tag/{slug}` routes and handlers are removed.

### `GET /posts/{post_id}` — detail, expand, view bump

```python
class Expandable(str, Enum):
    comments = "comments"

@router.get("/posts/{post_id}", response={200: Envelope[PostDetailOut], 404: Envelope[None]})
def get_post(request, post_id: int, expand: list[Expandable] = Query([])):
```

- `Post.objects.select_related("author").prefetch_related("tags").filter(id=post_id).first()`;
  `None` → `NotFound("post_id", post_id)` → 404 envelope.
- `post.view_count += 1; post.save(update_fields=["view_count"])`.
- `comments`: populated only if `Expandable.comments in expand`, via
  `post.comments.select_related("author").order_by("created_at")`; otherwise `[]`.
- `PostDetailOut` unchanged (`comments` already defaults to `[]`).
- `?expand=comments` repeatable param (Ninja native). Comma-splitting is a possible
  follow-up, not in scope.

### `POST /posts` — sanitize, validate, create

```python
class PostCreateIn(Schema):
    author_id: int
    title: str
    body: str
    tag_slugs: list[str] = []
```

Field validators:
- `title`: `.strip()` → `nh3.clean(v, tags=set())` (strip all tags) → non-empty, `len <= 255`.
- `body`: `.strip()` → `nh3.clean(v)` (drops `<script>`, `on*` handlers, etc.) → non-empty.
- `tag_slugs`: lowercase each, must match `^[a-z0-9-]+$`, dedupe preserving order.

Handler `response={201: Envelope[PostDetailOut], 400: Envelope[None]}`, body wrapped in
`transaction.atomic()`:
1. `author = User.objects.filter(id=payload.author_id).first()`
2. `found = Tag.objects.filter(slug__in=payload.tag_slugs)`; `missing = set(slugs) - {t.slug}`
3. Build `errors`: `author_id` if no author, `tag_slugs` if `missing` (message lists them).
4. If `errors` → `raise ApiError(400, errors)` (rolls back, nothing created).
5. `post = Post.objects.create(author=author, title=payload.title, body=payload.body)`;
   `post.tags.set(found)`.
6. Return `ApiResponse.success(<detail dict with comments=[]>, status=201)`.

### `POST /posts/{post_id}/comments`

- `response={201: Envelope[CommentOut], 400: Envelope[None], 404: Envelope[None]}`.
- Missing post → 404. Missing author → 400 (`{field: "author_id", ...}`).
- `body`: `.strip()` → `nh3.clean(v)` → non-empty.
- Create, return the comment in `CommentOut` shape at `201`.

### `GET /users/{user_id}`

- `response={200: Envelope[UserDetailOut], 404: Envelope[None]}`.
- Missing user → 404 envelope. `_user_detail` helper unchanged.

### `GET /users/find`

Deleted — route and `find_user_by_email` handler removed. Rationale: unauthenticated
lookup by arbitrary email is an enumeration / DoS surface with no legitimate use here.

## Dependencies

- Add `nh3` to `[project].dependencies` in `pyproject.toml` (`uv add nh3`). Maintained
  Rust HTML sanitizer, ships compiled wheels for the target platforms.

## Documentation

- `README.md` "What the API does" table:
  - Remove `/posts/search`, `/posts/by-tag/{slug}`, `/users/find` rows.
  - Rewrite the `/posts` row: `?published=&sort=asc|desc&query=&slug=&page=&limit=` (max 100).
  - Add a one-line note: all responses use `{data, meta, status_code, errors}`.
- `/api/docs` (OpenAPI) updates automatically from the `Envelope[T]` response types.
- `NOTES.md`: logbook entry — found / fixed / kept out / next, per project rules.

## Tests

Update the existing smoke tests for the new envelope and status codes:
- `blog/tests/test_posts.py`: `response.json()["data"]` instead of bare list/object;
  detail `comments` assertion still valid (defaults `[]`).
- `blog/tests/test_comments.py`: envelope + `201`.

Add:
- `limit=101` → 400 with a `limit` error item.
- `published=false` returns only drafts; omitted returns all.
- `slug=` for a nonexistent tag → `200`, `data: []`, `meta.total: 0`.
- `expand=comments` populates `data.comments`; omitting it yields `[]`.
- `POST /posts` with unknown `author_id` and an unknown `tag_slug` → `400`, both errors
  present, no `Post` row created.

## Commit plan (Conventional Commits, small)

1. `refactor(api): split blog/api.py into a package per entity`
2. `feat(api): add the {data,meta,status_code,errors} response envelope`
3. `feat(api): filter, sort and paginate GET /posts; drop /posts/search and /posts/by-tag`
4. `feat(api): add expand param and safe view_count bump to GET /posts/{id}`
5. `feat(api): sanitize and validate POST /posts and comment creation`
6. `feat(api): envelope users endpoint and remove GET /users/find`
7. `docs: update README and NOTES for the reworked API`
