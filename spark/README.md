# Experimentação complementar com Spark e Databricks

## Importação em um único arquivo

O notebook `output/databricks/CitizenTech_Databricks.ipynb` incorpora o código, o snapshot Bronze e a referência Gold. Para reconstruí-lo, executar `python spark/build_notebook.py`. Ele foi verificado sintaticamente e o snapshot incorporado teve seus hashes validados. A versão corrigida para Serverless foi executada pelo usuário com paridade validada, conforme `docs/experimento_spark.md`.

No Databricks, usar a opção **Import** do Workspace para enviar o `.ipynb`. Antes de executar, conferir se a modalidade da conta é **Free Edition**, pois **Trial** é uma oferta temporária distinta. O notebook usa o catálogo atual, cria schema `citizentech` e volume `assets` se necessário, e cria tabelas Delta com nomes exclusivos por execução. Os parâmetros podem ser ajustados na primeira célula.

O notebook não consulta APIs nem precisa de uploads separados. Ao executar, ele usa compute, grava dados no volume e compara todas as colunas Gold com a referência local. As evidências são gravadas somente durante a execução real. Se a conta atual mostrar **Manage Trial**, verificar a modalidade antes de executar.

### Correção para o ambiente Serverless observado

A primeira execução na Free Edition retornou `[UNSUPPORTED_OPERATION] errorifexists is not supported` na gravação do experimento. O código passou a reservar exclusivamente uma pasta de saída nova e gravar seus arquivos filhos com `overwrite`. A reserva falha caso a pasta já exista, inclusive quando pertence a uma execução parcial. Tabelas Delta são publicadas por `CREATE TABLE ... USING DELTA AS SELECT`, sem substituir tabelas existentes.

O notebook corrigido está em `output/databricks/CitizenTech_Databricks_Serverless.ipynb`. Importe como um notebook novo e execute **Run all**, criando outra pasta de execução. A execução `20261109T131706Z_f0529b79` foi confirmada pelas saídas fornecidas pelo usuário: 3.288 linhas diárias e 108 mensais, com zero diferenças.

O comparador também aceita `decimal.Decimal`, tipo retornado pelo Spark SQL para alguns percentuais. Esses valores usam a mesma tolerância numérica dos tipos `int` e `float`, em vez de comparação textual. A correção não altera os dados processados. Em um notebook já em execução, adicionar `from decimal import Decimal` à célula de comparação e incluir `Decimal` no `isinstance`; executar novamente essa célula e continuar as seguintes.

**Status: executada e validada no Databricks Free Edition pelo usuário.** Spark 4.2.0; tempo observado da chamada do experimento de 11,014 segundos; sem diferenças nas tabelas Gold. O registro e as limitações estão em `docs/experimento_spark.md`. Este computador não dispõe de Java/Spark; o agente não consultou independentemente o workspace. Não há benchmark controlado ou evidência da configuração física de executores.

## O que o experimento implementa

`experiment.py` carrega o snapshot Bronze com schemas explícitos, expande os vetores diários, integra meteorologia, cadastro municipal e pontos configurados com joins, calcula janelas de calendário usando `rangeBetween`, executa agregações em Spark SQL e persiste/reabre tabelas Parquet. A fórmula de Wilson acompanha a referência local. `execution.json` só é criado depois de executar as ações Spark e reabrir os resultados.

A verificação de hashes e do contrato inicial reutiliza Python no driver. Isso mantém a consistência com a referência para o pequeno recorte. Em uma implantação de grande volume, validações, leitura e particionamento devem ser redesenhados para evitar processamento integral no driver.

## Executar em ambiente Spark

1. Disponibilizar o repositório e o snapshot Bronze em caminhos acessíveis ao driver e aos executores.
2. Em um ambiente Spark com Java e Python compatíveis, executar:

```text
spark-submit spark/experiment.py --bronze data/bronze/20261109T124404Z_377aa3e5 --output output/spark_primeira_execucao
```

O caminho de saída deve ser novo. O experimento não faz downloads nem sobrescreve execuções anteriores. Para clusters remotos, caminhos relativos locais não bastam: usar armazenamento compartilhado.

## Executar no Databricks

Preparar um workspace com capacidade Spark e um volume acessível ao compute. Não há provisionamento ou credenciais configurados neste projeto. Use um volume já autorizado para a atividade.

1. Colocar `pipeline.py` e a pasta `spark` em um diretório do projeto acessível ao notebook.
2. Transferir o snapshot completo, incluindo manifesto, JSONs e corpos `.body`, para um caminho `/Volumes/<catalogo>/<schema>/<volume>/bronze/<execucao>`.
3. No notebook, ajustar o diretório do projeto em `sys.path` e chamar:

```python
import sys
sys.path.insert(0, "/Workspace/Users/<usuario>/<projeto>")
from spark.experiment import run

daily, monthly = run(
    spark,
    "/Volumes/<catalogo>/<schema>/<volume>/bronze/<execucao>",
    "/Volumes/<catalogo>/<schema>/<volume>/experimentos/<nova_execucao>",
)
display(monthly.orderBy("municipality_id", "month"))
daily.explain("formatted")
```

Os caminhos são exemplos para preencher com recursos existentes. O compute deve oferecer acesso ao mesmo volume via filesystem Python e Spark. A execução confirmada utilizou o notebook autocontido e o volume `workspace.citizentech.assets`.

## Evidências para concluir a etapa

- Guardar `execution.json`, versão do runtime e log de execução sem dados de credenciais.
- Confirmar 3.288 linhas diárias, 108 linhas mensais e zero precipitações ausentes para o snapshot de referência.
- Comparar, por município/data, `precipitation_mm`, `rain_3d_mm`, `rain_7d_mm`, `antecedent_7d_mm` e indicadores com `output/<execucao>/gold/daily.csv`.
- Comparar, por município/mês, contagens, cobertura, totais, máximos e intervalos com `gold/monthly.csv`. Usar tolerância de 0,001 mm para agregações e 1e-6 para percentuais, preservando nulos.
- Inspecionar o plano físico dos joins, agregações e janelas; registrar shuffles observados e a configuração real de partições.
- Registrar tempos observados com o mesmo snapshot. Nesta escala pequena, o custo de inicialização e distribuição pode superar o ganho; não extrapolar um benchmark sem medição.

## Discussão a preencher após executar

Registrar ambiente, data, contagens, diferenças encontradas, armazenamento utilizado, plano físico e limitações. Não declarar ganho de desempenho ou escalabilidade comprovada antes da medição. O experimento demonstra operações distribuíveis, enquanto o recorte local cabe confortavelmente em memória.

Documentação oficial consultada: [janelas rangeBetween](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.Window.rangeBetween.html), [arrays_zip](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.functions.arrays_zip.html).
