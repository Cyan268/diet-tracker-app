import { canManageAiCredentials, isDemoAccount } from "@/features/demo/demoAccount";

describe("demo account policy", () => {
  it("recognizes an explicit demo account flag", () => {
    expect(isDemoAccount({ is_demo: true })).toBe(true);
    expect(isDemoAccount({ is_demo: false })).toBe(false);
    expect(isDemoAccount(null)).toBe(false);
  });

  it("never allows a shared demo account to manage API keys", () => {
    expect(canManageAiCredentials({ is_demo: true }, "authenticated")).toBe(false);
    expect(canManageAiCredentials({ is_demo: false }, "offline")).toBe(false);
    expect(canManageAiCredentials({ is_demo: false }, "authenticated")).toBe(true);
  });
});
