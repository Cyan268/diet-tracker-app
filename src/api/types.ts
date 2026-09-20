import type { components } from "./generated/schema";

export type AuthResponse = components["schemas"]["AuthResponse"];
export type TokenResponse = components["schemas"]["TokenResponse"];
export type AuthUser = components["schemas"]["UserResponse"];
export type LoginRequest = components["schemas"]["LoginRequest"];
export type RegisterRequest = components["schemas"]["RegisterRequest"];
export type RefreshRequest = components["schemas"]["RefreshRequest"];
export type PublicRuntimeConfigResponse = components["schemas"]["PublicRuntimeConfigResponse"];
export type ProfileUpsertRequest = components["schemas"]["ProfileUpsertRequest"];
export type ProfileResponse = components["schemas"]["ProfileResponse"];
export type LogResponse = components["schemas"]["LogResponse"];
export type SyncChangeResponse = components["schemas"]["SyncChangeResponse"];
export type SyncPageResponse = components["schemas"]["SyncPageResponse"];
export type FoodTextAnalyzeRequest = components["schemas"]["FoodTextAnalyzeRequest"];
export type FoodTextAnalyzeResponse = components["schemas"]["FoodTextAnalyzeResponse"];
export type AnalysisCreateRequest = components["schemas"]["AnalysisCreateRequest"];
export type AnalysisImageCreateRequest = components["schemas"]["AnalysisImageCreateRequest"];
export type AnalysisAcceptedResponse = components["schemas"]["AnalysisAcceptedResponse"];
export type AnalysisStatusResponse = components["schemas"]["AnalysisStatusResponse"];
export type AnalysisDraftResponse = components["schemas"]["AnalysisDraftResponse"];
export type AnalysisDraftEntityResponse = components["schemas"]["AnalysisDraftEntityResponse"];
export type AnalysisConfirmRequest = components["schemas"]["AnalysisConfirmRequest"];
export type AnalysisConfirmationResponse = components["schemas"]["AnalysisConfirmationResponse"];
export type UploadPresignResponse = components["schemas"]["UploadPresignResponse"];
export type UploadResponse = components["schemas"]["UploadResponse"];
export type AiMetricsResponse = components["schemas"]["AiMetricsResponse"];
export type AiCredentialUpsertRequest = components["schemas"]["AiCredentialUpsertRequest"];
export type AiCredentialStatusResponse = components["schemas"]["AiCredentialStatusResponse"];
export type AssistantQuestionRequest = components["schemas"]["AssistantQuestionRequest"];
export type AssistantAnswerResponse = components["schemas"]["AssistantAnswerResponse"];
export type AssistantToolEvidence = components["schemas"]["AssistantToolEvidence"];
export type AssistantConversationCreateRequest =
  components["schemas"]["AssistantConversationCreateRequest"];
export type AssistantConversationMessageCreateRequest =
  components["schemas"]["AssistantConversationMessageCreateRequest"];
export type AssistantConversationSummaryResponse =
  components["schemas"]["AssistantConversationSummaryResponse"];
export type AssistantConversationMessageResponse =
  components["schemas"]["AssistantConversationMessageResponse"];
export type AssistantConversationDetailResponse =
  components["schemas"]["AssistantConversationDetailResponse"];
export type AssistantConversationTurnResponse =
  components["schemas"]["AssistantConversationTurnResponse"];
export type WeeklyReportRequest = components["schemas"]["WeeklyReportRequest"];
export type WeeklyReportResponse = components["schemas"]["WeeklyReportResponse"];
