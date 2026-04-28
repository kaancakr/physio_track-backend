from django.urls import path

from apps.core.programs.views import ProgramAdminListView, ProgramDetailView, ProgramListView

urlpatterns = [
    path("", ProgramListView.as_view(), name="program-list"),
    path("all/", ProgramAdminListView.as_view(), name="program-admin-list"),
    path("<slug:id>/", ProgramDetailView.as_view(), name="program-detail"),
]
