from datetime import timedelta
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-secret-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.accounts",
    "apps.decks",
    "apps.cards",
    "apps.imports",
    "apps.books",
    "apps.subscriptions",
    "apps.support",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

db_url = os.getenv("DATABASE_URL")
if db_url:
    from urllib.parse import urlparse

    url = urlparse(db_url)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": url.path[1:],
            "USER": url.username,
            "PASSWORD": url.password,
            "HOST": url.hostname,
            "PORT": url.port or 5432,
        }
    }
    # Optional: pin tables to a specific schema. Used in prod to share a
    # single Render Postgres instance across multiple projects without
    # table-name collisions (each project gets its own schema). NOTE: no
    # `public` fallback — when another project lives in `public` on the
    # same DB, including it in search_path would let our migrate see (and
    # worse, write into) their django_migrations table on the first run.
    db_schema = os.getenv("DATABASE_SCHEMA", "").strip()
    if db_schema:
        DATABASES["default"]["OPTIONS"] = {
            "options": f"-c search_path={db_schema}",
        }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "nemo_anki"),
            "USER": os.getenv("POSTGRES_USER", "nemo"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "nemo"),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Media on Cloudflare R2 (S3-compatible). When the env vars are present
# Django uploads go to R2; when absent we fall through to local filesystem
# (good for dev, ephemeral on Render's free disk).
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY", "")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY", "")
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_BUCKET = os.getenv("R2_BUCKET", "")
R2_PUBLIC_DOMAIN = os.getenv("R2_PUBLIC_DOMAIN", "")
R2_LOCATION_PREFIX = os.getenv("R2_LOCATION_PREFIX", "").strip("/")

if R2_ACCESS_KEY and R2_SECRET_KEY and R2_ACCOUNT_ID and R2_BUCKET:
    _r2_options = {
        "bucket_name": R2_BUCKET,
        "access_key": R2_ACCESS_KEY,
        "secret_key": R2_SECRET_KEY,
        "endpoint_url": f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        "custom_domain": R2_PUBLIC_DOMAIN or None,
        "region_name": "auto",
    }
    if R2_LOCATION_PREFIX:
        _r2_options["location"] = R2_LOCATION_PREFIX
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": _r2_options,
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Allow the app to embed its own media (e.g. per-lesson PDFs) in an iframe.
X_FRAME_OPTIONS = "SAMEORIGIN"

CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5176,http://127.0.0.1:5176",
).split(",")

# Required for Django admin POSTs over HTTPS when hosted on a custom domain.
_csrf_trusted = os.getenv("CSRF_TRUSTED_ORIGINS", "").strip()
if _csrf_trusted:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_trusted.split(",") if o.strip()]

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

SIMPLE_JWT = {
    # Long-lived sessions: the frontend keeps tokens in localStorage and
    # silently refreshes, so users stay signed in until they log out. OTP is
    # only needed again once the refresh token finally expires (~1 year).
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=365),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# Gemini — powers the Import flow (paste book text -> draft cards).
# When unset, the import endpoint falls back to a deterministic line parser.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_VERIFY_SSL = os.getenv("GEMINI_VERIFY_SSL", "1") != "0"

# Resend — transactional email for sign-in OTP codes. When RESEND_API_KEY is
# set the code is emailed (and never returned in the API response); otherwise
# (local dev) the code is surfaced as `dev_code` so sign-in still works offline.
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
OTP_FROM_EMAIL = os.getenv("OTP_FROM_EMAIL", "Nemo Anki <noreply@nemoapps.xyz>")
