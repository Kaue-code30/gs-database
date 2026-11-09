# CitizenTech — Chuvas e preparação para enchentes

| Integrante | RM |
|---|---|
| Kaue Lima | 562071 |
| Pedro Gonçalves | 561506 |
| Edmario | 565486 |

Projeto aplicado de Big Data & Analytics da Global Solution 2026.2. Integra precipitação histórica de pontos representativos de **São Paulo, Santos e São Luiz do Paraitinga** ao cadastro municipal do IBGE, de **2023 a 2025**.

O objetivo é identificar períodos de chuva intensa para apoiar investigação e preparação municipal. O produto mede precipitação e acumulados; risco de inundação depende também de exposição, relevo, drenagem e ocorrências confirmadas, ainda não integrados.

## Executar

Python **3.11 ou superior**, sem dependências externas para o pipeline principal. Validado localmente com Python 3.14. As APIs públicas exigem internet, sem chave para este uso acadêmico. Observar os termos e limites das fontes antes de ampliar o uso.

```powershell
python pipeline.py
python -m unittest discover -s tests -v
```

Cada execução cria seu próprio identificador e preserva os arquivos anteriores:

```text
data/bronze/<execucao>/
  manifest.json             # configuração, URLs, horários UTC e hashes SHA-256
  <codigo>_ibge.json         # resposta normalizada de cada município
  <codigo>_weather.json      # resposta normalizada de precipitação
  *.json.body               # corpos recebidos, inclusive gzip quando enviado
output/<execucao>/
  silver/daily.csv           # fontes validadas e integradas
  gold/daily.csv             # features de precipitação
  gold/monthly.csv           # indicadores e cobertura
  analytics.sqlite          # tabelas SQL das camadas Silver e Gold
  quality.json              # verificações de integridade e completude
  manifest.json             # proveniência copiada da Bronze
  relatorio_executivo.md     # diagnóstico e recomendações gerados dos dados
  precipitacao_mensal.svg    # visualização comparativa com escala comum
```

Reprocessamento sem internet, usando um snapshot existente:

```powershell
python pipeline.py --bronze data/bronze/20261109T124404Z_377aa3e5
```

O reprocessamento valida os hashes e usa a configuração registrada na coleta; `--config` só vale para novas aquisições. Os CSVs Silver e Gold são determinísticos para o mesmo snapshot e versão do código. Relatórios preservam o identificador de cada execução.

Para alterar o recorte, edite `config.json` e execute novamente. Os pontos são escolhas explícitas do estudo, próximas às sedes urbanas, sem afirmação de cobertura municipal. A resposta contém as coordenadas da célula efetivamente usada. Intervalos históricos devem terminar antes de hoje; o provedor pode impor latência adicional de disponibilização.

## Resultados verificados

A coleta `20261109T124404Z_377aa3e5` produziu **3.288 registros diários**, **108 registros mensais**, **nenhum valor diário ausente** e chaves município/data únicas. Os primeiros dois acumulados de três dias de cada município permanecem nulos por falta de histórico anterior ao recorte.

| Ponto municipal | Total em 2023–2025 (mm) | Maior valor diário (mm) | Dias >= 50 mm |
|---|---:|---:|---:|
| São Paulo | 3.553,8 | 58,1 | 1 |
| Santos | 6.131,6 | 179,7 | 15 |
| São Luiz do Paraitinga | 3.801,2 | 44,1 | 0 |

São resultados de reanálise em grade, sujeitos às limitações descritas no relatório. Esses valores não contabilizam enchentes nem representam a precipitação média de toda a área municipal.

## Documentação e entrega

- [Problema, decisões e critérios de aceitação](docs/projeto.md)
- [Catálogo das fontes e dicionário de dados](docs/catalogo_dados.md)
- [Arquitetura, qualidade, features e atualização](docs/arquitetura.md)
- [Consultas SQL](sql/analises.sql)
- [Experimentação complementar Spark/Databricks](spark/README.md)
- [Código do experimento PySpark](spark/experiment.py)
- [Registro da execução Spark validada](docs/experimento_spark.md)
- [Consultas e roteiro do dashboard Databricks](docs/dashboard_databricks.md)

O relatório e a visualização são gerados automaticamente na pasta de saída. O repositório inclui o snapshot Bronze, as saídas locais de referência e os notebooks importáveis do Databricks, permitindo reproduzir a entrega sem depender de mudanças na API. Novas execuções criam outras pastas em `data/bronze` e `output`; revisar os arquivos antes de incluí-los em commits futuros.

O pipeline principal e seus testes foram executados localmente. O usuário também executou o experimento no Databricks Free Edition, Spark 4.2.0: **3.288 linhas diárias e 108 mensais, sem diferenças contra a referência**, conforme as saídas fornecidas e registradas em `docs/evidencias/databricks_execucao.json`. O tempo medido da chamada do experimento foi 11,014 segundos, sem alegação de ganho de desempenho. As três tabelas Silver/Gold foram publicadas no schema `workspace.citizentech`. O dashboard foi montado pelo usuário e revisado a partir das capturas enviadas: gráfico mensal, barras de dias intensos, tabela municipal e contexto dos dados. O link da versão publicada, fornecido pelo usuário, está em `docs/dashboard_databricks.md`; o acesso por terceiros não foi validado pelo agente.

## Fontes e atribuição

- [IBGE — API de localidades](https://servicodados.ibge.gov.br/api/docs/localidades): códigos oficiais, nomes, UF e região imediata.
- [Open-Meteo — Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api): precipitação diária, modelo ERA5 fixado para consistência da série.
- [Open-Meteo — termos e atribuição](https://open-meteo.com/en/terms): verificar condições de uso, atribuição e limites do serviço.
- [Copernicus Climate Data Store — ERA5](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels): conjunto subjacente de reanálise do ECMWF/Copernicus, acessado por intermédio do Open-Meteo.

Dados meteorológicos: Open-Meteo, com reanálise ERA5 do ECMWF/Copernicus. Cadastro territorial: IBGE. As análises e escolhas metodológicas são deste projeto, sem endosso dos provedores.
