import { getDatabase } from "../database";
import type { UserProfileRow } from "../rows";
import { v4 as uuidv4 } from "uuid";
import type { UserProfile } from "@/types/profile";
import { getCurrentUserId } from "../accountScope";

function rowToProfile(row: UserProfileRow): UserProfile {
  return {
    id: row.id,
    gender: row.gender,
    age: row.age,
    heightCm: row.height_cm,
    weightKg: row.weight_kg,
    activityLevel: row.activity_level,
    goal: row.goal,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export async function getProfile(): Promise<UserProfile | null> {
  const db = await getDatabase();
  const row = await db.getFirstAsync<UserProfileRow>(
    "SELECT * FROM user_profile WHERE owner_user_id = ? LIMIT 1",
    getCurrentUserId()
  );
  return row ? rowToProfile(row) : null;
}

export async function upsertProfile(
  profile: Omit<UserProfile, "id" | "createdAt" | "updatedAt">
): Promise<UserProfile> {
  const db = await getDatabase();
  const ownerUserId = getCurrentUserId();
  const existing = await getProfile();
  const now = new Date().toISOString();

  if (existing) {
    await db.runAsync(
      `UPDATE user_profile SET gender = ?, age = ?, height_cm = ?, weight_kg = ?, activity_level = ?, goal = ?, updated_at = ?
       WHERE id = ? AND owner_user_id = ?`,
      profile.gender,
      profile.age,
      profile.heightCm,
      profile.weightKg,
      profile.activityLevel,
      profile.goal,
      now,
      existing.id,
      ownerUserId
    );
    return { ...profile, id: existing.id, createdAt: existing.createdAt, updatedAt: now };
  }

  const id = uuidv4();
  await db.runAsync(
    `INSERT INTO user_profile (id, owner_user_id, gender, age, height_cm, weight_kg, activity_level, goal, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    id,
    ownerUserId,
    profile.gender,
    profile.age,
    profile.heightCm,
    profile.weightKg,
    profile.activityLevel,
    profile.goal,
    now,
    now
  );
  return { ...profile, id, createdAt: now, updatedAt: now };
}

export async function replaceProfileFromRemote(
  profile: Omit<UserProfile, "id">
): Promise<UserProfile> {
  const db = await getDatabase();
  const ownerUserId = getCurrentUserId();
  const existing = await getProfile();

  if (existing) {
    await db.runAsync(
      `UPDATE user_profile SET gender = ?, age = ?, height_cm = ?, weight_kg = ?, activity_level = ?, goal = ?, created_at = ?, updated_at = ?
       WHERE id = ? AND owner_user_id = ?`,
      profile.gender,
      profile.age,
      profile.heightCm,
      profile.weightKg,
      profile.activityLevel,
      profile.goal,
      profile.createdAt,
      profile.updatedAt,
      existing.id,
      ownerUserId
    );
    return { ...profile, id: existing.id };
  }

  const id = uuidv4();
  await db.runAsync(
    `INSERT INTO user_profile (id, owner_user_id, gender, age, height_cm, weight_kg, activity_level, goal, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    id,
    ownerUserId,
    profile.gender,
    profile.age,
    profile.heightCm,
    profile.weightKg,
    profile.activityLevel,
    profile.goal,
    profile.createdAt,
    profile.updatedAt
  );
  return { ...profile, id };
}
