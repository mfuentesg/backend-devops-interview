from django.conf import settings
from django.urls import include, path
from ninja import NinjaAPI

from blog.api import router as blog_router
from blog.api.helpers import register_exception_handlers

api = NinjaAPI()
api.add_router("/", blog_router)
register_exception_handlers(api)

urlpatterns = [
    path("api/", api.urls),
    path("", include("django_prometheus.urls")),
]

# Admin is opt-in (ADMIN_ENABLED) and mounted on a configurable, non-default
# path (ADMIN_URL) so the scanned "/admin/" isn't exposed unless asked for.
if settings.ADMIN_ENABLED:
    from django.contrib import admin

    urlpatterns.append(path(settings.ADMIN_URL, admin.site.urls))
