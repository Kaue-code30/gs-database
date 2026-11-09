# Catálogo e dicionário de dados

## Fontes investigadas e selecionadas

### IBGE — Localidades

- Documentação oficial: https://servicodados.ibge.gov.br/api/docs/localidades
- Endpoint: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo}`.
- Formato: JSON; uma resposta por município configurado.
- Atributos utilizados: `id`, `nome`, `regiao-imediata.nome`, `regiao-imediata.regiao-intermediaria.UF.sigla`.
- Contribuição: identificação e enriquecimento administrativo dos registros meteorológicos.
- Confiabilidade: cadastro oficial do IBGE. A API representa a divisão territorial disponível na consulta, sem reconstruir suas versões históricas para cada dia de 2023–2025.
- Limitação: não fornece, nesta consulta, população, exposição, ocorrência de desastres ou coordenadas do ponto de estudo.

### Open-Meteo — Historical Weather API / ERA5

- Documentação oficial: https://open-meteo.com/en/docs/historical-weather-api
- Endpoint: `https://archive-api.open-meteo.com/v1/archive`.
- Parâmetros: latitude, longitude, `start_date`, `end_date`, `daily=precipitation_sum`, `timezone=America/Sao_Paulo`, `models=era5`.
- Formato: JSON, com datas e precipitação em vetores correspondentes.
- Unidade: mm por dia local. O pipeline exige `daily_units.precipitation_sum = mm`.
- Contribuição: série diária consistente de precipitação para cada ponto selecionado.
- Confiabilidade: reanálise ERA5 acessada pelo provedor; modelo fixado para evitar a troca automática entre modelos ao longo do período.
- Limitações: produto em grade, aproximadamente 0,25° conforme a documentação, que pode suavizar extremos locais; não equivale a um pluviômetro ou à média do município. A célula devolvida pode diferir da coordenada solicitada.
- Atribuição: Open-Meteo e ECMWF/Copernicus ERA5. Termos do serviço: https://open-meteo.com/en/terms. A licença dos dados e as condições do serviço devem ser verificadas antes de redistribuição ou ampliação do uso.

### Fontes de expansão ainda não integradas

Registros oficiais de ocorrências de desastres, pluviômetros locais, níveis de rios, relevo e exposição da população seriam necessários para avaliar risco e danos. Não foram usados números provenientes dessas fontes no relatório. A integração atual combina meteorologia e cadastro territorial, não observações independentes de enchentes.

## Proveniência e periodicidade

O manifesto registra configuração integral, URL exata, horário de coleta em UTC, nome do arquivo e SHA-256 do corpo original e do JSON normalizado. O corpo `.body` preserva a resposta recebida; o `.json` é descomprimido e serializado para leitura. Os hashes são verificados antes de cada processamento.

A aquisição atual faz seis requisições lógicas: duas fontes para cada um dos três municípios. Falhas transitórias podem provocar até três tentativas por requisição. Uma coleta incompleta preserva o que foi obtido, mas não gera camada analítica. Os hashes verificam integridade em relação ao manifesto local, não autenticidade criptográfica do provedor.

O histórico é adquirido sob demanda. Não há agendador ou promessa de atualização em tempo real. Para atualizar o recorte, alterar as datas e criar outra execução. Comparar versões antes de substituir conclusões publicadas.

## Silver: `daily.csv` / `silver_daily`

Chave: `(municipality_id, date)`, uma linha por ponto municipal e dia esperado.

| Campo | Tipo lógico | Significado |
|---|---|---|
| municipality_id | inteiro | Código municipal oficial do IBGE, confirmado na resposta |
| municipality | texto | Nome retornado pelo IBGE |
| uf | texto | Sigla da UF |
| immediate_region | texto | Região geográfica imediata atual |
| date | data ISO | Dia local em America/Sao_Paulo |
| precipitation_mm | decimal ou nulo | Soma diária de precipitação da célula ERA5, em mm |
| requested_latitude / requested_longitude | decimal | Ponto configurado pelo estudo, WGS84 |
| grid_latitude / grid_longitude | decimal | Coordenadas devolvidas pelo serviço meteorológico |

## Gold diária: `daily.csv` / `gold_daily`

Contém todos os campos Silver e as features abaixo. Uma janela completa requer todos os dias e valores disponíveis; início de série e ausência geram nulos.

| Campo | Definição | Uso |
|---|---|---|
| rain_3d_mm | Soma de t, t−1, t−2 | Acúmulo recente para investigação |
| rain_7d_mm | Soma de t até t−6 | Persistência da chuva recente |
| antecedent_7d_mm | Soma de t−1 até t−7 | Contexto anterior ao dia, sem incluir t |
| heavy_day | 1 se chuva diária >= 50 mm; 0 caso contrário; nulo se ausente | Contagem de dias intensos conforme limiar exploratório |
| accumulated_attention | 1 se rain_3d_mm >= 100 mm; 0 caso contrário; nulo se janela incompleta | Seleção de dias com acúmulo elevado |
| month | `AAAA-MM` | Agrupamento temporal |

Os valores 50 e 100 mm são parâmetros didáticos ajustáveis em `config.json`. Não foram calibrados contra ocorrências nem apresentados como critérios oficiais. Dias consecutivos com atenção são contados separadamente, podendo pertencer ao mesmo episódio de chuva.

## Gold mensal: `monthly.csv` / `gold_monthly`

Chave: `(municipality_id, month)`. Identificação inclui código e nome municipal.

| Campo | Definição e interpretação |
|---|---|
| expected_days | Número de datas solicitadas naquele mês; meses nas bordas podem ser parciais |
| valid_days | Dias com precipitação não nula |
| coverage_pct | 100 × valid_days / expected_days |
| full_calendar_month | 1 somente quando há valores válidos para todos os dias do mês civil; 0 nos demais casos |
| total_mm | Soma dos valores válidos; nulo sem valores; cobertura deve acompanhar a interpretação |
| max_daily_mm | Máximo válido no período mensal |
| heavy_days | Número de valores válidos >= limiar diário |
| heavy_days_pct | 100 × heavy_days / valid_days; nulo sem valores |
| wilson_low_pct / wilson_high_pct | Intervalo de Wilson de 95% para a proporção de dias acima do limiar |
| valid_3d_windows | Dias com janela de 3 dias completa |
| attention_3d_days | Dias com acumulado de 3 dias acima do limiar; interpretar junto a valid_3d_windows |

Wilson usa z=1,959963984540054 e aproximação binomial. Dependência temporal entre chuvas limita o uso inferencial: não é intervalo de risco de enchente. O P95 do relatório usa dias >= 1 mm e interpolação linear em toda a amostra, apenas para descrição retrospectiva.
