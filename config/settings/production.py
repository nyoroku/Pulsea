from .base import *  # noqa: F403


def require_env(name: str) -> str:
    value = env(name)  # noqa: F405
    if not value:
        raise RuntimeError(f"Missing required production environment variable: {name}")
    return value


DEBUG = False
SECRET_KEY = require_env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")  # noqa: F405
if not ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must contain at least one production host")
FIELD_ENCRYPTION_KEYS = env_list("FIELD_ENCRYPTION_KEYS")  # noqa: F405
if not FIELD_ENCRYPTION_KEYS:
    raise RuntimeError("FIELD_ENCRYPTION_KEYS must contain at least one production Fernet key")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
