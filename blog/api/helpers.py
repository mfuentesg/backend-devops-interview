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
