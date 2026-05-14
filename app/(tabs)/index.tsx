import { View, Text, StyleSheet, ScrollView } from "react-native";
import { useEffect, useState, useCallback } from "react";
import { useFocusEffect } from "expo-router";
import { MetricCard } from "../../src/components/MetricCard";
import { FoodLogItem } from "../../src/components/FoodLogItem";
import { getTodaySummary, getTodayLogs } from "../../src/features/summary/summaryService";
import { getToday, formatDate } from "../../src/utils/date";
import type { DailySummary, FoodLog } from "../../src/types/log";

export default function HomeScreen() {
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [logs, setLogs] = useState<FoodLog[]>([]);
  const today = getToday();

  useFocusEffect(
    useCallback(() => {
      (async () => {
        const [s, l] = await Promise.all([getTodaySummary(today), getTodayLogs(today)]);
        setSummary(s);
        setLogs(l);
      })();
    }, [today])
  );

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.dateText}>今日总览</Text>
        <Text style={styles.dateSubText}>{formatDate(today)}</Text>
      </View>

      <View style={styles.calorieCard}>
        <Text style={styles.cardTitle}>热量摄入</Text>
        <View style={styles.calorieRow}>
          <Text style={styles.calorieValue}>{Math.round(summary?.totalKcal ?? 0)}</Text>
          <Text style={styles.calorieUnit}>/ 2000 kcal</Text>
        </View>
        <View style={styles.progressBar}>
          <View
            style={[
              styles.progressFill,
              { width: `${Math.min(((summary?.totalKcal ?? 0) / 2000) * 100, 100)}%` },
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
            target={60}
            color="#2196F3"
          />
        </View>
        <View style={styles.macroCardWrapper}>
          <MetricCard
            label="脂肪"
            value={summary?.totalFat ?? 0}
            unit="g"
            target={65}
            color="#FF9800"
          />
        </View>
        <View style={styles.macroCardWrapper}>
          <MetricCard
            label="碳水"
            value={summary?.totalCarbs ?? 0}
            unit="g"
            target={300}
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
            target={50}
            color="#E91E63"
          />
        </View>
        <View style={styles.macroCardWrapper}>
          <MetricCard
            label="钠"
            value={summary?.totalSodium ?? 0}
            unit="mg"
            target={2300}
            color="#9C27B0"
          />
        </View>
        <View style={styles.macroCardWrapper}>
          <MetricCard
            label="咖啡因"
            value={summary?.totalCaffeine ?? 0}
            unit="mg"
            target={400}
            color="#795548"
          />
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>今日记录</Text>
        {logs.length === 0 ? (
          <Text style={styles.emptyText}>还没有记录，去添加页面记录今日饮食吧</Text>
        ) : (
          logs.map((log) => <FoodLogItem key={log.id} log={log} />)
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
  emptyText: { fontSize: 14, color: "#999", textAlign: "center", paddingVertical: 20 },
});
