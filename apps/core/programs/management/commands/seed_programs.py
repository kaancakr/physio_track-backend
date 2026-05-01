from django.core.management.base import BaseCommand

from apps.core.programs.services import upsert_seed_programs


class Command(BaseCommand):
    help = "Seed the default PhysioTrack exercise programs."

    def handle(self, *args, **options):
        created_or_updated_count = upsert_seed_programs()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded or updated {created_or_updated_count} exercise programs."
            )
        )
