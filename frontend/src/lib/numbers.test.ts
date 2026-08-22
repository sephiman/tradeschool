import { describe, expect, it } from "vitest";
import { matchOptionValue, parseLocalizedNumber } from "@/lib/numbers";

describe("parseLocalizedNumber", () => {
  it("reads the separators the backend formatter emits for each locale", () => {
    expect(parseLocalizedNumber("70,000", "en")).toBe(70000);
    expect(parseLocalizedNumber("70.000", "es")).toBe(70000);
    expect(parseLocalizedNumber("1,234,567.5", "en")).toBe(1234567.5);
    expect(parseLocalizedNumber("1.234.567,5", "es")).toBe(1234567.5);
    expect(parseLocalizedNumber("35,00", "es")).toBe(35);
    expect(parseLocalizedNumber("-1.000,25", "es")).toBe(-1000.25);
  });

  it("is the reason the ES calculator match had to change: parseFloat gets 70.000 wrong", () => {
    // The bug this file exists to prevent — the old code read the ES label as seventy.
    expect(parseFloat("70.000")).toBe(70);
    expect(parseLocalizedNumber("70.000", "es")).toBe(70000);
  });

  it("returns NaN for anything that is not a number", () => {
    expect(parseLocalizedNumber("", "en")).toBeNaN();
    expect(parseLocalizedNumber("long", "en")).toBeNaN();
    expect(parseLocalizedNumber("0.05%", "en")).toBeNaN();
  });

  it("falls back to the EN separators for an unknown locale, as LocalizedText does", () => {
    expect(parseLocalizedNumber("70,000", "de")).toBe(70000);
  });
});

describe("matchOptionValue", () => {
  const options = [
    { id: "o0", value: "1.000,00" },
    { id: "o1", value: "500,00" },
    { id: "o2", value: "2.000,00" },
  ];

  it("finds the ES-labelled option a raw calculator result lands on", () => {
    expect(matchOptionValue(options, 1000, "es")?.id).toBe("o0");
    expect(matchOptionValue(options, 2000, "es")?.id).toBe("o2");
  });

  it("returns null when the result is not one of the options", () => {
    expect(matchOptionValue(options, 1234, "es")).toBeNull();
  });

  it("picks the closest option, not the first one inside the tolerance", () => {
    // Four display quanta apart on a four-decimal exercise is under the 0.001 tolerance, so a
    // first-match scan could select the neighbour of the real answer.
    const tight = [
      { id: "o0", value: "0.0800" },
      { id: "o1", value: "0.0804" },
    ];
    expect(matchOptionValue(tight, 0.0804, "en")?.id).toBe("o1");
    expect(matchOptionValue(tight, 0.08, "en")?.id).toBe("o0");
  });

  it("ignores options with no numeric value rather than matching them", () => {
    expect(matchOptionValue([{ id: "o0", value: undefined }], 0, "en")).toBeNull();
  });
});
