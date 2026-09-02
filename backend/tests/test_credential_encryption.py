from uuid import uuid4

import pytest

from app.services.credential_encryption import (
    CredentialDecryptionError,
    decrypt_api_key,
    encrypt_api_key,
)

MASTER_SECRET = "test-encryption-secret-that-is-long-enough"


def test_api_key_encryption_round_trip_does_not_contain_plaintext() -> None:
    user_id = uuid4()
    api_key = "fake-openai-key-for-tests-1234567890"

    encrypted = encrypt_api_key(api_key, user_id, MASTER_SECRET)

    assert api_key.encode() not in encrypted
    assert decrypt_api_key(encrypted, user_id, MASTER_SECRET) == api_key


@pytest.mark.parametrize("change", ["user", "secret", "ciphertext"])
def test_api_key_ciphertext_rejects_wrong_context_or_tampering(change: str) -> None:
    user_id = uuid4()
    encrypted = encrypt_api_key(
        "fake-openai-key-for-tests-1234567890",
        user_id,
        MASTER_SECRET,
    )
    decrypt_user_id = uuid4() if change == "user" else user_id
    decrypt_secret = f"{MASTER_SECRET}-different" if change == "secret" else MASTER_SECRET
    if change == "ciphertext":
        encrypted = encrypted[:-1] + bytes([encrypted[-1] ^ 1])

    with pytest.raises(CredentialDecryptionError):
        decrypt_api_key(encrypted, decrypt_user_id, decrypt_secret)
