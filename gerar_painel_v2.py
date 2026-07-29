#!/usr/bin/env python3
"""
gerar_painel_v2.py — Versão com detecção dinâmica de colunas.

Compatível com o novo formato do export Brudam (inclui CT-E, VENDEDOR, VALOR NF, RECEITA).
Uso idêntico ao gerar_painel.py original.
"""

import argparse, json, re, os
from collections import defaultdict

def parse_br(v):
    if not v or str(v).strip() in ('N/D', 'INDEFINIDO', '', '-', '0,00', '0'):
        return 0.0
    v = str(v).replace('%', '').strip().replace('.', '').replace(',', '.')
    try:
        return float(v)
    except Exception:
        return 0.0

def get_uf(destino):
    if destino and ' - ' in destino:
        return destino.split(' - ')[-1].strip()[:2]
    return ''

def normalize_servico(s):
    if not s:
        return s
    u = s.upper()
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

EXCLUIDOS = {'REPASSE', 'SERVIÇO LOGÍSTICO', 'CORTESIA'}

def is_excluido(servico):
    s = (servico or '').upper().strip()
    return any(ex.upper() in s for ex in EXCLUIDOS)

def normalizar_cliente(nome):
    n = (nome or '').strip()
    if 'HERCULES' in n.upper():
        return 'ANSELL BRAZIL L'
    if n.upper().startswith('MAC FER'):
        return 'MAC FER'
    return n

# ─── Carregar e processar registros de um sistema (ÍNDICES DINÂMICOS) ────────
def carregar_dados(path_json, sistema):
    with open(path_json, encoding='utf-8') as f:
        raw = json.load(f)

    hdrs = raw.get('headers', [])

    def idx(nome, default):
        try:
            return hdrs.index(nome)
        except ValueError:
            return default

    # Detectar índices por nome — fallback para valores antigos
    I_MINUTA        = idx('MINUTA',        0)
    I_DATA          = idx('DATA',          3)
    I_CLIENTE       = idx('CLIENTE TOMADOR', 6)
    I_SERVICO       = idx('SERVICO',       9)
    I_TIPO_CTE      = idx('TIPO CTE',     10)
    I_DESTINO       = idx('DESTINO',      11)
    I_FRETE         = idx('FRETE',        12)
    I_RESP_COLETA   = idx('RESP. COLETA', 15)
    I_CUSTO_COLETA  = idx('CUSTO COLETA', 16)
    I_RESP_ENTREGA  = idx('RESP. ENTREGA',17)
    I_CUSTO_ENTREGA = idx('CUSTO ENTREGA',18)
    I_RESP_TRANSF   = idx('RESP. TRANSF', 19)
    I_CUSTO_TRANSF  = idx('CUSTO TRANSF', 20)
    I_CTOTAL        = idx('C.TOTAL',      26)
    I_IMPOSTO       = idx('IMPOSTO',      28)
    I_RESULTADO     = idx('RESULTADO',    29)
    I_COMIS         = idx('COMIS',        30)
    I_LUCRO         = idx('LUCRO LIQ',   31)
    I_MARGEM        = idx('MARGEM',       32)
    I_MEMO          = idx('ULTIMO MEMO',  33)

    def g(row, i, default=''):
        return row[i] if i >= 0 and len(row) > i else default

    registros = []
    for row in raw['rows']:
        if len(row) < 12:
            continue

        minuta      = g(row, I_MINUTA).strip()
        servico_raw = g(row, I_SERVICO).upper().strip()
        servico     = normalize_servico(servico_raw)
        tipo_cte    = g(row, I_TIPO_CTE).upper()
        destino     = g(row, I_DESTINO).strip()
        cliente     = normalizar_cliente(g(row, I_CLIENTE).strip())
        data        = g(row, I_DATA).strip()

        frete     = parse_br(g(row, I_FRETE,    '0'))
        custo     = parse_br(g(row, I_CTOTAL,   '0'))
        imposto   = parse_br(g(row, I_IMPOSTO,  '0'))
        resultado = parse_br(g(row, I_RESULTADO,'0'))
        comis     = parse_br(g(row, I_COMIS,    '0'))
        lucro     = parse_br(g(row, I_LUCRO,    '0'))
        margem    = parse_br(g(row, I_MARGEM,   '0'))

        # Regra PERSONALIZADO_L → imposto real = 16%
        if servico_raw == 'PERSONALIZADO_L' and frete > 0:
            imposto   = round(frete * 0.16, 2)
            resultado = frete - custo - imposto
            lucro     = resultado - comis
            margem    = (lucro / frete * 100) if frete else 0.0

        # Calcular margem se ausente no export
        if margem == 0.0 and frete != 0:
            margem = (lucro / frete * 100)

        uf            = get_uf(destino)
        memo          = g(row, I_MEMO).upper()
        cliente_raw   = g(row, I_CLIENTE).upper()
        resp_coleta   = g(row, I_RESP_COLETA).strip()
        custo_coleta  = parse_br(g(row, I_CUSTO_COLETA,  '0'))
        resp_entrega  = g(row, I_RESP_ENTREGA).strip()
        custo_entrega = parse_br(g(row, I_CUSTO_ENTREGA, '0'))
        resp_transf   = g(row, I_RESP_TRANSF).strip()
        custo_transf  = parse_br(g(row, I_CUSTO_TRANSF,  '0'))

        registros.append({
            'minuta':       minuta,
            'sistema':      sistema,
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
    def is_complemento(r):
        t = r['tipoCte'].upper()
        return 'COMPLEMENT' in t or 'SUBSTITUT' in t

    principais = [r for r in registros_todos if not is_excluido(r['servico']) and not is_complemento(r)]

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
    clientes_list = sorted(cli_list, key=lambda x: x['resultado'], reverse=True)

    minutas_neg = [
        {
            'minuta':  r['minuta'],
            'sistema': r['sistema'],
            'data':    r['data'],
            'cliente': r['cliente'],
            'servico': r['servico'],
            'destino': r['destino'],
            'uf':      r['uf'],
            'frete':   round(r['frete'], 2),
            'custo':   round(r['custo'], 2),
            'lucro':   round(r['lucro'], 2),
            'margem':  round(r['margem'], 2),
        }
        for r in registros_todos
        if r['lucro'] < 0
    ]
    minutas_neg.sort(key=lambda x: x['lucro'])

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

    EXCLUIR_SC = {'SERVIÇO LOGÍSTICO', 'REPASSE', 'CORTESIA'}
    CRUZAMENTO = {'MATRIZ', 'PORTOEX', 'PORTOEXPRESS'}

    def eh_cruzamento(r):
        if 'PEX' not in r['sistema'].upper():
            return False
        for campo in ('resp_coleta', 'resp_entrega', 'resp_transf'):
            v = str(r.get(campo, '') or '').upper()
            if any(p in v for p in CRUZAMENTO):
                return True
        return False

    minutas_sem_custo = []
    for r in registros_todos:
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

    cortesia_recs = []
    for r in registros_todos:
        memo    = r.get('memo', '')
        frete   = r['frete']
        cli_raw = r.get('cliente_raw', '')
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

def atualizar_selects(html, registros_todos):
    ufs_cli  = sorted(set(r['uf'] for r in registros_todos if r['uf']))
    srvs_cli = sorted(set(r['servico'] for r in registros_todos if r['servico']))
    ufs_neg  = sorted(set(r['uf'] for r in registros_todos if r['uf'] and r['lucro'] < 0))
    srvs_neg = sorted(set(r['servico'] for r in registros_todos if r['servico'] and r['lucro'] < 0))

    def build_opts(vals):
        return '\n'.join(f'<option value="{v}">{v}</option>' for v in vals)

    html = re.sub(
        r'(<select id="cli-uf"[^>]*>.*?<option value="">Todas</option>)(.*?)(</select>)',
        lambda m: m.group(1) + '\n' + build_opts(ufs_cli) + '\n' + m.group(3),
        html, flags=re.DOTALL
    )
    html = re.sub(
        r'(<select id="cli-servico"[^>]*>.*?<option value="">Todos</option>)(.*?)(</select>)',
        lambda m: m.group(1) + '\n' + build_opts(srvs_cli) + '\n' + m.group(3),
        html, flags=re.DOTALL
    )
    html = re.sub(
        r'(<select id="neg-uf"[^>]*>.*?<option value="">Todas</option>)(.*?)(</select>)',
        lambda m: m.group(1) + '\n' + build_opts(ufs_neg) + '\n' + m.group(3),
        html, flags=re.DOTALL
    )
    html = re.sub(
        r'(<select id="neg-servico"[^>]*>.*?<option value="">Todos</option>)(.*?)(</select>)',
        lambda m: m.group(1) + '\n' + build_opts(srvs_neg) + '\n' + m.group(3),
        html, flags=re.DOTALL
    )
    return html

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dados',    required=True)
    ap.add_argument('--dados2',   required=True)
    ap.add_argument('--sistema1', default='PORTOEX')
    ap.add_argument('--sistema2', default='PEX LOGÍSTICA')
    ap.add_argument('--periodo',  required=True)
    ap.add_argument('--data_ini', required=True)
    ap.add_argument('--data_fin', required=True)
    ap.add_argument('--template', required=True)
    ap.add_argument('--output',   required=True)
    args = ap.parse_args()

    print(f'[painel] Carregando {args.sistema1}...')
    r1 = carregar_dados(args.dados, args.sistema1)
    print(f'  {len(r1)} registros')

    print(f'[painel] Carregando {args.sistema2}...')
    r2 = carregar_dados(args.dados2, args.sistema2)
    print(f'  {len(r2)} registros')

    todos = r1 + r2
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
    html = atualizar_selects(html, todos)

    print(f'[painel] Salvando → {args.output}')
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'[painel] ✓ Painel gerado: {len(html):,} chars')

if __name__ == '__main__':
    main()
