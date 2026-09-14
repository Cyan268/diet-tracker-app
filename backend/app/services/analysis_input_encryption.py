import json
from hashlib import sha256
from os import urandom
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT_VERSION = 1
NONCE_BYTES = 12


class AnalysisInputDecryptionError(Exception):
    pass


def _encryption_key(master_secret: str) -> bytes:
    material = f"nutripilot:analysis-input-key:v1:{master_secret}".encode()
    return sha256(material).digest()


def _associated_data(user_id: UUID, job_id: UUID) -> bytes:
    return f"nutripilot:analysis-input:v1:{user_id}:{job_id}".encode()


def encrypt_analysis_input(
    payload: dict[str, object],
    user_id: UUID,
    job_id: UUID,
    master_secret: str,
) -> bytes:
    plaintext = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    nonce = urandom(NONCE_BYTES)
    ciphertext = AESGCM(_encryption_key(master_secret)).encrypt(
        nonce,
        plaintext,
        _associated_data(user_id, job_id),
    )
    return bytes([FORMAT_VERSION]) + nonce + ciphertext


def decrypt_analysis_input(
    encrypted: bytes,
    user_id: UUID,
    job_id: UUID,
    master_secret: str,
) -> dict[str, object]:
    if len(encrypted) <= 1 + NONCE_BYTES or encrypted[0] != FORMAT_VERSION:
        raise AnalysisInputDecryptionError("unsupported analysis input ciphertext")
    nonce = encrypted[1 : 1 + NONCE_BYTES]
    ciphertext = encrypted[1 + NONCE_BYTES :]
    try:
        plaintext = AESGCM(_encryption_key(master_secret)).decrypt(
            nonce,
            ciphertext,
            _associated_data(user_id, job_id),
        )
        value = json.loads(plaintext)
    except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise AnalysisInputDecryptionError("analysis input decryption failed") from error
    if not isinstance(value, dict):
        raise AnalysisInputDecryptionError("analysis input plaintext must be an object")
    return value
