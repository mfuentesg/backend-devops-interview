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
