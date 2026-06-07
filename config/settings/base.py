import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parents[2]


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "unsafe-local-development-key")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
FIELD_ENCRYPTION_KEYS = env_list(
    "FIELD_ENCRYPTION_KEYS",
    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "clients",
    "campaigns",
    "publishing",
    "media",
    "collaboration",
    "notifications",
    "ai_studio",
    "integrations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "config.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "clients.middleware.ClientMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = env("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=env_bool("DATABASE_SSL_REQUIRE", False),
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", "pulsea"),
            "USER": env("POSTGRES_USER", "pulsea"),
            "PASSWORD": env("POSTGRES_PASSWORD", "pulsea-local"),
            "HOST": env("POSTGRES_HOST", "localhost"),
            "PORT": env("POSTGRES_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/portal/login/"

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Pulsea <noreply@example.com>")
PUBLIC_CONTACT_EMAIL = env("PUBLIC_CONTACT_EMAIL", "Pulsea <noreply@example.com>")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)

PRIVATE_STORAGE_BACKEND = env("PRIVATE_STORAGE_BACKEND", "local")
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "media-private")))
MEDIA_MAX_IMAGE_UPLOAD_BYTES = int(env("MEDIA_MAX_IMAGE_UPLOAD_BYTES", str(20 * 1024 * 1024)))
MEDIA_MAX_VIDEO_UPLOAD_BYTES = int(env("MEDIA_MAX_VIDEO_UPLOAD_BYTES", str(500 * 1024 * 1024)))
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL")
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")

CELERY_BROKER_URL = env("CELERY_BROKER_URL", env("REDIS_URL", "redis://localhost:6379/0"))
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TIMEZONE = TIME_ZONE
PUBLISHING_ADAPTER_MODE = env("PUBLISHING_ADAPTER_MODE", "fake")
META_APP_ID = env("META_APP_ID")
META_APP_SECRET = env("META_APP_SECRET")
META_BUSINESS_ID = env("META_BUSINESS_ID")
META_GRAPH_API_VERSION = env("META_GRAPH_API_VERSION", "v23.0")
META_OAUTH_REDIRECT_URI = env(
    "META_OAUTH_REDIRECT_URI",
    "http://localhost:8000/operator/connections/meta/callback/",
)
INSTAGRAM_APP_ID = env("INSTAGRAM_APP_ID")
INSTAGRAM_APP_SECRET = env("INSTAGRAM_APP_SECRET")
INSTAGRAM_API_VERSION = env("INSTAGRAM_API_VERSION", "v23.0")
INSTAGRAM_OAUTH_REDIRECT_URI = env(
    "INSTAGRAM_OAUTH_REDIRECT_URI",
    "http://localhost:8000/operator/connections/instagram/callback/",
)
INSTAGRAM_WEBHOOK_VERIFY_TOKEN = env(
    "INSTAGRAM_WEBHOOK_VERIFY_TOKEN",
    "pulsea-instagram-webhook-2026",
)
INSTAGRAM_CONTAINER_POLL_ATTEMPTS = int(env("INSTAGRAM_CONTAINER_POLL_ATTEMPTS", "5"))
INSTAGRAM_CONTAINER_POLL_INTERVAL_SECONDS = int(
    env("INSTAGRAM_CONTAINER_POLL_INTERVAL_SECONDS", "60")
)
PINTEREST_APP_ID = env("PINTEREST_APP_ID")
PINTEREST_APP_SECRET = env("PINTEREST_APP_SECRET")
PINTEREST_OAUTH_REDIRECT_URI = env(
    "PINTEREST_OAUTH_REDIRECT_URI",
    "http://localhost:8000/operator/connections/pinterest/callback/",
)
CELERY_BEAT_SCHEDULE = {
    "foundation-heartbeat": {
        "task": "publishing.tasks.foundation_heartbeat",
        "schedule": 60.0,
    },
    "enqueue-due-posts": {
        "task": "publishing.tasks.enqueue_due_posts",
        "schedule": 120.0,
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_secrets": {"()": "config.logging.RedactSecretsFilter"},
        "request_id": {"()": "config.logging.RequestIdFilter"},
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["redact_secrets", "request_id"],
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}
