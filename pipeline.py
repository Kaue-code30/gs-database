"""CitizenTech: pipeline reprodutível de precipitação, apenas biblioteca padrão."""
import argparse
import calendar
import csv
import gzip
import hashlib
import json
import math
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def read_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    start, end = (date.fromisoformat(config[k]) for k in ("start_date", "end_date"))
    if start > end or end >= date.today():
        raise ValueError("O intervalo deve ser histórico, com início <= fim < hoje")
    if config["timezone"] != "America/Sao_Paulo" or config["model"] != "era5":
        raise ValueError("Este projeto requer America/Sao_Paulo e modelo era5")
    for key in ("heavy_daily_mm", "accumulated_3d_mm"):
        if isinstance(config[key], bool) or not isinstance(config[key], (int, float)) or not math.isfinite(config[key]) or config[key] <= 0:
            raise ValueError(f"Limiar inválido: {key}")
    cities = config["municipalities"]
    if not cities or len({c["id"] for c in cities}) != len(cities):
        raise ValueError("Municípios ausentes ou duplicados")
    for city in cities:
        if not isinstance(city["id"], int) or not -90 <= city["latitude"] <= 90 or not -180 <= city["longitude"] <= 180:
            raise ValueError("Código ou coordenadas inválidos")
    return config


def fetch(url):
    """Retentativas limitadas; nenhuma substituição por dados simulados."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CitizenTech-Academic/1.0", "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
            # Alguns servidores/proxies enviam gzip mesmo com identity.
            decoded = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
            return raw, json.loads(decoded)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def acquire(config, bronze):
    bronze.mkdir(parents=True, exist_ok=False)
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "config": config, "sources": []}
    write_json(bronze / "manifest.json", manifest)
    for city in config["municipalities"]:
        params = urllib.parse.urlencode({"latitude": city["latitude"], "longitude": city["longitude"],
            "start_date": config["start_date"], "end_date": config["end_date"],
            "daily": "precipitation_sum", "timezone": config["timezone"], "models": config["model"]})
        urls = {"ibge": f"https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{city['id']}",
                "weather": "https://archive-api.open-meteo.com/v1/archive?" + params}
        for source, url in urls.items():
            print(f"Coletando {source}: {city['label']}", flush=True)
            raw, payload = fetch(url)
            filename = f"{city['id']}_{source}.json"
            # JSON descomprimido para portabilidade + corpo original para auditoria.
            (bronze / f"{filename}.body").write_bytes(raw)
            write_json(bronze / filename, payload)
            manifest["sources"].append({"municipality_id": city["id"], "source": source, "url": url,
                "file": filename, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "body_sha256": hashlib.sha256(raw).hexdigest(),
                "json_sha256": hashlib.sha256((bronze / filename).read_bytes()).hexdigest()})
            write_json(bronze / "manifest.json", manifest)
    return manifest


def verify_snapshot(bronze):
    manifest = json.loads((bronze / "manifest.json").read_text(encoding="utf-8"))
    expected = {(c["id"], s) for c in manifest["config"]["municipalities"] for s in ("ibge", "weather")}
    actual = [(s["municipality_id"], s["source"]) for s in manifest["sources"]]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Snapshot incompleto ou duplicado")
    for source in manifest["sources"]:
        filename = source["file"]
        if Path(filename).name != filename:
            raise ValueError("Nome de arquivo inválido no manifesto")
        for suffix, key in (("", "json_sha256"), (".body", "body_sha256")):
            if hashlib.sha256((bronze / (filename + suffix)).read_bytes()).hexdigest() != source[key]:
                raise ValueError(f"Checksum divergente: {filename}{suffix}")
    return manifest


def clean_city(city, metadata, weather, config):
    if metadata["id"] != city["id"]:
        raise ValueError("Identificador IBGE divergente")
    region = metadata["regiao-imediata"]["regiao-intermediaria"]["UF"]
    if weather.get("timezone") != config["timezone"] or weather.get("daily_units", {}).get("precipitation_sum") != "mm":
        raise ValueError("Timezone ou unidade de precipitação inesperada")
    days = weather["daily"]["time"]
    values = weather["daily"]["precipitation_sum"]
    start, end = (date.fromisoformat(config[k]) for k in ("start_date", "end_date"))
    expected = [(start + timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
    if days != expected or len(values) != len(days):
        raise ValueError("Datas incompletas, duplicadas, fora de ordem ou vetores incompatíveis")
    rows = []
    for day, value in zip(days, values):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            raise ValueError(f"Precipitação inválida: {city['id']} {day}")
        rows.append({"municipality_id": city["id"], "municipality": metadata["nome"],
            "uf": region["sigla"], "immediate_region": metadata["regiao-imediata"]["nome"],
            "date": day, "precipitation_mm": value,
            "requested_latitude": city["latitude"], "requested_longitude": city["longitude"],
            "grid_latitude": weather["latitude"], "grid_longitude": weather["longitude"]})
    return rows


def features(rows, config):
    """Janelas de calendário: nulo se faltar qualquer dia ou valor."""
    by_city = defaultdict(list)
    for row in rows:
        by_city[row["municipality_id"]].append(row)
    result = []
    for group in by_city.values():
        group.sort(key=lambda r: r["date"])
        if len({r["date"] for r in group}) != len(group):
            raise ValueError("Chave município/data duplicada")
        history = {date.fromisoformat(r["date"]): r["precipitation_mm"] for r in group}
        for row in group:
            current = date.fromisoformat(row["date"])
            new = dict(row)
            for name, offsets in (("rain_3d_mm", range(3)), ("rain_7d_mm", range(7)), ("antecedent_7d_mm", range(1, 8))):
                values = [history.get(current-timedelta(days=i)) for i in offsets]
                new[name] = round(sum(values), 3) if all(v is not None for v in values) else None
            value = row["precipitation_mm"]
            new["heavy_day"] = None if value is None else int(value >= config["heavy_daily_mm"])
            new["accumulated_attention"] = None if new["rain_3d_mm"] is None else int(new["rain_3d_mm"] >= config["accumulated_3d_mm"])
            new["month"] = row["date"][:7]
            result.append(new)
    return result


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    index = (len(values)-1)*q
    low = math.floor(index)
    return values[low] + (values[math.ceil(index)]-values[low])*(index-low)


def wilson(successes, total):
    if not total:
        return None, None
    z = 1.959963984540054
    p = successes/total
    center = (p+z*z/(2*total))/(1+z*z/total)
    radius = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/(1+z*z/total)
    return 100*(center-radius), 100*(center+radius)


def aggregate(rows, config):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["municipality_id"], row["month"])].append(row)
    result = []
    for (code, month), group in sorted(grouped.items()):
        values = [r["precipitation_mm"] for r in group if r["precipitation_mm"] is not None]
        heavy = sum(v >= config["heavy_daily_mm"] for v in values)
        lo, hi = wilson(heavy, len(values))
        result.append({"municipality_id": code, "municipality": group[0]["municipality"], "month": month,
            "expected_days": len(group), "valid_days": len(values), "coverage_pct": 100*len(values)/len(group),
            "full_calendar_month": int(len(values) == calendar.monthrange(int(month[:4]), int(month[5:]))[1]),
            "total_mm": round(sum(values), 3) if values else None,
            "max_daily_mm": max(values) if values else None,
            "heavy_days": heavy, "heavy_days_pct": 100*heavy/len(values) if values else None,
            "wilson_low_pct": lo, "wilson_high_pct": hi,
            "valid_3d_windows": sum(r["rain_3d_mm"] is not None for r in group),
            "attention_3d_days": sum(r["accumulated_attention"] == 1 for r in group)})
    return result


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_database(path, tables):
    with closing(sqlite3.connect(path)) as db, db:
        for name, rows in tables.items():
            integer_fields = {"municipality_id", "heavy_day", "accumulated_attention", "expected_days", "valid_days", "heavy_days", "valid_3d_windows", "attention_3d_days", "full_calendar_month"}
            text_fields = {"municipality", "uf", "immediate_region", "date", "month"}
            types = {key: ("INTEGER" if key in integer_fields else "TEXT" if key in text_fields else "REAL") for key in rows[0]}
            columns = ', '.join(f'"{key}" {kind}' for key, kind in types.items())
            db.execute(f'CREATE TABLE "{name}" ({columns})')
            placeholders = ','.join('?' for _ in types)
            db.executemany(f'INSERT INTO "{name}" VALUES ({placeholders})', [tuple(r.values()) for r in rows])
        db.execute('CREATE UNIQUE INDEX daily_key ON gold_daily(municipality_id, date)')
        db.execute('CREATE UNIQUE INDEX monthly_key ON gold_monthly(municipality_id, month)')


def executive_report(rows, monthly, config, output, run_id):
    lines = ["# Relatório executivo: chuvas e preparação para enchentes", "",
        "**Integrantes:** Kaue Lima — RM 562071; Pedro Gonçalves — RM 561506; Edmario — RM 565486.", "",
        f"Execução: `{run_id}`. Período: {config['start_date']} a {config['end_date']}.", "",
        "Reanálise ERA5 obtida via Open-Meteo, integrada ao cadastro do IBGE. Cada município é representado por um ponto configurado; os valores não são médias municipais nem medições de pluviômetros.", "",
        f"Limiares exploratórios: chuva diária >= {config['heavy_daily_mm']} mm; acumulado de 3 dias >= {config['accumulated_3d_mm']} mm. Não são alertas oficiais ou probabilidades de inundação.", "",
        "| Município | Dias válidos/esperados | Total observado (mm) | Máximo diário (mm) | Dias acima do limiar | P95 dos dias chuvosos (mm) |", "|---|---:|---:|---:|---:|---:|"]
    for city in config["municipalities"]:
        group = [r for r in rows if r["municipality_id"] == city["id"]]
        values = [r["precipitation_mm"] for r in group if r["precipitation_mm"] is not None]
        wet = [v for v in values if v >= 1]
        p95 = percentile(wet, .95)
        fmt = lambda v: f"{v:.1f}" if v is not None else "indisponível"
        lines.append(f"| {group[0]['municipality']} | {len(values)}/{len(group)} | {fmt(sum(values) if values else None)} | {fmt(max(values) if values else None)} | {sum(v >= config['heavy_daily_mm'] for v in values)} | {fmt(p95)} |")
    eligible = [m for m in monthly if m["full_calendar_month"] == 1]
    lines += ["", "## Evidências e decisões", ""]
    if eligible:
        top = sorted(eligible, key=lambda r: r["total_mm"], reverse=True)[:5]
        for item in top:
            lines.append(f"- {item['municipality']} em {item['month']}: {item['total_mm']:.1f} mm, {item['heavy_days']} dias acima do limiar diário e {item['attention_3d_days']} dias acima do acumulado de 3 dias.")
        lines += ["", "Os meses acima tiveram os maiores totais entre os meses completos da amostra. Usá-los para selecionar períodos de investigação e planejar inspeções de drenagem. A chuva isolada não demonstra ocorrência ou dano de enchente."]
    else:
        lines += ["Nenhum mês com cobertura completa: corrigir a aquisição antes de comparar totais mensais."]
    lines += ["", "## Análise estatística e interpretação", "",
        "gold/monthly.csv inclui a frequência de dias acima do limiar e intervalo de Wilson de 95%. O denominador inclui apenas dias com valor válido. O intervalo pressupõe ensaios independentes e serve apenas como referência descritiva: a autocorrelação da chuva limita sua interpretação inferencial. Meses incompletos não entram no ranking acima.", "",
        "O P95 usa interpolação linear sobre dias com pelo menos 1 mm em todo o período. É uma referência retrospectiva da amostra, sem aplicação preditiva. Três anos não constituem normal climatológica nem permitem atribuir tendências às mudanças climáticas.", "",
        "## Recomendações e acompanhamento", "",
        "1. Cruzar os episódios selecionados com ocorrências oficiais de inundação e níveis de rios antes de priorizar obras ou classificar risco.",
        "2. Verificar sazonalidade com uma série mais longa e observações de estações locais; preparar inspeções antes dos períodos recorrentes de chuva intensa.",
        "3. Acompanhar cobertura dos dados, dias de chuva intensa, acumulados de 3/7 dias, ocorrências confirmadas, pessoas afetadas e tempo de resposta. Os três últimos indicadores exigem novas fontes.",
        "4. Para operação, incorporar previsão, exposição, relevo, drenagem e validação da Defesa Civil. Esta análise histórica não emite alertas.", "",
        "## Limitações", "",
        "A grade ERA5 suaviza extremos locais; os pontos não descrevem bairros, bacias ou toda a área municipal. Não há dados de exposição, população afetada, nível de rio, inundação observada ou validação de danos. A integração IBGE adiciona identidade e região administrativa, sem explicar vulnerabilidade. Nenhuma conclusão causal é sustentada.", "",
        "![Precipitação mensal](precipitacao_mensal.svg)", "",
        "Fontes: [Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api), [IBGE](https://servicodados.ibge.gov.br/api/docs/localidades). URLs, horários e hashes da coleta estão no manifesto Bronze."]
    (output / "relatorio_executivo.md").write_text('\n'.join(lines)+'\n', encoding="utf-8")
    chart(monthly, output / "precipitacao_mensal.svg")


def chart(monthly, path):
    from html import escape
    cities = sorted({r["municipality_id"] for r in monthly})
    months = sorted({r["month"] for r in monthly})
    maximum = max((r["total_mm"] or 0 for r in monthly), default=1) or 1
    width, panel = 1080, 230
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{len(cities)*panel+100}" viewBox="0 0 {width} {len(cities)*panel+100}">',
        '<rect width="100%" height="100%" fill="#f6f8fc"/>',
        '<g font-family="Arial, sans-serif" fill="#182c46">',
        '<text x="50" y="32" font-size="22">Precipitação mensal nos pontos selecionados (mm)</text>',
        '<text x="50" y="55" font-size="12">ERA5 / Open-Meteo + IBGE · meses incompletos em cinza · mesma escala em todos os painéis</text>']
    for index, city in enumerate(cities):
        group = {r["month"]: r for r in monthly if r["municipality_id"] == city}
        top = 85+index*panel
        elements.append(f'<text x="50" y="{top}" font-size="17">{escape(next(iter(group.values()))["municipality"])}</text>')
        elements.append(f'<text x="10" y="{top+25}" font-size="11">{maximum:.0f}</text>')
        elements.append(f'<text x="25" y="{top+160}" font-size="11">0</text>')
        for j, month in enumerate(months):
            row = group[month]
            step = 980/len(months)
            height = (row["total_mm"] or 0)/maximum*140
            x, y = 50+j*step, top+160-height
            color = '#247d95' if row["full_calendar_month"] == 1 else '#9da7b5'
            elements.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(1,step-4):.1f}" height="{height:.1f}" fill="{color}"><title>{month}: {row["total_mm"]} mm; cobertura {row["coverage_pct"]:.1f}%</title></rect>')
            if j % max(1, math.ceil(len(months)/12)) == 0:
                elements.append(f'<text x="{x:.1f}" y="{top+180}" font-size="10">{month}</text>')
        elements.append(f'<line x1="50" y1="{top+160}" x2="1035" y2="{top+160}" stroke="#9da7b5"/>')
    elements.append('</g></svg>')
    path.write_text('\n'.join(elements), encoding="utf-8")


def process(bronze, destination):
    manifest = verify_snapshot(bronze)
    config = manifest["config"]
    rows = []
    for city in config["municipalities"]:
        load = lambda source: json.loads((bronze / f"{city['id']}_{source}.json").read_text(encoding="utf-8"))
        rows.extend(clean_city(city, load("ibge"), load("weather"), config))
    daily = features(rows, config)
    monthly = aggregate(daily, config)
    # Publicar só depois da validação completa; execuções nunca sobrescrevem outras.
    destination.mkdir(parents=True, exist_ok=False)
    write_csv(destination / "silver" / "daily.csv", rows)
    write_csv(destination / "gold" / "daily.csv", daily)
    write_csv(destination / "gold" / "monthly.csv", monthly)
    write_database(destination / "analytics.sqlite", {"silver_daily": rows, "gold_daily": daily, "gold_monthly": monthly})
    write_json(destination / "quality.json", {"rows": len(rows), "unique_keys": len({(r['municipality_id'], r['date']) for r in rows}),
        "missing_precipitation": sum(r["precipitation_mm"] is None for r in rows),
        "incomplete_months": sum(r["coverage_pct"] < 100 for r in monthly),
        "null_3d_windows": sum(r["rain_3d_mm"] is None for r in daily),
        "bronze_manifest": str(bronze.resolve() / 'manifest.json')})
    write_json(destination / "manifest.json", manifest)
    executive_report(daily, monthly, config, destination, destination.name)
    print(f"Concluído: {destination}\n{len(rows)} linhas diárias; {len(monthly)} indicadores mensais", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--bronze", type=Path, help="Reprocessar snapshot existente sem rede")
    parser.add_argument("--output-root", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8]
    bronze = args.bronze
    if bronze is None:
        config = read_config(args.config)
        bronze = ROOT / "data" / "bronze" / run_id
        acquire(config, bronze)
    process(bronze, args.output_root / run_id)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, urllib.error.URLError) as exc:
        print(f"Falha: {exc}", file=sys.stderr)
        sys.exit(1)
