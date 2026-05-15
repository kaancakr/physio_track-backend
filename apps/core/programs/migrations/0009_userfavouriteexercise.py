from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("programs", "0008_exercisestepcompletion_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserFavouriteExercise",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("suggested_days_per_week", models.PositiveSmallIntegerField()),
                ("current_streak_days", models.PositiveIntegerField(default=0)),
                ("longest_streak_days", models.PositiveIntegerField(default=0)),
                ("last_completed_on", models.DateField(blank=True, null=True)),
                (
                    "exercise",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_favourite_exercises",
                        to="programs.exercise",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favourite_exercises",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["user_id", "exercise_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="userfavouriteexercise",
            constraint=models.UniqueConstraint(
                fields=("user", "exercise"),
                name="unique_user_favourite_exercise",
            ),
        ),
    ]
