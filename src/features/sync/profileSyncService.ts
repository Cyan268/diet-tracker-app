import { ApiError } from "@/api/http";
import type { ProfileResponse, ProfileUpsertRequest } from "@/api/types";
import { getProfile, replaceProfileFromRemote } from "@/db/repositories/profileRepository";
import type { AuthSession } from "@/features/auth/authSession";
import type { UserProfile } from "@/types/profile";

export type ProfileSyncOutcome = "missing" | "pulled" | "pushed" | "unchanged";

function toRemoteRequest(profile: UserProfile): ProfileUpsertRequest {
  return {
    gender: profile.gender,
    age: profile.age,
    height_cm: profile.heightCm,
    weight_kg: profile.weightKg,
    activity_level: profile.activityLevel,
    goal: profile.goal,
  };
}

function toLocalProfile(remote: ProfileResponse): Omit<UserProfile, "id"> {
  return {
    gender: remote.gender,
    age: remote.age,
    heightCm: remote.height_cm,
    weightKg: remote.weight_kg,
    activityLevel: remote.activity_level,
    goal: remote.goal,
    createdAt: remote.created_at,
    updatedAt: remote.updated_at,
  };
}

async function pushProfile(auth: AuthSession, local: UserProfile): Promise<ProfileResponse> {
  return auth.request<ProfileResponse>("/api/v1/users/me/profile", {
    method: "PUT",
    body: JSON.stringify(toRemoteRequest(local)),
  });
}

export async function syncRemoteProfile(auth: AuthSession): Promise<ProfileSyncOutcome> {
  const local = await getProfile();
  let remote: ProfileResponse | null = null;

  try {
    remote = await auth.request<ProfileResponse>("/api/v1/users/me/profile");
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
  }

  if (!remote) {
    if (!local) return "missing";
    const saved = await pushProfile(auth, local);
    await replaceProfileFromRemote(toLocalProfile(saved));
    return "pushed";
  }

  if (local && Date.parse(local.updatedAt) > Date.parse(remote.updated_at)) {
    const saved = await pushProfile(auth, local);
    await replaceProfileFromRemote(toLocalProfile(saved));
    return "pushed";
  }

  if (local?.updatedAt === remote.updated_at) return "unchanged";
  await replaceProfileFromRemote(toLocalProfile(remote));
  return "pulled";
}
