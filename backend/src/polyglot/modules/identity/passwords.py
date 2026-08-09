from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type


class PasswordPolicyError(ValueError):
    pass


class Argon2idPasswordHasher:
    def __init__(self) -> None:
        self._hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65_536,
            parallelism=4,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )

    @staticmethod
    def _validate_password(password: str) -> None:
        if not 12 <= len(password) <= 128 or len(password.encode("utf-8")) > 512:
            raise PasswordPolicyError("password must contain between 12 and 128 characters")

    def hash(self, password: str) -> str:
        self._validate_password(password)
        return self._hasher.hash(password)

    def verify(self, encoded_hash: str, password: str) -> bool:
        self._validate_password(password)
        if not encoded_hash.startswith("$argon2id$"):
            raise PasswordPolicyError("only Argon2id password hashes are accepted")
        try:
            return self._hasher.verify(encoded_hash, password)
        except VerifyMismatchError:
            return False
        except (InvalidHashError, VerificationError) as error:
            raise PasswordPolicyError("invalid Argon2id password hash") from error
