# Registro do experimento Databricks

## Execução e origem da evidência

O usuário executou o notebook `CitizenTech_Databricks_Serverless` no Databricks Free Edition com compute Serverless e forneceu as saídas de validação e publicação das tabelas nesta conversa. O agente registrou essas saídas em `docs/evidencias/databricks_execucao.json`; não houve consulta independente ao workspace pelo agente.

| Campo | Resultado fornecido |
|---|---|
| Identificador | `20261109T131706Z_f0529b79` |
| Spark | 4.2.0 |
| Tempo medido da chamada do experimento | 11,014 segundos |
| Gold diária | 3.288 linhas; zero diferenças contra a referência |
| Gold mensal | 108 linhas; zero diferenças contra a referência |
| Catálogo e schema | `workspace.citizentech` |
| Pasta de execução | `/Volumes/workspace/citizentech/assets/runs/20261109T131706Z_f0529b79` |

O tempo corresponde à chamada `experiment_module.run`, que lê dados, executa transformações, grava/reabre Parquet e realiza ações de contagem. Não inclui todas as células, a publicação das tabelas Delta nem constitui benchmark controlado de desempenho.

## Processamento realizado

O experimento carregou JSONs de meteorologia e do IBGE com schemas explícitos, expandiu vetores diários, integrou os dados com joins por código municipal, calculou janelas de calendário com PySpark e agregou indicadores mensais em Spark SQL. Persistiu e reabriu Parquet e, em uma célula posterior, publicou Silver diária, Gold diária e Gold mensal como tabelas Delta gerenciadas.

Os nomes completos das três tabelas constam no JSON de evidência. A comparação cobre todas as chaves e colunas dos CSVs Gold de referência, com tolerância absoluta de 0,001 mm para campos terminados em `_mm` e 1e-6 para os demais números. Campos nulos são comparados explicitamente; `Decimal`, `int` e `float` recebem comparação numérica.

## Ajustes encontrados durante a experimentação

1. O ambiente retornou `[UNSUPPORTED_OPERATION] errorifexists is not supported` na gravação. O código passou a reservar uma pasta de saída nova antes de gravar os filhos com `overwrite`. A publicação Delta usa `CREATE TABLE ... USING DELTA AS SELECT`, preservando tabelas existentes.
2. Percentuais retornaram como `decimal.Decimal`. A primeira versão do comparador fazia comparação textual desses campos; foi corrigida para aplicar a mesma tolerância numérica. A validação posterior apresentou zero diferenças.

## Possibilidades e limitações

A experiência demonstra carga de datasets, manipulação de DataFrames, junções, janelas, consultas, agregações e persistência no ambiente Databricks. Não comprova benefício de processamento distribuído para esta amostra pequena. A configuração física de executores, o plano de execução e as métricas de shuffle não foram fornecidos e não são inferidos deste registro.

A validação inicial e a comparação de referência fazem leitura/coleta no driver, adequadas ao recorte de 3.288 linhas. Uma implantação de grande volume deve distribuir também essas verificações e dimensionar particionamento e armazenamento. Recursos da Free Edition têm cotas e não foram avaliados para operação contínua.

O dashboard foi montado pelo usuário e revisado pelo agente a partir das capturas fornecidas, conforme `docs/dashboard_databricks.md`. Inclui gráfico mensal, barras de dias com chuva intensa, tabela municipal e contexto metodológico. O usuário forneceu o link da versão publicada, registrado nesse documento; o acesso por terceiros não foi validado pelo agente. Para a entrega, exportar o notebook com saídas e guardar capturas das tabelas e do dashboard.
