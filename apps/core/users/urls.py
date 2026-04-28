from django.urls import path

from apps.core.users.views import CurrentUserView, UserDetailView, UserListView

urlpatterns = [
    path("me/", CurrentUserView.as_view(), name="user-me"),
    path("", UserListView.as_view(), name="user-list"),
    path("<uuid:user_id>/", UserDetailView.as_view(), name="user-detail"),
]
