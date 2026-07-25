import { View, Text, StyleSheet } from "react-native";

interface MetricCardProps {
  label: string;
  value: number;
  unit: string;
  target?: number;
  color?: string;
}

export function MetricCard({ label, value, unit, target, color = "#4CAF50" }: MetricCardProps) {
  const progress = target ? Math.min(value / target, 1) : undefined;

  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.valueRow}>
        <Text style={[styles.value, { color }]}>{Math.round(value)}</Text>
        <Text style={styles.unit}>
          {target ? `/ ${target}` : ""} {unit}
        </Text>
      </View>
      {progress !== undefined && (
        <View style={styles.progressBar}>
          <View
            style={[styles.progressFill, { width: `${progress * 100}%`, backgroundColor: color }]}
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    padding: 16,
    borderRadius: 12,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  label: {
    fontSize: 12,
    color: "#666",
    marginBottom: 4,
  },
  valueRow: {
    flexDirection: "row",
    alignItems: "baseline",
  },
  value: {
    fontSize: 24,
    fontWeight: "bold",
  },
  unit: {
    fontSize: 12,
    color: "#999",
    marginLeft: 4,
  },
  progressBar: {
    height: 6,
    backgroundColor: "#e0e0e0",
    borderRadius: 3,
    marginTop: 8,
  },
  progressFill: {
    height: 6,
    borderRadius: 3,
  },
});
