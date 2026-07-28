from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.openapi import OPENAPI_RENDERER_CLASSES
from apps.core.views import HealthCheckView

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path(
        "schema/",
        SpectacularAPIView.as_view(renderer_classes=OPENAPI_RENDERER_CLASSES),
        name="schema",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("auth/", include("apps.core.authentication.urls")),
    path("users/", include("apps.core.users.urls")),
    path("programs/", include("apps.core.programs.urls")),
]
