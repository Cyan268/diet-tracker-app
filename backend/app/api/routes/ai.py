from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.ai import (
    AssistantProvider,
    FoodTextProvider,
    OpenAIResponsesAssistantProvider,
    OpenAIResponsesFoodTextProvider,
    OpenAIResponsesWeeklyReportProvider,
    ProviderError,
    RuleBasedAssistantProvider,
    RuleBasedFoodTextProvider,
    RuleBasedWeeklyReportProvider,
    WeeklyReportProvider,
)
from app.api.dependencies import CurrentUserDep, DemoGuardDep, SessionDep, SettingsDep
from app.models import AiCredential
from app.repositories.ai import (
    delete_ai_credential,
    get_ai_credential,
    get_ai_metrics,
    record_ai_call,
    save_ai_credential,
)
from app.repositories.assistant_conversations import (
    ConversationAppendConflictError,
    ConversationNotFoundError,
    append_conversation_turn,
    count_messages,
    create_conversation,
    delete_conversation,
    get_completed_turn_by_client_id,
    get_conversation,
    list_conversations,
    list_messages,
    load_conversation_context,
)
from app.schemas.ai import (
    AiCredentialStatusResponse,
    AiCredentialUpsertRequest,
    AiMetricsResponse,
    FoodTextAnalyzeRequest,
    FoodTextAnalyzeResponse,
)
from app.schemas.assistant import (
    AssistantAnswerResponse,
    AssistantConversationCreateRequest,
    AssistantConversationDetailResponse,
    AssistantConversationMessageCreateRequest,
    AssistantConversationMessageResponse,
    AssistantConversationSummaryResponse,
    AssistantConversationTurnResponse,
    AssistantQuestionRequest,
)
from app.schemas.weekly_report import WeeklyReportRequest, WeeklyReportResponse
from app.services.ai import AiCallTelemetry, analyze_food_text
from app.services.assistant import answer_assistant_question
from app.services.credential_encryption import (
    CredentialDecryptionError,
    decrypt_api_key,
    encrypt_api_key,
)
from app.services.weekly_report import generate_weekly_report

router = APIRouter()


async def _conversation_detail_response(
    session: SessionDep,
    conversation,
) -> AssistantConversationDetailResponse:
    messages = await list_messages(session, conversation.id)
    return AssistantConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        message_count=await count_messages(session, conversation.id),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            AssistantConversationMessageResponse.model_validate(message) for message in messages
        ],
    )


async def _openai_api_key_for_user(
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> str | None:
    if current_user.is_demo:
        return None
    credential = await get_ai_credential(session, current_user.id)
    if credential is not None:
        try:
            return decrypt_api_key(
                credential.encrypted_api_key,
                current_user.id,
                settings.credential_encryption_key.get_secret_value(),
            )
        except CredentialDecryptionError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="AI credential must be configured again",
            ) from error
    if settings.ai_provider == "openai":
        assert settings.openai_api_key is not None
        return settings.openai_api_key.get_secret_value()
    return None


def _openai_provider(api_key: str, settings: SettingsDep) -> FoodTextProvider:
    return OpenAIResponsesFoodTextProvider(
        api_key=api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
    )


async def _provider_for_user(
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> tuple[FoodTextProvider, bool]:
    api_key = await _openai_api_key_for_user(current_user, session, settings)
    if api_key is not None:
        return _openai_provider(api_key, settings), True
    return RuleBasedFoodTextProvider(), False


async def _assistant_provider_for_user(
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> tuple[AssistantProvider, bool]:
    api_key = await _openai_api_key_for_user(current_user, session, settings)
    if api_key is None:
        return RuleBasedAssistantProvider(), False
    return (
        OpenAIResponsesAssistantProvider(
            api_key=api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.ai_timeout_seconds,
        ),
        True,
    )


async def _weekly_report_provider_for_user(
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> tuple[WeeklyReportProvider, bool]:
    api_key = await _openai_api_key_for_user(current_user, session, settings)
    if api_key is None:
        return RuleBasedWeeklyReportProvider(), False
    return (
        OpenAIResponsesWeeklyReportProvider(
            api_key=api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.ai_timeout_seconds,
        ),
        True,
    )


def _credential_status(credential: AiCredential | None) -> AiCredentialStatusResponse:
    if credential is None:
        return AiCredentialStatusResponse(configured=False)
    return AiCredentialStatusResponse(
        configured=True,
        key_hint=f"••••{credential.key_last_four}",
        updated_at=credential.updated_at,
    )


@router.get("/credentials", response_model=AiCredentialStatusResponse)
async def read_ai_credential(
    current_user: CurrentUserDep,
    session: SessionDep,
) -> AiCredentialStatusResponse:
    if current_user.is_demo:
        return AiCredentialStatusResponse(configured=False)
    return _credential_status(await get_ai_credential(session, current_user.id))


@router.put("/credentials", response_model=AiCredentialStatusResponse)
async def upsert_ai_credential(
    request: AiCredentialUpsertRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> AiCredentialStatusResponse:
    if current_user.is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="demo accounts cannot store AI credentials",
        )
    api_key = request.api_key.get_secret_value()
    encrypted_api_key = encrypt_api_key(
        api_key,
        current_user.id,
        settings.credential_encryption_key.get_secret_value(),
    )
    credential = await save_ai_credential(
        session,
        current_user.id,
        encrypted_api_key,
        api_key[-4:],
    )
    return _credential_status(credential)


@router.delete("/credentials", status_code=status.HTTP_204_NO_CONTENT)
async def remove_ai_credential(
    current_user: CurrentUserDep,
    session: SessionDep,
) -> Response:
    if current_user.is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="demo accounts cannot store AI credentials",
        )
    await delete_ai_credential(session, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/food-text:analyze", response_model=FoodTextAnalyzeResponse)
async def analyze_text(
    request: FoodTextAnalyzeRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    demo_guard: DemoGuardDep,
) -> FoodTextAnalyzeResponse:
    await demo_guard.enforce_rate(current_user, "ai")
    provider, using_openai = await _provider_for_user(current_user, session, settings)
    fallback = RuleBasedFoodTextProvider() if using_openai else None
    try:
        execution = await analyze_food_text(
            request,
            provider,
            fallback=fallback,
            max_attempts=settings.ai_max_attempts,
            retry_delay_seconds=settings.ai_retry_delay_seconds,
            input_price_per_million=settings.ai_input_price_per_million_usd,
            output_price_per_million=settings.ai_output_price_per_million_usd,
        )
    except ProviderError as error:
        telemetry = AiCallTelemetry(
            provider=provider.name,
            model=settings.openai_model,
            status="failed",
            fallback_used=False,
            latency_ms=0,
            attempt_count=settings.ai_max_attempts,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_usd=None,
            error_code=error.code,
        )
        await record_ai_call(session, current_user.id, request.text, telemetry)
        raise HTTPException(
            status_code=503, detail="AI analysis is temporarily unavailable"
        ) from error
    log = await record_ai_call(session, current_user.id, request.text, execution.telemetry)
    return execution.response.model_copy(update={"trace_id": log.id})


@router.get("/metrics", response_model=AiMetricsResponse)
async def read_ai_metrics(
    current_user: CurrentUserDep,
    session: SessionDep,
) -> AiMetricsResponse:
    return await get_ai_metrics(session, current_user.id)


@router.post("/reports/weekly:generate", response_model=WeeklyReportResponse)
async def create_weekly_report(
    request: WeeklyReportRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    demo_guard: DemoGuardDep,
) -> WeeklyReportResponse:
    await demo_guard.enforce_rate(current_user, "ai")
    provider, using_openai = await _weekly_report_provider_for_user(current_user, session, settings)
    fallback = RuleBasedWeeklyReportProvider() if using_openai else None
    try:
        execution = await generate_weekly_report(
            session,
            current_user.id,
            request,
            provider,
            fallback=fallback,
            max_attempts=settings.ai_max_attempts,
            retry_delay_seconds=settings.ai_retry_delay_seconds,
            input_price_per_million=settings.ai_input_price_per_million_usd,
            output_price_per_million=settings.ai_output_price_per_million_usd,
        )
    except ProviderError as error:
        telemetry = AiCallTelemetry(
            provider=provider.name,
            model=provider.model,
            status="failed",
            fallback_used=False,
            latency_ms=0,
            attempt_count=settings.ai_max_attempts,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_usd=None,
            error_code=error.code,
        )
        await record_ai_call(
            session,
            current_user.id,
            request.end_date.isoformat(),
            telemetry,
            operation="weekly_report",
        )
        raise HTTPException(
            status_code=503,
            detail="AI weekly report is temporarily unavailable",
        ) from error
    log = await record_ai_call(
        session,
        current_user.id,
        request.end_date.isoformat(),
        execution.telemetry,
        operation="weekly_report",
    )
    return execution.response.model_copy(update={"trace_id": log.id})


@router.post("/assistant:answer", response_model=AssistantAnswerResponse)
async def answer_question(
    request: AssistantQuestionRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    demo_guard: DemoGuardDep,
) -> AssistantAnswerResponse:
    await demo_guard.enforce_rate(current_user, "ai")
    provider, using_openai = await _assistant_provider_for_user(current_user, session, settings)
    fallback = RuleBasedAssistantProvider() if using_openai else None
    try:
        execution = await answer_assistant_question(
            session,
            current_user.id,
            request,
            provider,
            fallback=fallback,
            max_attempts=settings.ai_max_attempts,
            retry_delay_seconds=settings.ai_retry_delay_seconds,
            input_price_per_million=settings.ai_input_price_per_million_usd,
            output_price_per_million=settings.ai_output_price_per_million_usd,
        )
    except ProviderError as error:
        telemetry = AiCallTelemetry(
            provider=provider.name,
            model=provider.model,
            status="failed",
            fallback_used=False,
            latency_ms=0,
            attempt_count=settings.ai_max_attempts,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_usd=None,
            error_code=error.code,
        )
        await record_ai_call(
            session,
            current_user.id,
            request.question,
            telemetry,
            operation="assistant_question",
        )
        raise HTTPException(
            status_code=503,
            detail="AI assistant is temporarily unavailable",
        ) from error
    log = await record_ai_call(
        session,
        current_user.id,
        request.question,
        execution.telemetry,
        operation="assistant_question",
    )
    return execution.response.model_copy(update={"trace_id": log.id})


@router.get(
    "/assistant/conversations",
    response_model=list[AssistantConversationSummaryResponse],
)
async def read_assistant_conversations(
    current_user: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[AssistantConversationSummaryResponse]:
    rows = await list_conversations(session, current_user.id, limit)
    return [
        AssistantConversationSummaryResponse(
            id=conversation.id,
            title=conversation.title,
            message_count=message_count,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
        for conversation, message_count in rows
    ]


@router.post(
    "/assistant/conversations",
    response_model=AssistantConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_assistant_conversation(
    request: AssistantConversationCreateRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    demo_guard: DemoGuardDep,
) -> AssistantConversationDetailResponse:
    await demo_guard.enforce_rate(current_user, "write")
    await demo_guard.enforce_capacity(session, current_user, "conversations")
    conversation = await create_conversation(session, current_user.id, request.title)
    return await _conversation_detail_response(session, conversation)


@router.get(
    "/assistant/conversations/{conversation_id}",
    response_model=AssistantConversationDetailResponse,
)
async def read_assistant_conversation(
    conversation_id: UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> AssistantConversationDetailResponse:
    conversation = await get_conversation(session, current_user.id, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return await _conversation_detail_response(session, conversation)


@router.delete(
    "/assistant/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_assistant_conversation(
    conversation_id: UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    demo_guard: DemoGuardDep,
) -> Response:
    await demo_guard.enforce_rate(current_user, "write")
    if not await delete_conversation(session, current_user.id, conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/assistant/conversations/{conversation_id}/messages",
    response_model=AssistantConversationTurnResponse,
)
async def add_assistant_message(
    conversation_id: UUID,
    request: AssistantConversationMessageCreateRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    demo_guard: DemoGuardDep,
) -> AssistantConversationTurnResponse:
    await demo_guard.enforce_rate(current_user, "ai")
    conversation = await get_conversation(session, current_user.id, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    try:
        replay = await get_completed_turn_by_client_id(
            session,
            conversation_id,
            request.client_message_id,
        )
    except ConversationAppendConflictError as error:
        raise HTTPException(status_code=409, detail="message is still being processed") from error
    if replay is not None:
        if (
            replay[0].content != request.question.strip()
            or replay[0].reference_date != request.reference_date
        ):
            raise HTTPException(
                status_code=409,
                detail="client_message_id was already used with different content",
            )
        return AssistantConversationTurnResponse(
            conversation=await _conversation_detail_response(session, conversation),
            replayed=True,
        )

    await demo_guard.enforce_capacity(
        session,
        current_user,
        "messages",
        conversation_id=conversation_id,
    )

    history = await load_conversation_context(session, conversation_id)
    provider, using_openai = await _assistant_provider_for_user(current_user, session, settings)
    fallback = RuleBasedAssistantProvider() if using_openai else None
    try:
        execution = await answer_assistant_question(
            session,
            current_user.id,
            request,
            provider,
            fallback=fallback,
            max_attempts=settings.ai_max_attempts,
            retry_delay_seconds=settings.ai_retry_delay_seconds,
            input_price_per_million=settings.ai_input_price_per_million_usd,
            output_price_per_million=settings.ai_output_price_per_million_usd,
            history=history,
        )
    except ProviderError as error:
        telemetry = AiCallTelemetry(
            provider=provider.name,
            model=provider.model,
            status="failed",
            fallback_used=False,
            latency_ms=0,
            attempt_count=settings.ai_max_attempts,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_usd=None,
            error_code=error.code,
        )
        await record_ai_call(
            session,
            current_user.id,
            request.question,
            telemetry,
            operation="assistant_conversation",
        )
        raise HTTPException(
            status_code=503,
            detail="AI assistant is temporarily unavailable",
        ) from error
    log = await record_ai_call(
        session,
        current_user.id,
        request.question,
        execution.telemetry,
        operation="assistant_conversation",
    )
    answer = execution.response.model_copy(update={"trace_id": log.id})
    try:
        _, _, replayed = await append_conversation_turn(
            session,
            current_user.id,
            conversation_id,
            request.client_message_id,
            request.question,
            request.reference_date,
            answer,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="conversation not found") from error
    except ConversationAppendConflictError as error:
        raise HTTPException(
            status_code=409,
            detail="conversation changed; retry the request",
        ) from error
    await session.refresh(conversation)
    return AssistantConversationTurnResponse(
        conversation=await _conversation_detail_response(session, conversation),
        replayed=replayed,
    )
