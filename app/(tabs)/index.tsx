import { View, Text, StyleSheet, ScrollView } from "react-native";

export default function HomeScreen() {
  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.dateText}>今日总览</Text>
        <Text style={styles.dateSubText}>2026年5月9日 星期五</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>热量摄入</Text>
        <View style={styles.calorieRow}>
          <Text style={styles.calorieValue}>0</Text>
          <Text style={styles.calorieUnit}>/ 2000 kcal</Text>
        </View>
        <View style={styles.progressBar}>
          <View style={[styles.progressFill, { width: "0%" }]} />
        </View>
      </View>

      <View style={styles.macroRow}>
        <View style={[styles.macroCard, { backgroundColor: "#E3F2FD" }]}>
          <Text style={styles.macroLabel}>蛋白质</Text>
          <Text style={styles.macroValue}>0g</Text>
        </View>
        <View style={[styles.macroCard, { backgroundColor: "#FFF3E0" }]}>
          <Text style={styles.macroLabel}>脂肪</Text>
          <Text style={styles.macroValue}>0g</Text>
        </View>
        <View style={[styles.macroCard, { backgroundColor: "#E8F5E9" }]}>
          <Text style={styles.macroLabel}>碳水</Text>
          <Text style={styles.macroValue}>0g</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>今日记录</Text>
        <Text style={styles.emptyText}>还没有记录，去添加页面记录今日饮食吧</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#f5f5f5",
  },
  header: {
    padding: 20,
    paddingBottom: 10,
  },
  dateText: {
    fontSize: 24,
    fontWeight: "bold",
    color: "#333",
  },
  dateSubText: {
    fontSize: 14,
    color: "#666",
    marginTop: 4,
  },
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
  cardTitle: {
    fontSize: 16,
    fontWeight: "600",
    color: "#333",
    marginBottom: 12,
  },
  calorieRow: {
    flexDirection: "row",
    alignItems: "baseline",
  },
  calorieValue: {
    fontSize: 36,
    fontWeight: "bold",
    color: "#4CAF50",
  },
  calorieUnit: {
    fontSize: 14,
    color: "#999",
    marginLeft: 8,
  },
  progressBar: {
    height: 8,
    backgroundColor: "#e0e0e0",
    borderRadius: 4,
    marginTop: 12,
  },
  progressFill: {
    height: 8,
    backgroundColor: "#4CAF50",
    borderRadius: 4,
  },
  macroRow: {
    flexDirection: "row",
    marginHorizontal: 16,
    marginBottom: 12,
    gap: 8,
  },
  macroCard: {
    flex: 1,
    padding: 12,
    borderRadius: 10,
    alignItems: "center",
  },
  macroLabel: {
    fontSize: 12,
    color: "#666",
    marginBottom: 4,
  },
  macroValue: {
    fontSize: 18,
    fontWeight: "bold",
    color: "#333",
  },
  emptyText: {
    fontSize: 14,
    color: "#999",
    textAlign: "center",
    paddingVertical: 20,
  },
});
