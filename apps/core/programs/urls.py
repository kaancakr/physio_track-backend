from django.urls import path

from apps.core.programs.views import (
    ExerciseStepCompletionView,
    ProgramAdminListView,
    ProgramExerciseDetailView,
    ProgramExerciseListView,
    ProgramListView,
)

urlpatterns = [
    path("", ProgramListView.as_view(), name="program-list"),
    path("all/", ProgramAdminListView.as_view(), name="program-admin-list"),
    path("<uuid:id>/exercises/", ProgramExerciseListView.as_view(), name="program-exercise-list"),
    path(
        "<uuid:id>/exercises/<uuid:exercise_id>/",
        ProgramExerciseDetailView.as_view(),
        name="program-exercise-detail",
    ),
    path(
        "<uuid:id>/exercises/<uuid:exercise_id>/steps/<int:step_index>/complete/",
        ExerciseStepCompletionView.as_view(),
        name="exercise-step-complete",
    ),
]
