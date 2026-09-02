import {
  getAssistantMessageProviderLabel,
  getAssistantProviderLabel,
  getToolLabel,
} from "../src/features/assistant/presentation";

describe("assistant presentation", () => {
  test("maps every server tool to a user-facing evidence label", () => {
    expect(getToolLabel("get_today_summary")).toBe("每日汇总");
    expect(getToolLabel("get_weekly_trend")).toBe("七天趋势");
    expect(getToolLabel("search_food")).toBe("食品库搜索");
  });

  test("does not present a fallback response as OpenAI", () => {
    expect(
      getAssistantProviderLabel({ provider: "rule_based_assistant_v1", fallback_used: true })
    ).toBe("本地降级助手");
    expect(
      getAssistantProviderLabel({ provider: "openai_responses_assistant", fallback_used: false })
    ).toBe("OpenAI Tool Calling");
  });

  test("renders persisted assistant metadata without inventing a provider", () => {
    expect(
      getAssistantMessageProviderLabel({
        provider: "openai_responses_assistant",
        fallback_used: true,
      })
    ).toBe("本地降级助手");
    expect(getAssistantMessageProviderLabel({ provider: null, fallback_used: null })).toBe(
      "本地只读助手"
    );
  });
});
