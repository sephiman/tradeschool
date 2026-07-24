import { useTranslation } from "react-i18next";

/** A hand-drawn, theme-aware, responsive SVG of a single candle with its OHLC parts labeled — used
 * as the m03 "anatomy of a candle" figure. Scales to the container width (no fixed pixel size). */
export function CandleAnatomy() {
  const { t } = useTranslation();
  // Geometry in a 340×220 viewBox: one bullish candle, wicks to high/low, dashed guides to labels.
  const cx = 120;
  const high = 24, bodyTop = 66, bodyBottom = 150, low = 196;
  const guide = "stroke-gray-300 dark:stroke-gray-700";
  const label = "fill-gray-600 dark:fill-gray-300 text-[13px]";
  const rows: [number, string][] = [
    [high, t("candle.high")],
    [bodyTop, t("candle.close")],
    [bodyBottom, t("candle.open")],
    [low, t("candle.low")],
  ];
  return (
    <svg viewBox="0 0 340 220" className="mx-auto h-auto w-full max-w-md" role="img">
      {rows.map(([y, text]) => (
        <g key={text}>
          <line x1={cx} y1={y} x2={250} y2={y} strokeDasharray="3 3" className={guide} />
          <text x={258} y={y + 4} className={label}>{text}</text>
        </g>
      ))}
      {/* wicks */}
      <line x1={cx} y1={high} x2={cx} y2={bodyTop} className="stroke-emerald-600" strokeWidth={2} />
      <line x1={cx} y1={bodyBottom} x2={cx} y2={low} className="stroke-emerald-600" strokeWidth={2} />
      {/* body (bullish: close above open) */}
      <rect x={cx - 26} y={bodyTop} width={52} height={bodyBottom - bodyTop} rx={2} className="fill-emerald-500" />
      {/* body / wick callouts on the left */}
      <text x={78} y={(bodyTop + bodyBottom) / 2 + 4} textAnchor="end" className={label}>
        {t("candle.body")}
      </text>
      <text x={78} y={(high + bodyTop) / 2 + 4} textAnchor="end" className={label}>
        {t("candle.wick")}
      </text>
      <line x1={82} y1={(bodyTop + bodyBottom) / 2} x2={cx - 26} y2={(bodyTop + bodyBottom) / 2} strokeDasharray="3 3" className={guide} />
      <line x1={82} y1={(high + bodyTop) / 2} x2={cx} y2={(high + bodyTop) / 2} strokeDasharray="3 3" className={guide} />
    </svg>
  );
}
