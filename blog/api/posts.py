from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Query, Router

from blog.api.helpers import (
    ApiError,
    _serialize_author,
    _serialize_comment,
    _serialize_tag,
    paginate,
)
from blog.api.responses import ApiResponse
from blog.models import Post, Tag, User
from blog.schemas import (
    Envelope,
    Expandable,
    PostCreateIn,
    PostCreateOut,
    PostDetailOut,
    PostFilters,
    PostListOut,
    SortOrder,
)

router = Router()

# B008: Query(...) must not be called in an argument default; bind it once here.
_EXPAND_QUERY = Query([])


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
def get_post(request, post_id: int, expand: list[Expandable] = _EXPAND_QUERY):
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


@router.post("/posts", response=PostCreateOut)
def create_post(request, payload: PostCreateIn):
    author = get_object_or_404(User, id=payload.author_id)
    post = Post.objects.create(author=author, title=payload.title, body=payload.body)
    for slug in payload.tag_slugs:
        tag = Tag.objects.get(slug=slug)
        post.tags.add(tag)
    return {"id": post.id, "title": post.title}
