import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

# Ambiguous characters (O/0, l/1) left out — these passwords get copy-pasted
# and read aloud.
PASSWORD_ALPHABET = "".join(
    c for c in string.ascii_letters + string.digits + "!@#$%^&*-_" if c not in "Ol01Il"
)


def generate_password(length: int = 20) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


class Command(BaseCommand):
    help = (
        "Set a Django-admin password for a user, creating the user if it does not "
        "exist, and grant the flags admin login requires. Idempotent — re-running "
        "only resets the password. Unlike createsuperuser --noinput, this does not "
        "fail when the account already exists."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="User email (the USERNAME_FIELD).")
        parser.add_argument(
            "--password",
            help="Password to set. Omit to generate a strong one and print it — "
            "preferred, so the secret never lands in shell history.",
        )
        parser.add_argument(
            "--staff-only",
            action="store_true",
            help="Grant is_staff but not is_superuser. The user can log in but sees "
            "nothing until per-model permissions are granted.",
        )

    def handle(self, *args, **opts):
        User = get_user_model()
        email = opts["email"].strip().lower()
        password = opts.get("password")
        generated = password is None
        if generated:
            password = generate_password()

        user, created = User.objects.get_or_create(email=email)

        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError("Password rejected: " + "; ".join(exc.messages)) from exc

        user.set_password(password)
        user.is_active = True
        user.is_staff = True
        user.is_superuser = not opts["staff_only"]
        user.save(update_fields=["password", "is_active", "is_staff", "is_superuser"])

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Updated'} {user.email} "
                f"(is_staff={user.is_staff}, is_superuser={user.is_superuser})"
            )
        )
        if generated:
            self.stdout.write(f"Generated password: {password}")
