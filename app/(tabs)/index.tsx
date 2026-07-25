import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from "react-native";
import { useState, useCallback, useEffect } from "react";
import { router, useFocusEffect } from "expo-router";
import { MetricCard } from "../../src/components/MetricCard";
import { FoodLogItem } from "../../src/components/FoodLogItem";
import { ReminderCard } from "../../src/components/ReminderCard";
import { EmptyState } from "../../src/components/EmptyState";
import { getTodaySummary, getTodayLogs } from "../../src/features/summary/summaryService";
import { getProfile } from "../../src/db/repositories/profileRepository";
import { calcDailyTargets } from "../../src/features/profile/profileCalculator";
import { getEnabledRules } from "../../src/db/repositories/reminderRepository";
import { generateReminders } from "../../src/features/summary/reminderService";
import { getToday, formatDate } from "../../src/utils/date";
import type { DailySummary, FoodLog } from "../../src/types/log";
import type { DailyTargets } from "../../src/types/profile";
import type { Reminder } from "../../src/types/reminder";
import { useAuth } from "../../src/features/auth/AuthContext";

export default function HomeScreen() {
  const { lastSyncAt, status } = useAuth();
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [logs, setLogs] = useState<FoodLog[]>([]);
  const [targets, setTargets] = useState<DailyTargets | null>(null);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [hasProfile, setHasProfile] = useState<boolean | null>(null);
  const today = getToday();
  const accountReady = status === "authenticated" || status === "offline";

  const loadData = useCallback(async () => {
    if (!accountReady) return;
    const [s, l] = await Promise.all([getTodaySummary(today), getTodayLogs(today)]);
    setSummary(s);
    setLogs(l);

    const profile = await getProfile();
    setHasProfile(profile !== null);
    if (profile) {
      const t = calcDailyTargets(profile);
      setTargets(t);
      const rules = await getEnabledRules();
      setReminders(generateReminders(s, t, rules));
    } else {
      setTargets(null);
      setReminders([]);
    }
  }, [accountReady, today]);

  useFocusEffect(
    useCallback(() => {
      if (accountReady) loadData();
    }, [accountReady, loadData])
  );

  useEffect(() => {
    if (accountReady && lastSyncAt !== null) loadData();
  }, [accountReady, lastSyncAt, loadData]);

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.dateText}>今日总览</Text>
        <Text style={styles.dateSubText}>{formatDate(today)}</Text>
      </View>

      {hasProfile === false && (
        <View style={styles.onboardingCard}>
          <View style={styles.onboardingText}>
            <Text style={styles.onboardingTitle}>先生成你的个性化营养目标</Text>
            <Text style={styles.onboardingDesc}>
              填写年龄、身高、体重、生理性别、活动量和目标后，首页不再使用通用参考值。
            </Text>
          </View>
          <TouchableOpacity
            style={styles.onboardingButton}
            onPress={() => router.push("/edit-profile")}
          >
            <Text style={styles.onboardingButtonText}>去设置</Text>
          </TouchableOpacity>
        </View>
      )}

      <View style={styles.calorieCard}>
        <Text style={styles.cardTitle}>热量摄入</Text>
        <View style={styles.calorieRow}>
          <Text style={styles.calorieValue}>{Math.round(summary?.totalKcal ?? 0)}</Text>
          <Text style={styles.calorieUnit}>/ {targets?.kcal ?? 2000} kcal</Text>
        </View>
        <View style={styles.progressBar}>
          <View
            style={[
              styles.progressFill,
              {
                width: `${Math.min(
                  ((summary?.totalKcal ?? 0) / (targets?.kcal ?? 2000)) * 100,
                  100
                )}%`,
              },
            ]}
          />
        </View>
      </View>

      <View style={styles.macroRow}>
        <View style={styles.macroCardWrapper}>
          <MetricCard
            label="蛋白质"
            value={summary?.totalProtein ?? 0}
            unit="g"
            target={targets?.protein ?? 60}
            color="#2196F3"
          />
        </View>
        <View style={styles.macroCardWrapper}>
          <MetricCard
            label="脂肪"
            value={summary?.totalFat ?? 0}
            unit="g"
            target={targets?.fat ?? 65}
            color="#FF9800"
          />
        </View>
        <View style={styles.macroCardWrapper}>
          <MetricCard
            label="碳水"
            value={summary?.totalCarbs ?? 0}
            unit="g"
            target={targets?.carbs ?? 300}
            color="#4CAF50"
          />
        </View>
      </View>

      <View style={styles.macroRow}>
        <View style={styles.macroCardWrapper}>
          <MetricCard
            label="糖"
            value={summary?.totalSugar ?? 0}
            unit="g"
            target={targets?.sugar ?? 50}
            color="#E91E63"
          />
        </View>
        <View style={styles.macroCardWrapper}>
          <MetricCard
            label="钠"
            value={summary?.totalSodium ?? 0}
            unit="mg"
            target={targets?.sodium ?? 2300}
            color="#9C27B0"
          />
        </View>
        <View style={styles.macroCardWrapper}>
          <MetricCard
            label="咖啡因"
            value={summary?.totalCaffeine ?? 0}
            unit="mg"
            target={targets?.caffeine ?? 400}
            color="#795548"
          />
        </View>
      </View>

      {reminders.length > 0 && (
        <View style={styles.reminderSection}>
          {reminders.map((r, i) => (
            <View key={i} style={styles.reminderWrapper}>
              <ReminderCard icon={r.icon} message={r.message} type={r.type} />
            </View>
          ))}
        </View>
      )}

      <View style={styles.card}>
        <Text style={styles.cardTitle}>今日记录</Text>
        {logs.length === 0 ? (
          <EmptyState
            icon="restaurant-outline"
            title="还没有记录"
            subtitle="去添加页面记录今日饮食吧"
          />
        ) : (
          logs.map((log) => <FoodLogItem key={log.id} log={log} onDeleted={loadData} />)
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  header: { padding: 20, paddingBottom: 10 },
  dateText: { fontSize: 24, fontWeight: "bold", color: "#333" },
  dateSubText: { fontSize: 14, color: "#666", marginTop: 4 },
  onboardingCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#E8F5E9",
    borderColor: "#A5D6A7",
    borderWidth: 1,
    marginHorizontal: 16,
    marginBottom: 12,
    padding: 14,
    borderRadius: 12,
    gap: 12,
  },
  onboardingText: { flex: 1 },
  onboardingTitle: { fontSize: 14, fontWeight: "700", color: "#2E5D32" },
  onboardingDesc: { fontSize: 11, color: "#607662", lineHeight: 17, marginTop: 4 },
  onboardingButton: {
    backgroundColor: "#4CAF50",
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: 9,
  },
  onboardingButtonText: { color: "#fff", fontSize: 13, fontWeight: "600" },
  calorieCard: {
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginBottom: 12,
    padding: 16,
    borderRadius: 12,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  cardTitle: { fontSize: 16, fontWeight: "600", color: "#333", marginBottom: 12 },
  calorieRow: { flexDirection: "row", alignItems: "baseline" },
  calorieValue: { fontSize: 36, fontWeight: "bold", color: "#4CAF50" },
  calorieUnit: { fontSize: 14, color: "#999", marginLeft: 8 },
  progressBar: { height: 8, backgroundColor: "#e0e0e0", borderRadius: 4, marginTop: 12 },
  progressFill: { height: 8, backgroundColor: "#4CAF50", borderRadius: 4 },
  macroRow: { flexDirection: "row", marginHorizontal: 16, marginBottom: 12, gap: 8 },
  macroCardWrapper: { flex: 1 },
  reminderSection: { marginHorizontal: 16, marginBottom: 12, gap: 8 },
  reminderWrapper: {},
  card: {
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginBottom: 12,
    padding: 16,
    borderRadius: 12,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
});
