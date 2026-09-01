from ninja import Router

from blog.api.comments import router as comments_router
from blog.api.posts import router as posts_router
from blog.api.users import router as users_router

router = Router()
router.add_router("", posts_router)
router.add_router("", comments_router)
router.add_router("", users_router)
