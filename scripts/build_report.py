"""Gera o relatório acadêmico Word a partir dos dados reais da entrega.

Requer python-docx e Node com sharp para rasterizar as figuras SVG.
Executar com os runtimes de documentos disponibilizados pelo ambiente.
"""
import argparse
import csv
import json
import subprocess
from collections import defaultdict
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'output/20261109T125036Z_b1308a4d'
BRONZE = ROOT / 'data/bronze/20261109T124404Z_377aa3e5'
TMP = ROOT / 'tmp/word_report'
DEST = ROOT / 'output/docs/Relatorio_CitizenTech_GS.docx'
REPO = 'https://github.com/Kaue-code30/gs-database'
DASHBOARD = 'https://dbc-7c2b7043-d5a8.cloud.databricks.com/dashboardsv3/01f1dc408dcd1121a6aa7037e6e266c0/published?o=7474652161886930'
TEAM = [('Kaue Lima', '562071'), ('Pedro Gonçalves', '561506'), ('Edmario', '565486')]


def number(value, places=1):
    return f'{float(value):,.{places}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def load_csv(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def hyperlink(paragraph, label, url):
    relation = paragraph.part.relate_to(url, 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink', is_external=True)
    link = OxmlElement('w:hyperlink')
    link.set(qn('r:id'), relation)
    run = OxmlElement('w:r')
    prop = OxmlElement('w:rPr')
    color = OxmlElement('w:color')
    color.set(qn('w:val'), '155E75')
    prop.append(color)
    underline = OxmlElement('w:u')
    underline.set(qn('w:val'), 'single')
    prop.append(underline)
    run.append(prop)
    text = OxmlElement('w:t')
    text.text = label
    run.append(text)
    link.append(run)
    paragraph._p.append(link)


def p(doc, text='', style=None, bold=False):
    paragraph = doc.add_paragraph(style=style)
    paragraph.add_run(text).bold = bold
    return paragraph


def h(doc, text, level=1):
    return doc.add_heading(text, level=level)


def page(doc, title):
    doc.add_page_break()
    h(doc, title)


def table(doc, headers, rows, widths, numeric=()):
    result = doc.add_table(rows=1, cols=len(headers))
    result.autofit = False
    for col, width in zip(result.columns, widths):
        col.width = Cm(width)
    for cell, value in zip(result.rows[0].cells, headers):
        cell.text = str(value)
    for row in rows:
        cells = result.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = str(value)
    for row_index, row in enumerate(result.rows):
        props = row._tr.get_or_add_trPr()
        no_split = OxmlElement('w:cantSplit')
        props.append(no_split)
        if row_index == 0:
            repeat = OxmlElement('w:tblHeader')
            props.append(repeat)
        for col_index, cell in enumerate(row.cells):
            cell.width = Cm(widths[col_index])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr = cell._tc.get_or_add_tcPr()
            shade = OxmlElement('w:shd')
            shade.set(qn('w:fill'), '183B56' if row_index == 0 else ('F0F5F8' if row_index % 2 else 'FFFFFF'))
            tcpr.append(shade)
            borders = OxmlElement('w:tcBorders')
            for edge in ('top', 'left', 'bottom', 'right'):
                border = OxmlElement('w:' + edge)
                for key, value in [('val', 'single'), ('sz', '4'), ('color', 'D9D9D9')]:
                    border.set(qn('w:' + key), value)
                borders.append(border)
            tcpr.append(borders)
            margins = OxmlElement('w:tcMar')
            for edge in ('top', 'left', 'bottom', 'right'):
                item = OxmlElement('w:' + edge)
                item.set(qn('w:w'), '85')
                item.set(qn('w:type'), 'dxa')
                margins.append(item)
            tcpr.append(margins)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.space_before = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.08
                if col_index in numeric:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.size = Pt(9.3)
                    run.font.color.rgb = RGBColor.from_string('FFFFFF' if row_index == 0 else '000000')
                    run.bold = row_index == 0
    p(doc).paragraph_format.space_after = Pt(2)
    return result


def picture(doc, path, caption, alt, width=16.0):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.keep_with_next = True
    shape = paragraph.add_run().add_picture(str(path), width=Cm(width))
    shape._inline.docPr.set('descr', alt)
    cap = p(doc, caption, 'Caption')
    cap.paragraph_format.keep_with_next = False


def linkline(doc, label, url):
    paragraph = doc.add_paragraph()
    hyperlink(paragraph, label, url)
    return paragraph


def code(doc, text):
    paragraph = p(doc, text, 'Code')
    return paragraph


def make_figures(node_bin, node_modules, summary):
    TMP.mkdir(parents=True, exist_ok=True)
    architecture = '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="460" viewBox="0 0 1200 460">
    <rect width="1200" height="460" fill="white"/>
    <g font-family="Arial" fill="#111111" text-anchor="middle">
    <text x="600" y="32" font-size="25">Fluxo de dados e produtos analíticos</text>
    <rect x="20" y="80" width="210" height="100" rx="9" fill="#edf3f8" stroke="#b9c9d5"/>
    <text x="125" y="120" font-size="23">IBGE</text><text x="125" y="150" font-size="19">Cadastro municipal</text>
    <rect x="20" y="210" width="210" height="100" rx="9" fill="#edf3f8" stroke="#b9c9d5"/>
    <text x="125" y="250" font-size="23">Open Meteo</text><text x="125" y="280" font-size="19">Precipitação ERA5</text>
    <rect x="290" y="145" width="240" height="135" rx="9" fill="#f3e5d5" stroke="#c9af91"/>
    <text x="410" y="182" font-size="25">Bronze</text><text x="410" y="215" font-size="19">Corpos e JSON originais</text><text x="410" y="245" font-size="19">Manifesto e hashes</text>
    <rect x="590" y="145" width="240" height="135" rx="9" fill="#e9edf1" stroke="#a8b3bf"/>
    <text x="710" y="182" font-size="25">Silver</text><text x="710" y="215" font-size="19">Validação e integração</text><text x="710" y="245" font-size="19">Município e dia</text>
    <rect x="890" y="145" width="290" height="135" rx="9" fill="#f5edce" stroke="#c5b66d"/>
    <text x="1035" y="182" font-size="25">Gold</text><text x="1035" y="215" font-size="19">Janelas e indicadores</text><text x="1035" y="245" font-size="19">Diário e mensal</text>
    <g stroke="#183b56" stroke-width="3" fill="none"><path d="M230 130 H260 V210 H290"/><path d="M230 260 H260 V210"/><path d="M530 210 H590"/><path d="M830 210 H890"/><path d="M1035 280 V345 H600"/></g>
    <text x="600" y="385" font-size="22">Local  CSV e SQLite    |    Databricks  Parquet e Delta</text>
    <text x="600" y="424" font-size="22">Relatório executivo e dashboard com gráficos e tabela municipal</text>
    </g></svg>'''
    (TMP/'arquitetura.svg').write_text(architecture, encoding='utf-8')
    from xml.sax.saxutils import escape
    maximum = max(r['heavy'] for r in summary)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="470" viewBox="0 0 1200 470">',
        '<rect width="1200" height="470" fill="white"/>', '<g font-family="Arial" fill="#111">',
        '<text x="50" y="36" font-size="25">Dias com precipitação de pelo menos 50 mm em 2023 a 2025</text>']
    for tick in range(0, maximum+1, 5):
        y = 365-tick/maximum*270
        svg += [f'<line x1="90" y1="{y}" x2="1150" y2="{y}" stroke="#D9D9D9"/>', f'<text x="50" y="{y+7}" font-size="20">{tick}</text>']
    for i, row in enumerate(sorted(summary, key=lambda r:r['heavy'], reverse=True)):
        x = 150+i*350
        height = row['heavy']/maximum*270
        svg += [f'<rect x="{x}" y="{365-height}" width="230" height="{height}" fill="#247d95"/>',
                f'<text x="{x+115}" y="{350-height}" text-anchor="middle" font-size="24">{row["heavy"]}</text>',
                f'<text x="{x+115}" y="408" text-anchor="middle" font-size="20">{escape(row["name"])}</text>']
    svg += ['<text x="90" y="452" font-size="18">Contagem de dias meteorológicos   Não representa ocorrências de enchente</text>', '</g></svg>']
    (TMP/'dias_intensos.svg').write_text('\n'.join(svg), encoding='utf-8')
    monthly_svg = (REFERENCE/'precipitacao_mensal.svg').read_text(encoding='utf-8')
    for old, new in [('font-size="10"','font-size="16"'), ('font-size="11"','font-size="16"'), ('font-size="12"','font-size="15"'), ('font-size="17"','font-size="22"')]:
        monthly_svg = monthly_svg.replace(old, new)
    (TMP/'mensal_legivel.svg').write_text(monthly_svg, encoding='utf-8')
    sources = [(TMP/'mensal_legivel.svg', TMP/'mensal.png'), (TMP/'arquitetura.svg', TMP/'arquitetura.png'), (TMP/'dias_intensos.svg', TMP/'dias_intensos.png')]
    js = "const sharp=require(process.argv[1]); sharp(process.argv[2],{density:200}).png().toFile(process.argv[3]).catch(e=>{console.error(e);process.exit(1)});"
    for source, target in sources:
        subprocess.run([str(node_bin), '-e', js, str(node_modules/'sharp'), str(source), str(target)], check=True)


def main(node_bin, node_modules):
    from pipeline import percentile
    daily = load_csv(REFERENCE/'gold/daily.csv')
    monthly = load_csv(REFERENCE/'gold/monthly.csv')
    config = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
    evidence = json.loads((ROOT/'docs/evidencias/databricks_execucao.json').read_text(encoding='utf-8'))
    manifest = json.loads((BRONZE/'manifest.json').read_text(encoding='utf-8'))
    by_city = defaultdict(list)
    for row in daily:
        by_city[row['municipality_id']].append(row)
    summary = []
    annual = []
    for city in config['municipalities']:
        group = by_city[str(city['id'])]
        values = [float(r['precipitation_mm']) for r in group if r['precipitation_mm'] != '']
        summary.append({'name':group[0]['municipality'], 'n':len(values), 'total':sum(values), 'maximum':max(values),
            'heavy':sum(int(r['heavy_day']) for r in group), 'max3':max(float(r['rain_3d_mm']) for r in group if r['rain_3d_mm']),
            'max7':max(float(r['rain_7d_mm']) for r in group if r['rain_7d_mm']), 'p95':percentile([v for v in values if v>=1], .95)})
        for year in ('2023','2024','2025'):
            rows = [r for r in group if r['date'].startswith(year)]
            annual.append([group[0]['municipality'],year,len(rows),number(sum(float(r['precipitation_mm']) for r in rows)),int(sum(float(r['heavy_day']) for r in rows))])
    top = sorted(monthly, key=lambda r:float(r['total_mm']), reverse=True)[:5]
    make_figures(node_bin, node_modules, summary)
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(1.9), Cm(1.8)
    section.left_margin, section.right_margin = Cm(2.1), Cm(2.1)
    section.footer_distance = Cm(.8)
    for name in ('Normal','Title','Subtitle','Heading 1','Heading 2','Caption'):
        style = doc.styles[name]
        style.font.name = 'Calibri'
        style.font.color.rgb = RGBColor(0,0,0)
        style.paragraph_format.space_after = Pt(7)
    normal = doc.styles['Normal']
    normal.font.size = Pt(10.5)
    normal.paragraph_format.line_spacing = 1.12
    normal.paragraph_format.widow_control = True
    doc.styles['Title'].font.size = Pt(27)
    doc.styles['Title'].font.bold = True
    for border in doc.styles.element.xpath('.//w:pBdr'):
        border.getparent().remove(border)
    doc.styles['Subtitle'].font.size = Pt(14)
    doc.styles['Heading 1'].font.size = Pt(17)
    doc.styles['Heading 2'].font.size = Pt(12)
    for name in ('Heading 1','Heading 2'):
        doc.styles[name].paragraph_format.keep_with_next = True
    doc.styles['Caption'].font.size = Pt(9)
    doc.styles['Caption'].font.italic = True
    if 'Code' not in doc.styles:
        doc.styles.add_style('Code', 1)
    doc.styles['Code'].font.name = 'Consolas'
    doc.styles['Code'].font.size = Pt(8.5)
    doc.styles['Code'].paragraph_format.space_after = Pt(5)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run('CitizenTech  |  ')
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    footer._p.append(field)
    for run in footer.runs:
        run.font.size = Pt(8)
    doc.core_properties.title = 'Chuvas e preparação para enchentes'
    doc.core_properties.subject = 'Global Solution 2026.2 Big Data e Analytics'
    doc.core_properties.author = 'Kaue Lima; Pedro Gonçalves; Edmario'
    doc.core_properties.keywords = 'CitizenTech; ERA5; IBGE; Medallion; PySpark; Databricks'

    p(doc, 'GLOBAL SOLUTION 2026 2', bold=True)
    p(doc, 'Chuvas e preparação para enchentes', 'Title')
    p(doc, 'Relatório do projeto CitizenTech de Big Data e Analytics', 'Subtitle')
    p(doc, 'Análise histórica de pontos selecionados de São Paulo, Santos e São Luiz do Paraitinga entre 1 de janeiro de 2023 e 31 de dezembro de 2025.')
    h(doc, 'Integrantes', 2)
    table(doc, ['Nome','RM'], TEAM, [12.0,4.8], numeric=(1,))
    h(doc, 'Apresentação', 2)
    p(doc, 'Desenvolvemos um pipeline que integra precipitação histórica ERA5 obtida pelo Open-Meteo ao cadastro municipal do IBGE. O processamento organiza dados em Bronze, Silver e Gold e produz indicadores, análises, recomendações e um dashboard no Databricks.')
    p(doc, 'A execução no Spark 4.2.0 produziu 3.288 linhas diárias e 108 mensais, com zero diferenças em relação à referência local. O ponto de Santos apresentou os maiores totais e mais dias acima do limiar exploratório de 50 mm. Essa evidência seleciona períodos para investigação; não estabelece ocorrência ou probabilidade de enchentes.')
    h(doc, 'Acessos da entrega', 2)
    linkline(doc, 'Repositório GitHub com código dados notebooks e documentação', REPO)
    linkline(doc, 'Dashboard publicado no Databricks', DASHBOARD)
    p(doc, 'O dashboard requer autenticação e autorização na conta Databricks. O repositório contém os dados e as saídas locais para reprodução e avaliação independente do acesso ao workspace.')
    p(doc, 'Data da entrega  9 de novembro de 2026', bold=True)

    page(doc, '1 Investigação e definição do problema')
    h(doc, 'Problema e pergunta de investigação', 2)
    p(doc, 'Equipes municipais precisam compreender quando a precipitação se intensifica e se acumula para orientar preparação, inspeções e investigação de episódios de inundação. Informações meteorológicas isoladas e sem identificação territorial dificultam a comparação entre localidades e períodos.')
    p(doc, 'A pergunta deste estudo é quais períodos de 2023 a 2025 apresentaram maiores totais e acumulados de chuva nos pontos selecionados dos três municípios e como esses padrões podem apoiar decisões de preparação municipal.')
    h(doc, 'Público afetado e dimensão analisada', 2)
    p(doc, 'O público potencialmente beneficiado inclui moradores de áreas sujeitas a alagamentos, equipes de manutenção urbana e Defesa Civil. Analisamos a dimensão meteorológica e temporal da preparação. Não estimamos pessoas expostas ou afetadas porque a solução ainda não integra população, localização de danos ou ocorrências confirmadas.')
    h(doc, 'Recorte e viabilidade', 2)
    p(doc, 'Selecionamos capital, litoral e interior paulista para uma comparação exploratória de contextos distintos. Os pontos configurados ficam próximos às sedes urbanas e não equivalem à média municipal, a uma bacia hidrográfica ou a bairros. A seleção não é uma amostra representativa de municípios vulneráveis.')
    table(doc, ['Município','Código IBGE','Latitude','Longitude'], [[c['label'],c['id'],number(c['latitude'],4),number(c['longitude'],4)] for c in config['municipalities']], [7.0,3.4,3.2,3.2], numeric=(1,2,3))
    p(doc, 'O intervalo inclui 2024 bissexto e contém 1.096 dias por município. As fontes públicas tornam a aquisição viável e a dimensão da base permite uma referência local reproduzível antes da experimentação em nuvem.')
    h(doc, 'Decisões e informações necessárias', 2)
    p(doc, 'Os indicadores apoiam a seleção de episódios para cruzamento com registros oficiais, a investigação de períodos recorrentes de chuva intensa e o planejamento de inspeções de drenagem. Priorizar obras ou emitir alertas exige também níveis de rios, relevo, drenagem, previsão e exposição, além da validação por equipes competentes.')

    page(doc, '2 Investigação e aquisição dos dados')
    h(doc, 'Catálogo das fontes utilizadas', 2)
    p(doc, 'Integramos duas fontes com funções diferentes. O cadastro oficial do IBGE fornece identidade e contexto administrativo; o Open-Meteo disponibiliza a série meteorológica de reanálise. Essa integração evita tratar os dados climáticos como um dataset isolado, embora não acrescente observações de enchentes.')
    table(doc, ['Fonte','Dados utilizados','Papel e restrição'], [
        ['IBGE Localidades','Código, nome, UF e região imediata','Identificação oficial atual. Não reconstitui versões territoriais históricas.'],
        ['Open-Meteo com ERA5','Data, precipitação diária, unidade, timezone e célula retornada','Histórico em grade. Não equivale a observação de pluviômetro ou média municipal.']
    ], [4.0,5.6,7.2])
    h(doc, 'Seleção e confiabilidade', 2)
    p(doc, 'O IBGE é a referência oficial para códigos e divisões municipais. A consulta de localidades é adequada ao enriquecimento territorial, mas não fornece população exposta nesta implementação. Usamos a região geográfica imediata retornada pela API.')
    p(doc, 'Fixamos o modelo ERA5 para manter consistência da série. A documentação do Open-Meteo descreve uma grade de aproximadamente 0,25 grau para esse modelo. A resolução espacial pode suavizar extremos locais; a célula retornada pode diferir da coordenada solicitada. A análise mantém ambas as coordenadas para rastreabilidade.')
    h(doc, 'Aquisição implementada', 2)
    p(doc, 'A coleta usa seis requisições lógicas, uma por fonte para cada município. Solicitamos precipitation_sum diária, unidade em mm e timezone America/Sao_Paulo. A função de aquisição define timeout de 45 segundos e até três tentativas para falhas transitórias, sem substituir dados indisponíveis por números simulados.')
    code(doc, 'IBGE  /api/v1/localidades/municipios/{codigo}\nOpen-Meteo  /v1/archive\nParâmetros  start_date  end_date  latitude  longitude\n            daily=precipitation_sum  models=era5')
    p(doc, 'A Bronze preserva o corpo recebido e o JSON normalizado. O manifesto registra URLs exatas, horários UTC, configuração e hashes SHA-256. Os seis arquivos JSON e seis corpos podem ser auditados e reprocessados sem rede.')
    h(doc, 'Atualização e fontes de expansão', 2)
    p(doc, 'A aquisição é executada sob demanda; não há atualização contínua ou agendador ativo. Registros oficiais de desastres, estações locais, níveis de rios e exposição são próximos candidatos de integração. Nenhum resultado neste relatório pressupõe que essas bases já foram incorporadas.')

    page(doc, '3 Arquitetura da solução e pipeline')
    picture(doc, TMP/'arquitetura.png', 'Figura 1  Arquitetura Medallion implementada no projeto', 'Fontes IBGE e Open-Meteo alimentam Bronze, seguida por Silver, Gold e produtos locais ou no Databricks.')
    h(doc, 'Camadas e responsabilidades', 2)
    p(doc, 'Bronze armazena os dados adquiridos e sua proveniência. Silver verifica contratos, padroniza a série diária e integra a identidade municipal. Gold acrescenta acumulados, indicadores e agregações mensais. A chave diária é a combinação do código municipal com a data local.')
    h(doc, 'Fluxo implementado', 2)
    for text in [
        'Validar configuração e intervalo histórico antes de consultar as APIs.',
        'Adquirir as fontes e registrar corpos, JSONs, URLs e hashes na Bronze.',
        'Verificar integridade, identidade, datas, unidade, timezone e valores.',
        'Integrar as fontes e construir a Silver diária.',
        'Calcular features por calendário e produzir Gold diária e mensal.',
        'Exportar CSV, SQLite, relatório e gráfico; no experimento, persistir Parquet e tabelas Delta.'
    ]:
        p(doc, text, 'List Number')
    h(doc, 'Decisões técnicas', 2)
    p(doc, 'O pipeline principal usa Python com biblioteca padrão e SQLite para permitir execução local simples. A base possui apenas 3.288 registros e não exige infraestrutura distribuída permanente. A experimentação complementar utiliza PySpark e Databricks para explorar operações distribuíveis e armazenamento analítico em nuvem.')
    p(doc, 'Cada execução usa uma pasta exclusiva. A referência local está em output/20261109T125036Z_b1308a4d; seu snapshot está em data/bronze/20261109T124404Z_377aa3e5. O manifesto conecta as camadas à mesma aquisição.')

    page(doc, '4 Qualidade rastreabilidade e confiabilidade')
    p(doc, 'Tratamos integridade de arquivos, contratos das fontes e completude temporal antes de produzir análises. Ausência explícita de precipitação permanece nula; uma data faltante na sequência esperada causa rejeição da resposta.')
    table(doc, ['Controle','Regra aplicada','Evidência da referência'], [
        ['Integridade','SHA-256 dos JSONs e corpos deve corresponder ao manifesto','Snapshot verificável sem rede'],
        ['Identidade','Código IBGE devolvido deve corresponder ao configurado','Três municípios integrados'],
        ['Calendário','Sequência exata de datas, ordenada e sem duplicações','3.288 chaves diárias únicas'],
        ['Unidade e timezone','Precipitação em mm e America/Sao_Paulo','Contratos verificados'],
        ['Valores','Rejeitar negativos, textos, booleanos, NaN e infinitos','Zero precipitações ausentes'],
        ['Janelas','Exigir todos os dias e valores de cada janela','Seis janelas de três dias nulas no início'],
        ['Meses','Exigir mês civil completo para o ranking de totais','108 meses municipais completos'],
        ['Unicidade SQL','Índices únicos nas chaves diária e mensal','Verificação no SQLite']
    ], [3.3,7.8,5.7])
    h(doc, 'Interpretação de cobertura', 2)
    p(doc, 'A cobertura mensal divide dias válidos por dias esperados no recorte solicitado. O campo full_calendar_month exige também todos os dias do mês civil, evitando incluir meses parciais nas bordas em rankings comparativos. Totais de meses incompletos não devem ser interpretados como precipitação integral do mês.')
    h(doc, 'Testes e reprodução', 2)
    p(doc, 'A suíte local passou em 21 testes, cobrindo integração, valores inválidos, datas, unidades, nulos, janelas, limite entre municípios, gzip, percentil, Wilson, checksums, replay, gravação e comparação de Decimal. Os dados sintéticos existem exclusivamente nos testes; as análises usam a coleta real.')
    p(doc, 'O replay com o mesmo snapshot gerou CSV diário idêntico. No Databricks, a comparação de todas as chaves e colunas Gold resultou em zero diferenças, respeitadas as tolerâncias numéricas descritas na seção 10. Hashes verificam integridade em relação ao manifesto local; não são assinaturas do provedor.')

    page(doc, '5 Feature Engineering e camada analítica')
    p(doc, 'As features representam intensidade e persistência da precipitação. Janelas são calculadas por município e por dias de calendário, sem atravessar séries distintas. O símbolo t representa o dia analisado.')
    table(doc, ['Feature','Construção','Contribuição analítica'], [
        ['rain_3d_mm','Soma dos dias t, t menos 1 e t menos 2','Selecionar acúmulo recente'],
        ['rain_7d_mm','Soma de t até t menos 6','Caracterizar persistência semanal'],
        ['antecedent_7d_mm','Soma de t menos 1 até t menos 7','Descrever chuva anterior sem incluir o dia corrente'],
        ['heavy_day','1 se precipitação diária for pelo menos 50 mm','Contar dias de chuva intensa conforme parâmetro do estudo'],
        ['accumulated_attention','1 se acumulado de três dias for pelo menos 100 mm','Selecionar dias com acúmulo elevado'],
        ['month','Ano e mês da data local','Apoiar agregação e evolução temporal']
    ], [4.5,5.6,6.7])
    h(doc, 'Nulos e limites das features', 2)
    p(doc, 'Janelas incompletas permanecem nulas, inclusive no início do recorte. O acumulado de três dias tem dois valores iniciais nulos por município. Flags também ficam nulas quando sua variável de origem está ausente. Não transformamos falta de medição em ausência de chuva.')
    p(doc, 'Os limiares de 50 e 100 mm são exploratórios e ajustáveis. Não foram calibrados contra ocorrências e não correspondem a critérios oficiais de alerta. Dias consecutivos com acumulado elevado podem pertencer ao mesmo episódio e não devem ser somados como eventos independentes.')
    h(doc, 'Organização da camada analítica', 2)
    p(doc, 'A Gold diária mantém os atributos Silver e acrescenta as features. A Gold mensal reúne cobertura, total observado, máximo diário, frequência de dias intensos, intervalos de Wilson e quantidade de janelas válidas. CSV e SQLite permitem inspeção local; as tabelas Delta servem ao dashboard e às consultas no Databricks.')
    p(doc, 'Acumulados de chuva não medem saturação do solo, vazão ou área inundada. Para relacioná-los a impactos seria necessário integrar uma variável de ocorrência e definir corretamente a unidade espacial e temporal do evento.')

    page(doc, '6 Indicadores para tomada de decisão')
    table(doc, ['Indicador','Obtenção','Interpretação e decisão'], [
        ['Precipitação total mensal','Somar os valores diários válidos do município e mês','Comparar períodos completos e selecionar meses para investigação'],
        ['Máximo diário','Maior valor válido no período','Identificar dias extremos na série de grade'],
        ['Dias de chuva intensa','Contar dias com precipitação de pelo menos 50 mm','Dimensionar recorrência conforme limiar exploratório'],
        ['Frequência de dias intensos','Dividir dias intensos por dias válidos e multiplicar por 100','Comparar frequências com denominadores explícitos'],
        ['Cobertura','Dividir dias válidos por dias esperados e multiplicar por 100','Avaliar a comparabilidade das análises'],
        ['Acumulado máximo','Maior soma em janela completa de três ou sete dias','Selecionar períodos com persistência de chuva'],
        ['P95 dos dias chuvosos','Percentil 95 com interpolação linear sobre dias de pelo menos 1 mm','Descrever a cauda da distribuição da amostra'],
        ['Intervalo de Wilson','Intervalo de 95 por cento para a proporção de dias intensos','Referência descritiva da incerteza da frequência']
    ], [4.2,5.7,6.9])
    h(doc, 'Uso responsável dos denominadores', 2)
    p(doc, 'O percentual de dias intensos considera apenas valores válidos; a interpretação sempre deve acompanhar a cobertura. Para acumulados, o campo valid_3d_windows informa quantas janelas puderam ser calculadas. Meses sem valores válidos têm total e frequência nulos.')
    h(doc, 'Perguntas respondidas', 2)
    p(doc, 'Os indicadores descrevem características do problema meteorológico, diferenças entre os pontos e evolução mensal ou anual. O recorte não permite comparar grupos sociais, estimar exposição ou identificar causalmente fatores de inundação. Essas perguntas exigem bases adicionais e estão explicitadas como continuidade da investigação.')

    page(doc, '7 Resultados da investigação')
    h(doc, 'Síntese por ponto municipal', 2)
    table(doc, ['Município','Total mm','Máximo diário mm','Dias de pelo menos 50 mm','Máximo de 3 dias mm'], [
        [r['name'],number(r['total']),number(r['maximum']),r['heavy'],number(r['max3'])] for r in summary
    ], [5.0,2.9,2.8,3.2,2.9], numeric=(1,2,3,4))
    p(doc, 'Todos os pontos têm 1.096 dias válidos. Santos acumulou 6.131,6 mm e apresentou 15 dias com pelo menos 50 mm; São Paulo teve um dia e São Luiz do Paraitinga nenhum. Os valores selecionam Santos para investigação meteorológica adicional dentro desta amostra, sem demonstrar maior dano, vulnerabilidade ou número de enchentes.')
    h(doc, 'Evolução anual', 2)
    table(doc, ['Município','Ano','Dias válidos','Total mm','Dias intensos'], annual, [6.0,1.7,2.5,3.6,3.0], numeric=(1,2,3,4))
    p(doc, 'A comparação anual descreve a variação dentro dos três anos observados. A série é curta para estimar uma tendência climática, e totais diferentes não demonstram por si só mudanças permanentes. As consultas anuais e mensais estão disponíveis em sql/analises.sql.')

    page(doc, '8 Distribuição mensal e períodos de atenção')
    picture(doc, TMP/'mensal.png', 'Figura 2  Precipitação mensal dos pontos selecionados com a mesma escala vertical', 'Três painéis de precipitação mensal de 2023 a 2025, com a mesma escala. Santos apresenta os maiores picos.', width=16.2)
    table(doc, ['Município','Mês','Total mm','Dias intensos','Dias com acumulado de 3 dias de pelo menos 100 mm'], [
        [r['municipality'],r['month'],number(r['total_mm']),int(r['heavy_days']),int(r['attention_3d_days'])] for r in top
    ], [5.4,2.2,2.7,2.3,4.2], numeric=(1,2,3,4))
    p(doc, 'Santos em fevereiro de 2023 apresentou 577,8 mm, o maior total mensal do recorte, com dois dias de pelo menos 50 mm. Os quatro dias acima do acumulado de três dias não representam quatro enchentes e podem se sobrepor no mesmo episódio.')
    p(doc, 'As séries mostram variação mensal e picos em períodos distintos. É adequado investigar sazonalidade com histórico maior; três anos não estabelecem uma normal climatológica nem justificam atribuição a mudanças climáticas.')

    page(doc, '9 Análises estatísticas e aprofundamento')
    h(doc, 'Distribuição dos dias chuvosos', 2)
    table(doc, ['Município','P95 dos dias com pelo menos 1 mm','Máximo acumulado de 7 dias mm'], [[r['name'],number(r['p95'])+' mm',number(r['max7'])] for r in summary], [6.5,5.5,4.8], numeric=(1,2))
    p(doc, 'O percentil 95 foi calculado por interpolação linear sobre os dias com pelo menos 1 mm em todo o período. Ele descreve a cauda superior da distribuição observada. Foi calculado retrospectivamente e não deve ser usado como limiar preditivo sem separar dados de calibração e avaliação.')
    h(doc, 'Incerteza da frequência de dias intensos', 2)
    feb = next(r for r in monthly if r['municipality_id']=='3548500' and r['month']=='2023-02')
    p(doc, f"Em Santos, fevereiro de 2023 teve {feb['heavy_days']} dias intensos em {feb['valid_days']} dias válidos, uma frequência de {number(feb['heavy_days_pct'],2)} por cento. O intervalo de Wilson de 95 por cento foi de {number(feb['wilson_low_pct'],2)} a {number(feb['wilson_high_pct'],2)} por cento.")
    p(doc, 'A fórmula usa z igual a 1,959963984540054 e o denominador de dias válidos. Sua interpretação binomial pressupõe independência entre ensaios, hipótese limitada pela autocorrelação e persistência das chuvas. Por isso, o intervalo é uma referência descritiva da frequência e não um intervalo para risco de inundação.')
    h(doc, 'Escolha das técnicas e Machine Learning', 2)
    p(doc, 'Optamos por percentis, frequências, acumulados e análise temporal porque eles respondem às perguntas do recorte sem exigir uma variável-alvo inexistente. Não treinamos um modelo de Machine Learning: não há ocorrência de inundação confirmada para definir rótulos e avaliar previsões pertinentes.')
    p(doc, 'Uma próxima etapa pode integrar ocorrências oficiais por município e data, construir relações entre chuva antecedente e eventos e avaliar modelos com separação temporal. As métricas devem acompanhar a finalidade, por exemplo precisão, recall e taxa de falsos alertas; nenhum valor de desempenho é apresentado sem modelo e teste realizados.')
    h(doc, 'Limites da inferência', 2)
    p(doc, 'O cadastro territorial adiciona contexto, não uma variável independente de danos. Não estimamos relações causais entre chuva e enchentes. A grade ERA5 e os pontos aproximados podem omitir extremos de curta duração e diferenças importantes dentro de cada município.')

    page(doc, '10 Experimentação com Databricks e Apache Spark')
    table(doc, ['Item','Resultado'], [
        ['Ambiente','Databricks Free Edition com compute Serverless'],
        ['Versão do Spark',evidence['spark_version']],
        ['Execução',evidence['run_id']],
        ['Tempo da chamada do experimento','11,014 segundos'],
        ['Comparação diária','3.288 linhas e zero diferenças'],
        ['Comparação mensal','108 linhas e zero diferenças']
    ], [5.1,11.7])
    p(doc, 'Executamos o notebook autocontido no workspace e registramos as saídas em docs/evidencias/databricks_execucao.json. A validação de paridade cobre todas as colunas e chaves Gold. A tolerância absoluta é 0,001 mm nos campos terminados em _mm e 1e-6 nos demais números; nulos são verificados explicitamente.')
    h(doc, 'Operações exploradas', 2)
    p(doc, 'O experimento lê JSON com schema explícito, expande vetores diários, une DataFrames por código municipal, aplica janelas por calendário, executa agregações e consultas Spark SQL, grava e reabre Parquet. A publicação posterior cria três tabelas Delta para consumo analítico no catálogo workspace e schema citizentech.')
    for layer in ('silver_daily','gold_daily','gold_monthly'):
        code(doc, f'{layer}_20261109t131706z_f0529b79')
    h(doc, 'Experiência e ajustes técnicos', 2)
    p(doc, 'O Serverless rejeitou o modo errorifexists na gravação. Ajustamos o experimento para reservar exclusivamente uma pasta nova e gravar apenas seus filhos com overwrite; tabelas usam CREATE TABLE AS SELECT. Também corrigimos a validação para tratar Decimal como número, aplicando a tolerância em vez de comparar representações textuais.')
    h(doc, 'Possibilidades e limitações do ambiente', 2)
    p(doc, 'Spark oferece operações distribuíveis e armazenamento colunar, mas a amostra pequena não comprova ganho de desempenho. O tempo observado inclui a chamada do experimento e não todo o notebook. Não realizamos benchmark controlado nem inferimos o número de executores ou métricas de shuffle. Validação e comparação no driver precisam ser redesenhadas para grande volume. A Free Edition possui cotas de uso.')

    page(doc, '11 Dashboard e visualização dos resultados')
    linkline(doc, 'Abrir dashboard publicado no Databricks', DASHBOARD)
    p(doc, 'O dashboard foi montado no Databricks e revisado visualmente com os resultados da execução validada. Apresenta precipitação mensal em três séries, barras de dias intensos, tabela municipal e um bloco explicativo sobre as fontes e limitações.')
    picture(doc, TMP/'dias_intensos.png', 'Figura 3  Reconstituição do indicador de dias intensos usando a Gold validada', 'Gráfico de barras com 15 dias em Santos, um em São Paulo e zero em São Luiz do Paraitinga.', width=16.1)
    h(doc, 'Leitura dos componentes', 2)
    p(doc, 'O gráfico mensal compara a evolução dos pontos com datas e precipitação em mm. As barras contam dias com pelo menos 50 mm no período integral. A tabela apresenta dias válidos, total observado, máximo diário, contagem de dias intensos e maior acumulado de três dias.')
    p(doc, 'O bloco Sobre os dados informa o recorte 2023 a 2025, as fontes IBGE e Open-Meteo com ERA5 e a diferença entre um ponto de grade e a média de toda a área municipal. Também esclarece que os indicadores não representam ocorrências ou probabilidades de enchente.')
    h(doc, 'Acesso e evidência visual', 2)
    p(doc, 'O link corresponde à versão publicada fornecida para a entrega. O compartilhamento do Databricks exige usuários autenticados e autorizados na conta; publicar não torna o dashboard anônimo na internet. Os gráficos deste documento são gerados a partir da referência validada e não são capturas da interface do Databricks.')

    page(doc, '12 Diagnóstico e recomendações executivas')
    h(doc, 'O que os dados revelam', 2)
    p(doc, 'Os três pontos apresentam diferenças relevantes de precipitação no período. Santos concentrou o maior total, o maior máximo diário e 15 dos 16 dias de pelo menos 50 mm da amostra. A cobertura foi completa, o que permite comparar os registros dentro do recorte, respeitadas as limitações espaciais da grade.')
    h(doc, 'Situações que merecem investigação', 2)
    p(doc, 'Recomendamos começar pelo ponto de Santos e pelos meses com maiores totais, especialmente fevereiro de 2023 e dezembro de 2024. Isso define prioridade de investigação meteorológica, sem concluir que esses locais tiveram os maiores danos ou que os demais estão livres de risco. O estudo não identifica grupos sociais mais afetados.')
    h(doc, 'Padrões e evolução observados', 2)
    p(doc, 'Há variação mensal e anual e episódios de acúmulo de chuva em dias consecutivos. Os maiores totais mensais do ranking concentram-se em Santos; São Luiz do Paraitinga também aparece entre os cinco maiores meses, em dezembro de 2024. A série curta não estabelece tendência climática persistente.')
    h(doc, 'Decisões propostas', 2)
    table(doc, ['Decisão recomendada','Fundamento e próximo dado necessário'], [
        ['Investigar os episódios selecionados','Cruzar os maiores diários e acumulados com ocorrências oficiais e níveis de rios.'],
        ['Planejar inspeções de drenagem','Usar a distribuição temporal como ponto de partida e validar com série longa e equipes locais.'],
        ['Aprimorar a observação local','Comparar a grade com pluviômetros, delimitar bacias e ampliar pontos instrumentados.'],
        ['Avaliar intervenções futuras','Acompanhar precipitação junto a ocorrências, exposição e capacidade de resposta.']
    ], [6.0,10.8])
    h(doc, 'Resultados a acompanhar', 2)
    p(doc, 'Acompanhar cobertura, máximos diários, dias intensos e acumulados de três e sete dias. Para avaliar decisões reais, incorporar ocorrências confirmadas, pessoas afetadas e tempo de resposta. Esses últimos indicadores ainda dependem de novas fontes. O pipeline atual apoia preparação e investigação histórica, sem emitir alertas operacionais.')

    page(doc, '13 Reprodução e materiais da entrega')
    h(doc, 'Código e dados no GitHub', 2)
    linkline(doc, REPO, REPO)
    p(doc, 'O repositório reúne código do pipeline, configuração, snapshot bruto, saídas de referência, testes, consultas, documentação e notebooks importáveis. O pipeline principal exige Python 3.11 ou superior e usa somente biblioteca padrão. Os scripts de geração deste Word têm dependências separadas de documentação.')
    code(doc, 'git clone https://github.com/Kaue-code30/gs-database.git\ncd gs-database\npython -m unittest discover -s tests -v\npython pipeline.py')
    p(doc, 'Para reprocessar a aquisição preservada sem consultar as APIs, executar o comando abaixo. O manifesto do snapshot determina fontes e parâmetros. Os arquivos brutos são versionados sem conversão de fim de linha para preservar os hashes.')
    code(doc, 'python pipeline.py --bronze data/bronze/20261109T124404Z_377aa3e5')
    h(doc, 'Experimento em nuvem', 2)
    p(doc, 'Importar output/databricks/CitizenTech_Databricks_Serverless.ipynb no Workspace do Databricks e executar as células em ordem. O notebook incorpora código, dados Bronze e referência Gold, cria pasta exclusiva em volume e compara os resultados antes de publicar tabelas Delta.')
    h(doc, 'Artefatos principais', 2)
    table(doc, ['Material','Localização no repositório'], [
        ['Pipeline e configuração','pipeline.py e config.json'],
        ['Snapshot de aquisição','data/bronze/20261109T124404Z_377aa3e5'],
        ['Referência e relatório local','output/20261109T125036Z_b1308a4d'],
        ['Experimento e notebook','spark/experiment.py e output/databricks'],
        ['Consultas analíticas e dashboard','sql/analises.sql e sql/dashboard'],
        ['Registro da execução em nuvem','docs/evidencias/databricks_execucao.json'],
        ['Relatório Word','output/docs/Relatorio_CitizenTech_GS.docx']
    ], [5.8,11.0])
    p(doc, 'O notebook com saídas e o dashboard no workspace complementam os artefatos locais. A referência em CSV e SQLite permanece disponível para quem não possuir acesso à conta Databricks.')

    page(doc, '14 Correspondência com o enunciado e referências')
    table(doc, ['Entregável do enunciado','Atendimento neste relatório e no projeto'], [
        ['Investigação do problema','Seção 1 com contexto, público, recorte e decisões'],
        ['Catálogo de dados','Seção 2 e docs/catalogo_dados.md'],
        ['Arquitetura da solução','Seção 3 e Figura 1 com fluxo Medallion'],
        ['Pipeline implementado','Seções 3 e 4, pipeline.py e testes'],
        ['Feature Engineering','Seção 5 com construção e justificativas'],
        ['Camada analítica','Seções 5 e 6, Gold em CSV, SQLite e Delta'],
        ['Análises','Seções 7, 8 e 9 com tabelas, gráficos e limitações'],
        ['Dashboard','Seção 11 e link da versão publicada'],
        ['Experimentação Spark','Seção 10, notebook e registro da paridade'],
        ['Relatório executivo','Síntese inicial e seção 12 com diagnóstico e recomendações']
    ], [5.2,11.6])
    h(doc, 'Referências e links de consulta', 2)
    p(doc, 'Enunciado da atividade CitizenTech de Big Data e Analytics da Global Solution 2026.2, disponibilizado no arquivo GS - Cloud Database (1).pdf. A seção 10 desse enunciado define os dez entregáveis relacionados acima.')
    for label, url in [
        ('IBGE API de localidades', 'https://servicodados.ibge.gov.br/api/docs/localidades'),
        ('Open-Meteo Historical Weather API', 'https://open-meteo.com/en/docs/historical-weather-api'),
        ('Open-Meteo Termos e atribuição', 'https://open-meteo.com/en/terms'),
        ('Apache Spark Janelas por intervalo', 'https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.Window.rangeBetween.html'),
        ('Databricks Free Edition', 'https://docs.databricks.com/aws/en/getting-started/free-edition'),
        ('Databricks Compartilhamento de dashboards', 'https://docs.databricks.com/aws/en/dashboards/share/share'),
        ('Código dados e documentação da equipe', REPO),
        ('Dashboard publicado da equipe', DASHBOARD)
    ]:
        linkline(doc, label, url)
    p(doc, 'Dados meteorológicos disponibilizados pelo Open-Meteo com reanálise ERA5 do ECMWF e Copernicus; cadastro territorial do IBGE. As análises, limiares e recomendações são de responsabilidade da equipe, sem endosso dos provedores.')
    DEST.parent.mkdir(parents=True, exist_ok=True)
    doc.save(DEST)
    audit = {'destination':str(DEST), 'paragraphs':len(doc.paragraphs), 'tables':len(doc.tables),
        'figures':len(doc.inline_shapes), 'sections':14, 'daily_rows':len(daily), 'monthly_rows':len(monthly),
        'source_manifest':manifest['created_at_utc'], 'links':[REPO,DASHBOARD]}
    (TMP/'content_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node-bin', type=Path, required=True)
    parser.add_argument('--node-modules', type=Path, required=True)
    args = parser.parse_args()
    main(args.node_bin, args.node_modules)
