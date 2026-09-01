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


@router.get("/users/{int:user_id}", response={200: Envelope[UserDetailOut], 404: Envelope[None]})
def get_user(request, user_id: int):
    user = User.objects.filter(id=user_id).first()
    if user is None:
        raise ApiError(404, [{"field": "user_id", "message": f"No user with id {user_id}"}])
    return ApiResponse.success(_user_detail(user))
