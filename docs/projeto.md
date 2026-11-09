# Investigação do problema

## Integrantes

| Nome | RM |
|---|---|
| Kaue Lima | 562071 |
| Pedro Gonçalves | 561506 |
| Edmario | 565486 |

## Pergunta e recorte

Quais períodos entre janeiro de 2023 e dezembro de 2025 apresentam maiores totais e acumulados de chuva nos pontos selecionados de São Paulo, Santos e São Luiz do Paraitinga, e como essa informação pode apoiar a preparação municipal para investigar enchentes?

As pessoas potencialmente beneficiadas são moradores de áreas sujeitas a alagamentos e equipes de manutenção urbana e Defesa Civil. O estudo não estima quantas pessoas foram afetadas: não há base de população exposta ou registro de danos integrado.

Os municípios oferecem um recorte exploratório entre capital, litoral e interior paulista. Essa escolha busca diversidade espacial para comparação; não constitui amostragem representativa nem seleção comprovada dos locais mais vulneráveis. As coordenadas em `config.json` são aproximações de pontos nas sedes urbanas, escolhidas como parâmetros do estudo.

## Justificativa e viabilidade

Precipitação diária é mensurável e pode ser adquirida por API pública. O cadastro do IBGE permite integrar códigos oficiais, região imediata e UF. A janela de três anos fornece material para estudar episódios e variação mensal, com execução viável em um computador pessoal. Uma série de referência climatológica e registros de enchentes seriam necessários para conclusões sobre anomalias persistentes e associação a danos.

## Decisões apoiadas

| Decisão | Evidência produzida | Informação adicional necessária |
|---|---|---|
| Selecionar episódios para investigação | Máximos diários e acumulados de 3/7 dias | Registro oficial de ocorrência e localização |
| Preparar calendário de inspeções | Totais e frequência mensal de chuva intensa | Série histórica longa, drenagem e capacidade operacional |
| Definir próximos pontos a instrumentar | Contrastes entre os pontos e lacunas de cobertura | Estações locais e delimitação de bacias |
| Avaliar intervenções futuras | Linha de base descritiva da precipitação | Ocorrências, exposição e comparação antes/depois controlada |

As recomendações do relatório se baseiam nos resultados efetivamente processados. Nenhum limiar exploratório substitui parâmetros oficiais de alerta. A ausência de dias acima de 50 mm na reanálise não significa ausência de enchentes.

## Relação com os entregáveis

| Item da atividade | Material |
|---|---|
| Investigação e justificativa | Este documento |
| Catálogo de dados | `docs/catalogo_dados.md` e manifesto de coleta |
| Arquitetura e fluxo | `docs/arquitetura.md` |
| Pipeline implementado | `pipeline.py`, `config.json`, `tests/test_pipeline.py` |
| Feature Engineering | Janelas e limiares em `pipeline.py`, documentados na arquitetura |
| Camada analítica | CSVs Gold e tabelas SQLite por execução |
| Análises e estatística | SQL, P95, frequências, intervalos de Wilson e relatório |
| Visualização quando aplicável | Gráfico SVG mensal por ponto, gerado automaticamente |
| Experimentação Spark | Executado pelo usuário no Databricks Free Edition; registro em `docs/experimento_spark.md` e JSON de evidência |
| Relatório executivo | `output/<execucao>/relatorio_executivo.md` |

## Critérios de aceitação

1. Obter duas fontes reais, preservar os corpos recebidos e documentar URLs e horários.
2. Validar identidade municipal, unidade, timezone e sequência completa de datas, incluindo ano bissexto.
3. Não converter ausência em zero; rejeitar valores negativos, não numéricos ou infinitos.
4. Separar Bronze, Silver e Gold e manter chaves únicas e rastreabilidade.
5. Construir janelas de calendário por município, sem usar dados futuros.
6. Explicitar definições, denominadores, limiares e limites das análises.
7. Reproduzir Silver e Gold sem rede a partir do mesmo snapshot.
8. Executar e registrar o experimento PySpark em ambiente compatível para concluir a etapa complementar.

Os critérios 1 a 7 têm implementação e verificação local. O critério 8 foi atendido pela execução no Databricks Free Edition, com saídas fornecidas pelo usuário, validação de paridade sem diferenças e registro em `docs/experimento_spark.md`.
