import {
  ActivityIndicator,
  Alert,
  Dimensions,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useState, useCallback, useEffect } from "react";
import { useFocusEffect } from "expo-router";
import { LineChart, PieChart } from "react-native-chart-kit";
import {
  getWeeklyData,
  getTodayMealBreakdown,
  getTodayOverview,
} from "../../src/features/stats/statsService";
import { EmptyState } from "../../src/components/EmptyState";
import { round } from "../../src/utils/number";
import type {
  WeeklyData,
  MealBreakdownItem,
  TodayOverview,
} from "../../src/features/stats/statsService";
import { useAuth } from "../../src/features/auth/AuthContext";
import type { WeeklyReportResponse } from "../../src/api/types";
import { getToday } from "../../src/utils/date";
import {
  formatCoverage,
  formatWeeklyChange,
  getWeeklyReportProviderLabel,
} from "../../src/features/stats/weeklyReportPresentation";

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
  const { apiRequest, lastSyncAt, status } = useAuth();
  const [weekly, setWeekly] = useState<WeeklyData | null>(null);
  const [mealBreakdown, setMealBreakdown] = useState<MealBreakdownItem[]>([]);
  const [overview, setOverview] = useState<TodayOverview | null>(null);
  const [report, setReport] = useState<WeeklyReportResponse | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);
  const accountReady = status === "authenticated" || status === "offline";

  const loadData = useCallback(async () => {
    if (!accountReady) return;
    const [w, m, o] = await Promise.all([
      getWeeklyData(),
      getTodayMealBreakdown(),
      getTodayOverview(),
    ]);
    setWeekly(w);
    setMealBreakdown(m);
    setOverview(o);
  }, [accountReady]);

  useFocusEffect(
    useCallback(() => {
      if (accountReady) loadData();
    }, [accountReady, loadData])
  );

  useEffect(() => {
    if (accountReady && lastSyncAt !== null) loadData();
  }, [accountReady, lastSyncAt, loadData]);

  const pieData = mealBreakdown.map((item) => ({
    name: item.name,
    kcal: item.kcal,
    color: item.color,
    legendFontColor: "#666",
    legendFontSize: 12,
  }));

  const generateReport = async () => {
    if (status === "offline") {
      Alert.alert("当前处于离线模式", "AI 周报需要连接后端，已有本地统计仍可正常查看。");
      return;
    }
    setGeneratingReport(true);
    try {
      const response = await apiRequest<WeeklyReportResponse>(
        "/api/v1/ai/reports/weekly:generate",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ end_date: getToday(), locale: "zh-CN" }),
        }
      );
      setReport(response);
    } catch {
      Alert.alert("周报生成失败", "后端暂时不可用，请稍后重试。现有统计数据不会受到影响。");
    } finally {
      setGeneratingReport(false);
    }
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>统计</Text>
      <Text style={styles.subtitle}>查看你的饮食数据</Text>

      <View style={[styles.card, styles.reportCard]}>
        <View style={styles.reportHeader}>
          <View style={styles.reportHeaderText}>
            <Text style={styles.reportEyebrow}>PERSONALIZED AI REPORT</Text>
            <Text style={styles.reportTitle}>个性化营养周报</Text>
          </View>
          {report && <Text style={styles.reportBadge}>{getWeeklyReportProviderLabel(report)}</Text>}
        </View>

        {report ? (
          <View>
            <Text style={styles.reportHeadline}>{report.narrative.headline}</Text>
            <Text style={styles.reportSummary}>{report.narrative.summary}</Text>

            <View style={styles.reportMetrics}>
              <View style={styles.reportMetric}>
                <Text style={styles.reportMetricValue}>
                  {formatCoverage(report.facts.current.days_with_records)}
                </Text>
                <Text style={styles.reportMetricLabel}>记录完整度</Text>
              </View>
              <View style={styles.reportMetric}>
                <Text style={styles.reportMetricValue}>
                  {Math.round(report.facts.current.average_kcal)}
                </Text>
                <Text style={styles.reportMetricLabel}>日均 kcal（按 7 天）</Text>
              </View>
            </View>
            <Text style={styles.comparisonText}>
              {formatWeeklyChange(report.facts.changes.average_kcal_percent)}
            </Text>

            <Text style={styles.reportSectionTitle}>本周要点</Text>
            {report.narrative.highlights.map((item) => (
              <Text key={item} style={styles.reportListItem}>
                • {item}
              </Text>
            ))}
            <Text style={styles.reportSectionTitle}>下周行动</Text>
            {report.narrative.actions.map((item, index) => (
              <Text key={item} style={styles.reportListItem}>
                {index + 1}. {item}
              </Text>
            ))}
            {(report.warnings ?? []).map((warning) => (
              <Text key={warning} style={styles.reportWarning}>
                {warning}
              </Text>
            ))}
            <Text style={styles.reportMeta}>
              {report.model} · {report.latency_ms} ms · {report.usage.total_tokens} tokens ·
              数据指纹 {report.data_fingerprint.slice(0, 8)}
            </Text>
            <Text style={styles.disclaimer}>{report.disclaimer}</Text>
          </View>
        ) : (
          <Text style={styles.reportIntro}>
            汇总最近两周记录，结合个人目标生成结构化结论。营养数字由后端确定性计算，AI 只负责解释。
          </Text>
        )}

        <TouchableOpacity
          accessibilityRole="button"
          style={[styles.reportButton, generatingReport && styles.reportButtonDisabled]}
          disabled={generatingReport}
          onPress={generateReport}
        >
          {generatingReport ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.reportButtonText}>{report ? "重新生成周报" : "生成本周周报"}</Text>
          )}
        </TouchableOpacity>
      </View>

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
          <EmptyState icon="pie-chart-outline" title="今日暂无记录" />
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
          <EmptyState icon="trending-up-outline" title="暂无数据" subtitle="请先添加几天记录" />
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
          <EmptyState icon="cafe-outline" title="暂无咖啡因数据" />
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
          <EmptyState icon="water-outline" title="今日暂无记录" />
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
  reportCard: { backgroundColor: "#F1F8E9", borderWidth: 1, borderColor: "#C5E1A5" },
  reportHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 8,
  },
  reportHeaderText: { flex: 1 },
  reportEyebrow: { fontSize: 10, letterSpacing: 1, color: "#558B2F", fontWeight: "700" },
  reportTitle: { fontSize: 20, fontWeight: "800", color: "#263238", marginTop: 3 },
  reportBadge: {
    maxWidth: 112,
    fontSize: 10,
    lineHeight: 14,
    color: "#33691E",
    backgroundColor: "#DCEDC8",
    paddingHorizontal: 7,
    paddingVertical: 5,
    borderRadius: 6,
    textAlign: "center",
  },
  reportIntro: { color: "#546E7A", fontSize: 13, lineHeight: 20, marginTop: 12 },
  reportHeadline: { fontSize: 17, fontWeight: "700", color: "#263238", marginTop: 14 },
  reportSummary: { color: "#455A64", fontSize: 13, lineHeight: 20, marginTop: 6 },
  reportMetrics: { flexDirection: "row", gap: 10, marginTop: 14 },
  reportMetric: { flex: 1, backgroundColor: "#fff", borderRadius: 10, padding: 12 },
  reportMetricValue: { fontSize: 18, fontWeight: "800", color: "#2E7D32" },
  reportMetricLabel: { color: "#78909C", fontSize: 10, marginTop: 3 },
  comparisonText: { color: "#33691E", fontWeight: "600", fontSize: 12, marginTop: 9 },
  reportSectionTitle: { color: "#37474F", fontWeight: "700", fontSize: 13, marginTop: 14 },
  reportListItem: { color: "#546E7A", fontSize: 12, lineHeight: 19, marginTop: 3 },
  reportWarning: {
    color: "#E65100",
    backgroundColor: "#FFF3E0",
    borderRadius: 6,
    padding: 8,
    fontSize: 11,
    lineHeight: 16,
    marginTop: 8,
  },
  reportMeta: { color: "#90A4AE", fontSize: 10, lineHeight: 15, marginTop: 12 },
  disclaimer: { color: "#90A4AE", fontSize: 10, lineHeight: 15, marginTop: 4 },
  reportButton: {
    height: 44,
    borderRadius: 10,
    backgroundColor: "#2E7D32",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 14,
  },
  reportButtonDisabled: { opacity: 0.55 },
  reportButtonText: { color: "#fff", fontSize: 14, fontWeight: "700" },
});
