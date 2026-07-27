import { useTranslation } from "react-i18next";

export const GENERIC_FORMULAS: Record<string, { en: string; es: string }> = {
  liquidation_price: {
    en: "liq = entry × (1 ∓ 1/leverage ± mmr)",
    es: "liq = entrada × (1 ∓ 1/apalancamiento ± mmr)",
  },
  funding_payment: {
    en: "funding = notional × rate × (+1 long / −1 short)",
    es: "financiación = notional × tasa × (+1 long / −1 short)",
  },
  initial_margin: {
    en: "margin = (entry × quantity) / leverage",
    es: "margen = (entrada × cantidad) / apalancamiento",
  },
  net_pnl: {
    en: "gross = quantity × (price move) | fees = fee_rate × quantity × (entry + exit) | net = gross − fees",
    es: "bruto = cantidad × (var. precio) | comisiones = tasa × cantidad × (entrada + salida) | neto = bruto − comisiones",
  },
  market_cap: {
    en: "market cap = price × circulating supply",
    es: "cap. mercado = precio × oferta circulante",
  },
  fdv: {
    en: "FDV = price × max supply",
    es: "FDV = precio × oferta máxima",
  },
  position_size_from_risk: {
    en: "quantity = (equity × risk %) / stop distance",
    es: "cantidad = (capital × riesgo %) / distancia al stop",
  },
  expectancy: {
    en: "expectancy = win% × avg win − loss% × avg loss",
    es: "esperanza = %ganado × ganancia prom. − %perdido × pérdida prom.",
  },
  net_delta: {
    en: "delta = taker buy volume − taker sell volume",
    es: "delta = vol. compra taker − vol. venta taker",
  },
  venue_premium_pct: {
    en: "premium % = (price_other − price_ref) / price_ref × 100",
    es: "prima % = (precio_otro − precio_ref) / precio_ref × 100",
  },
  style_net_result: {
    en: "gross = notional × move | net = gross − costs (fees + funding)",
    es: "bruto = notional × movimiento | neto = bruto − costes (comisiones + financiación)",
  },
};

export function FormulaReminder({ formula }: { formula?: string | null }) {
  const { t, i18n } = useTranslation();
  if (!formula) return null;

  const item = GENERIC_FORMULAS[formula];
  if (!item) return null;

  const lang = (i18n.resolvedLanguage || "en").startsWith("es") ? "es" : "en";
  const formulaText = item[lang];

  return (
    <div className="inline-flex max-w-full flex-wrap items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50/70 px-2.5 py-1 text-xs font-mono text-indigo-900 dark:border-indigo-900/60 dark:bg-indigo-950/40 dark:text-indigo-200">
      <span className="font-sans font-semibold text-indigo-600 dark:text-indigo-400">
        {t("exercise.formula")}:
      </span>
      <span className="break-all">{formulaText}</span>
    </div>
  );
}
