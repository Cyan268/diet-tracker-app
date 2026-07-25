import type {
  AssistantAnswerResponse,
  AssistantConversationMessageResponse,
  AssistantToolEvidence,
} from "@/api/types";

const TOOL_LABELS: Record<AssistantToolEvidence["tool_name"], string> = {
  get_today_summary: "每日汇总",
  get_weekly_trend: "七天趋势",
  search_food: "食品库搜索",
};

export function getToolLabel(toolName: AssistantToolEvidence["tool_name"]): string {
  return TOOL_LABELS[toolName];
}

export function getAssistantProviderLabel(
  response: Pick<AssistantAnswerResponse, "provider" | "fallback_used">
): string {
  if (response.fallback_used) return "本地降级助手";
  if (response.provider.startsWith("openai")) return "OpenAI Tool Calling";
  return "本地只读助手";
}

export function getAssistantMessageProviderLabel(
  message: Pick<AssistantConversationMessageResponse, "provider" | "fallback_used">
): string {
  return getAssistantProviderLabel({
    provider: message.provider ?? "rule_based_assistant_v1",
    fallback_used: message.fallback_used ?? false,
  });
}
