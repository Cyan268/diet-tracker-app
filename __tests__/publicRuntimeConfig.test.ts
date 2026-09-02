import { fetchPublicRuntimeConfig } from "../src/features/auth/publicRuntimeConfig";

describe("public runtime config", () => {
  it("reads the registration policy without authentication", async () => {
    const fetcher = jest.fn(
      async () =>
        new Response(JSON.stringify({ registration_enabled: false }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
    );

    await expect(fetchPublicRuntimeConfig(fetcher, "https://api.example.com")).resolves.toEqual({
      registration_enabled: false,
    });
    expect(fetcher).toHaveBeenCalledWith(
      "https://api.example.com/api/v1/meta/config",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });
});
