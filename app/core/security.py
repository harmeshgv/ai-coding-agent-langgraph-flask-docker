"""Helper class to handle the security aspects, i.e. encryption."""

from cryptography.fernet import Fernet
from flask import current_app
from sqlalchemy import LargeBinary, TypeDecorator

from app.core.config import get_env_settings


# pylint: disable=too-many-ancestors
class EncryptedString(TypeDecorator):
    """Encrypts strings on write and decrypts on read."""

    impl = LargeBinary
    cache_ok = True

    @property
    def encryption_key(self):
        """Get the encryption key without caching.
        
        Note: We don't cache the key to ensure tests can change settings
        and have the new key take effect immediately. The performance impact
        is negligible since Fernet key creation is fast.
        """
        key = None
        if current_app:
            key = current_app.config.get("ENCRYPTION_KEY")

        if not key:
            # Fallback to environment settings for non-app contexts (e.g., shell)
            key = get_env_settings().encryption_key

        if not key:
            raise ValueError("ENCRYPTION_KEY is not set in app config or environment.")

        return Fernet(key.encode())

    @property
    def python_type(self):
        """Return the Python type for this custom type."""
        return str

    def process_bind_param(self, value, dialect):  # pylint: disable=unused-argument
        """Encrypt before saving."""
        if value is None:
            return value

        if not isinstance(value, str):
            raise TypeError("EncryptedString only supports string values.")

        value_bytes = value.encode("utf-8")
        return self.encryption_key.encrypt(value_bytes)

    def process_result_value(self, value, dialect):  # pylint: disable=unused-argument
        """Decrypt after loading."""
        if value is None:
            return value

        # Handle backward compatibility: if value is already a string (unencrypted),
        # return it as-is. This allows migration from unencrypted to encrypted data.
        if isinstance(value, str):
            return value

        try:
            decrypted_value = self.encryption_key.decrypt(value)
            return decrypted_value.decode("utf-8")
        except Exception:  # pylint: disable=broad-exception-caught
            # If decryption fails, assume it's legacy unencrypted data
            # Try to decode as UTF-8 string
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return str(value)

    def process_literal_param(self, value, dialect):
        """Handles rendering of a literal parameter for this type.

        This is used for features like literal_binds.
        """
        processed_value = self.process_bind_param(value, dialect)
        if processed_value is None:
            return "NULL"

        return dialect.type_descriptor(self.impl).process_literal_param(  # type: ignore[attr-defined] # pylint: disable=line-too-long
            processed_value, dialect
        )
