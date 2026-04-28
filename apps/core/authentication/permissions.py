from rest_framework.permissions import BasePermission


class IsUnauthenticated(BasePermission):
    message = "This endpoint is only available to unauthenticated clients."

    def has_permission(self, request, view) -> bool:
        return not request.user.is_authenticated
