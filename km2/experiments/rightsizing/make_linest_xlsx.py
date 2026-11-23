#!/usr/bin/env python3
"""mix-cpu5 の β・ν・c を、mc5raw のデータの上で Excel の式だけで計算するファイルを作る (2026-11-22)。

入力: analysis-rho5-work/mc5raw.csv (CPU は生カウンタの差分で作り直した値。rho_raw_mc4mc5.py の出力)
出力: analysis-rho5-linest.xlsx
  「mc5raw」シート … mc5raw.csv の全行・全列をそのままの並びで写し、右端に 2 列を足す
        使う (1/0)   … 除外の規則を Excel の式で判定 (analyze_rho2.py の load() と同じ規則)
        除外の理由   … 同じ判定を文字で
  「計算」シート   … サービス × 台数ごとに、mc5raw シートから「使う = 1」の行だけを FILTER で取り出して LINEST
                       (Excel 2021 / Microsoft 365 の FILTER が要る)。右に analyze_rho2.py の値を並べて比較
  「説明」シート
除外の規則 (analyze_rho2.py と同じ):
  - summary 未回収 (achieved が空で目標 > 0) → 除外
  - 取りこぼし (窓) が 目標 × 180 秒 の 1% 超 → その点は全サービス除外 (取りこぼしは点ごとに同じ値が全行に入っている)
  - 絞り > 5% → その行だけ除外
  - redis-cart・k6load は対象外
使い方 (rightsizing/ で): python3 make_linest_xlsx.py   (openpyxl が必要)
"""
import csv, io, contextlib, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

SRC = 'analysis-rho5-work/mc5raw.csv'
OUT = 'analysis-rho5-linest.xlsx'

src = open('analyze_rho2.py', encoding='utf-8').read().split('SEED = 20261010')[0]
sys.argv = ['x', SRC, SRC]
with contextlib.redirect_stdout(io.StringIO()):
    exec(src)
with contextlib.redirect_stdout(io.StringIO()):
    ref = load(SRC)

rows = list(csv.DictReader(open(SRC, encoding='utf-8')))
cols = list(rows[0].keys())
L = {c: get_column_letter(i + 1) for i, c in enumerate(cols)}   # 列名 → 列の文字
N = len(rows) + 1                                                # 最終行
USE = get_column_letter(len(cols) + 1); WHY = get_column_letter(len(cols) + 2)
NUMERIC = set(cols) - {'point', 'deploy', 'container'}

HEAD = Font(bold=True, color='FFFFFF'); HFILL = PatternFill('solid', fgColor='1B4F72')
KEYFILL = PatternFill('solid', fgColor='FCE4D6'); ADDFILL = PatternFill('solid', fgColor='E8F0F6')
wb = Workbook()

# ---- 説明 ----
ws = wb.active; ws.title = '説明'
svc_list = ','.join(f'"{s}"' for s in SVCS)
lines = [
    'mix-cpu5 の予測式 CPU = c + β × 購入 + ν × 閲覧 を、mc5raw のデータの上で Excel の LINEST (最小二乗法) で求める',
    '',
    '入力: km2/experiments/rightsizing/analysis-rho5-work/mc5raw.csv (全 2448 行。CPU = usage_mc は生カウンタの差分で作り直した値)',
    '作成: km2/experiments/rightsizing/make_linest_xlsx.py (2026-11-22)',
    '',
    '■ mc5raw シート',
    f'  A〜{L[cols[-1]]} 列 = mc5raw.csv そのまま (行の並びも同じ)。右端の 2 列 (水色) だけ足した:',
    f'  {USE} 列「使う」 … 1 = 当てはめに使う、0 = 除外。式で判定している (行をクリックすると式が見える)',
    f'  {WHY} 列「除外の理由」 … 0 の行の理由',
    '  使う列: 購入 = buy_target (D 列)、閲覧 = view_target (E 列)、CPU = usage_mc (S 列)、サービス = deploy (P 列)、台数 = replicas (C 列)',
    '',
    '■ 除外の規則 (analyze_rho2.py と同じ)',
    '  ・summary 未回収 (buy_achieved / view_achieved が空で目標 > 0)',
    '  ・取りこぼし (buy_dropped_win / view_dropped_win) が 目標 × 180 秒 の 1% を超えた点 → その点の全サービスを除外',
    '  ・CPU の絞り (throttle_pct) が 5% を超えた行 → その行だけ除外',
    '  ・redis-cart と k6load は対象外 (10 サービスだけ)',
    '',
    '■ 計算シート',
    '  FILTER(…) で mc5raw シートから「そのサービス・その台数・使う = 1」の行だけを取り出し、LINEST に渡している',
    '  LINEST の 1 行目は入れた列と逆の順:  [ν (閲覧の係数), β (購入の係数), c (切片)]。3 行目の 1 列目が R²',
    '  オレンジの列が Excel で計算した値。右の灰色の列は analyze_rho2.py (Python) で計算した値で、差がほぼ 0 なら一致',
    '  FILTER は Excel 2021 / Microsoft 365 の関数 (古い Excel では #NAME? になる)',
]
for i, t in enumerate(lines, 1):
    ws.cell(i, 1, t)
ws['A1'].font = Font(bold=True, size=13)
ws.column_dimensions['A'].width = 120

# ---- mc5raw ----
wd = wb.create_sheet('mc5raw')
for j, c in enumerate(cols + ['使う (1/0)', '除外の理由'], 1):
    cell = wd.cell(1, j, c); cell.font = HEAD; cell.fill = HFILL
for i, r in enumerate(rows, 2):
    for j, c in enumerate(cols, 1):
        v = r[c]
        if c in NUMERIC and v != '':
            v = float(v)
            if v.is_integer() and c in ('cycle', 'replicas', 'pods'):
                v = int(v)
        wd.cell(i, j, v)
    D, E, F, G, H, I, P, V = (f'{L[k]}{i}' for k in
        ('buy_target', 'view_target', 'buy_achieved', 'view_achieved', 'buy_dropped_win', 'view_dropped_win', 'deploy', 'throttle_pct'))
    nosvc = f'ISNA(MATCH({P},{{{svc_list}}},0))'
    nosum = f'OR(AND({F}="",{D}>0),AND({G}="",{E}>0))'
    drop = f'OR(N({H})>0.01*{D}*180,N({I})>0.01*{E}*180)'
    thr = f'N({V})>5'
    wd.cell(i, len(cols) + 1, f'=IF(OR({nosvc},{nosum},{drop},{thr}),0,1)').fill = ADDFILL
    wd.cell(i, len(cols) + 2,
            f'=IF({nosvc},"対象外 (サービスでない)",IF({nosum},"summary 未回収",IF({drop},"取りこぼし超過 (点ごと除外)",IF({thr},"絞り > 5%",""))))').fill = ADDFILL
wd.freeze_panes = 'D2'
wd.auto_filter.ref = f'A1:{WHY}{N}'
wd.column_dimensions[L['deploy']].width = 22
wd.column_dimensions[WHY].width = 26

# ---- 計算 ----
wr = wb.create_sheet('計算', 1)
rh = ['サービス (deploy)', '台数 (replicas)', '使った行の数',
      'β (購入 1 周あたり) [m]', 'ν (閲覧 1 周あたり) [m]', 'c (切片) [m]', 'R²', 'ρ = ν ÷ β',
      'Python の β', 'Python の ν', 'Python の c', 'Python の ρ', 'ρ の差 (Excel − Python)']
for j, h in enumerate(rh, 1):
    c = wr.cell(1, j, h); c.font = HEAD; c.fill = HFILL
    c.alignment = Alignment(wrap_text=True, vertical='center')
wr.row_dimensions[1].height = 45
rng = lambda col: f"mc5raw!${L[col]}$2:${L[col]}${N}"
X = f"mc5raw!${L['buy_target']}$2:${L['view_target']}${N}"
U = f"mc5raw!${USE}$2:${USE}${N}"
GREY = PatternFill('solid', fgColor='F2F2F2')
order = [(s, n) for s in SVCS for n in ('1', '2')]
for i, (s, n) in enumerate(order, 2):
    k = f"({rng('deploy')}=$A{i})*({rng('replicas')}=$B{i})*({U}=1)"
    lin = f"LINEST(_xlfn._xlws.FILTER({rng('usage_mc')},{k}),_xlfn._xlws.FILTER({X},{k}),TRUE,TRUE)"
    p = params(ref[(s, n)])
    vals = [s, int(n), f"=SUMPRODUCT({k})",
            f'=INDEX({lin},1,2)', f'=INDEX({lin},1,1)', f'=INDEX({lin},1,3)', f'=INDEX({lin},3,1)', f'=E{i}/D{i}',
            p['beta'], p['nu'], p['c'], p['rho'], f'=H{i}-L{i}']
    for j, v in enumerate(vals, 1):
        c = wr.cell(i, j, v)
        if 4 <= j <= 8: c.fill = KEYFILL
        if 9 <= j <= 12: c.fill = GREY
    for j, fmt in zip(range(4, 14), ['0.00', '0.00', '0.0', '0.0000', '0.0000', '0.00', '0.00', '0.0', '0.0000', '0.0E+00']):
        wr.cell(i, j).number_format = fmt
for j, w in enumerate([24, 9, 9, 13, 13, 11, 9, 11, 11, 11, 11, 11, 14], 1):
    wr.column_dimensions[get_column_letter(j)].width = w
wr.freeze_panes = 'C2'

wb.save(OUT)
print(f'wrote {OUT}: mc5raw {len(rows)} 行 (Python の除外後 {sum(len(v) for v in ref.values())} 行)、組 {len(order)}')
