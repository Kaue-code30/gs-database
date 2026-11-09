# Dashboard — Chuvas e preparação para enchentes

## Situação

O usuário montou o dashboard no Databricks Free Edition usando as tabelas da execução `20261109T131706Z_f0529b79`. O agente revisou as capturas fornecidas na conversa: gráfico mensal com três séries, barras de dias com chuva intensa, tabela de resumo e bloco de contexto. Não houve controle direto do workspace pelo agente. O usuário forneceu o link da versão publicada abaixo; o agente não conseguiu abri-lo com a ferramenta de navegação e não confirmou acesso sem autenticação.

[Abrir versão publicada no Databricks](https://dbc-7c2b7043-d5a8.cloud.databricks.com/dashboardsv3/01f1dc408dcd1121a6aa7037e6e266c0/published?o=7474652161886930)

Publicar um dashboard não equivale a disponibilizá-lo anonimamente na internet. O compartilhamento documentado do Databricks exige usuários autenticados e autorizados na conta. A opção **Anyone in my account can view** se refere aos membros da conta, não a qualquer visitante com o link. Referência: [compartilhamento de dashboards](https://docs.databricks.com/aws/en/dashboards/share/share).

### Resultado da revisão visual

- Gráfico mensal: séries de Santos, São Paulo e São Luiz do Paraitinga, no período 2023–2025. Foram solicitados rótulos em português para os eixos.
- Gráfico de barras: Santos com 15 dias >= 50 mm, São Paulo com 1 e São Luiz do Paraitinga com 0; rótulos em português conferidos na captura final.
- Tabela: 1.096 dias válidos para cada município. Totais de 3.553,8 mm em São Paulo, 3.801,2 mm em São Luiz do Paraitinga e 6.131,6 mm em Santos. Máximos diários de 58,1, 44,1 e 179,7 mm, respectivamente. Acumulados máximos de três dias exibidos: 91,3, 85,2 e 271,3 mm. Foi solicitado o título com período explícito: **Resumo por município — 2023–2025**.
- Bloco **Sobre os dados**: informa período, pontos selecionados, fontes IBGE/Open-Meteo/ERA5 e a distinção entre chuva em grade e ocorrência/probabilidade de enchente.

As evidências da revisão são as capturas enviadas pelo usuário na conversa; elas não foram salvas como arquivos locais. A revisão visual não incluiu testes de filtros nem de acesso por outros usuários.

## Criar e conectar

1. No menu lateral, selecionar **New → Dashboard**.
2. Nomear `CitizenTech — Chuvas e preparação para enchentes`.
3. Na aba **Data**, selecionar **Add SQL dataset** e colar o conteúdo de `sql/dashboard/01_precipitacao_mensal.sql`. Nomear o dataset `precipitacao_mensal` e executar a consulta.
4. Repetir para os arquivos `02_resumo_municipal.sql` e `03_episodios_para_investigacao.sql`, com nomes `resumo_municipal` e `episodios`.
5. Na aba **Canvas**, adicionar as visualizações descritas abaixo. Usar o SQL warehouse disponível na conta Free Edition.

As consultas são somente leitura, sem comandos de criação ou alteração de tabelas. Elas apontam explicitamente à execução validada; uma nova execução exige atualizar os nomes de tabela, sem misturar snapshots.

## Visualizações

| Título | Dataset | Tipo | Configuração |
|---|---|---|---|
| Precipitação mensal nos pontos selecionados (mm) | precipitacao_mensal | Linha | X: `month_date`; Y: soma de `total_mm`; cor/série: `municipality` |
| Dias com precipitação >= 50 mm | precipitacao_mensal | Barras | X: `municipality`; Y: soma de `heavy_days` |
| Resumo municipal — período completo 2023–2025 | resumo_municipal | Tabela | Município, cobertura, total, máximo diário, dias >= 50 mm e máximo de 3 dias |
| Dias para investigação de chuva intensa ou acumulada | episodios | Tabela | Município, data, precipitação e acumulados; ordenar por `precipitation_mm` decrescente |

Adicionar filtro de município e conectá-lo aos três datasets. Um filtro de período pode ser conectado a `month_date` do dataset mensal e `date` dos episódios. O resumo municipal foi pré-agregado para todo o período: seu título deve continuar indicando 2023–2025 e ele não deve ser apresentado como se respondesse ao filtro de data.

O dataset mensal exclui meses sem todos os dias válidos do calendário. O filtro mensal pode selecionar um intervalo distinto do diário; manter os rótulos visíveis para não sugerir equivalência exata entre recortes.

## Texto no dashboard

> Recorte histórico 2023–2025. Precipitação de pontos de grade ERA5/Open-Meteo integrada ao cadastro municipal IBGE. Os pontos não representam médias de toda a área municipal. Limiares exploratórios: 50 mm/dia ou 100 mm em três dias. Os indicadores selecionam períodos de investigação; não contabilizam enchentes nem estimam sua probabilidade. Janelas consecutivas podem representar o mesmo episódio.

Fontes: [Open-Meteo / ERA5](https://open-meteo.com/en/docs/historical-weather-api) e [IBGE](https://servicodados.ibge.gov.br/api/docs/localidades).

## Verificações e evidências

- Sem filtros: o dataset mensal deve ter 108 linhas, e o resumo municipal deve ter três municípios com 1.096 dias válidos cada.
- Os dias >= 50 mm no período completo devem ser 15 em Santos, 1 em São Paulo e 0 em São Luiz do Paraitinga, conforme a referência validada.
- Conferir unidades em mm, datas em ordem e separação das séries por município. Não somar precipitação entre pontos diferentes em um cartão de "chuva total regional".
- Conferir se o filtro municipal afeta as visualizações esperadas e se o resumo mantém o rótulo de período completo.
- Guardar capturas e exportar o notebook com saídas. Compartilhamento/publicação do dashboard deve ser tratado separadamente da sua criação.

Documentação oficial: [criar dashboard](https://docs.databricks.com/aws/en/dashboards/tutorials/create-dashboard), [datasets](https://docs.databricks.com/aws/en/dashboards/manage/data-modeling/datasets), [visualizações](https://docs.databricks.com/aws/en/dashboards/manage/visualizations).
