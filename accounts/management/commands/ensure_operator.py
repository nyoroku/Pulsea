import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the configured Pulsea operator account."

    def handle(self, *args, **options):
        username = os.environ.get("PULSEA_OPERATOR_USERNAME")
        password = os.environ.get("PULSEA_OPERATOR_PASSWORD")
        if not username or not password:
            self.stdout.write("Pulsea operator bootstrap skipped.")
            return

        User = get_user_model()
        user, created = User.objects.update_or_create(
            username=username,
            defaults={
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user.set_password(password)
        user.save(update_fields=["password", "is_active", "is_staff", "is_superuser"])
        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Pulsea operator {action}: {username}"))
