-- Resumo de todo o período 2023–2025, sem filtro temporal dinâmico.
SELECT
  municipality_id,
  municipality,
  min(date) AS start_date,
  max(date) AS end_date,
  count(*) AS expected_days,
  count(precipitation_mm) AS valid_days,
  round(100.0 * count(precipitation_mm) / count(*), 2) AS coverage_pct,
  round(sum(precipitation_mm), 1) AS total_mm,
  max(precipitation_mm) AS max_daily_mm,
  sum(heavy_day) AS heavy_days,
  round(100.0 * sum(heavy_day) / nullif(count(precipitation_mm), 0), 2) AS heavy_days_pct,
  max(rain_3d_mm) AS max_3d_mm,
  max(rain_7d_mm) AS max_7d_mm
FROM `workspace`.`citizentech`.`gold_daily_20261109t131706z_f0529b79`
GROUP BY municipality_id, municipality
