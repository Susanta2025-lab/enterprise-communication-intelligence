const KIB = 1024;
const MIB = 1024 * 1024;

export function formatReportedSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return "Size unavailable";
  }
  if (bytes >= MIB) {
    const value = bytes / MIB;
    return Number.isInteger(value) ? `${value} MiB` : `${trimDecimal(value)} MiB`;
  }
  if (bytes >= KIB) {
    const value = bytes / KIB;
    return Number.isInteger(value) ? `${value} KiB` : `${trimDecimal(value)} KiB`;
  }
  return `${bytes} B`;
}

function trimDecimal(value: number): string {
  return value.toFixed(1).replace(/\.0$/, "");
}
