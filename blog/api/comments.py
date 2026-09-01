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
