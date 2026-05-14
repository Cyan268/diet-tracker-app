import { getDatabase } from "../database";
import { v4 as uuidv4 } from "uuid";
import type { UserProfile } from "@/types/profile";

function rowToProfile(row: any): UserProfile {
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
  const row = await db.getFirstAsync<any>("SELECT * FROM user_profile LIMIT 1");
  return row ? rowToProfile(row) : null;
}

export async function upsertProfile(
  profile: Omit<UserProfile, "id" | "createdAt" | "updatedAt">
): Promise<UserProfile> {
  const db = await getDatabase();
  const existing = await getProfile();
  const now = new Date().toISOString();

  if (existing) {
    await db.runAsync(
      `UPDATE user_profile SET gender = ?, age = ?, height_cm = ?, weight_kg = ?, activity_level = ?, goal = ?, updated_at = ?
       WHERE id = ?`,
      profile.gender,
      profile.age,
      profile.heightCm,
      profile.weightKg,
      profile.activityLevel,
      profile.goal,
      now,
      existing.id
    );
    return { ...profile, id: existing.id, createdAt: existing.createdAt, updatedAt: now };
  }

  const id = uuidv4();
  await db.runAsync(
    `INSERT INTO user_profile (id, gender, age, height_cm, weight_kg, activity_level, goal, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    id,
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
