import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


OTP_LENGTH = 5
OTP_TTL = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5

# No 0/O/1/l/i — referral codes get read aloud and retyped from chat apps.
REFERRAL_CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
REFERRAL_CODE_LENGTH = 8


def generate_referral_code() -> str:
    return "".join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(REFERRAL_CODE_LENGTH))


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields["is_staff"] is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields["is_superuser"] is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    UI_LANGUAGE_CHOICES = [("en", "English"), ("fa", "Persian")]

    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=80, blank=True, default="")
    ui_language = models.CharField(max_length=4, choices=UI_LANGUAGE_CHOICES, default="en")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    # Per-user feature flags — a list of capability strings (see
    # accounts.feature_flags). Editable in the Django admin; gate features with
    # `user.has_flag(...)` rather than reading this directly.
    feature_flags = models.JSONField(default=list, blank=True)
    # When the welcome flow was completed. Null means "still needs onboarding",
    # which is what routes a fresh account into it. A timestamp rather than a
    # boolean so we can tell *when* someone joined the flow as it changes.
    onboarded_at = models.DateTimeField(null=True, blank=True)
    # This user's own invite code — the `?ref=` value in the links they share.
    referral_code = models.CharField(
        max_length=12, unique=True, default=generate_referral_code
    )
    # Who invited this user. Set once at account creation (verify-otp) and never
    # rewritten, so referral rewards can't be re-triggered on later sign-ins.
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals"
    )
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email

    @property
    def effective_flags(self) -> list[str]:
        """Flags this user actually holds — stored flags plus every flag for a
        superuser (so an admin is never locked out of a gated feature)."""
        from .feature_flags import ALL_FLAGS, clean

        flags = set(clean(self.feature_flags))
        if self.is_superuser:
            flags |= ALL_FLAGS
        return sorted(flags)

    def has_flag(self, flag: str) -> bool:
        return flag in self.effective_flags


def _generate_otp_code() -> str:
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


class EmailOTP(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    code = models.CharField(max_length=OTP_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["email", "-created_at"])]

    @classmethod
    def issue(cls, email: str) -> "EmailOTP":
        return cls.objects.create(
            email=email.lower(),
            code=_generate_otp_code(),
            expires_at=timezone.now() + OTP_TTL,
        )

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_locked(self) -> bool:
        return self.attempt_count >= OTP_MAX_ATTEMPTS

    def mark_used(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])

    def register_failed_attempt(self) -> None:
        self.attempt_count = models.F("attempt_count") + 1
        self.save(update_fields=["attempt_count"])
        self.refresh_from_db(fields=["attempt_count"])
