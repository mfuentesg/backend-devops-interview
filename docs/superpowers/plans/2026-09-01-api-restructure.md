# API Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-file `blog/api.py` prototype into a per-entity package where every endpoint returns one documented response envelope and validates its inputs.

**Architecture:** `blog/api.py` becomes a `blog/api/` package, one module per entity (`posts`, `comments`, `users`), plus `responses.py` (the envelope builder) and `helpers.py` (exception handlers, pagination, shared serializers). A generic `Envelope[T]` Pydantic schema is the declared `response=` type on every operation, so `/api/docs` shows the real wrapped shape. Views stay thin and call the ORM directly — no service layer this pass.

**Tech Stack:** Python 3.14, Django 5.2, django-ninja 1.6, Pydantic v2, Postgres, pytest / pytest-django, `nh3` (HTML sanitizer, new), ruff.

**Spec:** `docs/superpowers/specs/2026-09-01-api-restructure-design.md` — read it alongside this plan.

## Global Constraints

- Conventional Commits: `type(scope): summary`. **No `Co-Authored-By` trailer.**
- `ruff check .` must stay clean. Config: line-length 100, rules `E, F, I, UP, B`, target `py314`, migrations excluded.
- Run tests with `uv run pytest`. Run lint with `ruff check .` (ruff is on `PATH` via mise).
- `nh3` is a **runtime** dependency: add with `uv add nh3` (lands in `[project].dependencies`, never the `dev` group).
- All settings come from the environment via `django-environ`; this plan adds no new settings.
- Keep `NOTES.md` updated — first-person logbook, terse: found / fixed / kept out / next.
- The API is mounted at `/api/` (`core/urls.py`), so every route below is reachable at `/api/<path>`.
- Response envelope shape, every endpoint, success and error:
  `{"data": <obj|list|null>, "meta": <obj|null>, "status_code": <int>, "errors": [{"field": <str|null>, "message": <str>}]}`
- `meta` is `{"page", "limit", "total", "total_pages"}` on list endpoints only, else `null`.
- Pagination: `page >= 1` (default 1), `1 <= limit <= 100` (default 20).

---

## File Structure

**Created:**
- `blog/api/__init__.py` — builds the top-level `Router`, mounts the three sub-routers. Exposes `router`.
- `blog/api/posts.py` — `GET /posts`, `GET /posts/{post_id}`, `POST /posts`; post serializers.
- `blog/api/comments.py` — `POST /posts/{post_id}/comments`.
- `blog/api/users.py` — `GET /users/{user_id}`; user serializer.
- `blog/api/responses.py` — `ApiResponse` envelope builder.
- `blog/api/helpers.py` — `ApiError`, `register_exception_handlers`, `paginate`, shared `_serialize_author` / `_serialize_tag` / `_serialize_comment`.
- `blog/tests/test_api_envelope.py` — envelope + exception-handler tests.

**Modified:**
- `blog/api.py` — **deleted** (replaced by the package).
- `blog/schemas.py` — add `Envelope`, `Meta`, `ErrorItem`, `PostFilters`, `SortOrder`, `Expandable`; add validators to `PostCreateIn` / `CommentCreateIn`; `PostCreateOut` unused after this (leave or remove).
- `core/urls.py` — call `register_exception_handlers(api)` after creating the `NinjaAPI`.
- `blog/tests/test_posts.py` — adapt to the envelope; add filter/pagination/expand tests.
- `blog/tests/test_comments.py` — adapt to the envelope + `201`.
- `pyproject.toml` — `nh3` in `[project].dependencies` (via `uv add`).
- `README.md` — API table + envelope note.
- `NOTES.md` — logbook entry.

**Created (HTTP request files, Task 8):**
- `requests/http-client.env.json` — environment vars (`baseUrl`) for the JetBrains HTTP Client / VS Code REST Client.
- `requests/posts.http` — every `GET /posts`, `GET /posts/{id}`, `POST /posts` scenario.
- `requests/comments.http` — comment-creation scenarios.
- `requests/users.http` — user scenarios + the removed `/users/find` (documented as gone).
- `requests/README.md` — one paragraph: which editor plugins read these, how to pick the env.

---

## Task 1: Split `blog/api.py` into a package (pure refactor)

No behavior change. Every existing test must still pass **unmodified**.

**Files:**
- Create: `blog/api/__init__.py`, `blog/api/posts.py`, `blog/api/comments.py`, `blog/api/users.py`, `blog/api/helpers.py`
- Delete: `blog/api.py`
- Test: existing `blog/tests/test_posts.py`, `blog/tests/test_comments.py` (unchanged)

**Interfaces:**
- Produces: `blog.api.router` (a `ninja.Router`) — consumed by `core/urls.py`.
- Produces: `blog.api.helpers._serialize_author(user) -> dict`, `_serialize_tag(tag) -> dict`, `_serialize_comment(comment) -> dict`.

- [ ] **Step 1: Verify the current tests pass (baseline)**

Run: `uv run pytest blog/tests -q`
Expected: PASS (2 test files, 3 tests).

- [ ] **Step 2: Create `blog/api/helpers.py` with the shared serializers**

```python
from blog.models import Comment, Tag, User


def _serialize_author(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
    }


def _serialize_tag(tag: Tag) -> dict:
    return {"id": tag.id, "name": tag.name, "slug": tag.slug}


def _serialize_comment(comment: Comment) -> dict:
    return {
        "id": comment.id,
        "author": _serialize_author(comment.author),
        "body": comment.body,
        "created_at": comment.created_at,
    }
```

- [ ] **Step 3: Create `blog/api/posts.py` (move the three post endpoints verbatim)**

```python
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router

from blog.api.helpers import _serialize_author, _serialize_comment, _serialize_tag
from blog.models import Post, Tag, User
from blog.schemas import PostCreateIn, PostCreateOut, PostDetailOut, PostListOut

router = Router()


def _serialize_post_list(post: Post) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "author": _serialize_author(post.author),
        "tags": [_serialize_tag(t) for t in post.tags.all()],
        "view_count": post.view_count,
        "created_at": post.created_at,
    }


@router.get("/posts", response=list[PostListOut])
def list_posts(request):
    posts = Post.objects.filter(is_published=True).order_by("-created_at")
    return [_serialize_post_list(p) for p in posts]


@router.get("/posts/search", response=list[PostListOut])
def search_posts(request, q: str):
    posts = Post.objects.filter(
        Q(title__icontains=q) | Q(body__icontains=q),
        is_published=True,
    ).order_by("-created_at")
    return [_serialize_post_list(p) for p in posts]


@router.get("/posts/by-tag/{slug}", response=list[PostListOut])
def posts_by_tag(request, slug: str):
    tag = get_object_or_404(Tag, slug=slug)
    posts = tag.posts.filter(is_published=True).order_by("-created_at")
    return [_serialize_post_list(p) for p in posts]


@router.get("/posts/{post_id}", response=PostDetailOut)
def get_post(request, post_id: int):
    post = get_object_or_404(Post, id=post_id)
    post.view_count += 1
    post.save()

    comments = [_serialize_comment(c) for c in post.comments.order_by("created_at")]

    return {
        "id": post.id,
        "title": post.title,
        "body": post.body,
        "author": _serialize_author(post.author),
        "tags": [_serialize_tag(t) for t in post.tags.all()],
        "comments": comments,
        "view_count": post.view_count,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }


@router.post("/posts", response=PostCreateOut)
def create_post(request, payload: PostCreateIn):
    author = get_object_or_404(User, id=payload.author_id)
    post = Post.objects.create(author=author, title=payload.title, body=payload.body)
    for slug in payload.tag_slugs:
        tag = Tag.objects.get(slug=slug)
        post.tags.add(tag)
    return {"id": post.id, "title": post.title}
```

- [ ] **Step 4: Create `blog/api/comments.py`**

```python
from django.shortcuts import get_object_or_404
from ninja import Router

from blog.models import Comment, Post, User
from blog.schemas import CommentCreateIn, CommentCreateOut

router = Router()


@router.post("/posts/{post_id}/comments", response=CommentCreateOut)
def create_comment(request, post_id: int, payload: CommentCreateIn):
    post = get_object_or_404(Post, id=post_id)
    author = get_object_or_404(User, id=payload.author_id)
    comment = Comment.objects.create(post=post, author=author, body=payload.body)
    return {"id": comment.id}
```

- [ ] **Step 5: Create `blog/api/users.py`**

```python
from django.shortcuts import get_object_or_404
from ninja import Router

from blog.api.helpers import _serialize_author  # noqa: F401  (kept for symmetry; remove if unused)
from blog.models import User
from blog.schemas import UserDetailOut

router = Router()


def _user_detail(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "bio": user.bio,
        "post_count": user.posts.count(),
        "comment_count": user.comments.count(),
    }


@router.get("/users/find", response=UserDetailOut)
def find_user_by_email(request, email: str):
    user = get_object_or_404(User, email=email)
    return _user_detail(user)


@router.get("/users/{user_id}", response=UserDetailOut)
def get_user(request, user_id: int):
    user = get_object_or_404(User, id=user_id)
    return _user_detail(user)
```

If ruff flags the unused `_serialize_author` import, delete that line — it was only listed to show the helper is importable.

- [ ] **Step 6: Create `blog/api/__init__.py`**

```python
from ninja import Router

from blog.api.comments import router as comments_router
from blog.api.posts import router as posts_router
from blog.api.users import router as users_router

router = Router()
router.add_router("", posts_router)
router.add_router("", comments_router)
router.add_router("", users_router)
```

- [ ] **Step 7: Delete the old module**

Run: `git rm blog/api.py`

- [ ] **Step 8: Run lint and the full test suite**

Run: `ruff check . && uv run pytest -q`
Expected: lint clean; all tests PASS unchanged. If `/api/posts/search` route ordering breaks (`search` vs `{post_id}`), keep the declaration order above — `search` and `by-tag` are declared before `{post_id}`, same as the original file.

- [ ] **Step 9: Commit**

```bash
git add blog/api blog/tests
git commit -m "refactor(api): split blog/api.py into a package per entity"
```

---

## Task 2: Envelope schemas + `ApiResponse` builder

**Files:**
- Modify: `blog/schemas.py` (add `ErrorItem`, `Meta`, `Envelope`)
- Create: `blog/api/responses.py`
- Test: `blog/tests/test_api_envelope.py`

**Interfaces:**
- Produces: `blog.schemas.Envelope[T]`, `blog.schemas.Meta`, `blog.schemas.ErrorItem`.
- Produces: `blog.api.responses.ApiResponse` with:
  - `success(data, *, status: int = 200, meta: dict | None = None) -> tuple[int, dict]`
  - `paginated(items: list, *, page: int, limit: int, total: int) -> tuple[int, dict]`
  - `error(errors: list[dict | str], *, status: int = 400) -> tuple[int, dict]`
  - Every returned dict has keys `data, meta, status_code, errors`.

- [ ] **Step 1: Write the failing test**

`blog/tests/test_api_envelope.py`:

```python
from blog.api.responses import ApiResponse


def test_success_wraps_data():
    status, body = ApiResponse.success({"id": 1})
    assert status == 200
    assert body == {"data": {"id": 1}, "meta": None, "status_code": 200, "errors": []}


def test_success_custom_status():
    status, body = ApiResponse.success({"id": 1}, status=201)
    assert status == 201
    assert body["status_code"] == 201


def test_paginated_computes_total_pages():
    status, body = ApiResponse.paginated([1, 2], page=1, limit=20, total=42)
    assert status == 200
    assert body["data"] == [1, 2]
    assert body["meta"] == {"page": 1, "limit": 20, "total": 42, "total_pages": 3}
    assert body["errors"] == []


def test_paginated_zero_total_is_zero_pages():
    _, body = ApiResponse.paginated([], page=1, limit=20, total=0)
    assert body["meta"]["total_pages"] == 0


def test_error_normalises_strings_and_dicts():
    status, body = ApiResponse.error(
        ["bad thing", {"field": "limit", "message": "too big"}], status=400
    )
    assert status == 400
    assert body["data"] is None and body["meta"] is None
    assert body["errors"] == [
        {"field": None, "message": "bad thing"},
        {"field": "limit", "message": "too big"},
    ]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest blog/tests/test_api_envelope.py -q`
Expected: FAIL — `ModuleNotFoundError: blog.api.responses`.

- [ ] **Step 3: Add the schemas to `blog/schemas.py`**

Add at the top: `from typing import Generic, TypeVar` and after the existing imports `T = TypeVar("T")`. Append:

```python
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

- [ ] **Step 4: Create `blog/api/responses.py`**

```python
import math


def _norm(errors):
    out = []
    for e in errors:
        if isinstance(e, dict):
            out.append({"field": e.get("field"), "message": e["message"]})
        else:
            out.append({"field": None, "message": str(e)})
    return out


class ApiResponse:
    @staticmethod
    def success(data, *, status: int = 200, meta: dict | None = None) -> tuple[int, dict]:
        return status, {"data": data, "meta": meta, "status_code": status, "errors": []}

    @staticmethod
    def paginated(items: list, *, page: int, limit: int, total: int) -> tuple[int, dict]:
        total_pages = math.ceil(total / limit) if total else 0
        meta = {"page": page, "limit": limit, "total": total, "total_pages": total_pages}
        return 200, {"data": items, "meta": meta, "status_code": 200, "errors": []}

    @staticmethod
    def error(errors, *, status: int = 400) -> tuple[int, dict]:
        return status, {"data": None, "meta": None, "status_code": status, "errors": _norm(errors)}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest blog/tests/test_api_envelope.py -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Lint + commit**

```bash
ruff check .
git add blog/schemas.py blog/api/responses.py blog/tests/test_api_envelope.py
git commit -m "feat(api): add the response envelope schema and builder"
```

---

## Task 3: Exception handlers → 400/404/500 envelopes

**Files:**
- Modify: `blog/api/helpers.py` (add `ApiError`, `register_exception_handlers`, `paginate`)
- Modify: `core/urls.py`
- Test: `blog/tests/test_api_envelope.py` (append)

**Interfaces:**
- Consumes: `blog.api.responses.ApiResponse`.
- Produces: `blog.api.helpers.ApiError(status: int, errors: list[dict])` — attributes `.status`, `.errors`.
- Produces: `blog.api.helpers.register_exception_handlers(api: NinjaAPI) -> None`.
- Produces: `blog.api.helpers.paginate(queryset, page: int, limit: int) -> tuple[list, int]` — returns `(items, total)`.

- [ ] **Step 1: Write the failing test (append to `test_api_envelope.py`)**

```python
import pytest
from django.test import Client

from blog.models import Post, User


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_bad_path_param_returns_400_envelope(client):
    # non-integer post id -> Ninja ValidationError -> our handler
    response = client.get("/api/posts/not-an-int")
    assert response.status_code == 400
    body = response.json()
    assert body["data"] is None
    assert body["status_code"] == 400
    assert body["errors"] and "field" in body["errors"][0]


@pytest.mark.django_db
def test_paginate_helper_slices_and_counts():
    from blog.api.helpers import paginate

    u = User.objects.create(username="p", email="p@e.com", display_name="P")
    for i in range(5):
        Post.objects.create(author=u, title=f"t{i}", body="b")
    items, total = paginate(Post.objects.order_by("id"), page=2, limit=2)
    assert total == 5
    assert len(items) == 2
```

- [ ] **Step 2: Run it — verify failure**

Run: `uv run pytest blog/tests/test_api_envelope.py -q`
Expected: `test_bad_path_param_returns_400_envelope` FAILS (Ninja returns 422, not 400); `test_paginate_helper_slices_and_counts` FAILS (`ImportError: paginate`).

- [ ] **Step 3: Extend `blog/api/helpers.py`**

Add these imports at the top: `from ninja import NinjaAPI` and `from ninja.errors import ValidationError`, plus `from blog.api.responses import ApiResponse`. Append:

```python
class ApiError(Exception):
    def __init__(self, status: int, errors: list[dict]):
        self.status = status
        self.errors = errors
        super().__init__(f"{status}: {errors}")


def paginate(queryset, page: int, limit: int) -> tuple[list, int]:
    total = queryset.count()
    start = (page - 1) * limit
    return list(queryset[start : start + limit]), total


def register_exception_handlers(api: NinjaAPI) -> None:
    @api.exception_handler(ValidationError)
    def _on_validation_error(request, exc):
        errors = [
            {
                "field": str(e["loc"][-1]) if e.get("loc") else None,
                "message": e["msg"],
            }
            for e in exc.errors
        ]
        status, body = ApiResponse.error(errors, status=400)
        return api.create_response(request, body, status=status)

    @api.exception_handler(ApiError)
    def _on_api_error(request, exc):
        status, body = ApiResponse.error(exc.errors, status=exc.status)
        return api.create_response(request, body, status=status)
```

Note: we do **not** register a catch-all `Exception` handler — Ninja's default (traceback page when `DEBUG=True`, plain 500 otherwise) is acceptable and keeps debugging sane. The spec's optional 500 envelope is deferred.

- [ ] **Step 4: Wire it into `core/urls.py`**

Modify:

```python
from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

from blog.api import router as blog_router
from blog.api.helpers import register_exception_handlers

api = NinjaAPI()
api.add_router("/", blog_router)
register_exception_handlers(api)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
```

- [ ] **Step 5: Run tests — verify pass**

Run: `uv run pytest blog/tests/test_api_envelope.py -q`
Expected: PASS. Then `uv run pytest -q` — the 3 original tests still pass (they don't touch error paths).

- [ ] **Step 6: Lint + commit**

```bash
ruff check .
git add blog/api/helpers.py core/urls.py blog/tests/test_api_envelope.py
git commit -m "feat(api): reshape validation and app errors into the envelope"
```

---

## Task 4: `GET /posts` — filters, sort, pagination, envelope

Deletes `GET /posts/search` and `GET /posts/by-tag/{slug}`.

**Files:**
- Modify: `blog/schemas.py` (add `SortOrder`, `PostFilters`)
- Modify: `blog/api/posts.py`
- Test: `blog/tests/test_posts.py`

**Interfaces:**
- Consumes: `ApiResponse.paginated`, `helpers.paginate`, `helpers.ApiError`.
- Produces: `blog.schemas.SortOrder` (`asc` / `desc`), `blog.schemas.PostFilters`.
- Produces: `GET /api/posts?published=&sort=&query=&slug=&page=&limit=` → `Envelope[list[PostListOut]]`.

- [ ] **Step 1: Write the failing tests — replace `test_list_posts_returns_published` and add cases**

`blog/tests/test_posts.py` (full new content):

```python
import pytest
from django.test import Client

from blog.models import Post, Tag, User


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user(db):
    return User.objects.create(
        username="alice",
        email="alice@example.com",
        display_name="Alice",
    )


def _titles(response):
    return [p["title"] for p in response.json()["data"]]


@pytest.mark.django_db
def test_list_posts_returns_published_by_default(client, user):
    tag = Tag.objects.create(name="Python", slug="python")
    post = Post.objects.create(author=user, title="Hello", body="World")
    post.tags.add(tag)
    Post.objects.create(author=user, title="Draft", body="...", is_published=False)

    response = client.get("/api/posts")

    assert response.status_code == 200
    body = response.json()
    assert body["status_code"] == 200
    assert "Hello" in _titles(response)
    # default returns published only? No — see spec: omitted = all. Draft IS included.
    assert "Draft" in _titles(response)
    assert body["meta"]["page"] == 1
    assert body["meta"]["limit"] == 20
    assert body["meta"]["total"] == 2


@pytest.mark.django_db
def test_published_filter(client, user):
    Post.objects.create(author=user, title="Live", body="x")
    Post.objects.create(author=user, title="Draft", body="x", is_published=False)

    assert _titles(client.get("/api/posts?published=true")) == ["Live"]
    assert _titles(client.get("/api/posts?published=false")) == ["Draft"]


@pytest.mark.django_db
def test_query_filter_matches_title_or_body(client, user):
    Post.objects.create(author=user, title="Django tips", body="orm")
    Post.objects.create(author=user, title="Cooking", body="about django too")
    Post.objects.create(author=user, title="Unrelated", body="nothing")

    assert sorted(_titles(client.get("/api/posts?query=django"))) == ["Cooking", "Django tips"]


@pytest.mark.django_db
def test_slug_filter_by_tag(client, user):
    tag = Tag.objects.create(name="Python", slug="python")
    tagged = Post.objects.create(author=user, title="Tagged", body="x")
    tagged.tags.add(tag)
    Post.objects.create(author=user, title="Untagged", body="x")

    assert _titles(client.get("/api/posts?slug=python")) == ["Tagged"]


@pytest.mark.django_db
def test_slug_filter_unknown_tag_is_empty_200(client, user):
    Post.objects.create(author=user, title="X", body="x")
    response = client.get("/api/posts?slug=does-not-exist")
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"]["total"] == 0


@pytest.mark.django_db
def test_sort_asc_and_desc(client, user):
    from django.utils import timezone

    old = Post.objects.create(author=user, title="Old", body="x")
    new = Post.objects.create(author=user, title="New", body="x")
    Post.objects.filter(id=old.id).update(created_at=timezone.now() - timezone.timedelta(days=1))

    assert _titles(client.get("/api/posts?sort=asc")) == ["Old", "New"]
    assert _titles(client.get("/api/posts?sort=desc")) == ["New", "Old"]


@pytest.mark.django_db
def test_pagination(client, user):
    for i in range(25):
        Post.objects.create(author=user, title=f"P{i:02d}", body="x")

    response = client.get("/api/posts?sort=asc&page=2&limit=10")
    body = response.json()
    assert [p["title"] for p in body["data"]] == [f"P{i:02d}" for i in range(10, 20)]
    assert body["meta"] == {"page": 2, "limit": 10, "total": 25, "total_pages": 3}


@pytest.mark.django_db
def test_limit_over_max_is_400(client):
    response = client.get("/api/posts?limit=101")
    assert response.status_code == 400
    assert any(e["field"] == "limit" for e in response.json()["errors"])


@pytest.mark.django_db
def test_invalid_sort_is_400(client):
    response = client.get("/api/posts?sort=sideways")
    assert response.status_code == 400


@pytest.mark.django_db
def test_search_and_by_tag_endpoints_are_gone(client):
    assert client.get("/api/posts/search?q=x").status_code == 404
    assert client.get("/api/posts/by-tag/python").status_code == 404
```

- [ ] **Step 2: Run — verify failures**

Run: `uv run pytest blog/tests/test_posts.py -q`
Expected: multiple FAIL (no envelope, filters unrecognised, old endpoints still 200).

- [ ] **Step 3: Add `SortOrder` + `PostFilters` to `blog/schemas.py`**

Add `from enum import Enum` to the imports. Append:

```python
class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class PostFilters(Schema):
    published: bool | None = None
    sort: SortOrder = SortOrder.desc
    query: str | None = None
    slug: str | None = None
```

- [ ] **Step 4: Rewrite `blog/api/posts.py` list section**

Replace the imports and the `list_posts` / `search_posts` / `posts_by_tag` block with:

```python
from django.db.models import Q
from ninja import Query, Router

from blog.api.helpers import ApiError, _serialize_author, _serialize_comment, _serialize_tag, paginate
from blog.api.responses import ApiResponse
from blog.models import Post, Tag, User
from blog.schemas import (
    Envelope,
    PostCreateIn,
    PostDetailOut,
    PostFilters,
    PostListOut,
    SortOrder,
)

router = Router()


def _serialize_post_list(post: Post) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "author": _serialize_author(post.author),
        "tags": [_serialize_tag(t) for t in post.tags.all()],
        "view_count": post.view_count,
        "created_at": post.created_at,
    }


@router.get("/posts", response={200: Envelope[list[PostListOut]], 400: Envelope[None]})
def list_posts(
    request,
    filters: Query[PostFilters],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    qs = Post.objects.select_related("author").prefetch_related("tags")
    if filters.published is not None:
        qs = qs.filter(is_published=filters.published)
    if filters.query:
        qs = qs.filter(Q(title__icontains=filters.query) | Q(body__icontains=filters.query))
    if filters.slug:
        qs = qs.filter(tags__slug=filters.slug)
    qs = qs.order_by("created_at" if filters.sort == SortOrder.asc else "-created_at")

    items, total = paginate(qs, page, limit)
    return ApiResponse.paginated(
        [_serialize_post_list(p) for p in items], page=page, limit=limit, total=total
    )
```

Delete `search_posts` and `posts_by_tag` entirely. Remove now-unused imports (`get_object_or_404` is still used by `get_post`/`create_post` for now — keep it until Task 5/6).

- [ ] **Step 5: Run tests — verify pass**

Run: `uv run pytest blog/tests/test_posts.py -q`
Expected: the list/filter/pagination tests PASS. `test_get_post_returns_detail` still uses the old bare shape and will FAIL — that is fixed in Task 5. Leave it for now.

- [ ] **Step 6: Lint + commit**

```bash
ruff check .
git add blog/schemas.py blog/api/posts.py blog/tests/test_posts.py
git commit -m "feat(api): filter, sort and paginate GET /posts; drop search and by-tag"
```

---

## Task 5: `GET /posts/{post_id}` — expand + envelope + safe view bump

**Files:**
- Modify: `blog/schemas.py` (add `Expandable`)
- Modify: `blog/api/posts.py` (`get_post`)
- Test: `blog/tests/test_posts.py` (append)

**Interfaces:**
- Produces: `blog.schemas.Expandable` (`comments`).
- Produces: `GET /api/posts/{post_id}?expand=comments` → `Envelope[PostDetailOut]`; 404 → `Envelope[None]`.
- Produces: `blog.api.posts._serialize_post_detail(post, comments: list) -> dict`.

- [ ] **Step 1: Append failing tests to `blog/tests/test_posts.py`**

```python
@pytest.mark.django_db
def test_get_post_detail_envelope_no_comments_by_default(client, user):
    from blog.models import Comment

    post = Post.objects.create(author=user, title="Hello", body="World")
    Comment.objects.create(post=post, author=user, body="hi")

    response = client.get(f"/api/posts/{post.id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["title"] == "Hello"
    assert data["author"]["username"] == "alice"
    assert data["comments"] == []


@pytest.mark.django_db
def test_get_post_expand_comments(client, user):
    from blog.models import Comment

    post = Post.objects.create(author=user, title="Hello", body="World")
    Comment.objects.create(post=post, author=user, body="hi")

    response = client.get(f"/api/posts/{post.id}?expand=comments")

    data = response.json()["data"]
    assert [c["body"] for c in data["comments"]] == ["hi"]


@pytest.mark.django_db
def test_get_post_invalid_expand_is_400(client, user):
    post = Post.objects.create(author=user, title="Hello", body="World")
    assert client.get(f"/api/posts/{post.id}?expand=nope").status_code == 400


@pytest.mark.django_db
def test_get_post_missing_is_404_envelope(client):
    response = client.get("/api/posts/999999")
    assert response.status_code == 404
    body = response.json()
    assert body["data"] is None
    assert body["errors"][0]["field"] == "post_id"


@pytest.mark.django_db
def test_get_post_increments_view_count(client, user):
    post = Post.objects.create(author=user, title="Hello", body="World")
    client.get(f"/api/posts/{post.id}")
    post.refresh_from_db()
    assert post.view_count == 1
```

Also delete the old `test_get_post_returns_detail` (replaced by `test_get_post_detail_envelope_no_comments_by_default`).

- [ ] **Step 2: Run — verify failure**

Run: `uv run pytest blog/tests/test_posts.py -q -k "post_detail or expand or missing_is_404 or view_count"`
Expected: FAIL (bare shape, no `expand` param, 404 not an envelope).

- [ ] **Step 3: Add `Expandable` to `blog/schemas.py`**

```python
class Expandable(str, Enum):
    comments = "comments"
```

- [ ] **Step 4: Rewrite `get_post` in `blog/api/posts.py`**

Add `Expandable` to the `blog.schemas` import. Replace `get_post`:

```python
def _serialize_post_detail(post: Post, comments: list) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "body": post.body,
        "author": _serialize_author(post.author),
        "tags": [_serialize_tag(t) for t in post.tags.all()],
        "comments": comments,
        "view_count": post.view_count,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }


@router.get("/posts/{post_id}", response={200: Envelope[PostDetailOut], 404: Envelope[None]})
def get_post(request, post_id: int, expand: list[Expandable] = Query([])):
    post = (
        Post.objects.select_related("author")
        .prefetch_related("tags")
        .filter(id=post_id)
        .first()
    )
    if post is None:
        raise ApiError(404, [{"field": "post_id", "message": f"No post with id {post_id}"}])

    post.view_count += 1
    post.save(update_fields=["view_count"])

    comments = []
    if Expandable.comments in expand:
        comments = [
            _serialize_comment(c)
            for c in post.comments.select_related("author").order_by("created_at")
        ]
    return ApiResponse.success(_serialize_post_detail(post, comments))
```

- [ ] **Step 5: Run tests — verify pass**

Run: `uv run pytest blog/tests/test_posts.py -q`
Expected: all PASS except `create_post`-related (untouched — still old shape, but there is no create test yet, so suite is green). Run `uv run pytest -q` — `test_comments.py` still green (unchanged behavior).

- [ ] **Step 6: Lint + commit**

```bash
ruff check .
git add blog/schemas.py blog/api/posts.py blog/tests/test_posts.py
git commit -m "feat(api): add expand param and update_fields view bump to GET /posts/{id}"
```

---

## Task 6: `POST /posts` — sanitize, validate, envelope

**Files:**
- Modify: `pyproject.toml` (via `uv add nh3`)
- Modify: `blog/schemas.py` (`PostCreateIn` validators)
- Modify: `blog/api/posts.py` (`create_post`)
- Test: `blog/tests/test_posts.py` (append)

**Interfaces:**
- Consumes: `nh3`, `helpers.ApiError`, `ApiResponse.success`, `_serialize_post_detail`.
- Produces: `POST /api/posts` → `201 Envelope[PostDetailOut]` (`comments: []`); `400 Envelope[None]` with per-field errors.

- [ ] **Step 1: Add the dependency**

Run: `uv add nh3`
Expected: `nh3` appears in `[project].dependencies` in `pyproject.toml`, `uv.lock` updated.
Verify: `uv run python -c "import nh3; print(nh3.clean('<script>x</script><b>hi</b>'))"` → prints `hi` (or ` hi `).

- [ ] **Step 2: Write the failing tests (append to `blog/tests/test_posts.py`)**

```python
import json


def _post(client, payload):
    return client.post(
        "/api/posts", data=json.dumps(payload), content_type="application/json"
    )


@pytest.mark.django_db
def test_create_post_success_returns_201_detail_shape(client, user):
    Tag.objects.create(name="Python", slug="python")
    response = _post(
        client,
        {"author_id": user.id, "title": "  Hi  ", "body": "Body text", "tag_slugs": ["python"]},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["title"] == "Hi"  # stripped
    assert data["comments"] == []
    assert [t["slug"] for t in data["tags"]] == ["python"]
    assert Post.objects.filter(title="Hi").exists()


@pytest.mark.django_db
def test_create_post_strips_html(client, user):
    response = _post(
        client,
        {"author_id": user.id, "title": "<b>Bold</b>", "body": "<script>evil()</script>safe"},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["title"] == "Bold"
    assert "<script>" not in data["body"] and "safe" in data["body"]


@pytest.mark.django_db
def test_create_post_empty_title_is_400(client, user):
    response = _post(client, {"author_id": user.id, "title": "   ", "body": "x"})
    assert response.status_code == 400
    assert any(e["field"] == "title" for e in response.json()["errors"])


@pytest.mark.django_db
def test_create_post_unknown_author_and_tag_reports_both(client):
    response = _post(
        client,
        {"author_id": 999999, "title": "T", "body": "B", "tag_slugs": ["ghost"]},
    )
    assert response.status_code == 400
    fields = {e["field"] for e in response.json()["errors"]}
    assert fields == {"author_id", "tag_slugs"}
    assert Post.objects.count() == 0


@pytest.mark.django_db
def test_create_post_invalid_slug_format_is_400(client, user):
    response = _post(
        client, {"author_id": user.id, "title": "T", "body": "B", "tag_slugs": ["Bad Slug!"]}
    )
    assert response.status_code == 400
    assert any(e["field"] == "tag_slugs" for e in response.json()["errors"])
```

- [ ] **Step 3: Run — verify failure**

Run: `uv run pytest blog/tests/test_posts.py -q -k create_post`
Expected: FAIL (old handler returns 200 + `{id,title}`, no validation, unknown tag → 500).

- [ ] **Step 4: Add validators to `PostCreateIn` in `blog/schemas.py`**

Add imports: `import re` and `from pydantic import field_validator`. Replace `PostCreateIn`:

```python
class PostCreateIn(Schema):
    author_id: int
    title: str
    body: str
    tag_slugs: list[str] = []

    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        import nh3

        v = nh3.clean(v.strip(), tags=set()).strip()
        if not v:
            raise ValueError("title must not be empty")
        if len(v) > 255:
            raise ValueError("title must be at most 255 characters")
        return v

    @field_validator("body")
    @classmethod
    def _clean_body(cls, v: str) -> str:
        import nh3

        v = nh3.clean(v.strip()).strip()
        if not v:
            raise ValueError("body must not be empty")
        return v

    @field_validator("tag_slugs")
    @classmethod
    def _clean_slugs(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in v:
            s = raw.strip().lower()
            if not re.fullmatch(r"[a-z0-9-]+", s):
                raise ValueError(f"invalid tag slug: {raw!r}")
            if s not in out:
                out.append(s)
        return out
```

(`import nh3` inside the validator keeps the module import cost off schema import; a top-level `import nh3` is equally fine — move it up if ruff `PLC0415`-style rules are added later. Current ruleset does not flag it.)

- [ ] **Step 5: Rewrite `create_post` in `blog/api/posts.py`**

Add `from django.db import transaction` to imports. Replace `create_post`:

```python
@router.post("/posts", response={201: Envelope[PostDetailOut], 400: Envelope[None]})
def create_post(request, payload: PostCreateIn):
    with transaction.atomic():
        errors: list[dict] = []

        author = User.objects.filter(id=payload.author_id).first()
        if author is None:
            errors.append(
                {"field": "author_id", "message": f"No user with id {payload.author_id}"}
            )

        found = list(Tag.objects.filter(slug__in=payload.tag_slugs))
        missing = [s for s in payload.tag_slugs if s not in {t.slug for t in found}]
        if missing:
            errors.append(
                {"field": "tag_slugs", "message": f"unknown slugs: {', '.join(missing)}"}
            )

        if errors:
            raise ApiError(400, errors)

        post = Post.objects.create(
            author=author, title=payload.title, body=payload.body
        )
        post.tags.set(found)

    return ApiResponse.success(_serialize_post_detail(post, []), status=201)
```

`get_object_or_404` is now unused in `posts.py` — remove the import.

- [ ] **Step 6: Run tests — verify pass**

Run: `uv run pytest blog/tests/test_posts.py -q`
Expected: all PASS.

- [ ] **Step 7: Lint + commit**

```bash
ruff check .
git add pyproject.toml uv.lock blog/schemas.py blog/api/posts.py blog/tests/test_posts.py
git commit -m "feat(api): sanitize and validate POST /posts"
```

---

## Task 7: Comments + users envelopes; delete `GET /users/find`

**Files:**
- Modify: `blog/schemas.py` (`CommentCreateIn` validator; `CommentOut` reused for response)
- Modify: `blog/api/comments.py`
- Modify: `blog/api/users.py`
- Test: `blog/tests/test_comments.py`, `blog/tests/test_posts.py` (append a users test) or new `blog/tests/test_users.py`

**Interfaces:**
- Produces: `POST /api/posts/{post_id}/comments` → `201 Envelope[CommentOut]`; `400` / `404` → `Envelope[None]`.
- Produces: `GET /api/users/{user_id}` → `200 Envelope[UserDetailOut]`; `404` → `Envelope[None]`.
- Removes: `GET /api/users/find`.

- [ ] **Step 1: Rewrite `blog/tests/test_comments.py`**

```python
import json

import pytest
from django.test import Client

from blog.models import Comment, Post, User


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user(db):
    return User.objects.create(username="bob", email="bob@example.com", display_name="Bob")


@pytest.mark.django_db
def test_create_comment_returns_201_envelope(client, user):
    post = Post.objects.create(author=user, title="T", body="B")

    response = client.post(
        f"/api/posts/{post.id}/comments",
        data=json.dumps({"author_id": user.id, "body": "Nice post!"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["body"] == "Nice post!"
    assert data["author"]["username"] == "bob"
    assert Comment.objects.filter(post=post, body="Nice post!").exists()


@pytest.mark.django_db
def test_create_comment_strips_html(client, user):
    post = Post.objects.create(author=user, title="T", body="B")
    response = client.post(
        f"/api/posts/{post.id}/comments",
        data=json.dumps({"author_id": user.id, "body": "<script>x</script>ok"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert "<script>" not in response.json()["data"]["body"]


@pytest.mark.django_db
def test_create_comment_missing_post_is_404(client, user):
    response = client.post(
        "/api/posts/999999/comments",
        data=json.dumps({"author_id": user.id, "body": "hi"}),
        content_type="application/json",
    )
    assert response.status_code == 404
    assert response.json()["errors"][0]["field"] == "post_id"


@pytest.mark.django_db
def test_create_comment_missing_author_is_400(client, user):
    post = Post.objects.create(author=user, title="T", body="B")
    response = client.post(
        f"/api/posts/{post.id}/comments",
        data=json.dumps({"author_id": 999999, "body": "hi"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["errors"][0]["field"] == "author_id"


@pytest.mark.django_db
def test_create_comment_empty_body_is_400(client, user):
    post = Post.objects.create(author=user, title="T", body="B")
    response = client.post(
        f"/api/posts/{post.id}/comments",
        data=json.dumps({"author_id": user.id, "body": "   "}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert any(e["field"] == "body" for e in response.json()["errors"])
```

- [ ] **Step 2: Create `blog/tests/test_users.py`**

```python
import pytest
from django.test import Client

from blog.models import User


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_get_user_envelope(client):
    u = User.objects.create(username="cara", email="cara@e.com", display_name="Cara")
    response = client.get(f"/api/users/{u.id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["username"] == "cara"
    assert data["post_count"] == 0


@pytest.mark.django_db
def test_get_user_missing_is_404_envelope(client):
    response = client.get("/api/users/999999")
    assert response.status_code == 404
    assert response.json()["errors"][0]["field"] == "user_id"


@pytest.mark.django_db
def test_users_find_is_gone(client):
    response = client.get("/api/users/find?email=cara@e.com")
    assert response.status_code == 404
```

- [ ] **Step 3: Run — verify failure**

Run: `uv run pytest blog/tests/test_comments.py blog/tests/test_users.py -q`
Expected: FAIL (bare `{id}` at 200; `/users/find` still 200; 404s not envelopes).

- [ ] **Step 4: Add the `CommentCreateIn` validator in `blog/schemas.py`**

```python
class CommentCreateIn(Schema):
    author_id: int
    body: str

    @field_validator("body")
    @classmethod
    def _clean_body(cls, v: str) -> str:
        import nh3

        v = nh3.clean(v.strip()).strip()
        if not v:
            raise ValueError("body must not be empty")
        return v
```

- [ ] **Step 5: Rewrite `blog/api/comments.py`**

```python
from ninja import Router

from blog.api.helpers import ApiError, _serialize_comment
from blog.api.responses import ApiResponse
from blog.models import Comment, Post, User
from blog.schemas import CommentCreateIn, CommentOut, Envelope

router = Router()


@router.post(
    "/posts/{post_id}/comments",
    response={201: Envelope[CommentOut], 400: Envelope[None], 404: Envelope[None]},
)
def create_comment(request, post_id: int, payload: CommentCreateIn):
    post = Post.objects.filter(id=post_id).first()
    if post is None:
        raise ApiError(404, [{"field": "post_id", "message": f"No post with id {post_id}"}])

    author = User.objects.filter(id=payload.author_id).first()
    if author is None:
        raise ApiError(
            400, [{"field": "author_id", "message": f"No user with id {payload.author_id}"}]
        )

    comment = Comment.objects.create(post=post, author=author, body=payload.body)
    return ApiResponse.success(_serialize_comment(comment), status=201)
```

- [ ] **Step 6: Rewrite `blog/api/users.py`**

```python
from ninja import Router

from blog.api.helpers import ApiError
from blog.api.responses import ApiResponse
from blog.models import User
from blog.schemas import Envelope, UserDetailOut

router = Router()


def _user_detail(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "bio": user.bio,
        "post_count": user.posts.count(),
        "comment_count": user.comments.count(),
    }


@router.get("/users/{user_id}", response={200: Envelope[UserDetailOut], 404: Envelope[None]})
def get_user(request, user_id: int):
    user = User.objects.filter(id=user_id).first()
    if user is None:
        raise ApiError(404, [{"field": "user_id", "message": f"No user with id {user_id}"}])
    return ApiResponse.success(_user_detail(user))
```

- [ ] **Step 7: Run the whole suite — verify pass**

Run: `ruff check . && uv run pytest -q`
Expected: lint clean; every test passes.

- [ ] **Step 8: Commit**

```bash
git add blog/schemas.py blog/api/comments.py blog/api/users.py blog/tests/test_comments.py blog/tests/test_users.py
git commit -m "feat(api): envelope comments and users; remove GET /users/find"
```

---

## Task 8: HTTP request files for editor plugins

Runnable `.http` files covering every scenario, for the JetBrains HTTP Client (built into
IntelliJ/PyCharm) and the VS Code "REST Client" extension — both read the same syntax.
Do this task **after** Tasks 4–7 so the requests match the final routes.

**Files:**
- Create: `requests/http-client.env.json`, `requests/posts.http`, `requests/comments.http`, `requests/users.http`, `requests/README.md`

- [ ] **Step 1: Create `requests/http-client.env.json`**

```json
{
  "local": {
    "baseUrl": "http://localhost:8000/api"
  }
}
```

- [ ] **Step 2: Create `requests/posts.http`**

```http
### List posts — defaults (page 1, limit 20, newest first, all publish states)
GET {{baseUrl}}/posts

### List posts — published only
GET {{baseUrl}}/posts?published=true

### List posts — drafts only
GET {{baseUrl}}/posts?published=false

### List posts — text search across title and body
GET {{baseUrl}}/posts?query=django

### List posts — by tag slug (unknown slug returns an empty list, still 200)
GET {{baseUrl}}/posts?slug=python

### List posts — oldest first
GET {{baseUrl}}/posts?sort=asc

### List posts — page 2, 50 per page
GET {{baseUrl}}/posts?page=2&limit=50

### List posts — combined filters
GET {{baseUrl}}/posts?published=true&query=django&sort=desc&page=1&limit=10

### List posts — limit over the max => 400 with a `limit` error
GET {{baseUrl}}/posts?limit=101

### List posts — invalid sort value => 400
GET {{baseUrl}}/posts?sort=sideways

### Post detail — no comments by default
GET {{baseUrl}}/posts/1

### Post detail — expand comments
GET {{baseUrl}}/posts/1?expand=comments

### Post detail — invalid expand value => 400
GET {{baseUrl}}/posts/1?expand=nope

### Post detail — unknown id => 404 envelope
GET {{baseUrl}}/posts/999999

### Create post — success => 201, returns the post in detail shape
POST {{baseUrl}}/posts
Content-Type: application/json

{
  "author_id": 1,
  "title": "A brand new post",
  "body": "Body text goes here.",
  "tag_slugs": ["python"]
}

### Create post — HTML in title/body is stripped
POST {{baseUrl}}/posts
Content-Type: application/json

{
  "author_id": 1,
  "title": "<b>Bold</b> title",
  "body": "<script>alert(1)</script>Safe body"
}

### Create post — empty title => 400
POST {{baseUrl}}/posts
Content-Type: application/json

{ "author_id": 1, "title": "   ", "body": "x" }

### Create post — unknown author and unknown tag => 400 listing both
POST {{baseUrl}}/posts
Content-Type: application/json

{ "author_id": 999999, "title": "T", "body": "B", "tag_slugs": ["ghost"] }

### Removed — search is folded into ?query= (expect 404)
GET {{baseUrl}}/posts/search?q=django

### Removed — by-tag is folded into ?slug= (expect 404)
GET {{baseUrl}}/posts/by-tag/python
```

- [ ] **Step 3: Create `requests/comments.http`**

```http
### Add a comment — success => 201, returns the comment
POST {{baseUrl}}/posts/1/comments
Content-Type: application/json

{ "author_id": 1, "body": "Great post!" }

### Add a comment — HTML in body is stripped
POST {{baseUrl}}/posts/1/comments
Content-Type: application/json

{ "author_id": 1, "body": "<script>x</script>still fine" }

### Add a comment — unknown post => 404 envelope
POST {{baseUrl}}/posts/999999/comments
Content-Type: application/json

{ "author_id": 1, "body": "hi" }

### Add a comment — unknown author => 400 envelope
POST {{baseUrl}}/posts/1/comments
Content-Type: application/json

{ "author_id": 999999, "body": "hi" }

### Add a comment — empty body => 400
POST {{baseUrl}}/posts/1/comments
Content-Type: application/json

{ "author_id": 1, "body": "   " }
```

- [ ] **Step 4: Create `requests/users.http`**

```http
### User profile — success
GET {{baseUrl}}/users/1

### User profile — unknown id => 404 envelope
GET {{baseUrl}}/users/999999

### Removed — lookup by email was deleted (privacy / enumeration). Expect 404.
GET {{baseUrl}}/users/find?email=alice@example.com
```

- [ ] **Step 5: Create `requests/README.md`**

```markdown
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
```

- [ ] **Step 6: Sanity-check against a running server (optional but recommended)**

```bash
uv run python manage.py runserver &
# in the editor, run a GET and a 400 case, confirm the envelope shape
```

- [ ] **Step 7: Commit**

```bash
git add requests
git commit -m "docs(api): add .http request files covering every endpoint scenario"
```

---

## Task 9: Docs — README + NOTES

**Files:**
- Modify: `README.md`
- Modify: `NOTES.md`

- [ ] **Step 1: Update the README API table**

Replace the "What the API does" table with:

```markdown
All responses share one envelope: `{ "data": …, "meta": … | null, "status_code": …, "errors": [ { "field", "message" } ] }`.
`meta` carries `page`, `limit`, `total`, `total_pages` on list endpoints.

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET    | `/api/posts` | List posts. Query params: `published` (`true`/`false`/omit=all), `sort` (`asc`/`desc` on `created_at`), `query` (matches title or body), `slug` (posts carrying that tag slug), `page` (≥1), `limit` (1–100, default 20). |
| GET    | `/api/posts/{id}` | Post detail. `expand=comments` to include comments (omitted → `[]`). |
| POST   | `/api/posts` | Create a post. Title/body are HTML-sanitised; unknown `author_id` or `tag_slugs` → 400. Returns 201 with the post in detail shape. |
| POST   | `/api/posts/{id}/comments` | Add a comment. Returns 201 with the comment. |
| GET    | `/api/users/{id}` | User profile with post and comment counts. |
```

Also update the prose line under "What the API does" if it references the old `/posts/search` etc. Confirm `/api/docs` still described. Add one line pointing at the request files:

```markdown
Ready-to-run requests for every scenario live in `requests/*.http` (JetBrains HTTP
Client or the VS Code REST Client extension) — see `requests/README.md`.
```

- [ ] **Step 2: Update `NOTES.md`**

Append under "What I fixed and why" (keep the terse first-person logbook voice), e.g.:

```markdown
* `blog/api.py` split into a `blog/api/` package: `posts`, `comments`, `users`, plus
  `responses.py` (envelope builder) and `helpers.py` (exception handlers, pagination,
  shared serializers). One file per entity, thin views, no service layer yet.
* Every endpoint now returns `{data, meta, status_code, errors}`. Ninja `ValidationError`
  and a small `ApiError` are reshaped into that envelope (400 / 404); `/api/docs` shows
  the wrapped shape via a generic `Envelope[T]` response schema.
* `GET /posts` takes `published`, `sort`, `query`, `slug`, `page`, `limit` (max 100),
  all validated. `select_related`/`prefetch_related` kill the author+tags N+1. Deleted
  `/posts/search` and `/posts/by-tag/{slug}` — folded into the filters.
* `GET /posts/{id}` gained `expand=comments`; comments are skipped unless asked for.
  `view_count` bump uses `update_fields=["view_count"]`.
* `POST /posts` sanitises title/body with `nh3`, validates author + tag slugs up front,
  returns 400 listing every bad value, 201 with the created post otherwise.
* Deleted `GET /users/find` — unauthenticated lookup by arbitrary email is an
  enumeration / DoS surface with no real use here.
* Added `requests/*.http` — runnable request files (JetBrains HTTP Client / VS Code
  REST Client) with every success and error scenario, so the API is explorable from
  the editor without curl.
```

And under "Things I'll keep out": `* A selector/service layer and a hexagonal layout — the package split is enough for now.`
And under "What I'd do next": `* Race-safe view_count via F("view_count") + 1. Comma-separated expand values. Full-text index for the query filter.`

- [ ] **Step 3: Commit**

```bash
git add README.md NOTES.md
git commit -m "docs: document the reworked API and record it in NOTES"
```

---

## Self-Review

**Spec coverage:**

| Spec item | Task |
| --- | --- |
| Module split, one file per entity, helpers | Task 1 |
| `Envelope[T]` + docs fidelity + `ApiResponse` template | Task 2 |
| `{field, message}` errors, 400 for validation, 404 stays 404 | Task 3 |
| `published` / `sort` / `query` / `slug` filters, typed filter object | Task 4 |
| Pagination `page`/`limit`, max 100, list never 404 | Task 4 |
| Delete `/posts/search`, `/posts/by-tag/{slug}` | Task 4 |
| `expand` enum, comments default `[]` | Task 5 |
| `update_fields=["view_count"]` | Task 5 |
| POST payload sanitisation (nh3) | Task 6 |
| POST create validation, 400 with error list, all-or-nothing | Task 6 |
| `nh3` dependency | Task 6 |
| Envelope on comments + users | Task 7 |
| Delete `/users/find` | Task 7 |
| `.http` files covering every scenario (DX) | Task 8 |
| README + `/api/docs` + NOTES | Task 9 |
| Parameterised queries (ORM kwargs only, no raw SQL) | Tasks 4–7 (by construction) |

No gaps.

**Placeholder scan:** No TBD/TODO. Every code step has real code. Test steps contain full test bodies. The one judgement call left to the implementer (removing an unused import) is called out explicitly with the condition.

**Type consistency:**
- `ApiResponse.success(data, *, status, meta)` / `.paginated(items, *, page, limit, total)` / `.error(errors, *, status)` — defined Task 2, used Tasks 3–7 with matching kwargs.
- `ApiError(status, errors)` with `.status` / `.errors` — defined Task 3, raised Tasks 5–7, caught by the handler in Task 3.
- `paginate(queryset, page, limit) -> (items, total)` — defined Task 3, used Task 4.
- `_serialize_post_detail(post, comments)` — defined Task 5, reused Task 6.
- `_serialize_author` / `_serialize_tag` / `_serialize_comment` — defined Task 1, used throughout.
- `Envelope[T]`, `Meta`, `ErrorItem`, `SortOrder`, `PostFilters`, `Expandable` — all in `blog/schemas.py`, added in the task that first needs them (2, 4, 5).

**Known runtime confirmation:** Ninja 1.6 renders `Envelope[list[PostListOut]]` and `Query[PostFilters]` into OpenAPI correctly — verified during design against the installed version. If a future bump breaks it, fall back to explicit `PostListEnvelope(Envelope)` subclasses per the spec.
