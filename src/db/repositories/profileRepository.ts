import { getDatabase } from "../database";
import type { UserProfileRow } from "../rows";
import { v4 as uuidv4 } from "uuid";
import type { UserProfile } from "@/types/profile";
import { getCurrentUserId } from "../accountScope";
import { withWriteTransaction } from "../transactions";

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

export async function getProfile(ownerUserId = getCurrentUserId()): Promise<UserProfile | null> {
  const db = await getDatabase();
  const row = await db.getFirstAsync<UserProfileRow>(
    "SELECT * FROM user_profile WHERE owner_user_id = ? LIMIT 1",
    ownerUserId
  );
  return row ? rowToProfile(row) : null;
}

async function saveProfile(
  profile: Omit<UserProfile, "id" | "createdAt" | "updatedAt">,
  ownerUserId: string,
  remote?: Omit<UserProfile, "id">,
  assertCurrent: () => void = () => undefined
): Promise<UserProfile> {
  const db = await getDatabase();
  return withWriteTransaction(db, async (txn) => {
    assertCurrent();
    const row = await txn.getFirstAsync<UserProfileRow>(
      "SELECT * FROM user_profile WHERE owner_user_id = ? LIMIT 1",
      ownerUserId
    );
    const id = row?.id ?? uuidv4();
    const now = new Date().toISOString();
    const createdAt = remote?.createdAt ?? row?.created_at ?? now;
    const updatedAt = remote?.updatedAt ?? now;
    if (row) {
      await txn.runAsync(
        `UPDATE user_profile SET gender = ?, age = ?, height_cm = ?, weight_kg = ?, activity_level = ?,
         goal = ?, created_at = ?, updated_at = ? WHERE id = ? AND owner_user_id = ?`,
        profile.gender,
        profile.age,
        profile.heightCm,
        profile.weightKg,
        profile.activityLevel,
        profile.goal,
        createdAt,
        updatedAt,
        id,
        ownerUserId
      );
    } else {
      await txn.runAsync(
        `INSERT INTO user_profile (id, owner_user_id, gender, age, height_cm, weight_kg,
         activity_level, goal, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        id,
        ownerUserId,
        profile.gender,
        profile.age,
        profile.heightCm,
        profile.weightKg,
        profile.activityLevel,
        profile.goal,
        createdAt,
        updatedAt
      );
    }
    assertCurrent();
    return { ...profile, id, createdAt, updatedAt };
  });
}

export async function upsertProfile(
  profile: Omit<UserProfile, "id" | "createdAt" | "updatedAt">
): Promise<UserProfile> {
  return saveProfile(profile, getCurrentUserId());
}

export async function replaceProfileFromRemote(
  profile: Omit<UserProfile, "id">,
  ownerUserId: string,
  assertCurrent: () => void
): Promise<UserProfile> {
  return saveProfile(profile, ownerUserId, profile, assertCurrent);
}
