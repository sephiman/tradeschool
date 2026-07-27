import { describe, expect, it } from "vitest";
import { GENERIC_FORMULAS } from "./FormulaReminder";

describe("GENERIC_FORMULAS mapping", () => {
  it("contains generic formulas for all registered calculation types in both en and es", () => {
    const requiredKeys = [
      "liquidation_price",
      "funding_payment",
      "initial_margin",
      "net_pnl",
      "market_cap",
      "fdv",
      "position_size_from_risk",
      "expectancy",
      "net_delta",
      "venue_premium_pct",
      "style_net_result",
    ];

    for (const key of requiredKeys) {
      expect(GENERIC_FORMULAS[key]).toBeDefined();
      expect(GENERIC_FORMULAS[key].en).toBeTruthy();
      expect(GENERIC_FORMULAS[key].es).toBeTruthy();
      // Ensure formula reminder does NOT instantiate numbers from exercise
      expect(GENERIC_FORMULAS[key].en).not.toMatch(/\d{4,}/);
    }
  });

  it("liquidation_price generic formula correctly shows symbols without numbers", () => {
    const item = GENERIC_FORMULAS["liquidation_price"];
    expect(item.en).toBe("liq = entry × (1 ∓ 1/leverage ± mmr)");
    expect(item.es).toBe("liq = entrada × (1 ∓ 1/apalancamiento ± mmr)");
  });
});
