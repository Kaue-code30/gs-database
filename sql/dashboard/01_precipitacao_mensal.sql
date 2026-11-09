SELECT
  municipality_id,
  municipality,
  to_date(concat(month, '-01')) AS month_date,
  month,
  total_mm,
  max_daily_mm,
  heavy_days,
  heavy_days_pct,
  coverage_pct,
  valid_days,
  expected_days,
  attention_3d_days,
  valid_3d_windows
FROM `workspace`.`citizentech`.`gold_monthly_20261109t131706z_f0529b79`
WHERE full_calendar_month = 1
