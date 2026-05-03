from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0003_user_token_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("male", "Male"),
                    ("female", "Female"),
                    ("prefer_not_to_say", "Prefer not to say"),
                ],
                max_length=32,
            ),
        ),
    ]
