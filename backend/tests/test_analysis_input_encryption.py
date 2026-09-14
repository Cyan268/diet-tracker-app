from uuid import uuid4

import pytest

from app.services.analysis_input_encryption import (
    AnalysisInputDecryptionError,
    decrypt_analysis_input,
    encrypt_analysis_input,
)


def test_analysis_input_round_trip_and_context_binding() -> None:
    user_id = uuid4()
    job_id = uuid4()
    secret = "test-master-secret-that-is-long-enough"
    payload = {"text": "午餐吃了一碗米饭", "log_date": "2026-09-09"}

    encrypted = encrypt_analysis_input(payload, user_id, job_id, secret)

    assert encrypted != encrypt_analysis_input(payload, user_id, job_id, secret)
    assert decrypt_analysis_input(encrypted, user_id, job_id, secret) == payload
    with pytest.raises(AnalysisInputDecryptionError):
        decrypt_analysis_input(encrypted, uuid4(), job_id, secret)
    with pytest.raises(AnalysisInputDecryptionError):
        decrypt_analysis_input(encrypted, user_id, uuid4(), secret)


def test_analysis_input_rejects_tampering_and_unknown_format() -> None:
    user_id = uuid4()
    job_id = uuid4()
    secret = "test-master-secret-that-is-long-enough"
    encrypted = encrypt_analysis_input({"text": "苹果"}, user_id, job_id, secret)
    tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])

    with pytest.raises(AnalysisInputDecryptionError):
        decrypt_analysis_input(tampered, user_id, job_id, secret)
    with pytest.raises(AnalysisInputDecryptionError):
        decrypt_analysis_input(bytes([99]) + encrypted[1:], user_id, job_id, secret)
