from hashlib import sha256
from os import urandom
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT_VERSION = 1
NONCE_BYTES = 12


class CredentialDecryptionError(Exception):
    pass


def _encryption_key(master_secret: str) -> bytes:
    return sha256(master_secret.encode("utf-8")).digest()


def _associated_data(user_id: UUID) -> bytes:
    return f"nutripilot:ai-credential:v1:{user_id}".encode()


def encrypt_api_key(api_key: str, user_id: UUID, master_secret: str) -> bytes:
    nonce = urandom(NONCE_BYTES)
    ciphertext = AESGCM(_encryption_key(master_secret)).encrypt(
        nonce,
        api_key.encode("utf-8"),
        _associated_data(user_id),
    )
    return bytes([FORMAT_VERSION]) + nonce + ciphertext


def decrypt_api_key(payload: bytes, user_id: UUID, master_secret: str) -> str:
    if len(payload) <= 1 + NONCE_BYTES or payload[0] != FORMAT_VERSION:
        raise CredentialDecryptionError("unsupported credential ciphertext")
    nonce = payload[1 : 1 + NONCE_BYTES]
    ciphertext = payload[1 + NONCE_BYTES :]
    try:
        plaintext = AESGCM(_encryption_key(master_secret)).decrypt(
            nonce,
            ciphertext,
            _associated_data(user_id),
        )
    except (InvalidTag, ValueError) as error:
        raise CredentialDecryptionError("credential decryption failed") from error
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CredentialDecryptionError("credential plaintext is invalid") from error
