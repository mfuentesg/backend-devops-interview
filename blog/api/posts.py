from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Query, Router

from blog.api.helpers import _serialize_author, _serialize_comment, _serialize_tag, paginate
from blog.api.responses import ApiResponse
from blog.models import Post, Tag, User
from blog.schemas import (
    Envelope,
    PostCreateIn,
    PostCreateOut,
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
