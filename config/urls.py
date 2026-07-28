from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from apps.core.openapi import OPENAPI_RENDERER_CLASSES

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "swagger/",
        SpectacularAPIView.as_view(renderer_classes=OPENAPI_RENDERER_CLASSES),
        name="swagger-schema",
    ),
    path("api/", include("apps.core.urls")),
]
