#!/usr/bin/env python3
"""
gerar_painel.py — Gera o index.html do Painel Operacional Portoex.

Lê /tmp/dados_s1.json e /tmp/dados_s2.json (extraídos do Brudam 147),
aplica todas as regras de negócio e injeta o DATA no template HTML,
gerando o arquivo index.html pronto para upload no GitHub Pages.

Uso:
    python3 gerar_painel.py \
        --dados     /tmp/dados_s1.json \
        --dados2    /tmp/dados_s2.json \
        --sistema1  "PORTOEX" \
        --sistema2  "PEX LOGÍSTICA" \
        --periodo   "1ª Quinzena Jul/2026" \
        --data_ini  "01/07/2026" \
        --data_fin  "15/07/2026" \
        --template  <skill_dir>/assets/painel_template.html \
        --output    /sessions/friendly-fervent-cannon/mnt/Downloads/index.html
"""

import argparse, json, re, os
from collections import defaultdict

# ─── Parser de número brasileiro ─────────────────────────────────────────────
def parse_br(v):
    if not v or str(v).strip() in ('N/D', 'INDEFINIDO', '', '-', '0,00', '0'):
        return 0.0
    v = str(v).replace('%', '').strip().replace('.', '').replace(',', '.')
    try:
        return float(v)
    except Exception:
        return 0.0

def get_uf(destino):
    """Extrai UF de strings como 'SAO PAULO - SP'"""
    if destino and ' - ' in destino:
        return destino.split(' - ')[-1].strip()[:2]
    return ''

# ─── Normalização de serviços ────────────────────────────────────────────────
def normalize_servico(s):
    """Unifica variações de nome de serviço do Brudam em categorias padrão."""
    if not s:
        return s
    u = s.upper()
    if 'PERSONALIZADO_L' in u:
        return 'PERSONALIZADO_L'
    if 'PERSONALIZADO' in u or '_PER' in u:
        return 'PERSONALIZADO'
    if 'LOGIST' in u:
        return 'SERVIÇO LOGÍSTICO'
    if 'REPASSE' in u:
        return 'REPASSE'
    if 'ECO' in u:
        return 'ECONOMICO'
    if 'EXP' in u:
        return 'EXPRESSO'
    return s

# ─── Serviços excluídos das análises (TOP20, Por Serviço, Por UF, Clientes) ─
EXCLUIDOS = {'REPASSE', 'SERVIÇO LOGÍSTICO', 'CORTESIA'}

def is_excluido(servico):
    s = (servico or '').upper().strip()
    return any(ex.upper() in s for ex in EXCLUIDOS)

# ─── Normalização de clientes ─────────────────────────────────────────────────
def normalizar_cliente(nome):
    n = (nome or '').strip()
    if 'HERCULES' in n.upper():
        return 'ANSELL BRAZIL L'
    if n.upper().startswith('MAC FER'):
        return 'MAC FER'
    return n

# ─── Carregar e processar registros de um sistema ────────────────────────────
def carregar_dados(path_json, sistema):
    with open(path_json, encoding='utf-8') as f:
        raw = json.load(f)

    # Detecção dinâmica de índices de colunas
    hdrs = raw.get('headers', [])
    def idx(nome, fallback=-1):
        try: return hdrs.index(nome)
        except ValueError: return fallback

    I_BASE          = idx('BASE', 1)
    I_DATA          = idx('DATA', 3)
    I_CLIENTE       = idx('CLIENTE TOMADOR', idx('CLIENTE', 6))
    I_SERVICO       = idx('SERVICO', 9)
    I_TIPO_CTE      = idx('TIPO CTE', 10)
    I_DESTINO       = idx('DESTINO', 11)
    I_FRETE         = idx('FRETE', 12)
    I_RESP_COLETA   = idx('RESP. COLETA', 15)
    I_CUSTO_COLETA  = idx('CUSTO COLETA', 16)
    I_RESP_ENTREGA  = idx('RESP. ENTREGA', 17)
    I_CUSTO_ENTREGA = idx('CUSTO ENTREGA', 18)
    I_RESP_TRANSF   = idx('RESP. TRANSF', 19)
    I_CUSTO_TRANSF  = idx('CUSTO TRANSF', 20)
    I_CTOTAL        = idx('C.TOTAL', 26)
    I_IMPOSTO       = idx('IMPOSTO', 28)
    I_RESULTADO     = idx('RESULTADO', 29)
    I_COMIS         = idx('COMIS', 30)
    I_LUCRO         = idx('LUCRO LIQ', 31)
    I_MEMO          = idx('ULTIMO MEMO', 33)

    registros = []
    for row in raw['rows']:
        if len(row) < 12:
            continue

        minuta      = row[0].strip()

        # ── Override de serviço: minutas emitidas errado pelo comercial (24/09/2026)
        # AC Comercial (Tiago Santana): emitidas como PERSONALIZADO mas são PERSONALIZADO_L
        MINUTAS_PERSONALIZADO_L_OVERRIDE = {
            "3147","3148","3149","3150","3151","3152","3153",
        }

        servico_raw = (row[I_SERVICO].strip() if I_SERVICO >= 0 and len(row) > I_SERVICO else '').upper().strip()
        if minuta in MINUTAS_PERSONALIZADO_L_OVERRIDE:
            servico_raw = 'PERSONALIZADO_L'
        servico     = normalize_servico(servico_raw)
        tipo_cte = (row[I_TIPO_CTE].strip() if I_TIPO_CTE >= 0 and len(row) > I_TIPO_CTE else '').upper()
        destino  = row[I_DESTINO].strip() if I_DESTINO >= 0 and len(row) > I_DESTINO else ''
        cliente  = normalizar_cliente(row[I_CLIENTE].strip() if I_CLIENTE >= 0 and len(row) > I_CLIENTE else '')
        data     = row[I_DATA].strip() if I_DATA >= 0 and len(row) > I_DATA else ''

        # Excluir globalmente minutas cujo tomador/cliente é PORTOEX (cruzamento interno)
        if 'PORTOEX' in cliente.upper() or 'PORTOEXPRESS' in cliente.upper():
            continue

        frete     = parse_br(row[I_FRETE]    if I_FRETE >= 0   and len(row) > I_FRETE    else 0)
        custo     = parse_br(row[I_CTOTAL]   if I_CTOTAL >= 0  and len(row) > I_CTOTAL   else 0)
        imposto   = parse_br(row[I_IMPOSTO]  if I_IMPOSTO >= 0 and len(row) > I_IMPOSTO  else 0)
        resultado = parse_br(row[I_RESULTADO] if I_RESULTADO >= 0 and len(row) > I_RESULTADO else 0)
        comis     = parse_br(row[I_COMIS]    if I_COMIS >= 0   and len(row) > I_COMIS    else 0)
        lucro     = parse_br(row[I_LUCRO]    if I_LUCRO >= 0   and len(row) > I_LUCRO    else 0)
        margem    = (lucro / frete * 100) if frete else 0.0

        # Regras de imposto (alterado em 24/09/2026 — autorização Chico):
        # PERSONALIZADO_L (inicia com PERSONALIZADO_L) → 11% sobre frete
        # Demais serviços → 26% sobre frete (fixo, substitui valor Brudam)
        if frete > 0:
            if servico_raw.startswith('PERSONALIZADO_L'):
                imposto = round(frete * 0.11, 2)
            else:
                imposto = round(frete * 0.26, 2)
            resultado = frete - custo - imposto
            lucro     = resultado - comis
            margem    = (lucro / frete * 100) if frete else 0.0

        uf = get_uf(destino)

        memo          = (row[I_MEMO].strip() if I_MEMO >= 0 and len(row) > I_MEMO else '').upper()
        cliente_raw   = (row[I_CLIENTE].strip() if I_CLIENTE >= 0 and len(row) > I_CLIENTE else '').upper()
        resp_coleta   = row[I_RESP_COLETA].strip()   if I_RESP_COLETA >= 0   and len(row) > I_RESP_COLETA   else ''
        custo_coleta  = parse_br(row[I_CUSTO_COLETA]  if I_CUSTO_COLETA >= 0  and len(row) > I_CUSTO_COLETA  else 0)
        resp_entrega  = row[I_RESP_ENTREGA].strip()  if I_RESP_ENTREGA >= 0  and len(row) > I_RESP_ENTREGA  else ''
        custo_entrega = parse_br(row[I_CUSTO_ENTREGA] if I_CUSTO_ENTREGA >= 0 and len(row) > I_CUSTO_ENTREGA else 0)
        resp_transf   = row[I_RESP_TRANSF].strip()   if I_RESP_TRANSF >= 0   and len(row) > I_RESP_TRANSF   else ''
        custo_transf  = parse_br(row[I_CUSTO_TRANSF]  if I_CUSTO_TRANSF >= 0  and len(row) > I_CUSTO_TRANSF  else 0)

        base_val = (row[I_BASE].strip() if I_BASE >= 0 and len(row) > I_BASE else '').upper()
        # Normaliza: MATRIZ → 'MATRIZ', FILIAL SP / FILIAL* → 'FILIAL'
        base_norm = 'FILIAL' if base_val.startswith('FILIAL') else ('MATRIZ' if base_val == 'MATRIZ' else base_val)

        registros.append({
            'minuta':       minuta,
            'sistema':      sistema,
            'base':         base_norm,
            'data':         data,
            'cliente':      cliente,
            'cliente_raw':  cliente_raw,
            'servico':      servico,
            'tipoCte':      tipo_cte,
            'destino':      destino,
            'uf':           uf,
            'frete':        frete,
            'custo':        custo,
            'imposto':      imposto,
            'resultado':    resultado,
            'comis':        comis,
            'lucro':        lucro,
            'margem':       margem,
            'memo':         memo,
            'resp_coleta':  resp_coleta,
            'custo_coleta': custo_coleta,
            'resp_entrega': resp_entrega,
            'custo_entrega':custo_entrega,
            'resp_transf':  resp_transf,
            'custo_transf': custo_transf,
        })

    return registros

# ─── Construir DATA para o painel ────────────────────────────────────────────
def construir_data(registros_todos, periodo, data_ini, data_fin):
    # Excluir CT-e Complemento e Substituto das análises
    def is_complemento(r):
        t = r['tipoCte'].upper()
        return 'COMPLEMENT' in t or 'SUBSTITUT' in t

    # Registros "principais" = não excluídos + não complementos
    principais = [r for r in registros_todos if not is_excluido(r['servico']) and not is_complemento(r)]

    # ── KPIs ─────────────────────────────────────────────────────────────────
    total_minutas = len(principais)
    total_frete   = sum(r['frete'] for r in principais)
    total_lucro   = sum(r['lucro'] for r in principais)
    total_custo   = sum(r['custo'] for r in principais)
    com_lucro     = sum(1 for r in principais if r['lucro'] >= 0)
    com_prejuizo  = sum(1 for r in principais if r['lucro'] < 0)
    margem_geral  = (total_lucro / total_frete * 100) if total_frete else 0.0
    pct_luc  = (com_lucro   / total_minutas * 100) if total_minutas else 0.0
    pct_prej = (com_prejuizo / total_minutas * 100) if total_minutas else 0.0

    kpis = {
        'minutas': total_minutas,
        'frete': round(total_frete, 2),
        'custo': round(total_custo, 2),
        'lucro': round(total_lucro, 2),
        'margem': round(margem_geral, 2),
        'pct_lucrativas': round(pct_luc, 2),
        'pct_prejuizo': round(pct_prej, 2),
        'com_lucro': com_lucro,
        'com_prejuizo': com_prejuizo,
        'periodo': periodo,
        'data_inicial': data_ini,
        'data_final': data_fin,
    }

    # ── Por Serviço ──────────────────────────────────────────────────────────
    por_serv = defaultdict(lambda: {'minutas': 0, 'frete': 0.0, 'custo': 0.0, 'lucro': 0.0})
    for r in principais:
        s = r['servico']
        por_serv[s]['minutas'] += 1
        por_serv[s]['frete']   += r['frete']
        por_serv[s]['custo']   += r['custo']
        por_serv[s]['lucro']   += r['lucro']

    por_servico_list = []
    for serv, v in sorted(por_serv.items(), key=lambda x: -x[1]['frete']):
        m = (v['lucro'] / v['frete'] * 100) if v['frete'] else 0.0
        pct = (v['frete'] / total_frete * 100) if total_frete else 0.0
        por_servico_list.append({
            'servico': serv,
            'minutas': v['minutas'],
            'frete': round(v['frete'], 2),
            'custo': round(v['custo'], 2),
            'resultado': round(v['lucro'], 2),
            'margem': round(m, 2),
            'pct_total': round(pct, 2),
        })

    # ── Por UF ───────────────────────────────────────────────────────────────
    por_uf_dict = defaultdict(lambda: {'minutas': 0, 'frete': 0.0, 'custo': 0.0, 'lucro': 0.0})
    for r in principais:
        uf = r['uf'] or 'N/D'
        por_uf_dict[uf]['minutas'] += 1
        por_uf_dict[uf]['frete']   += r['frete']
        por_uf_dict[uf]['custo']   += r['custo']
        por_uf_dict[uf]['lucro']   += r['lucro']

    por_uf_list = []
    for uf, v in sorted(por_uf_dict.items(), key=lambda x: -x[1]['frete']):
        m   = (v['lucro'] / v['frete'] * 100) if v['frete'] else 0.0
        pct = (v['frete'] / total_frete * 100) if total_frete else 0.0
        por_uf_list.append({
            'uf': uf,
            'minutas': v['minutas'],
            'frete': round(v['frete'], 2),
            'custo': round(v['custo'], 2),
            'resultado': round(v['lucro'], 2),
            'margem': round(m, 2),
            'pct_total': round(pct, 2),
        })

    # ── TOP 20 Melhores / Piores ─────────────────────────────────────────────
    por_cli = defaultdict(lambda: {'minutas': 0, 'frete': 0.0, 'lucro': 0.0,
                                    'ufs': set(), 'servicos': set()})
    for r in principais:
        c = r['cliente']
        por_cli[c]['minutas']  += 1
        por_cli[c]['frete']    += r['frete']
        por_cli[c]['lucro']    += r['lucro']
        por_cli[c]['ufs'].add(r['uf'])
        por_cli[c]['servicos'].add(r['servico'])

    cli_list = []
    for cli, v in por_cli.items():
        m = (v['lucro'] / v['frete'] * 100) if v['frete'] else 0.0
        cli_list.append({
            'cliente': cli,
            'minutas': v['minutas'],
            'frete': round(v['frete'], 2),
            'resultado': round(v['lucro'], 2),
            'margem': round(m, 2),
            'ufs': sorted(v['ufs'] - {''}),
            'servicos': sorted(v['servicos'] - {''}),
        })

    top20   = sorted(cli_list, key=lambda x: -x['resultado'])[:20]
    piores  = sorted([c for c in cli_list if c['resultado'] < 0], key=lambda x: x['resultado'])

    # ── Clientes (tabela completa) ────────────────────────────────────────────
    clientes_list = sorted(cli_list, key=lambda x: x['resultado'], reverse=True)

    # ── Minutas Negativas ─────────────────────────────────────────────────────
    minutas_neg = [
        {
            'minuta':       r['minuta'],
            'sistema':      r['sistema'],
            'tipoCte':      r.get('tipoCte', ''),
            'data':         r['data'],
            'cliente':      r['cliente'],
            'servico':      r['servico'],
            'destino':      r['destino'],
            'uf':           r['uf'],
            'frete':        round(r['frete'], 2),
            'custo':        round(r['custo'], 2),
            'resultado':    round(r.get('resultado', 0), 2),
            'comis':        round(r.get('comis', 0), 2),
            'lucro':        round(r['lucro'], 2),
            'margem':       round(r['margem'], 2),
            'respColeta':   str(r.get('resp_coleta', '') or ''),
            'custoColeta':  round(r.get('custo_coleta', 0), 2),
            'respEntrega':  str(r.get('resp_entrega', '') or ''),
            'custoEntrega': round(r.get('custo_entrega', 0), 2),
            'respTransf':   str(r.get('resp_transf', '') or ''),
            'custoTransf':  round(r.get('custo_transf', 0), 2),
        }
        for r in registros_todos   # todas as minutas (inclui excluídos também para análise de prejuízo)
        if r['lucro'] < 0
    ]
    minutas_neg.sort(key=lambda x: x['lucro'])

    # ── Minutas excluídas da aba Negativos (justificativa operacional) ────────
    MINUTAS_EXCLUIR_NEG = {
        # frete mínimo
        "299796","299956","299385","2968","2867","299799","299526","2993",
        # aprovado dedicado (Julia)
        "2985",
        # composição de carga
        "299475","299649","2997","299864",
        # rateio incorreto
        "299397","299396","2962","300013","300015","299377",
        # emissão triangulação / manifestado incorretamente
        "299530",
        # venda baixa
        "299761","299379","299892","2946","299725","299826","299978",
        "299459","299644","299972","299545","299509","2959","2949",
        "299684","299813","2972","2964","299461","2952",
        # triangulação
        "299994",
    }
    antes = len(minutas_neg)
    minutas_neg = [m for m in minutas_neg if m['minuta'] not in MINUTAS_EXCLUIR_NEG]
    print(f'  Neg excluídas (justificadas): {antes - len(minutas_neg)} | Restantes: {len(minutas_neg)}')

    # ── Minutas completas (para aba "todas" e "sem custo") ───────────────────
    minutas_all = [
        {
            'minuta':   r['minuta'],
            'sistema':  r['sistema'],
            'data':     r['data'],
            'cliente':  r['cliente'],
            'servico':  r['servico'],
            'tipoCte':  r['tipoCte'],
            'destino':  r['destino'],
            'uf':       r['uf'],
            'frete':    round(r['frete'], 2),
            'custo':    round(r['custo'], 2),
            'resultado': round(r['resultado'], 2),
            'lucro':    round(r['lucro'], 2),
            'margem':   round(r['margem'], 2),
        }
        for r in registros_todos
    ]

    # ── Sem Custo de Transporte ───────────────────────────────────────────────
    EXCLUIR_SC = {'SERVIÇO LOGÍSTICO', 'REPASSE', 'CORTESIA'}
    CRUZAMENTO = {'MATRIZ', 'PORTOEX', 'PORTOEXPRESS'}

    def eh_cruzamento(r):
        # Para PEX: exclui se coleta/entrega/transf for feita pela PORTOEX/MATRIZ/PORTOEXPRESS
        # Para qualquer sistema: exclui se PORTOEXPRESS for responsável pelo transporte
        for campo in ('resp_coleta', 'resp_entrega', 'resp_transf'):
            v = str(r.get(campo, '') or '').upper()
            if 'PORTOEXPRESS' in v:
                return True
            if 'PEX' in r['sistema'].upper() and any(p in v for p in CRUZAMENTO):
                return True
        return False

    # Minutas a excluir permanentemente da aba Sem Custo (lista fixa)
    MINUTAS_EXCLUIR_SC = {
        "292132","291486","291487","293305","290738","290965","293316","293482",
        "291055","292148","294140","294141","293116","290290","294867","290423",
        "292799","291695","291158","292791","292790","292520","292914",
        # adicionadas em 10/08/2026
        "290906","293980","293985","291163","295519","295551",
        "294787","294788","294789","294790","294191","294793",
        "2147","2184","2185",
        # adicionadas em 13/08/2026
        "294846","294848","296221","295437","295123","295126","295128",
        "295662","295607","295174","295175","295380","295381","295390",
        "295755","295756","295773",
        # adicionadas em 14/08/2026
        "2397","296229","296266","296242","295434","295435","296225",
        "295722","296159","296081","296256","296023","295217","295185",
        # adicionadas em 21/08/2026
        "296831","296865","296891","296905","296906","296920","297007","297020",
        "296737","296781","296782","296783","296784","296785","296786","296814",
        "297019","296496","296509","296521","296729","296731","296732","296741",
        "296747","296763","296791","296792","296793","296794","297168","297176",
        "296838","297186",
        # adicionadas em 03/09/2026
        "297953","296867","297285","297302","296651",
        "264061","264079","264097",
        # adicionadas em 03/09/2026 (2º lote)
        "299122","299124","299125","296612",
        "298753","298754","298755","298756",
        "298773","298774","299034",
        # adicionadas em 04/09/2026
        "298987","299418","296533",
        # adicionadas em 09/09/2026
        "299728","2978","2979","2980","2982",
        # adicionadas em 22/09/2026
        "301492","299948","300233","301493","301541","300576","301491","300573",
        "300581","301494","300572","300569","301518","300570","301595","301495",
        "300574","300559","300560","300580","300584","300571","300575","301546",
        "300583","301263","300578","301340","300567","301516","301053","300588",
        "300577","300591","300589","301510","301490","300568","300587","300590",
        "300582","300561","301511","301509","300566","301172","300586","300564",
        "301499","301387","300579","300562","300593","300563","301312","300585",
        "300510","2904","300565","301488","301477","301517","301655","300592",
        "301176","301324","301502","301202","301503","301123","301489","301656",
        "301200","301508","301660","300932","301426","300933","301661","301659",
        "301658","301507","301657","301501","301345","301653","301054","301540",
        "300479","300482","301475","301486","301654","301337","301498","301357",
        "301504","301146","301550","301506","301323","301515","301500","301547",
        "301339","3206","301514","301478","301178","301145","301544","301513",
        "301542","301556","300377","301338","301512","301292","301330","3205",
        "301299","301487","300633","301505","301535","301543","301355","301496",
        "301300","301484","301333"
    }

    minutas_sem_custo = []
    for r in registros_todos:
        if r['minuta'] in MINUTAS_EXCLUIR_SC:
            continue
        if any(ex in r['servico'] for ex in EXCLUIR_SC):
            continue
        tc = r['tipoCte'].upper()
        if 'COMPLEMENT' in tc or 'SUBSTITUT' in tc:
            continue
        c_col = r.get('custo_coleta', 0)
        c_ent = r.get('custo_entrega', 0)
        c_tra = r.get('custo_transf', 0)
        if not (c_col == 0 and c_ent == 0 and c_tra == 0):
            continue
        if eh_cruzamento(r):
            continue
        minutas_sem_custo.append({
            'sistema':      r['sistema'],
            'minuta':       r['minuta'],
            'tipoCte':      r['tipoCte'],
            'data':         r['data'],
            'cliente':      r['cliente'],
            'servico':      r['servico'],
            'destino':      r['destino'],
            'uf':           r['uf'],
            'frete':        round(r['frete'], 2),
            'respColeta':   str(r.get('resp_coleta', '') or ''),
            'custoColeta':  round(c_col, 2),
            'respEntrega':  str(r.get('resp_entrega', '') or ''),
            'custoEntrega': round(c_ent, 2),
            'respTransf':   str(r.get('resp_transf', '') or ''),
            'custoTransf':  round(c_tra, 2),
            'resultado':    round(r['resultado'], 2),
            'comis':        round(r.get('comis', 0), 2),
            'lucro':        round(r['lucro'], 2),
            'margem':       round(r['margem'], 2),
        })

    # ── CORTESIA ─────────────────────────────────────────────────────────────
    cortesia_recs = []
    for r in registros_todos:
        memo       = r.get('memo', '')
        frete      = r['frete']
        cli_raw    = r.get('cliente_raw', '')
        if memo.startswith('CORTESIA'):
            cortesia_recs.append(r)
        elif (frete <= 0.01
              and 'PORTOEXPRESS' in cli_raw
              and ('CORTESIA' in memo or 'AUTORIZADO' in memo)):
            cortesia_recs.append(r)

    cortesia = {
        'minutas':      len(cortesia_recs),
        'frete':        round(sum(r['frete'] for r in cortesia_recs), 2),
        'custo':        round(sum(r['custo'] for r in cortesia_recs), 2),
        'lucro':        round(sum(r['lucro'] for r in cortesia_recs), 2),
        'com_lucro':    sum(1 for r in cortesia_recs if r['lucro'] >= 0),
        'com_prejuizo': sum(1 for r in cortesia_recs if r['lucro'] < 0),
    }

    return {
        'kpis':              kpis,
        'por_servico':       por_servico_list,
        'por_uf':            por_uf_list,
        'top20':             top20,
        'piores':            piores,
        'clientes':          clientes_list,
        'minutas_neg':       minutas_neg,
        'minutas':           minutas_all,
        'minutas_sem_custo': minutas_sem_custo,
        'cortesia':          cortesia,
    }

# ─── Detectar UFs e Serviços presentes (para atualizar os selects do HTML) ───
def atualizar_selects(html, registros_todos):
    """Substitui as opções dos selects de filtro com base nos dados reais do período."""

    ufs_cli  = sorted(set(r['uf'] for r in registros_todos if r['uf']))
    srvs_cli = sorted(set(r['servico'] for r in registros_todos if r['servico']))
    ufs_neg  = sorted(set(r['uf'] for r in registros_todos if r['uf'] and r['lucro'] < 0))
    srvs_neg = sorted(set(r['servico'] for r in registros_todos if r['servico'] and r['lucro'] < 0))

    def build_opts(vals):
        return '\n'.join(f'<option value="{v}">{v}</option>' for v in vals)

    # cli-uf
    html = re.sub(
        r'(<select id="cli-uf"[^>]*>.*?<option value="">Todas</option>)(.*?)(</select>)',
        lambda m: m.group(1) + '\n' + build_opts(ufs_cli) + '\n' + m.group(3),
        html, flags=re.DOTALL
    )
    # cli-servico
    html = re.sub(
        r'(<select id="cli-servico"[^>]*>.*?<option value="">Todos</option>)(.*?)(</select>)',
        lambda m: m.group(1) + '\n' + build_opts(srvs_cli) + '\n' + m.group(3),
        html, flags=re.DOTALL
    )
    # neg-uf
    html = re.sub(
        r'(<select id="neg-uf"[^>]*>.*?<option value="">Todas</option>)(.*?)(</select>)',
        lambda m: m.group(1) + '\n' + build_opts(ufs_neg) + '\n' + m.group(3),
        html, flags=re.DOTALL
    )
    # neg-servico
    html = re.sub(
        r'(<select id="neg-servico"[^>]*>.*?<option value="">Todos</option>)(.*?)(</select>)',
        lambda m: m.group(1) + '\n' + build_opts(srvs_neg) + '\n' + m.group(3),
        html, flags=re.DOTALL
    )
    return html

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dados',    required=True, help='JSON sistema 1')
    ap.add_argument('--dados2',   required=True, help='JSON sistema 2')
    ap.add_argument('--sistema1', default='PORTOEX')
    ap.add_argument('--sistema2', default='PEX LOGÍSTICA')
    ap.add_argument('--periodo',  required=True, help='Ex: "Julho 2026"')
    ap.add_argument('--data_ini', required=True, help='DD/MM/AAAA')
    ap.add_argument('--data_fin', required=True, help='DD/MM/AAAA')
    ap.add_argument('--template', default='/sessions/friendly-fervent-cannon/mnt/Downloads/portoex-repo/painel_template.html', help='Caminho do painel_template.html')
    ap.add_argument('--output',   required=True, help='Caminho do index.html gerado')
    ap.add_argument('--base',     default='MATRIZ', choices=['ALL', 'MATRIZ', 'FILIAL'],
                    help='Filtrar por base emissora: MATRIZ (padrão), ALL ou FILIAL')
    args = ap.parse_args()

    print(f'[painel] Carregando {args.sistema1}...')
    r1 = carregar_dados(args.dados, args.sistema1)
    print(f'  {len(r1)} registros')

    print(f'[painel] Carregando {args.sistema2}...')
    r2 = carregar_dados(args.dados2, args.sistema2)
    print(f'  {len(r2)} registros')

    todos = r1 + r2

    # ── Filtrar por base emissora se solicitado ───────────────────────────────
    if args.base != 'ALL':
        todos = [r for r in todos if r.get('base', '').upper() == args.base.upper()]
        print(f'[painel] Filtro base={args.base}: {len(todos)} registros')
    else:
        print(f'[painel] Total: {len(todos)} registros')

    print('[painel] Construindo DATA...')
    data = construir_data(todos, args.periodo, args.data_ini, args.data_fin)

    print(f'  KPIs: {data["kpis"]["minutas"]} minutas | margem {data["kpis"]["margem"]:.1f}%')
    print(f'  Por Serviço: {len(data["por_servico"])} serviços')
    print(f'  Por UF:      {len(data["por_uf"])} UFs')
    print(f'  Clientes:    {len(data["clientes"])} clientes')
    print(f'  Neg:         {len(data["minutas_neg"])} minutas negativas')

    data_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

    print('[painel] Lendo template...')
    with open(args.template, encoding='utf-8') as f:
        html = f.read()

    html = html.replace('__DATA_PORTOEX_PAINEL__', data_json)

    # ── Injetar badge de base emissora no título ──────────────────────────────
    if args.base != 'ALL':
        badge_color = '#1F3864' if args.base == 'MATRIZ' else '#2E75B6'
        badge_label = f'Base Emissora: {args.base}'
        badge_html  = (f' <span style="background:{badge_color};color:#fff;font-size:.7rem;'
                       f'font-weight:700;padding:2px 10px;border-radius:12px;vertical-align:middle;'
                       f'letter-spacing:.5px">{badge_label}</span>')
        # Injetar após a primeira tag <title> no <head>
        html = re.sub(
            r'(<title>)(.*?)(</title>)',
            lambda m: m.group(1) + m.group(2) + f' — {args.base}' + m.group(3),
            html, count=1
        )
        # Injetar badge no header principal (após o h1 com nome da empresa)
        html = re.sub(
            r'(Painel Operacional — Portoex)(</h1>)',
            r'\1' + badge_html + r'\2',
            html, count=1
        )

    # Atualizar selects com os dados reais do período
    html = atualizar_selects(html, todos)

    # ── Injetar filtro de período global ──────────────────────────────────────
    PERIODO_BAR = (
        '<div id="periodo-filter-bar" style="background:var(--surface);border-bottom:1px solid var(--border);'
        'padding:8px 20px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:.82rem;">\n'
        '  <span style="font-weight:600;color:var(--text-muted)">Filtrar Período:</span>\n'
        '  <input type="date" id="date-from" onchange="applyDateFilter()" style="border:1px solid var(--border);'
        'border-radius:6px;padding:4px 8px;background:var(--bg);color:var(--text);font-size:.82rem;">\n'
        '  <span style="color:var(--text-muted)">até</span>\n'
        '  <input type="date" id="date-to" onchange="applyDateFilter()" style="border:1px solid var(--border);'
        'border-radius:6px;padding:4px 8px;background:var(--bg);color:var(--text);font-size:.82rem;">\n'
        '  <span id="date-filter-info" style="color:var(--accent);font-weight:600;"></span>\n'
        '  <button onclick="resetDateFilter()" style="border:1px solid var(--border);border-radius:6px;'
        'padding:4px 12px;background:var(--bg);color:var(--text);cursor:pointer;font-size:.82rem;">Limpar</button>\n'
        '</div>\n'
    )
    if 'id="periodo-filter-bar"' not in html:
        html = html.replace('<main class="main">', PERIODO_BAR + '<main class="main">', 1)

    # ── Injetar botão tab Curva ABC (somente se não existir) ─────────────────
    if "showTab('curva-abc')" not in html:
        ABC_BTN = (
            '  <button class="tab-btn" onclick="showTab(\'curva-abc\')">\n'
            '    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
            '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>'
            '<line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg>\n'
            '    Curva ABC\n'
            '  </button>\n'
            '</nav>'
        )
        html = html.replace('</nav>', ABC_BTN, 1)

    # ── Injetar painel Curva ABC ──────────────────────────────────────────────
    ABC_PANEL = '''
<div id="tab-curva-abc" class="tab-panel">
  <div class="card">
    <div class="c-head">
      <span class="c-tit">Curva ABC — Comparativo de Períodos</span>
      <span class="c-sub">Resultado operacional por cliente (baseado em DATA.minutas)</span>
    </div>
    <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px;">
      <div>
        <div style="font-size:.75rem;font-weight:600;color:var(--text-muted);margin-bottom:4px;">PERÍODO A — REFERÊNCIA</div>
        <div style="display:flex;gap:8px;align-items:center;">
          <input type="date" id="abc-a-from" style="border:1px solid var(--border);border-radius:6px;padding:4px 8px;background:var(--bg);color:var(--text);font-size:.82rem;">
          <span style="color:var(--text-muted)">até</span>
          <input type="date" id="abc-a-to" style="border:1px solid var(--border);border-radius:6px;padding:4px 8px;background:var(--bg);color:var(--text);font-size:.82rem;">
        </div>
      </div>
      <div>
        <div style="font-size:.75rem;font-weight:600;color:var(--text-muted);margin-bottom:4px;">PERÍODO B — ATUAL</div>
        <div style="display:flex;gap:8px;align-items:center;">
          <input type="date" id="abc-b-from" style="border:1px solid var(--border);border-radius:6px;padding:4px 8px;background:var(--bg);color:var(--text);font-size:.82rem;">
          <span style="color:var(--text-muted)">até</span>
          <input type="date" id="abc-b-to" style="border:1px solid var(--border);border-radius:6px;padding:4px 8px;background:var(--bg);color:var(--text);font-size:.82rem;">
        </div>
      </div>
      <button onclick="renderCurvaABC()" style="padding:6px 18px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:600;">Comparar</button>
    </div>
    <div style="display:flex;gap:12px;margin-bottom:12px;font-size:.78rem;flex-wrap:wrap;">
      <span style="background:#27AE60;color:#fff;padding:2px 8px;border-radius:12px;font-weight:700;">A</span><span style="color:var(--text-muted)">Top 60% do faturamento</span>
      <span style="background:#F39C12;color:#fff;padding:2px 8px;border-radius:12px;font-weight:700;">B</span><span style="color:var(--text-muted)">60% – 90%</span>
      <span style="background:#E74C3C;color:#fff;padding:2px 8px;border-radius:12px;font-weight:700;">C</span><span style="color:var(--text-muted)">90% – 100%</span>
      <span style="margin-left:8px;">▲ Melhorou</span><span>▼ Piorou</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Classe</th><th>Cliente</th>
          <th class="text-right">Min. A</th><th class="text-right">Min. B</th>
          <th class="text-right">Lucro A</th><th class="text-right">Lucro B</th>
          <th class="text-right">Δ Variação</th><th>Tendência</th>
        </tr></thead>
        <tbody id="abc-tbody"><tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:24px;">Selecione os períodos e clique em Comparar</td></tr></tbody>
      </table>
    </div>
  </div>
</div>'''
    if 'id="tab-curva-abc"' not in html:
        html = html.replace('</main>', ABC_PANEL + '\n</main>', 1)

    # ── Permitir reassignment das vars de minutas (const → let) ─────────────
    html = html.replace(
        'const minutasNeg = DATA.minutas_neg;',
        'let minutasNeg = DATA.minutas_neg;', 1)
    html = html.replace(
        'const minutasSemCusto = DATA.minutas_sem_custo || [];',
        'let minutasSemCusto = DATA.minutas_sem_custo || [];', 1)

    # ── SheetJS CDN para download Excel ──────────────────────────────────────
    html = html.replace(
        '</head>',
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>\n</head>',
        1)

    # ── Botões de download Excel (Neg e Sem Custo) ───────────────────────────
    DL_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
              '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
              '<polyline points="7 10 12 15 17 10"/>'
              '<line x1="12" y1="15" x2="12" y2="3"/></svg>')
    BTN_STYLE = 'style="background:var(--accent);color:#fff;border-color:var(--accent)"'
    BTN_NEG = (
        f'\n        <button class="btn-reset" onclick="downloadNegExcel()" {BTN_STYLE}>'
        f'{DL_SVG} Minutas Neg.</button>'
    )
    BTN_SC = (
        f'\n        <button class="btn-reset" onclick="downloadSemCustoExcel()" {BTN_STYLE}>'
        f'{DL_SVG} Excel</button>'
    )
    # Injetar dentro do filter-row (antes do </div> que fecha o bloco de filtros)
    html = html.replace(
        '\n      </div>\n      <div class="result-count" id="neg-count">',
        BTN_NEG + '\n      </div>\n      <div class="result-count" id="neg-count">',
        1)
    html = html.replace(
        '\n      </div>\n      <div class="result-count" id="sc-count">',
        BTN_SC + '\n      </div>\n      <div class="result-count" id="sc-count">',
        1)

    # ── Injetar funções JS (filtro + ABC) antes do último </script> ──────────
    ABC_JS = r"""
// ─── FILTRO DE PERÍODO GLOBAL ──────────────────────────────────────────────
let _dateFrom = null, _dateTo = null;
function parseDataBR(s){
  if(!s)return null;
  const parts=s.split('/');
  if(parts.length!==3)return null;
  return new Date(+parts[2],+parts[1]-1,+parts[0]);
}
function _updateKpis(mins){
  const n=mins.length;
  const lucro=mins.reduce((s,m)=>s+(m.lucro||0),0);
  const frete=mins.reduce((s,m)=>s+(m.frete||0),0);
  const margem=frete?lucro/frete*100:0;
  const comLucro=mins.filter(m=>(m.lucro||0)>=0).length;
  const comPrej =mins.filter(m=>(m.lucro||0)<0).length;
  document.getElementById('kpi-minutas').textContent=n.toLocaleString('pt-BR');
  document.getElementById('kpi-margem').textContent=margem.toFixed(1)+'%';
  document.getElementById('kpi-lucrativas').textContent=n?(comLucro/n*100).toFixed(1)+'%':'0.0%';
  document.getElementById('kpi-prejuizo').textContent=n?(comPrej/n*100).toFixed(1)+'%':'0.0%';
  const lcEl=document.getElementById('kpi-lucro-count');
  if(lcEl)lcEl.textContent=comLucro.toLocaleString('pt-BR')+' minutas com lucro';
  const pjEl=document.getElementById('kpi-prej-count');
  if(pjEl)pjEl.textContent=comPrej.toLocaleString('pt-BR')+' minutas negativas';
}
function applyDateFilter(){
  const fv=document.getElementById('date-from').value;
  const tv=document.getElementById('date-to').value;
  _dateFrom=fv?new Date(fv):null;
  _dateTo  =tv?new Date(tv):null;
  const info=document.getElementById('date-filter-info');
  if(_dateFrom||_dateTo){
    const f=fv?new Date(fv).toLocaleDateString('pt-BR'):'—';
    const t=tv?new Date(tv).toLocaleDateString('pt-BR'):'—';
    info.textContent='Filtrando: '+f+' até '+t;
  } else {info.textContent='';}
  if(_dateFrom||_dateTo){
    const ok=m=>{const d=parseDataBR(m.data);return d&&(!_dateFrom||d>=_dateFrom)&&(!_dateTo||d<=_dateTo);};
    minutasNeg        =(DATA.minutas_neg||[]).filter(ok);
    minutasSemCusto   =(DATA.minutas_sem_custo||[]).filter(ok);
    _updateKpis((DATA.minutas||[]).filter(ok));
  } else {
    minutasNeg      =DATA.minutas_neg;
    minutasSemCusto =DATA.minutas_sem_custo||[];
    _updateKpis(DATA.minutas||[]);
  }
  const negBadge=document.getElementById('neg-count-badge');
  if(negBadge)negBadge.textContent=minutasNeg.length;
  const scBadge=document.getElementById('sc-count-badge');
  if(scBadge)scBadge.textContent=minutasSemCusto.length;
  renderNeg(); renderSemCusto();
}
function resetDateFilter(){
  document.getElementById('date-from').value='';
  document.getElementById('date-to').value='';
  _dateFrom=null; _dateTo=null;
  document.getElementById('date-filter-info').textContent='';
  minutasNeg=DATA.minutas_neg;
  minutasSemCusto=DATA.minutas_sem_custo||[];
  _updateKpis(DATA.minutas||[]);
  const negBadge=document.getElementById('neg-count-badge');
  if(negBadge)negBadge.textContent=minutasNeg.length;
  const scBadge=document.getElementById('sc-count-badge');
  if(scBadge)scBadge.textContent=minutasSemCusto.length;
  renderNeg(); renderSemCusto();
}
// ─── CURVA ABC ─────────────────────────────────────────────────────────────
function renderCurvaABC(){
  const aF=document.getElementById('abc-a-from').value;
  const aT=document.getElementById('abc-a-to').value;
  const bF=document.getElementById('abc-b-from').value;
  const bT=document.getElementById('abc-b-to').value;
  if(!aF||!aT||!bF||!bT){alert('Preencha todos os campos de data.');return;}
  const dAF=new Date(aF),dAT=new Date(aT),dBF=new Date(bF),dBT=new Date(bT);
  const filterP=(f,t)=>(DATA.minutas||[]).filter(m=>{const d=parseDataBR(m.data);return d&&d>=f&&d<=t;});
  const group=mins=>{
    const mp={};
    for(const m of mins){
      if(!mp[m.cliente])mp[m.cliente]={minutas:0,frete:0,lucro:0};
      mp[m.cliente].minutas++; mp[m.cliente].frete+=m.frete||0; mp[m.cliente].lucro+=m.lucro||0;
    }
    return Object.entries(mp).map(([k,v])=>({...v,cliente:k})).sort((a,b)=>b.frete-a.frete);
  };
  const classify=list=>{
    const tot=list.reduce((s,c)=>s+c.frete,0); let acc=0;
    return list.map(c=>{acc+=c.frete;const p=tot?acc/tot*100:0;return{...c,classe:p<=60?'A':p<=90?'B':'C'};});
  };
  const pA=classify(group(filterP(dAF,dAT)));
  const pB=classify(group(filterP(dBF,dBT)));
  const mapB=Object.fromEntries(pB.map(c=>[c.cliente,c]));
  const allC=[...new Set([...pA.map(c=>c.cliente),...Object.keys(mapB)])];
  const rows=allC.map(cli=>{
    const a=pA.find(c=>c.cliente===cli)||{frete:0,lucro:0,minutas:0,classe:'—'};
    const b=mapB[cli]||{frete:0,lucro:0,minutas:0,classe:'—'};
    return{cli,a,b,delta:b.lucro-a.lucro};
  }).sort((x,y)=>y.b.frete-x.b.frete);
  const bg={A:'#27AE60',B:'#F39C12',C:'#E74C3C','—':'#999'};
  document.getElementById('abc-tbody').innerHTML=rows.map(r=>`<tr>
    <td><span style="background:${bg[r.b.classe]};color:#fff;padding:2px 8px;border-radius:12px;font-weight:700;">${r.b.classe}</span></td>
    <td>${r.cli}</td>
    <td class="text-right">${r.a.minutas}</td><td class="text-right">${r.b.minutas}</td>
    <td class="text-right">${fmtBRL(r.a.lucro)}</td><td class="text-right">${fmtBRL(r.b.lucro)}</td>
    <td class="text-right" style="color:${r.delta>=0?'#27AE60':'#E74C3C'}">${r.delta>=0?'+':''}${fmtBRL(r.delta)}</td>
    <td style="font-size:1.1rem;color:${r.delta>=0?'#27AE60':'#E74C3C'}">${r.delta>0?'▲':r.delta<0?'▼':'—'}</td>
  </tr>`).join('')||'<tr><td colspan="8" style="text-align:center;padding:24px;color:#999">Sem dados</td></tr>';
}
// ─── DOWNLOAD EXCEL ────────────────────────────────────────────────────────
function downloadNegExcel(){
  if(!window.XLSX){alert('Aguarde o carregamento da biblioteca Excel.');return;}
  const wb=XLSX.utils.book_new();
  const headers=['Minuta','Data','Sistema','Cliente','Serviço','Destino','Frete','Custo','Lucro Líq.','Margem %'];
  const rows=(minutasNeg||[]).map(m=>[m.minuta,m.data,m.sistema,m.cliente,m.servico,m.destino,m.frete||0,m.custo||0,m.lucro||0,m.margem||0]);
  const ws=XLSX.utils.aoa_to_sheet([headers,...rows]);
  ws['!cols']=[{wch:10},{wch:12},{wch:12},{wch:35},{wch:20},{wch:20},{wch:14},{wch:14},{wch:14},{wch:12}];
  XLSX.utils.book_append_sheet(wb,ws,'Minutas Negativas');
  XLSX.writeFile(wb,'MinutasNegativas.xlsx');
}
function downloadSemCustoExcel(){
  if(!window.XLSX){alert('Aguarde o carregamento da biblioteca Excel.');return;}
  const wb=XLSX.utils.book_new();
  const headers=['Minuta','Data','Sistema','Cliente','Serviço','Destino','Frete','Resp. Coleta','Resp. Entrega','Resp. Transf.','Lucro Líq.','Margem %'];
  const rows=(minutasSemCusto||[]).map(m=>[m.minuta,m.data,m.sistema,m.cliente,m.servico,m.destino,m.frete||0,m.respColeta||'',m.respEntrega||'',m.respTransf||'',m.lucro||0,m.margem||0]);
  const ws=XLSX.utils.aoa_to_sheet([headers,...rows]);
  ws['!cols']=[{wch:10},{wch:12},{wch:12},{wch:35},{wch:20},{wch:20},{wch:14},{wch:20},{wch:20},{wch:20},{wch:14},{wch:12}];
  XLSX.utils.book_append_sheet(wb,ws,'Sem Custo Transporte');
  XLSX.writeFile(wb,'SemCustoTransporte.xlsx');
}
"""
    last_close = html.rfind('</script>')
    if 'function applyDateFilter' not in html and 'function renderCurvaABC' not in html:
        # Template não tem nenhuma das funções — injetar tudo
        html = html[:last_close] + ABC_JS + '</script>' + html[last_close+len('</script>'):]
    elif 'function applyDateFilter' not in html:
        # Template tem renderCurvaABC mas não applyDateFilter — injetar só o filtro
        FILTER_JS = ABC_JS[:ABC_JS.find('// ─── CURVA ABC')]
        html = html[:last_close] + FILTER_JS + '</script>' + html[last_close+len('</script>'):]
    # else: template já tem ambas as funções — não injetar nada

    print(f'[painel] Salvando → {args.output}')
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'[painel] ✓ Painel gerado: {len(html):,} chars')

if __name__ == '__main__':
    main()
