from ninja import NinjaAPI
from ninja.errors import ValidationError

from blog.api.responses import ApiResponse
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
