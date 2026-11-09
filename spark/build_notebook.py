"""Empacota código, snapshot e referência em um notebook importável no Databricks."""
import argparse
import base64
import hashlib
import io
import json
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = '20261109T124404Z_377aa3e5'
REFERENCE = '20261109T125036Z_b1308a4d'


def main(destination=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ('pipeline.py', 'spark/experiment.py'):
            archive.write(ROOT / name, name)
        for path in sorted((ROOT / 'data/bronze' / SNAPSHOT).iterdir()):
            archive.write(path, 'bronze/' + path.name)
        for name in ('daily.csv', 'monthly.csv'):
            archive.write(ROOT / 'output' / REFERENCE / 'gold' / name, 'reference/' + name)
    payload = buffer.getvalue()
    cells = []

    def markdown(source):
        cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': textwrap.dedent(source).strip().splitlines(keepends=True)})

    def code(source):
        source = textwrap.dedent(source).strip() + '\n'
        compile(source, '<notebook>', 'exec')
        cells.append({'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': source.splitlines(keepends=True)})

    markdown('''
        # CitizenTech — Chuvas e preparação para enchentes

        **Integrantes**
        - Kaue Lima — RM 562071
        - Pedro Gonçalves — RM 561506
        - Edmario — RM 565486

        Notebook autocontido com dados públicos IBGE + ERA5/Open-Meteo, código e resultados de referência.
        Recorte: São Paulo, Santos e São Luiz do Paraitinga, 2023–2025.

        **Antes de executar:** confirmar que a conta é Databricks Free Edition. Um workspace Trial é uma modalidade diferente.
        Este notebook executa compute, cria um schema/volume gerenciados e três tabelas Delta com nomes novos por execução.
        Não solicita credenciais, não altera permissões e não faz downloads de APIs.

        Resultados esperados: 3.288 linhas diárias e 108 linhas mensais. Os dados descrevem chuva em pontos de grade;
        não estimam probabilidade de inundação. Limiares de 50 mm/dia e 100 mm/3 dias são exploratórios.

        Fonte meteorológica: [Open-Meteo / ERA5 ECMWF-Copernicus](https://open-meteo.com/en/docs/historical-weather-api).
        Fonte territorial: [IBGE Localidades](https://servicodados.ibge.gov.br/api/docs/localidades).
        URLs exatas, horários e hashes estão no manifesto incorporado.

        O notebook foi gerado e suas células foram verificadas sintaticamente localmente. Confirmar cada execução pelas saídas de paridade e publicação de tabelas abaixo.
    ''')
    code('''
        # Parâmetros: catálogo atual do workspace e recursos exclusivos do projeto.
        CATALOG = spark.sql("SELECT current_catalog()").first()[0]
        SCHEMA = "citizentech"
        VOLUME = "assets"
        print("Destino:", CATALOG, SCHEMA, VOLUME)
    ''')
    markdown('''
        ## Preparar armazenamento e snapshot
        A próxima célula cria schema/volume caso não existam. Cada execução usa uma pasta nova;
        arquivos e tabelas de execuções anteriores são preservados.
    ''')
    code(textwrap.dedent('''
        import base64, hashlib, io, json, re, sys, types, uuid, zipfile
        from datetime import datetime, timezone
        from pathlib import Path

        for name in (CATALOG, SCHEMA, VOLUME):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError("Ajuste o identificador do catálogo/schema/volume: " + name)
        namespace = f"`{CATALOG}`.`{SCHEMA}`"
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {namespace}")
        spark.sql(f"CREATE VOLUME IF NOT EXISTS {namespace}.`{VOLUME}`")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        run_root = Path(f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/runs/{run_id}")
        run_root.mkdir(parents=True, exist_ok=False)
    ''') + '\nPAYLOAD_SHA256 = ' + repr(hashlib.sha256(payload).hexdigest()) +
        '\nPAYLOAD_BASE64 = ' + repr(base64.b64encode(payload).decode('ascii')) + '\n' + textwrap.dedent('''
        payload = base64.b64decode(PAYLOAD_BASE64, validate=True)
        assert hashlib.sha256(payload).hexdigest() == PAYLOAD_SHA256, "Pacote corrompido"
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for member in archive.infolist():
                target = (run_root / member.filename).resolve()
                if not target.is_relative_to(run_root.resolve()):
                    raise ValueError("Caminho inválido no pacote")
            archive.extractall(run_root)
        print("Snapshot preparado em:", run_root)
        # Executar módulos próprios incorporados, sem instalação de pacotes.
        pipeline_module = types.ModuleType("pipeline")
        pipeline_module.__file__ = str(run_root / "pipeline.py")
        sys.modules["pipeline"] = pipeline_module
        exec(compile((run_root / "pipeline.py").read_text(encoding="utf-8"), pipeline_module.__file__, "exec"), pipeline_module.__dict__)
        experiment_module = types.ModuleType("citizentech_experiment")
        experiment_module.__file__ = str(run_root / "spark/experiment.py")
        exec(compile((run_root / "spark/experiment.py").read_text(encoding="utf-8"), experiment_module.__file__, "exec"), experiment_module.__dict__)
        pipeline_module.verify_snapshot(run_root / "bronze")
        print("Integridade Bronze verificada")
    '''))
    markdown('''
        ## Executar PySpark
        Leitura JSON com schema, integração IBGE/meteorologia, janelas por calendário,
        agregações SQL e persistência/releitura Parquet. A validação inicial no driver atende ao pequeno recorte deste estudo.
    ''')
    code('''
        import time
        started = time.perf_counter()
        daily, monthly = experiment_module.run(spark, str(run_root / "bronze"), str(run_root / "spark_result"))
        elapsed_seconds = time.perf_counter() - started
        print("Tempo do experimento (s):", round(elapsed_seconds, 2))
        display(monthly.orderBy("municipality_id", "month"))
    ''')
    markdown('''
        ## Comparar com a referência Python/SQLite
        Compara todas as chaves e colunas das tabelas Gold. A coleta no driver é proposital para as 3.288 linhas;
        não é uma estratégia para grande volume. Tolerância: 0,001 mm e 1e-6 nos demais números.
    ''')
    code('''
        import csv, math
        from decimal import Decimal
        def compare_reference(frame, filename, keys):
            with (run_root / "reference" / filename).open(encoding="utf-8", newline="") as stream:
                expected_rows = list(csv.DictReader(stream))
            columns = list(expected_rows[0])
            actual_rows = [r.asDict() for r in frame.select(*columns).collect()]
            def row_key(row):
                return tuple(str(row[k]) for k in keys)
            expected = {row_key(r): r for r in expected_rows}
            actual = {row_key(r): r for r in actual_rows}
            assert len(expected) == len(expected_rows), "Referência duplicada"
            assert len(actual) == len(actual_rows), "Resultado Spark duplicado"
            assert expected.keys() == actual.keys(), "Chaves divergentes"
            differences = []
            for key, ref in expected.items():
                for col in columns:
                    value, target = actual[key][col], ref[col]
                    if target == "":
                        equal = value is None
                    elif isinstance(value, (int, float, Decimal)):
                        tolerance = .001 if col.endswith("_mm") else 1e-6
                        equal = math.isclose(float(value), float(target), abs_tol=tolerance, rel_tol=0)
                    else:
                        equal = str(value) == target
                    if not equal:
                        differences.append((key, col, value, target))
            assert not differences, repr(differences[:10])
            return {"file": filename, "rows": len(actual_rows), "differences": 0}

        validation = [compare_reference(daily, "daily.csv", ("municipality_id", "date")),
                      compare_reference(monthly, "monthly.csv", ("municipality_id", "month"))]
        (run_root / "parity.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
        print(validation)
    ''')
    markdown('''
        ## Disponibilizar tabelas Delta para SQL e dashboards
        Os nomes contêm o identificador da execução para preservar resultados anteriores.
    ''')
    code('''
        silver_columns = ["municipality_id", "municipality", "uf", "immediate_region", "date", "precipitation_mm",
            "requested_latitude", "requested_longitude", "grid_latitude", "grid_longitude"]
        tables = {}
        for layer, frame in [("silver_daily", daily.select(*silver_columns)), ("gold_daily", daily), ("gold_monthly", monthly)]:
            table = f"{namespace}.`{layer}_{run_id.lower()}`"
            # CTAS preserva o erro caso a tabela já exista, sem depender do
            # modo DataFrameWriter errorifexists rejeitado neste Serverless.
            view = f"citizentech_publish_{layer}_{run_id.lower()}"
            frame.createOrReplaceTempView(view)
            spark.sql(f"CREATE TABLE {table} USING DELTA AS SELECT * FROM `{view}`")
            tables[layer] = table
        evidence = {"run_id": run_id, "spark_version": spark.version, "elapsed_seconds": elapsed_seconds,
            "tables": tables, "parity": validation, "run_root": str(run_root)}
        (run_root / "databricks_execution.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    ''')
    code('''
        # Ordenação dos meses completos para investigação.
        display(spark.sql(f"""
            SELECT municipality, month, total_mm, max_daily_mm, heavy_days, attention_3d_days
            FROM {tables['gold_monthly']}
            WHERE full_calendar_month = 1
            ORDER BY total_mm DESC
            LIMIT 10
        """))
        # No resultado abaixo, usar a opção de visualização: linha, eixo X=month,
        # eixo Y=total_mm, séries=municipality.
        display(spark.sql(f"""
            SELECT municipality, month, total_mm
            FROM {tables['gold_monthly']}
            WHERE full_calendar_month = 1
            ORDER BY month, municipality
        """))
    ''')
    markdown('''
        ## Evidências e interpretação
        Salvar uma cópia deste notebook com saídas, `databricks_execution.json`, `parity.json` e o plano físico abaixo.
        Só declarar a etapa Spark concluída após as células terminarem e a comparação não apresentar diferenças.
        O tempo observado não comprova ganho de desempenho: não existe benchmark controlado contra outra execução.

        Próximos passos: cruzar episódios com ocorrências oficiais, níveis de rios e exposição; avaliar uma série mais longa.
        Os acumulados não representam área inundada ou saturação do solo, e três anos não são normal climatológica.
    ''')
    code('daily.explain("formatted")')
    notebook = {'nbformat': 4, 'nbformat_minor': 5,
        'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                     'language_info': {'name': 'python'}}, 'cells': cells}
    for i, cell in enumerate(cells):
        cell['id'] = f'citizentech-{i:02d}'
    destination = destination or ROOT / 'output/databricks/CitizenTech_Databricks.ipynb'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding='utf-8')
    print(destination)
    print(f'{len(cells)} células; {len(payload)} bytes incorporados; código verificado sintaticamente')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    main(parser.parse_args().output)
