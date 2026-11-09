-- Execute contra output/<execucao>/analytics.sqlite.
-- 1. Meses completos do recorte com maior precipitação observada.
SELECT municipality, month, total_mm, max_daily_mm, heavy_days, coverage_pct
FROM gold_monthly
WHERE full_calendar_month = 1
ORDER BY total_mm DESC
LIMIT 10;

-- 2. Dias com maior acumulado; janelas podem se sobrepor.
SELECT municipality, date, precipitation_mm, rain_3d_mm, antecedent_7d_mm
FROM gold_daily
WHERE accumulated_attention = 1
ORDER BY rain_3d_mm DESC;

-- 3. Evolução anual e frequência com denominador explícito.
SELECT municipality, substr(date, 1, 4) AS year,
       COUNT(*) AS expected_days,
       COUNT(precipitation_mm) AS valid_days,
       ROUND(SUM(precipitation_mm), 1) AS total_observed_mm,
       SUM(heavy_day) AS heavy_days,
       ROUND(100.0 * SUM(heavy_day) / NULLIF(COUNT(precipitation_mm), 0), 2) AS heavy_days_pct
FROM gold_daily
GROUP BY municipality_id, municipality, year
ORDER BY municipality, year;

-- 4. Sazonalidade da amostra, sem alegação de normal climatológica.
SELECT municipality, substr(date, 6, 2) AS calendar_month,
       COUNT(precipitation_mm) AS valid_days,
       ROUND(AVG(precipitation_mm), 2) AS mean_daily_mm,
       SUM(heavy_day) AS heavy_days
FROM gold_daily
GROUP BY municipality_id, municipality, calendar_month
ORDER BY municipality, calendar_month;

-- 5. Cobertura e incerteza descritiva (hipótese binomial limitada por autocorrelação).
SELECT municipality, month, valid_days, expected_days, coverage_pct,
       heavy_days_pct, wilson_low_pct, wilson_high_pct,
       valid_3d_windows, attention_3d_days
FROM gold_monthly
ORDER BY municipality, month;
