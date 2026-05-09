import { View, Text, StyleSheet, ScrollView } from "react-native";

export default function StatsScreen() {
  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>统计</Text>
      <Text style={styles.subtitle}>查看你的饮食数据</Text>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>本周热量趋势</Text>
        <View style={styles.placeholder}>
          <Text style={styles.placeholderText}>图表将在后续阶段实现</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>今日营养素分布</Text>
        <View style={styles.placeholder}>
          <Text style={styles.placeholderText}>图表将在后续阶段实现</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>饮品热量占比</Text>
        <View style={styles.placeholder}>
          <Text style={styles.placeholderText}>图表将在后续阶段实现</Text>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#f5f5f5",
    padding: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: "bold",
    color: "#333",
  },
  subtitle: {
    fontSize: 14,
    color: "#666",
    marginTop: 4,
    marginBottom: 20,
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
  cardTitle: {
    fontSize: 16,
    fontWeight: "600",
    color: "#333",
    marginBottom: 12,
  },
  placeholder: {
    height: 150,
    backgroundColor: "#f9f9f9",
    borderRadius: 8,
    justifyContent: "center",
    alignItems: "center",
  },
  placeholderText: {
    fontSize: 14,
    color: "#999",
  },
});
