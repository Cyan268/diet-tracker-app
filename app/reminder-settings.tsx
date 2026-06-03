import { View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput, Switch, Alert } from "react-native";
import { router } from "expo-router";
import { useState, useEffect } from "react";
import { Ionicons } from "@expo/vector-icons";
import { getAllRules, updateRule } from "../src/db/repositories/reminderRepository";
import type { ReminderRule } from "../src/types/reminder";

const METRIC_LABELS: Record<string, string> = {
  kcal: "热量",
  protein: "蛋白质",
  sugar: "糖",
  sodium: "钠",
  caffeine: "咖啡因",
};

const METRIC_UNITS: Record<string, string> = {
  kcal: "kcal",
  protein: "g",
  sugar: "g",
  sodium: "mg",
  caffeine: "mg",
};

const RULE_TYPE_LABELS: Record<string, string> = {
  too_high: "超过上限时提醒",
  too_low: "低于下限时提醒",
};

interface RuleState {
  rule: ReminderRule;
  enabled: boolean;
  thresholdStr: string;
  changed: boolean;
}

export default function ReminderSettingsScreen() {
  const [rules, setRules] = useState<RuleState[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAllRules().then((rs) => {
      setRules(
        rs.map((r) => ({
          rule: r,
          enabled: r.enabled,
          thresholdStr: r.thresholdType === "ratio_of_target"
            ? String(Math.round(r.thresholdValue * 100))
            : String(r.thresholdValue),
          changed: false,
        }))
      );
      setLoading(false);
    });
  }, []);

  const updateRuleState = (index: number, updates: Partial<RuleState>) => {
    setRules((prev) =>
      prev.map((r, i) => (i === index ? { ...r, ...updates, changed: true } : r))
    );
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      for (const rs of rules) {
        if (!rs.changed) continue;

        const thresholdValue = rs.rule.thresholdType === "ratio_of_target"
          ? (parseFloat(rs.thresholdStr) || 0) / 100
          : parseFloat(rs.thresholdStr) || 0;

        await updateRule(rs.rule.id, {
          enabled: rs.enabled,
          thresholdValue,
        });
      }
      router.back();
    } catch (e) {
      Alert.alert("错误", "保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>加载中...</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color="#333" />
        </TouchableOpacity>
        <Text style={styles.title}>提醒设置</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.tipCard}>
        <Ionicons name="information-circle" size={20} color="#2196F3" />
        <Text style={styles.tipText}>
          开启或关闭提醒规则，调整触发阈值。提醒文案会温和提示，不构成医疗建议。
        </Text>
      </View>

      {rules.map((rs, index) => {
        const metricLabel = METRIC_LABELS[rs.rule.metric] ?? rs.rule.metric;
        const unit = METRIC_UNITS[rs.rule.metric] ?? "";
        const ruleLabel = RULE_TYPE_LABELS[rs.rule.ruleType] ?? rs.rule.ruleType;
        const isRatio = rs.rule.thresholdType === "ratio_of_target";

        return (
          <View key={rs.rule.id} style={styles.ruleCard}>
            <View style={styles.ruleHeader}>
              <View style={styles.ruleTitleRow}>
                <Text style={styles.ruleMetric}>{metricLabel}</Text>
                <Text style={styles.ruleType}>{ruleLabel}</Text>
              </View>
              <Switch
                value={rs.enabled}
                onValueChange={(val) => updateRuleState(index, { enabled: val })}
                trackColor={{ false: "#e0e0e0", true: "#A5D6A7" }}
                thumbColor={rs.enabled ? "#4CAF50" : "#ccc"}
              />
            </View>

            <View style={styles.thresholdRow}>
              <Text style={styles.thresholdLabel}>
                {isRatio ? "目标百分比" : `阈值 (${unit})`}
              </Text>
              <View style={styles.thresholdInputRow}>
                <TextInput
                  style={styles.thresholdInput}
                  keyboardType="numeric"
                  value={rs.thresholdStr}
                  onChangeText={(val) => updateRuleState(index, { thresholdStr: val })}
                  editable={rs.enabled}
                />
                <Text style={styles.thresholdUnit}>{isRatio ? "%" : unit}</Text>
              </View>
            </View>

            {!rs.enabled && <View style={styles.disabledOverlay} />}
          </View>
        );
      })}

      <TouchableOpacity
        style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
        onPress={handleSave}
        disabled={saving}
      >
        <Text style={styles.saveBtnText}>{saving ? "保存中..." : "保存设置"}</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  loadingContainer: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: "#f5f5f5" },
  loadingText: { fontSize: 14, color: "#999" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingTop: 50,
    paddingBottom: 12,
    backgroundColor: "#fff",
  },
  backBtn: { padding: 4 },
  title: { fontSize: 18, fontWeight: "600", color: "#333" },
  tipCard: {
    flexDirection: "row",
    backgroundColor: "#E3F2FD",
    marginHorizontal: 16,
    marginTop: 16,
    padding: 14,
    borderRadius: 10,
    alignItems: "flex-start",
    gap: 8,
  },
  tipText: { flex: 1, fontSize: 13, color: "#555", lineHeight: 18 },
  ruleCard: {
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginTop: 12,
    padding: 14,
    borderRadius: 12,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  ruleHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  ruleTitleRow: { flex: 1 },
  ruleMetric: { fontSize: 16, fontWeight: "600", color: "#333" },
  ruleType: { fontSize: 12, color: "#999", marginTop: 2 },
  thresholdRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 0.5,
    borderTopColor: "#f0f0f0",
  },
  thresholdLabel: { fontSize: 13, color: "#666" },
  thresholdInputRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  thresholdInput: {
    backgroundColor: "#f5f5f5",
    borderRadius: 8,
    paddingHorizontal: 12,
    height: 36,
    width: 80,
    fontSize: 15,
    color: "#333",
    textAlign: "center",
  },
  thresholdUnit: { fontSize: 13, color: "#999", width: 30 },
  disabledOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(255,255,255,0.5)",
    borderRadius: 12,
  },
  saveBtn: {
    backgroundColor: "#4CAF50",
    marginHorizontal: 16,
    marginTop: 20,
    marginBottom: 40,
    borderRadius: 12,
    height: 48,
    justifyContent: "center",
    alignItems: "center",
  },
  saveBtnDisabled: { opacity: 0.6 },
  saveBtnText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});
