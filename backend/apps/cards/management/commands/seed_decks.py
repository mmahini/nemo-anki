from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.cards.seeding import seed_for_user


class Command(BaseCommand):
    help = "Seed Menschen + Oxford Word Skills deck trees and sample cards."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            help="Seed only this user. If omitted, seeds every existing user "
            "(creating a demo user if none exist).",
        )

    def handle(self, *args, **opts):
        User = get_user_model()
        email = opts.get("email")
        if email:
            user, _ = User.objects.get_or_create(email=email.lower())
            users = [user]
        else:
            users = list(User.objects.all())
            if not users:
                users = [User.objects.create_user(email="demo@nemo-anki.local")]

        for user in users:
            result = seed_for_user(user)
            self.stdout.write(self.style.SUCCESS(f"Seeded {user.email}: {result['decks']} decks"))
