-- Dias podem pertencer ao mesmo episódio; não representam ocorrências de inundação.
SELECT
  municipality,
  date,
  precipitation_mm,
  rain_3d_mm,
  rain_7d_mm,
  antecedent_7d_mm,
  heavy_day,
  accumulated_attention
FROM `workspace`.`citizentech`.`gold_daily_20261109t131706z_f0529b79`
WHERE heavy_day = 1 OR accumulated_attention = 1
