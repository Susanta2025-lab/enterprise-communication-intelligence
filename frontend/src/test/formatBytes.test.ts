import { describe, expect, it } from "vitest";

import { formatReportedSize } from "../lib/formatBytes";

describe("reported attachment size formatting", () => {
  it("formats bytes, KiB, and MiB", () => {
    expect(formatReportedSize(512)).toBe("512 B");
    expect(formatReportedSize(1024)).toBe("1 KiB");
    expect(formatReportedSize(1536)).toBe("1.5 KiB");
    expect(formatReportedSize(5 * 1024 * 1024)).toBe("5 MiB");
    expect(formatReportedSize(1_800_000)).toBe("1.7 MiB");
  });

  it("handles unavailable values", () => {
    expect(formatReportedSize(-1)).toBe("Size unavailable");
    expect(formatReportedSize(Number.NaN)).toBe("Size unavailable");
  });
});
