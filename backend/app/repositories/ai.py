from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiCallLog, AiCredential
from app.schemas.ai import AiMetricsResponse
from app.services.ai import AiCallTelemetry


async def get_ai_credential(session: AsyncSession, user_id: UUID) -> AiCredential | None:
    return await session.get(AiCredential, user_id)


async def save_ai_credential(
    session: AsyncSession,
    user_id: UUID,
    encrypted_api_key: bytes,
    key_last_four: str,
) -> AiCredential:
    credential = await get_ai_credential(session, user_id)
    if credential is None:
        credential = AiCredential(
            user_id=user_id,
            provider="openai",
            encrypted_api_key=encrypted_api_key,
            key_last_four=key_last_four,
        )
        session.add(credential)
    else:
        credential.encrypted_api_key = encrypted_api_key
        credential.key_last_four = key_last_four
    await session.commit()
    await session.refresh(credential)
    return credential


async def delete_ai_credential(session: AsyncSession, user_id: UUID) -> bool:
    credential = await get_ai_credential(session, user_id)
    if credential is None:
        return False
    await session.delete(credential)
    await session.commit()
    return True


async def record_ai_call(
    session: AsyncSession,
    user_id: UUID,
    request_text: str,
    telemetry: AiCallTelemetry,
    operation: str = "food_text_analysis",
) -> AiCallLog:
    log = AiCallLog(
        user_id=user_id,
        operation=operation,
        provider=telemetry.provider,
        model=telemetry.model,
        status=telemetry.status,
        fallback_used=telemetry.fallback_used,
        latency_ms=telemetry.latency_ms,
        attempt_count=telemetry.attempt_count,
        input_tokens=telemetry.input_tokens,
        output_tokens=telemetry.output_tokens,
        total_tokens=telemetry.total_tokens,
        estimated_cost_usd=telemetry.estimated_cost_usd,
        input_sha256=sha256(request_text.encode("utf-8")).hexdigest(),
        error_code=telemetry.error_code,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_ai_metrics(session: AsyncSession, user_id: UUID) -> AiMetricsResponse:
    statement = select(
        func.count(AiCallLog.id),
        func.coalesce(func.sum(case((AiCallLog.status == "success", 1), else_=0)), 0),
        func.coalesce(func.sum(case((AiCallLog.status == "fallback", 1), else_=0)), 0),
        func.coalesce(func.sum(case((AiCallLog.status == "failed", 1), else_=0)), 0),
        func.coalesce(func.avg(AiCallLog.latency_ms), 0),
        func.coalesce(func.sum(AiCallLog.input_tokens), 0),
        func.coalesce(func.sum(AiCallLog.output_tokens), 0),
        func.coalesce(func.sum(AiCallLog.total_tokens), 0),
        func.coalesce(func.sum(AiCallLog.estimated_cost_usd), 0),
        func.coalesce(
            func.sum(
                case(
                    (
                        (AiCallLog.total_tokens > 0) & (AiCallLog.estimated_cost_usd.is_(None)),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    ).where(AiCallLog.user_id == user_id)
    row = (await session.execute(statement)).one()
    return AiMetricsResponse(
        total_calls=int(row[0]),
        successful_calls=int(row[1]),
        fallback_calls=int(row[2]),
        failed_calls=int(row[3]),
        average_latency_ms=round(float(row[4]), 2),
        total_input_tokens=int(row[5]),
        total_output_tokens=int(row[6]),
        total_tokens=int(row[7]),
        estimated_cost_usd=Decimal(str(row[8])),
        unpriced_calls=int(row[9]),
    )
