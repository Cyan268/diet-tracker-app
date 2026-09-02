import { ApiError } from "@/api/http";
import type { ProfileResponse } from "@/api/types";
import { getProfile, replaceProfileFromRemote } from "@/db/repositories/profileRepository";
import type { AuthRequestScope } from "@/features/auth/authSession";
import { syncRemoteProfile } from "@/features/sync/profileSyncService";
import type { UserProfile } from "@/types/profile";

jest.mock("@/db/repositories/profileRepository", () => ({
  getProfile: jest.fn(),
  replaceProfileFromRemote: jest.fn(),
}));

jest.mock("@/db/accountScope", () => ({ getCurrentUserId: () => "user-1" }));

const getProfileMock = jest.mocked(getProfile);
const replaceProfileMock = jest.mocked(replaceProfileFromRemote);

const REMOTE: ProfileResponse = {
  gender: "female",
  age: 23,
  height_cm: 165,
  weight_kg: 55,
  activity_level: "moderate",
  goal: "maintain",
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
  daily_targets: {
    kcal: 2000,
    protein: 88,
    fat: 61,
    carbs: 275,
    sugar: 50,
    sodium: 2300,
    caffeine: 400,
  },
};

const LOCAL: UserProfile = {
  id: "local-profile",
  gender: "male",
  age: 24,
  heightCm: 180,
  weightKg: 70,
  activityLevel: "active",
  goal: "gain",
  createdAt: "2026-07-20T00:00:00Z",
  updatedAt: "2026-07-22T00:00:00Z",
};

function authWith(request: jest.Mock): AuthRequestScope {
  return {
    request,
    ownerUserId: "user-1",
    epoch: 1,
    assertCurrent: () => undefined,
  } as unknown as AuthRequestScope;
}

describe("profile sync service", () => {
  beforeEach(() => jest.clearAllMocks());

  it("hydrates a missing local profile from the cloud", async () => {
    getProfileMock.mockResolvedValue(null);
    const request = jest.fn().mockResolvedValue(REMOTE);

    await expect(syncRemoteProfile(authWith(request))).resolves.toBe("pulled");
    expect(request).toHaveBeenCalledWith("/api/v1/users/me/profile");
    expect(replaceProfileMock).toHaveBeenCalledWith(
      expect.objectContaining({ gender: "female", heightCm: 165, updatedAt: REMOTE.updated_at }),
      "user-1",
      expect.any(Function)
    );
  });

  it("pushes a newer local profile using the API field contract", async () => {
    getProfileMock.mockResolvedValue(LOCAL);
    const request = jest
      .fn()
      .mockResolvedValueOnce(REMOTE)
      .mockResolvedValueOnce({
        ...REMOTE,
        gender: LOCAL.gender,
        updated_at: "2026-07-22T00:00:01Z",
      });

    await expect(syncRemoteProfile(authWith(request))).resolves.toBe("pushed");
    expect(request).toHaveBeenLastCalledWith("/api/v1/users/me/profile", {
      method: "PUT",
      body: JSON.stringify({
        gender: "male",
        age: 24,
        height_cm: 180,
        weight_kg: 70,
        activity_level: "active",
        goal: "gain",
      }),
    });
  });

  it("creates the cloud profile when only a local copy exists", async () => {
    getProfileMock.mockResolvedValue(LOCAL);
    const request = jest
      .fn()
      .mockRejectedValueOnce(new ApiError(404, { detail: "profile not found" }))
      .mockResolvedValueOnce(REMOTE);

    await expect(syncRemoteProfile(authWith(request))).resolves.toBe("pushed");
    expect(request).toHaveBeenCalledTimes(2);
    expect(replaceProfileMock).toHaveBeenCalledTimes(1);
  });
});
