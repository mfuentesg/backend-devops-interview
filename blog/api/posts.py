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
