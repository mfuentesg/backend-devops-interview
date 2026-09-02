import html
import re
from datetime import datetime
from enum import StrEnum

import nh3
from ninja import Schema
from pydantic import field_validator


def _sanitize_text(value: str) -> str:
    """Reduce a free-text field to inert plain text.

    Unescape first so a pre-encoded payload (``&lt;script&gt;``) is exposed as
    real markup, strip every tag, then unescape again to undo nh3's
    re-encoding of bare ``&``/``<``/``>`` in ordinary prose.
    """
    return html.unescape(nh3.clean(html.unescape(value.strip()), tags=set())).strip()


class AuthorOut(Schema):
    id: int
    username: str
    display_name: str


class TagOut(Schema):
    id: int
    name: str
    slug: str


class PostListOut(Schema):
    id: int
    title: str
    author: AuthorOut
    tags: list[TagOut]
    view_count: int
    created_at: datetime


class CommentOut(Schema):
    id: int
    author: AuthorOut
    body: str
    created_at: datetime


class PostDetailOut(Schema):
    id: int
    title: str
    body: str
    author: AuthorOut
    tags: list[TagOut]
    comments: list[CommentOut]
    view_count: int
    created_at: datetime
    updated_at: datetime


class UserDetailOut(Schema):
    id: int
    username: str
    display_name: str
    email: str
    bio: str
    post_count: int
    comment_count: int


class PostCreateIn(Schema):
    author_id: int
    title: str
    body: str
    tag_slugs: list[str] = []

    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        v = _sanitize_text(v)
        if not v:
            raise ValueError("title must not be empty")
        if len(v) > 255:
            raise ValueError("title must be at most 255 characters")
        return v

    @field_validator("body")
    @classmethod
    def _clean_body(cls, v: str) -> str:
        v = _sanitize_text(v)
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


class CommentCreateIn(Schema):
    author_id: int
    body: str

    @field_validator("body")
    @classmethod
    def _clean_body(cls, v: str) -> str:
        v = _sanitize_text(v)
        if not v:
            raise ValueError("body must not be empty")
        return v


class ErrorItem(Schema):
    field: str | None = None
    message: str


class Meta(Schema):
    page: int
    limit: int
    total: int
    total_pages: int


class Envelope[T](Schema):
    data: T | None = None
    meta: Meta | None = None
    status_code: int
    errors: list[ErrorItem] = []


class SortOrder(StrEnum):
    asc = "asc"
    desc = "desc"


class PostFilters(Schema):
    published: bool | None = None
    sort: SortOrder = SortOrder.desc
    query: str | None = None
    slug: str | None = None


class Expandable(StrEnum):
    comments = "comments"
