#!/usr/bin/env python3
"""Painel local de observacao para o projeto Convergencia 3 Pro.

Le arquivos da sessao shadow e consulta somente endpoints publicos da Binance.
Nao conecta a contas, nao aceita chaves de API e nao envia ordens.
Por seguranca, o servidor escuta em 127.0.0.1 por padrao.
"""
from __future__ import annotations

import argparse
import csv
from collections import deque
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import webbrowser

BINANCE_24H = "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT"
CACHE_TTL_SECONDS = 8.0

HTML = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>3 Pro | Convergência</title>
<style>
:root{color-scheme:dark;--bg:#080b12;--panel:#101621;--panel2:#131c29;--line:#202b3a;--text:#eef3fa;--muted:#8b9aaf;--green:#20c997;--red:#ff6678;--blue:#68a8ff;--gold:#efc36a;--purple:#b8a1ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1000px 600px at 75% -15%,#182747 0%,transparent 65%),var(--bg);color:var(--text);font:14px/1.45 Inter,Segoe UI,Roboto,Arial,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:22px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:20px}.brand{display:flex;align-items:center;gap:13px}.logo{width:43px;height:43px;border-radius:13px;background:linear-gradient(135deg,#65a7ff,#9f8aff);display:grid;place-items:center;color:#09101b;font-weight:900;font-size:17px;box-shadow:0 8px 30px #578af533}.eyebrow{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--blue);font-weight:800}.brand h1{font-size:20px;letter-spacing:-.04em;margin:2px 0 0}.status{display:flex;align-items:center;gap:9px;padding:9px 12px;border:1px solid var(--line);border-radius:99px;background:#0f1621;color:#b5c5d7;font-size:12px}.dot{height:7px;width:7px;background:var(--green);border-radius:50%;box-shadow:0 0 12px #20c99788}.pill{font-size:10px;letter-spacing:.1em;text-transform:uppercase;background:#15362f;color:#72e1b8;border:1px solid #205342;padding:5px 8px;border-radius:7px;font-weight:800}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{background:linear-gradient(180deg,#111925,#0d131d);border:1px solid var(--line);border-radius:15px;padding:16px;min-width:0;box-shadow:0 14px 35px #00000012}.klabel{color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:700}.big{font-size:clamp(23px,2.5vw,32px);font-weight:750;letter-spacing:-.05em;margin:9px 0 3px;font-variant-numeric:tabular-nums}.sub{color:var(--muted);font-size:11px}.positive{color:var(--green)!important}.negative{color:var(--red)!important}.gold{color:var(--gold)!important}.blue{color:var(--blue)!important}
.section{display:flex;align-items:end;justify-content:space-between;gap:14px;margin:24px 2px 11px}.section h2{font-size:15px;letter-spacing:-.02em;margin:0}.section p{margin:4px 0 0;color:var(--muted);font-size:11px}.layout{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(290px,.8fr);gap:12px}.chart-card{padding:0;overflow:hidden}.chart-head{padding:15px 17px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:12px}.chart-title{font-weight:750;font-size:14px}.chart-title small{display:block;color:var(--muted);font-size:11px;font-weight:400;margin-top:3px}.price-now{font-size:17px;font-weight:800;font-variant-numeric:tabular-nums}.chart-wrap{height:385px;position:relative;padding:8px 10px 7px}.chart-wrap canvas{width:100%;height:100%;display:block}.chart-foot{display:flex;gap:16px;flex-wrap:wrap;padding:10px 17px;border-top:1px solid var(--line);color:var(--muted);font-size:11px}.legend{display:inline-flex;align-items:center;gap:6px}.swatch{height:7px;width:7px;border-radius:2px;background:var(--green)}.swatch.red{background:var(--red)}.aside{display:flex;flex-direction:column;gap:12px}.signal-card{background:linear-gradient(140deg,#151f30,#101621);border:1px solid #26364e;border-radius:15px;padding:17px}.signal-top{display:flex;justify-content:space-between;gap:10px;align-items:center}.signal-state{font-size:21px;font-weight:850;letter-spacing:-.04em;margin:12px 0 2px}.reason{color:#afbdd0;font-size:12px;line-height:1.5}.meta-row{display:flex;justify-content:space-between;gap:10px;padding-top:10px;margin-top:10px;border-top:1px solid #263144;color:var(--muted);font-size:11px}.model-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.model{padding:14px}.model-head{display:flex;justify-content:space-between;align-items:center;gap:5px}.model h3{font-size:12px;margin:0}.model small{display:block;color:var(--muted);font-size:10px;margin-top:5px}.model-value{font-size:17px;font-weight:800;margin-top:14px;letter-spacing:-.03em;overflow-wrap:anywhere}.status-tag{font-size:9px;border-radius:5px;padding:3px 5px;background:#202a39;color:#aab8ca;white-space:nowrap}.status-tag.ok{background:#14342e;color:#6fddb3}.status-tag.no{background:#37242b;color:#ff9ba7}.status-tag.wait{background:#342e20;color:#e8c875}.lower{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:12px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px;min-width:520px}th{text-align:left;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:700}th,td{padding:11px 12px;border-bottom:1px solid #1f2a38;white-space:nowrap}tbody tr:last-child td{border-bottom:0}.num{text-align:right;font-variant-numeric:tabular-nums}.empty{padding:24px;text-align:center;color:var(--muted);font-size:12px}.footnote{margin:20px 2px 8px;color:#718096;font-size:10px;line-height:1.6;display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}.warning{margin-top:12px;padding:11px 14px;border:1px solid #50432b;background:#211d15;border-radius:10px;color:#ddc58d;font-size:11px;display:none}.refresh{color:var(--muted);font-size:11px}@media(max-width:1050px){.model-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.layout{grid-template-columns:1fr}.aside{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.wrap{padding:12px}.top{align-items:flex-start}.status{font-size:10px}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.model-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.aside,.lower{display:flex;flex-direction:column}.chart-wrap{height:300px}.brand h1{font-size:17px}.pill{font-size:9px}}
</style></head><body><div class="wrap">
<header class="top"><div class="brand"><div class="logo">3P</div><div><div class="eyebrow">Quant research terminal</div><h1>Convergência <span style="color:#78aaff">Pai / Filho / Trindade</span></h1></div></div><div class="status"><span class="dot" id="dot"></span><span id="connection">Conectando ao painel…</span><span class="pill">Shadow only</span></div></header>
<div class="grid">
<div class="card"><div class="klabel">BTC / USDT · preço público</div><div class="big" id="price">—</div><div class="sub" id="change">Cotação pública em atualização</div></div>
<div class="card"><div class="klabel">Patrimônio virtual</div><div class="big" id="equity">1,000000</div><div class="sub" id="equitySub">Capital inicial normalizado = 1,00</div></div>
<div class="card"><div class="klabel">Drawdown máximo</div><div class="big" id="drawdown">0,00%</div><div class="sub">Desde o pico da sessão simulada</div></div>
<div class="card"><div class="klabel">Operações encerradas</div><div class="big" id="trades">0</div><div class="sub" id="decisions">0 decisões processadas</div></div>
</div>
<div class="section"><div><h2>Mercado em tempo real</h2><p>Preço consultado na API pública; candles de 1 minuto fechados na sessão local.</p></div><div class="refresh" id="updated">Atualizando…</div></div>
<div class="layout"><div class="card chart-card"><div class="chart-head"><div class="chart-title">BTCUSDT <span style="color:#7d8ba1">/ SPOT</span><small id="chartSub">Velas de 1 minuto · candles fechados</small></div><div class="price-now" id="chartPrice">—</div></div><div class="chart-wrap"><canvas id="chart"></canvas></div><div class="chart-foot"><span class="legend"><span class="swatch"></span> Fechamento acima da abertura</span><span class="legend"><span class="swatch red"></span> Fechamento abaixo da abertura</span><span id="lastCandle">Último candle: —</span></div></div>
<div class="aside"><div class="signal-card"><div class="signal-top"><div class="klabel">Última decisão do motor</div><span class="pill">Sem corretora</span></div><div class="signal-state" id="action">AGUARDANDO</div><div class="reason" id="reason">Aguardando novas decisões da sessão sombra.</div><div class="meta-row"><span>Posição simulada</span><strong id="position">FLAT</strong></div><div class="meta-row"><span>Última decisão UTC</span><strong id="lastDecision">—</strong></div><div class="meta-row"><span>Taxa / slippage por lado</span><strong id="costs">10 / 5 bps</strong></div></div><div class="card"><div class="klabel">Integridade da sessão</div><div class="model-value" id="sessionStatus">VERIFICANDO</div><div class="sub" id="sessionInfo" style="margin-top:6px">Lendo estado persistido e logs.</div><div class="warning" id="gapWarning"></div></div></div></div>
<div class="section"><div><h2>Convergência dos cinco modelos</h2><p>Valores da última decisão processada, não previsões garantidas.</p></div></div>
<div class="model-grid">
<div class="card model"><div class="model-head"><h3>01 · Fibonacci</h3><span class="status-tag wait" id="fibTag">AGUARDA</span></div><small>Nível 61,8% · reação</small><div class="model-value" id="fibVal">—</div><small id="fibNote">Sem decisão registrada</small></div>
<div class="card model"><div class="model-head"><h3>02 · Fractal</h3><span class="status-tag wait" id="fracTag">AGUARDA</span></div><small>Pai 15m × Filho 1m</small><div class="model-value" id="fracVal">—</div><small id="fracNote">Sem decisão registrada</small></div>
<div class="card model"><div class="model-head"><h3>03 · Regime</h3><span class="status-tag wait" id="regTag">AGUARDA</span></div><small>Z-score estatístico</small><div class="model-value" id="regVal">—</div><small id="regNote">Classificação do regime</small></div>
<div class="card model"><div class="model-head"><h3>04 · Energia</h3><span class="status-tag wait" id="volTag">AGUARDA</span></div><small>Volume relativo</small><div class="model-value" id="volVal">—</div><small id="volNote">Atividade negociada</small></div>
<div class="card model"><div class="model-head"><h3>05 · Momentum</h3><span class="status-tag wait" id="momTag">AGUARDA</span></div><small>Inclinação e aceleração</small><div class="model-value" id="momVal">—</div><small id="momNote">Força direcional normalizada</small></div>
</div>
<div class="section"><div><h2>Histórico de operações simuladas</h2><p>Execuções registradas pelo monitor, depois de custos estimados.</p></div></div>
<div class="lower"><div class="card"><div class="klabel" style="margin-bottom:8px">Últimas operações encerradas</div><div class="table-wrap" id="tradeTable"><div class="empty">Nenhuma operação encerrada nesta sessão.</div></div></div><div class="card"><div class="klabel" style="margin-bottom:8px">Eventos e observações</div><div class="table-wrap" id="eventTable"><div class="empty">Nenhum evento recente.</div></div></div></div>
<div class="footnote"><span>3 PRO · PAINEL LOCAL DE PESQUISA · SOMENTE SIMULAÇÃO</span><span>Atualização automática a cada 5 segundos · dados públicos BTC/USDT</span><span>Preço/vela e métricas de sessão podem ter atrasos. Não é recomendação financeira.</span></div>
</div>
<script>
const $=id=>document.getElementById(id);const fmt=(v,d=2)=>{if(v===null||v===undefined||v===''||!Number.isFinite(Number(v)))return '—';return Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d})};const pct=v=>v===null||v===undefined?'—':fmt(Number(v)*100,2)+'%';const priceFmt=v=>v==null?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});const shortTime=s=>{if(!s)return '—';let d=new Date(s);return Number.isNaN(d.getTime())?String(s):d.toLocaleString('pt-BR',{hour12:false,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})};
function tag(id,yes,detail){let e=$(id);e.className='status-tag '+(yes===true?'ok':yes===false?'no':'wait');e.textContent=detail||(yes===true?'CONFIRMA':yes===false?'NÃO CONF.':'AGUARDA')}
function direction(v){if(v===1||v==='1')return 'ALTA';if(v===-1||v==='-1')return 'BAIXA';if(v===0||v==='0')return 'NEUTRO';return '—'}
function drawChart(candles,current){const canvas=$('chart');const rect=canvas.getBoundingClientRect();const dpr=window.devicePixelRatio||1;canvas.width=Math.max(1,Math.floor(rect.width*dpr));canvas.height=Math.max(1,Math.floor(rect.height*dpr));const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);const w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);if(!candles||candles.length<2){ctx.fillStyle='#8b9aaf';ctx.fillText('Aguardando candles suficientes…',20,30);return}const list=candles.slice(-110);let lo=Math.min(...list.map(c=>Number(c.low))),hi=Math.max(...list.map(c=>Number(c.high)));if(current&&current>0){lo=Math.min(lo,current);hi=Math.max(hi,current)}const range=hi-lo||1;lo-=range*.06;hi+=range*.06;const left=8,right=78,top=10,bottom=26;const cw=w-left-right,ch=h-top-bottom;const y=p=>top+(hi-p)/(hi-lo)*ch;ctx.font='10px Segoe UI,Arial';ctx.strokeStyle='#202b3a';ctx.fillStyle='#8190a5';ctx.lineWidth=1;for(let i=0;i<5;i++){const yy=top+ch*i/4;ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(left+cw,yy);ctx.stroke();const p=hi-(hi-lo)*i/4;ctx.fillText(priceFmt(p),left+cw+8,yy+3)}const step=cw/list.length;const body=Math.max(2,Math.min(8,step*.62));list.forEach((c,i)=>{const x=left+step*(i+.5),o=Number(c.open),hig=Number(c.high),low=Number(c.low),cl=Number(c.close),col=cl>=o?'#20c997':'#ff6678';ctx.strokeStyle=col;ctx.fillStyle=col;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,y(hig));ctx.lineTo(x,y(low));ctx.stroke();const yy=Math.min(y(o),y(cl)),hh=Math.max(1.5,Math.abs(y(o)-y(cl)));ctx.fillRect(x-body/2,yy,body,hh)});if(current&&current>lo&&current<hi){const yy=y(current);ctx.save();ctx.strokeStyle='#68a8ff';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(left+cw,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#203854';ctx.fillRect(left+cw+2,yy-9,right-5,18);ctx.fillStyle='#a4ccff';ctx.fillText(priceFmt(current),left+cw+7,yy+4);ctx.restore()}const dates=[list[0],list[Math.floor(list.length/2)],list[list.length-1]];[0,Math.floor(list.length/2),list.length-1].forEach((idx,j)=>{const c=list[idx];const x=left+step*(idx+.5);ctx.fillStyle='#7f8da2';ctx.fillText((c.timestamp||'').slice(11,16),Math.min(x-14,left+cw-35),h-7)});}
function tableTrades(rows){if(!rows||!rows.length){$('tradeTable').innerHTML='<div class="empty">Nenhuma operação encerrada nesta sessão.</div>';return}const arr=rows.slice(-8).reverse();$('tradeTable').innerHTML='<table><thead><tr><th>Saída UTC</th><th class="num">Retorno líquido</th><th class="num">Duração</th><th>Motivo</th></tr></thead><tbody>'+arr.map(t=>{let n=Number(t.net_return_on_entry_equity);return `<tr><td>${shortTime(t.exit_execution_timestamp_utc)}</td><td class="num ${n>=0?'positive':'negative'}">${Number.isFinite(n)?pct(n):'—'}</td><td class="num">${fmt(t.holding_minutes,0)} min</td><td>${String(t.exit_reason||'—').replace(/[<>&]/g,'')}</td></tr>`}).join('')+'</tbody></table>'}
function tableEvents(rows){if(!rows||!rows.length){$('eventTable').innerHTML='<div class="empty">Nenhum evento recente.</div>';return}const arr=rows.slice(-7).reverse();$('eventTable').innerHTML='<table><thead><tr><th>Horário</th><th>Evento</th><th>Nota</th></tr></thead><tbody>'+arr.map(e=>`<tr><td>${shortTime(e.event_timestamp_utc)}</td><td>${String(e.event_type||'—').replace(/[<>&]/g,'')}</td><td>${String(e.note||'—').replace(/[<>&]/g,'').slice(0,100)}</td></tr>`).join('')+'</tbody></table>'}
function render(d){const s=d.session||{},m=d.market||{},sig=d.latest_signal||{};const p=m.last_price;$('price').textContent=p?priceFmt(p):'—';$('chartPrice').textContent=p?priceFmt(p):'—';$('change').textContent=m.price_change_percent_24h==null?'Cotação pública':`${fmt(m.price_change_percent_24h,2)}% nas últimas 24h`; $('change').className='sub '+(Number(m.price_change_percent_24h)>=0?'positive':'negative');$('equity').textContent=fmt(s.marked_equity??s.equity,6);$('equitySub').textContent=s.open_position_unrealized_display_only?'Marcado pelo último preço · informativo':'Capital inicial normalizado = 1,00';const dd=Number(s.max_drawdown||0);$('drawdown').textContent=pct(dd);$('drawdown').className='big '+(dd<0?'negative':'');$('trades').textContent=fmt(s.closed_trades||0,0);$('decisions').textContent=`${fmt(s.decisions_processed||0,0)} decisões processadas`;const mktOk=!!m.last_price;$('connection').textContent=mktOk?'Mercado público conectado':'Preço público indisponível';$('dot').style.background=mktOk?'#20c997':'#efc36a';$('dot').style.boxShadow=mktOk?'0 0 12px #20c99788':'none';$('updated').textContent='Atualizado '+shortTime(d.generated_at_utc);$('sessionStatus').textContent=!s.monitor_fresh?'SEM ATUALIZAÇÃO RECENTE':(s.data_gap_count?'COM LACUNAS REGISTRADAS':'MONITOR ATUALIZADO');$('sessionStatus').className='model-value '+(!s.monitor_fresh||s.data_gap_count?'gold':'positive');$('sessionInfo').textContent=`Início ${shortTime(s.started_at_utc)} · atualizado ${shortTime(s.updated_at_utc)} · ${s.symbol||'BTCUSDT'}`;$('position').textContent=s.position_open?'COMPRADO':'FLAT';$('position').className=s.position_open?'positive':'';$('lastDecision').textContent=shortTime(s.last_decision_timestamp_utc);$('costs').textContent=`${fmt(s.fee_bps_per_side,0)} / ${fmt(s.slippage_bps_per_side,0)} bps`;
const warn=$('gapWarning');if((s.data_gap_count||0)>0||s.max_drawdown_is_lower_bound_due_to_gap){warn.style.display='block';warn.textContent=`Atenção: ${s.data_gap_count||0} lacuna(s), ${s.missed_decision_bars||0} candles de decisão perdidos. Não foram inventados fills retroativos; o drawdown pode ser subestimado.`}else{warn.style.display='none'}
const act=String(sig.action||'AGUARDANDO').toUpperCase();$('action').textContent=act.replaceAll('_',' ');$('action').className='signal-state '+(act.includes('BUY')?'positive':(act.includes('SELL')||act.includes('EXIT')?'negative':''));$('reason').textContent=sig.action_reason||'Nenhuma decisão registrada ainda nesta sessão.';tag('fibTag',sig.fibonacci_confirmed===true,sig.fibonacci_confirmed===true?'CONFIRMA':sig.fibonacci_confirmed===false?'NÃO CONF.':'AGUARDA');$('fibVal').textContent=sig.fib_618?priceFmt(sig.fib_618):'—';$('fibNote').textContent=sig.fib_618?`Nível de retração observado`:'Sem nível nesta decisão';tag('fracTag',sig.parent_direction!=null&&sig.child_direction!=null&&Number(sig.parent_direction)===Number(sig.child_direction)&&Number(sig.parent_direction)!==0,sig.parent_direction==null?'AGUARDA':`${direction(sig.parent_direction)} / ${direction(sig.child_direction)}`);$('fracVal').textContent=`${direction(sig.parent_direction)} · ${direction(sig.child_direction)}`;$('fracNote').textContent='Pai 15m / Filho 1m';tag('regTag',sig.regime_acceptable===true,sig.regime_acceptable===true?'ACEITÁVEL':sig.regime_acceptable===false?'REJEITADO':'AGUARDA');$('regVal').textContent=sig.regime_zscore==null?'—':fmt(sig.regime_zscore,2);$('regNote').textContent='Z-score da última decisão';tag('volTag',sig.volume_confirmed===true,sig.volume_confirmed===true?'CONFIRMA':sig.volume_confirmed===false?'NÃO CONF.':'AGUARDA');$('volVal').textContent=sig.relative_volume==null?'—':`${fmt(sig.relative_volume,2)}×`;$('volNote').textContent='Volume relativo à janela anterior';tag('momTag',sig.momentum_confirmed===true,sig.momentum_confirmed===true?'CONFIRMA':sig.momentum_confirmed===false?'NÃO CONF.':'AGUARDA');$('momVal').textContent=sig.normalized_slope==null?'—':fmt(sig.normalized_slope,3);$('momNote').textContent=`Inclinação · acel. ${sig.normalized_acceleration==null?'—':fmt(sig.normalized_acceleration,3)}`;
$('lastCandle').textContent='Último candle fechado: '+shortTime((d.candles||[]).length?d.candles[d.candles.length-1].timestamp:null)+' UTC';drawChart(d.candles||[],p);tableTrades(d.trades||[]);tableEvents(d.events||[])}
async function refresh(){try{const r=await fetch('/api/snapshot',{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const d=await r.json();render(d)}catch(e){$('connection').textContent='Painel local sem resposta';$('dot').style.background='#ff6678';$('dot').style.boxShadow='none';$('updated').textContent='Falha: '+e.message}}
window.addEventListener('resize',()=>refresh());refresh();setInterval(refresh,5000);
</script></body></html>'''


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite_float(value, default=None):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def latest_session(root: Path) -> Path:
    parent = root / "data" / "shadow"
    candidates = [p for p in parent.glob("session_BTCUSDT_*") if p.is_dir() and (p / "state.json").is_file()]
    if not candidates:
        raise FileNotFoundError(f"Nenhuma sessao BTCUSDT em modo sombra encontrada em {parent}")
    return max(candidates, key=lambda p: (p / "state.json").stat().st_mtime)


def read_csv_tail(path: Path, max_rows: int = 180, max_bytes: int = 524288) -> list[dict]:
    """Read the tail of an append-only CSV without loading the historical cache fully."""
    if not path.is_file():
        return []
    try:
        header_line = None
        with path.open("rb") as stream:
            # Always read the real CSV header from byte zero. A tail chunk is
            # not self-describing; its first complete row must never become a header.
            header_line = stream.readline().decode("utf-8-sig", errors="strict").rstrip("\r\n")
            stream.seek(0, 2)
            size = stream.tell()
            start = max(0, size - max_bytes)
            stream.seek(start)
            raw = stream.read()
        if start > 0:
            cut = raw.find(b"\n")
            if cut < 0:
                return []
            raw = raw[cut + 1:]
        text = raw.decode("utf-8-sig", errors="strict")
        # Ignore a final line if the writer has not completed it yet.
        if text and not text.endswith("\n"):
            last_newline = text.rfind("\n")
            text = text[:last_newline + 1] if last_newline >= 0 else ""
        if not text.strip():
            return []
        # When a suffix was read, prepend the actual header. When the entire
        # file was read from byte zero, it already includes its header.
        if start > 0:
            text = header_line + "\n" + text
        lines = text.splitlines()
        if len(lines) <= 1:
            return []
        parsed = list(csv.DictReader(io.StringIO("\n".join(lines) + "\n")))
        return parsed[-max_rows:]
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _to_clean(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    x = finite_float(value, None)
    if x is not None:
        return x
    return str(value)


def clean_row(row: dict, numeric_fields: set[str]) -> dict:
    out = {}
    for k, v in row.items():
        if v == "":
            out[k] = None
        elif k in numeric_fields:
            out[k] = finite_float(v, None)
        elif v in ("True", "False"):
            out[k] = v == "True"
        else:
            out[k] = v
    return out


SIGNAL_NUMERIC = {
    "execution_open", "parent_direction", "child_direction", "fib_618", "regime_zscore",
    "relative_volume", "normalized_slope", "normalized_acceleration", "equity_after_execution",
    "fee_bps_per_side", "slippage_bps_per_side",
}
TRADE_NUMERIC = {
    "entry_price", "exit_price", "holding_minutes", "gross_price_return", "net_return_on_entry_equity",
    "entry_equity_before_cost", "equity_after_exit", "fee_bps_per_side", "slippage_bps_per_side",
}
EVENT_NUMERIC = {"missed_decision_bars", "equity_after_event"}


class SnapshotProvider:
    def __init__(self, root: Path, session: Path, symbol: str):
        self.root = root.resolve()
        self.session = session.resolve()
        self.symbol = symbol.upper()
        shadow_root = (self.root / "data" / "shadow").resolve()
        if shadow_root not in self.session.parents or not self.session.is_dir():
            raise ValueError("A sessao deve estar dentro de data/shadow do projeto.")
        self.cache_path = self.session / f"{self.symbol}_1m_cache.csv"
        self._market_lock = threading.Lock()
        self._market_cache: tuple[float, dict] | None = None

    def market(self) -> dict:
        now = time.monotonic()
        with self._market_lock:
            if self._market_cache and now - self._market_cache[0] < CACHE_TTL_SECONDS:
                return dict(self._market_cache[1])
            result = {
                "last_price": None, "price_change_percent_24h": None,
                "high_24h": None, "low_24h": None, "quote_volume_24h": None,
                "source": "Binance public Spot API", "market_error": None,
            }
            try:
                url = BINANCE_24H
                if self.symbol != "BTCUSDT":
                    url = "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=" + self.symbol
                req = Request(url, headers={"User-Agent": "Convergencia3ProDashboard/1.0", "Accept": "application/json"})
                with urlopen(req, timeout=4) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                result.update({
                    "last_price": finite_float(payload.get("lastPrice")),
                    "price_change_percent_24h": finite_float(payload.get("priceChangePercent")),
                    "high_24h": finite_float(payload.get("highPrice")),
                    "low_24h": finite_float(payload.get("lowPrice")),
                    "quote_volume_24h": finite_float(payload.get("quoteVolume")),
                    "price_timestamp_utc": utc_now_iso(),
                    "market_error": None,
                })
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                result["market_error"] = f"Cotacao publica indisponivel: {type(exc).__name__}: {exc}"
                # Display-only fallback to the most recent cached candle close.
                last = read_csv_tail(self.cache_path, max_rows=1, max_bytes=65536)
                if last:
                    result["last_price"] = finite_float(last[-1].get("close"))
                    result["price_timestamp_utc"] = last[-1].get("timestamp")
                    result["source"] = "Ultimo fechamento local (fallback)"
            self._market_cache = (time.monotonic(), dict(result))
            return result

    def snapshot(self) -> dict:
        state = read_json(self.session / "state.json")
        summary = read_json(self.session / "summary.json")
        if not state:
            state = summary
        signals = read_csv_tail(self.session / "shadow_signals.csv", max_rows=1, max_bytes=262144)
        trades = read_csv_tail(self.session / "shadow_trades.csv", max_rows=12, max_bytes=262144)
        events = read_csv_tail(self.session / "shadow_events.csv", max_rows=10, max_bytes=262144)
        candles = read_csv_tail(self.cache_path, max_rows=180, max_bytes=524288)
        candles_clean = []
        for row in candles:
            item = clean_row(row, {"open", "high", "low", "close", "volume", "quote_volume", "trades"})
            if all(item.get(k) is not None for k in ("open", "high", "low", "close")):
                candles_clean.append(item)
        latest_signal = clean_row(signals[-1], SIGNAL_NUMERIC) if signals else {}
        trades_clean = [clean_row(row, TRADE_NUMERIC) for row in trades]
        events_clean = [clean_row(row, EVENT_NUMERIC) for row in events]
        mkt = self.market()
        fallback_close = finite_float(candles_clean[-1].get("close")) if candles_clean else None
        if mkt.get("last_price") is None:
            mkt["last_price"] = fallback_close
        # Report the most recent market candle plus the last processed decision separately.
        updated_at = summary.get("updated_at_utc") or state.get("updated_at_utc")
        updated_age_seconds = None
        if updated_at:
            try:
                updated_stamp = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
                if updated_stamp.tzinfo is None:
                    updated_stamp = updated_stamp.replace(tzinfo=timezone.utc)
                updated_age_seconds = max(0.0, (datetime.now(timezone.utc) - updated_stamp.astimezone(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                updated_age_seconds = None
        session_info = {
            "session_name": self.session.name,
            "session_directory": str(self.session),
            "symbol": state.get("symbol", self.symbol),
            "mode": state.get("mode", "SHADOW_ONLY_NO_REAL_ORDERS"),
            "started_at_utc": state.get("started_at_utc"),
            "updated_at_utc": updated_at,
            "monitor_age_seconds": updated_age_seconds,
            "monitor_fresh": updated_age_seconds is not None and updated_age_seconds <= 180.0,
            "last_decision_timestamp_utc": state.get("last_decision_timestamp_utc"),
            "last_open_timestamp_utc": state.get("last_open_timestamp_utc"),
            "position_open": bool(state.get("position_open", False)),
            "equity": finite_float(state.get("equity"), 1.0),
            "marked_equity": finite_float(summary.get("equity_marked_to_latest_price_display_only"), finite_float(state.get("equity"), 1.0)),
            "open_position_unrealized_display_only": bool(summary.get("open_position_unrealized_display_only", False)),
            "peak_equity": finite_float(state.get("peak_equity"), 1.0),
            "max_drawdown": finite_float(state.get("max_drawdown"), 0.0),
            "closed_trades": int(state.get("closed_trades", 0) or 0),
            "decisions_processed": int(state.get("decisions_processed", 0) or 0),
            "fee_bps_per_side": finite_float(state.get("fee_bps_per_side"), 10.0),
            "slippage_bps_per_side": finite_float(state.get("slippage_bps_per_side"), 5.0),
            "data_gap_count": int(state.get("data_gap_count", 0) or 0),
            "missed_decision_bars": int(state.get("missed_decision_bars", 0) or 0),
            "max_drawdown_is_lower_bound_due_to_gap": bool(state.get("max_drawdown_is_lower_bound_due_to_gap", False)),
            "orders_sent": int(summary.get("orders_sent", 0) or 0),
            "live_broker_connected": bool(summary.get("live_broker_connected", False)),
            "base_csv_sha256": state.get("base_csv_sha256"),
        }
        return {
            "generated_at_utc": utc_now_iso(),
            "session": session_info,
            "market": mkt,
            "candles": candles_clean,
            "latest_signal": latest_signal,
            "trades": trades_clean,
            "events": events_clean,
        }


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        session = root / "data" / "shadow" / "session_BTCUSDT_selftest"
        session.mkdir(parents=True)
        (session / "state.json").write_text(json.dumps({"symbol": "BTCUSDT", "equity": 1.0, "position_open": False}), encoding="utf-8")
        (session / "summary.json").write_text(json.dumps({"orders_sent": 0, "live_broker_connected": False}), encoding="utf-8")
        (session / "BTCUSDT_1m_cache.csv").write_text(
            "timestamp,open,high,low,close,volume,close_time,quote_volume,trades,taker_buy_base_volume,taker_buy_quote_volume\n"
            "2026-10-21T03:20:00+00:00,100,102,99,101,10,2026-10-21T03:20:59.999000+00:00,1010,25,4,404\n",
            encoding="utf-8",
        )
        (session / "shadow_signals.csv").write_text(
            "decision_timestamp_utc,execution_timestamp_utc,execution_open,action,action_reason,entry_qualified,exit_condition,parent_direction,child_direction,fib_618,fibonacci_confirmed,regime_zscore,regime_acceptable,relative_volume,volume_confirmed,normalized_slope,normalized_acceleration,momentum_confirmed,position_before,position_after,equity_after_execution,fee_bps_per_side,slippage_bps_per_side\n",
            encoding="utf-8",
        )
        # Ensure tail reads retain the real header when a file exceeds max_bytes.
        tail_path = session / "tail_test.csv"
        with tail_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["timestamp", "close"])
            for i in range(30):
                writer.writerow([f"2026-10-21T03:{i:02d}:00+00:00", 100 + i])
        tail = read_csv_tail(tail_path, max_rows=2, max_bytes=80)
        assert len(tail) == 2 and tail[-1]["close"] == "129", tail
        provider = SnapshotProvider(root, session, "BTCUSDT")
        provider.market = lambda: {"last_price": 101.0, "price_change_percent_24h": 1.0, "source": "self-test"}
        snap = provider.snapshot()
        assert snap["session"]["orders_sent"] == 0
        assert len(snap["candles"]) == 1 and snap["market"]["last_price"] == 101.0
        assert snap["session"]["position_open"] is False
    print("SELF-TEST PASSED: session isolation, CSV tail header, candles and no-order status.")


def make_handler(provider: SnapshotProvider):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            if path == "/" or path == "/index.html":
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/health":
                payload = {"ok": True, "service": "3pro-local-dashboard", "mode": "shadow-only", "orders_sent": 0}
            elif path == "/api/snapshot":
                try:
                    payload = provider.snapshot()
                except Exception as exc:  # dashboard must show errors without mutating session
                    payload = {"generated_at_utc": utc_now_iso(), "error": f"{type(exc).__name__}: {exc}"}
                    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                    return
            else:
                self.send_error(404)
                return
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            print("[painel] " + (fmt % args))

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Raiz do projeto")
    parser.add_argument("--session", type=Path, default=None, help="Sessao existente; por padrao usa a sessao BTCUSDT mais recente")
    parser.add_argument("--host", default="127.0.0.1", help="Por seguranca, mantenha 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.host not in ("127.0.0.1", "localhost"):
        parser.error("O painel aceita apenas loopback local (127.0.0.1/localhost).")
    root = args.root.resolve()
    session = args.session.resolve() if args.session else latest_session(root)
    provider = SnapshotProvider(root, session, "BTCUSDT")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(provider))
    url = f"http://127.0.0.1:{args.port}/"
    print("=" * 68)
    print("PAINEL 3 PRO — CONVERGENCIA PAI / FILHO / TRINDADE")
    print("URL:", url)
    print("Sessao observada:", session)
    print("Modo: somente leitura + cotacao publica. Nenhuma ordem real pode ser enviada.")
    print("Atualizacao visual: 5 segundos. Candle de 1m local + ticker publico.")
    print("Pressione Ctrl+C para encerrar apenas o painel; o monitor sombra continua separado.")
    print("=" * 68)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nPainel encerrado. Sessao sombra e arquivos nao foram alterados pelo painel.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERRO NO PAINEL: {type(exc).__name__}: {exc}")
        raise SystemExit(2)
