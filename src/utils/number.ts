export function round(n: number, decimals: number = 0): number {
  const factor = Math.pow(10, decimals);
  return Math.round(n * factor) / factor;
}
