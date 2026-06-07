from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models

ENCRYPTED_PREFIX = "fernet$"


@lru_cache(maxsize=8)
def _fernet_for_keys(keys: tuple[str, ...]) -> MultiFernet:
    try:
        return MultiFernet([Fernet(key.encode("ascii")) for key in keys])
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS contains an invalid Fernet key.") from exc


def get_fernet() -> MultiFernet:
    keys = tuple(settings.FIELD_ENCRYPTION_KEYS)
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS must contain at least one Fernet key.")
    return _fernet_for_keys(keys)


class EncryptedTextField(models.TextField):
    description = "Text encrypted with the configured Fernet keys"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, "") or value.startswith(ENCRYPTED_PREFIX):
            return value
        encrypted = get_fernet().encrypt(value.encode("utf-8")).decode("ascii")
        return f"{ENCRYPTED_PREFIX}{encrypted}"

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        value = super().to_python(value)
        if value in (None, "") or not value.startswith(ENCRYPTED_PREFIX):
            return value
        try:
            token = value.removeprefix(ENCRYPTED_PREFIX).encode("ascii")
            return get_fernet().decrypt(token).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise ValidationError("Encrypted field value could not be decrypted.") from exc
