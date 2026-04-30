from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class VersionedJWTScheme(SimpleJWTScheme):
    target_class = "apps.core.authentication.jwt_authentication.VersionedJWTAuthentication"
