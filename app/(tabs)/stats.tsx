import { View, Text, StyleSheet, ScrollView, Dimensions } from "react-native";
import { useState, useCallback } from "react";
import { useFocusEffect } from "expo-router";
import { LineChart, PieChart } from "react-native-chart-kit";
import { getWeeklyData, getTodayMealBreakdown, getTodayOverview } from "../../src/features/stats/statsService";
import { round } from "../../src/utils/number";
import type { WeeklyData, MealBreakdownItem, TodayOverview } from "../../src/features/stats/statsService";

const screenWidth = Dimensions.get("window").width - 32;

const chartConfig = {
  backgroundGradientFrom: "#fff",
  backgroundGradientTo: "#fff",
  color: (opacity = 1) => `rgba(76, 175, 80, ${opacity})`,
  labelColor: () => "#666",
  propsForDots: { r: "4", strokeWidth: "2", stroke: "#4CAF50" },
  decimalPlaces: 0,
};

export default function StatsScreen() {
  const [weekly, setWeekly] = useState<WeeklyData | null>(null);
  const [mealBreakdown, setMealBreakdown] = useState<MealBreakdownItem[]>([]);
  const [overview, setOverview] = useState<TodayOverview | null>(null);

  useFocusEffect(
    useCallback(() => {
      (async () => {
        const [w, m, o] = await Promise.all([
          getWeeklyData(),
          getTodayMealBreakdown(),
          getTodayOverview(),
        ]);
        setWeekly(w);
        setMealBreakdown(m);
        setOverview(o);
      })();
    }, [])
  );

  const pieData = mealBreakdown.map((item) => ({
    name: item.name,
    kcal: item.kcal,
    color: item.color,
    legendFontColor: "#666",
    legendFontSize: 12,
  }));

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>统计</Text>
      <Text style={styles.subtitle}>查看你的饮食数据</Text>

      <View style={styles.overviewCard}>
        <Text style={styles.cardTitle}>今日总摄入</Text>
        <View style={styles.overviewGrid}>
          <View style={styles.overviewItem}>
            <Text style={styles.overviewValue}>{overview?.totalKcal ?? 0}</Text>
            <Text style={styles.overviewLabel}>热量(kcal)</Text>
          </View>
          <View style={styles.overviewItem}>
            <Text style={styles.overviewValue}>{overview?.totalProtein ?? 0}g</Text>
            <Text style={styles.overviewLabel}>蛋白质</Text>
          </View>
          <View style={styles.overviewItem}>
            <Text style={styles.overviewValue}>{overview?.totalFat ?? 0}g</Text>
            <Text style={styles.overviewLabel}>脂肪</Text>
          </View>
          <View style={styles.overviewItem}>
            <Text style={styles.overviewValue}>{overview?.totalCarbs ?? 0}g</Text>
            <Text style={styles.overviewLabel}>碳水</Text>
          </View>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>三餐热量占比</Text>
        {pieData.length > 0 ? (
          <PieChart
            data={pieData}
            width={screenWidth - 32}
            height={180}
            chartConfig={chartConfig}
            accessor="kcal"
            backgroundColor="transparent"
            paddingLeft="0"
            absolute
          />
        ) : (
          <Text style={styles.emptyText}>今日暂无记录</Text>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>一周热量趋势</Text>
        {weekly && weekly.kcalData.some((v) => v > 0) ? (
          <LineChart
            data={{
              labels: weekly.labels,
              datasets: [{ data: weekly.kcalData.map((v) => v || 0) }],
            }}
            width={screenWidth - 32}
            height={200}
            chartConfig={{
              ...chartConfig,
              color: (opacity = 1) => `rgba(76, 175, 80, ${opacity})`,
            }}
            bezier
            style={styles.chart}
          />
        ) : (
          <Text style={styles.emptyText}>暂无数据，请先添加几天记录</Text>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>一周咖啡因趋势</Text>
        {weekly && weekly.caffeineData.some((v) => v > 0) ? (
          <LineChart
            data={{
              labels: weekly.labels,
              datasets: [{ data: weekly.caffeineData.map((v) => v || 0) }],
            }}
            width={screenWidth - 32}
            height={200}
            chartConfig={{
              ...chartConfig,
              color: (opacity = 1) => `rgba(121, 85, 72, ${opacity})`,
            }}
            bezier
            style={styles.chart}
          />
        ) : (
          <Text style={styles.emptyText}>暂无咖啡因数据</Text>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>饮品热量占比</Text>
        {overview && overview.totalKcal > 0 ? (
          <View>
            <View style={styles.drinkRow}>
              <Text style={styles.drinkLabel}>饮品热量</Text>
              <Text style={styles.drinkValue}>{overview.drinkKcal} kcal</Text>
            </View>
            <View style={styles.progressBar}>
              <View
                style={[
                  styles.progressFill,
                  { width: `${Math.min(overview.drinkRatio * 100, 100)}%` },
                ]}
              />
            </View>
            <Text style={styles.drinkPercent}>
              占今日总摄入的 {round(overview.drinkRatio * 100, 1)}%
            </Text>
          </View>
        ) : (
          <Text style={styles.emptyText}>今日暂无记录</Text>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", padding: 20 },
  title: { fontSize: 24, fontWeight: "bold", color: "#333" },
  subtitle: { fontSize: 14, color: "#666", marginTop: 4, marginBottom: 20 },
  overviewCard: {
    backgroundColor: "#fff",
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  card: {
    backgroundColor: "#fff",
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  cardTitle: { fontSize: 16, fontWeight: "600", color: "#333", marginBottom: 12 },
  overviewGrid: { flexDirection: "row", justifyContent: "space-around" },
  overviewItem: { alignItems: "center" },
  overviewValue: { fontSize: 20, fontWeight: "bold", color: "#4CAF50" },
  overviewLabel: { fontSize: 11, color: "#999", marginTop: 2 },
  chart: { borderRadius: 8, marginLeft: -16 },
  emptyText: { fontSize: 14, color: "#999", textAlign: "center", paddingVertical: 30 },
  drinkRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  drinkLabel: { fontSize: 14, color: "#333" },
  drinkValue: { fontSize: 14, fontWeight: "600", color: "#795548" },
  progressBar: { height: 10, backgroundColor: "#e0e0e0", borderRadius: 5 },
  progressFill: { height: 10, backgroundColor: "#795548", borderRadius: 5 },
  drinkPercent: { fontSize: 12, color: "#999", marginTop: 6, textAlign: "right" },
});
