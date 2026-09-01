from django.db import transaction
from django.db.models import Q
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
    qs = qs.order_by("created_at" if filters.sort == SortOrder.asc else "-created_at", "id")

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


@router.get(
    "/posts/{post_id}",
    response={200: Envelope[PostDetailOut], 400: Envelope[None], 404: Envelope[None]},
)
def get_post(
    request,
    post_id: int,
    expand: list[Expandable] = Query(default_factory=list),  # noqa: B008  django-ninja param marker
):
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

        post = Post.objects.create(author=author, title=payload.title, body=payload.body)
        post.tags.set(found)

    return ApiResponse.success(_serialize_post_detail(post, []), status=201)
