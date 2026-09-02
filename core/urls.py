from django.contrib import admin
from django.urls import include, path
from ninja import NinjaAPI

from blog.api import router as blog_router
from blog.api.helpers import register_exception_handlers

api = NinjaAPI()
api.add_router("/", blog_router)
register_exception_handlers(api)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("", include("django_prometheus.urls")),
]
