from django.urls import path

from apps.core.programs.views import (
    ProgramAdminListView,
    ProgramCompletionView,
    ProgramDetailView,
    ProgramListView,
)

urlpatterns = [
    path("", ProgramListView.as_view(), name="program-list"),
    path("all/", ProgramAdminListView.as_view(), name="program-admin-list"),
    path("<uuid:id>/complete/", ProgramCompletionView.as_view(), name="program-complete"),
    path("<uuid:id>/", ProgramDetailView.as_view(), name="program-detail"),
]
