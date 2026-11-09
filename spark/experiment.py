"""Experimento complementar PySpark; executar em Spark/Databricks, não no pipeline principal.

Exemplo local com Spark instalado:
spark-submit spark/experiment.py --bronze data/bronze/<execucao> --output output/spark_<execucao>
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from functools import reduce
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import clean_city, verify_snapshot


def write_parquet_outputs(daily, monthly, output_path):
    """Reservar diretório novo antes de usar overwrite nos seus filhos.

    Alguns ambientes Serverless rejeitam errorifexists para arquivos. A reserva
    exclusiva mantém a proteção contra reutilização de saídas anteriores.
    Falhas preservam a pasta parcial; tentar novamente em outro caminho.
    """
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=False)
    daily.write.mode('overwrite').parquet(str(output / 'gold_daily'))
    monthly.write.mode('overwrite').parquet(str(output / 'gold_monthly'))


def run(spark, bronze_path, output_path):
    from pyspark.sql import Window, functions as F

    bronze = Path(bronze_path)
    output = Path(output_path)
    # Caminhos POSIX em volumes acessíveis pelo driver e pelo Spark no Databricks.
    if output.exists():
        raise ValueError('Use uma pasta de saída nova para preservar os experimentos')
    manifest = verify_snapshot(bronze)
    config = manifest['config']
    cities = config['municipalities']
    # Reutilizar o mesmo contrato do pipeline local antes do experimento.
    # A validação no driver é adequada somente ao pequeno recorte entregue.
    for city in cities:
        load = lambda source: json.loads((bronze / f'{city["id"]}_{source}.json').read_text(encoding='utf-8'))
        clean_city(city, load('ibge'), load('weather'), config)

    spark.conf.set('spark.sql.session.timeZone', config['timezone'])
    weather_schema = ('latitude DOUBLE, longitude DOUBLE, timezone STRING, '
        'daily_units STRUCT<precipitation_sum:STRING>, '
        'daily STRUCT<time:ARRAY<STRING>,precipitation_sum:ARRAY<DOUBLE>>')
    weather_frames = []
    for city in cities:
        source = spark.read.schema(weather_schema).option('multiLine', True).json(str(bronze / f'{city["id"]}_weather.json'))
        frame = (source.select('latitude', 'longitude', F.explode(F.arrays_zip('daily.time', 'daily.precipitation_sum')).alias('day'))
            .select(F.lit(city['id']).alias('municipality_id'),
                F.to_date('day.time').alias('date'), F.col('day.precipitation_sum').alias('precipitation_mm'),
                F.col('latitude').alias('grid_latitude'), F.col('longitude').alias('grid_longitude')))
        weather_frames.append(frame)
    weather = reduce(lambda a, b: a.unionByName(b), weather_frames)

    ibge_schema = ('id LONG, nome STRING, '
        '`regiao-imediata` STRUCT<nome:STRING,`regiao-intermediaria`:STRUCT<UF:STRUCT<sigla:STRING>>>')
    metadata = (spark.read.schema(ibge_schema).option('multiLine', True)
        .json([str(bronze / f'{city["id"]}_ibge.json') for city in cities])
        .select(F.col('id').alias('municipality_id'), F.col('nome').alias('municipality'),
            F.col('regiao-imediata.nome').alias('immediate_region'),
            F.col('regiao-imediata.regiao-intermediaria.UF.sigla').alias('uf')))
    points = spark.createDataFrame([(c['id'], float(c['latitude']), float(c['longitude'])) for c in cities],
        'municipality_id LONG, requested_latitude DOUBLE, requested_longitude DOUBLE')
    silver = weather.join(metadata, 'municipality_id', 'inner').join(points, 'municipality_id', 'inner')
    if silver.count() != weather.count():
        raise ValueError('Join alterou a quantidade de linhas')

    gold = silver.withColumn('_day', F.datediff('date', F.lit('1970-01-01')))
    for name, start, end, length in [('rain_3d_mm', -2, 0, 3), ('rain_7d_mm', -6, 0, 7), ('antecedent_7d_mm', -7, -1, 7)]:
        window = Window.partitionBy('municipality_id').orderBy('_day').rangeBetween(start, end)
        gold = gold.withColumn(name, F.when(F.count('precipitation_mm').over(window) == length,
            F.round(F.sum('precipitation_mm').over(window), 3)))
    gold = (gold.drop('_day')
        .withColumn('heavy_day', F.when(F.col('precipitation_mm').isNotNull(),
            (F.col('precipitation_mm') >= config['heavy_daily_mm']).cast('int')))
        .withColumn('accumulated_attention', F.when(F.col('rain_3d_mm').isNotNull(),
            (F.col('rain_3d_mm') >= config['accumulated_3d_mm']).cast('int')))
        .withColumn('month', F.date_format('date', 'yyyy-MM')))
    gold.createOrReplaceTempView('citizentech_daily')
    monthly = spark.sql('''
        SELECT municipality_id, municipality, month,
               count(*) AS expected_days,
               count(precipitation_mm) AS valid_days,
               100.0 * count(precipitation_mm) / count(*) AS coverage_pct,
               round(sum(precipitation_mm), 3) AS total_mm,
               max(precipitation_mm) AS max_daily_mm,
               coalesce(sum(heavy_day), 0) AS heavy_days,
               100.0 * sum(heavy_day) / nullif(count(precipitation_mm), 0) AS heavy_days_pct,
               count(rain_3d_mm) AS valid_3d_windows,
               coalesce(sum(accumulated_attention), 0) AS attention_3d_days
        FROM citizentech_daily
        GROUP BY municipality_id, municipality, month
    ''')
    monthly = monthly.withColumn('full_calendar_month',
        (F.col('valid_days') == F.dayofmonth(F.last_day(F.to_date(F.concat('month', F.lit('-01')))))).cast('int'))
    # Mesma fórmula de Wilson do pipeline padrão, sem UDF Python.
    n = F.col('valid_days')
    proportion = F.col('heavy_days') / F.when(n > 0, n)
    z = 1.959963984540054
    center = (proportion + z*z/(2*n)) / (1+z*z/n)
    radius = z*F.sqrt(proportion*(1-proportion)/n + z*z/(4*n*n))/(1+z*z/n)
    monthly = (monthly.withColumn('wilson_low_pct', F.when(n > 0, 100*(center-radius)))
        .withColumn('wilson_high_pct', F.when(n > 0, 100*(center+radius))))
    write_parquet_outputs(gold, monthly, output)
    persisted = spark.read.parquet(str(output / 'gold_monthly'))
    persisted.orderBy(F.desc('total_mm')).show(10, truncate=False)
    evidence = {'executed_at_utc': datetime.now(timezone.utc).isoformat(), 'spark_version': spark.version,
        'bronze': str(bronze), 'daily_rows': gold.count(), 'monthly_rows': persisted.count(),
        'missing_precipitation': gold.filter(F.col('precipitation_mm').isNull()).count(),
        'config': config,
        'notes': 'Execução real do experimento. Comparar com as tabelas locais conforme README.'}
    (output / 'execution.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    return gold, monthly


if __name__ == '__main__':
    from pyspark.sql import SparkSession
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bronze', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    session = SparkSession.builder.appName('CitizenTech-Chuvas').getOrCreate()
    try:
        run(session, args.bronze, args.output)
    finally:
        session.stop()
