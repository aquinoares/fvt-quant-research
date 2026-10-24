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
<title>3 Pro | Convergência — Backtest + Sinais ao Vivo</title>
<style>
:root{color-scheme:dark;--bg:#080b12;--panel:#101621;--panel2:#131c29;--line:#202b3a;--text:#eef3fa;--muted:#8b9aaf;--green:#20c997;--red:#ff6678;--blue:#68a8ff;--gold:#efc36a;--purple:#b8a1ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1000px 600px at 75% -15%,#182747 0%,transparent 65%),var(--bg);color:var(--text);font:14px/1.45 Inter,Segoe UI,Roboto,Arial,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:22px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:20px}.brand{display:flex;align-items:center;gap:13px}.logo{width:43px;height:43px;border-radius:13px;background:linear-gradient(135deg,#65a7ff,#9f8aff);display:grid;place-items:center;color:#09101b;font-weight:900;font-size:17px;box-shadow:0 8px 30px #578af533}.eyebrow{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--blue);font-weight:800}.brand h1{font-size:20px;letter-spacing:-.04em;margin:2px 0 0}.status{display:flex;align-items:center;gap:9px;padding:9px 12px;border:1px solid var(--line);border-radius:99px;background:#0f1621;color:#b5c5d7;font-size:12px}.dot{height:7px;width:7px;background:var(--green);border-radius:50%;box-shadow:0 0 12px #20c99788}.pill{font-size:10px;letter-spacing:.1em;text-transform:uppercase;background:#15362f;color:#72e1b8;border:1px solid #205342;padding:5px 8px;border-radius:7px;font-weight:800}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{background:linear-gradient(180deg,#111925,#0d131d);border:1px solid var(--line);border-radius:15px;padding:16px;min-width:0;box-shadow:0 14px 35px #00000012}.klabel{color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:700}.big{font-size:clamp(23px,2.5vw,32px);font-weight:750;letter-spacing:-.05em;margin:9px 0 3px;font-variant-numeric:tabular-nums}.sub{color:var(--muted);font-size:11px}.positive{color:var(--green)!important}.negative{color:var(--red)!important}.gold{color:var(--gold)!important}.blue{color:var(--blue)!important}
.section{display:flex;align-items:end;justify-content:space-between;gap:14px;margin:24px 2px 11px}.section h2{font-size:15px;letter-spacing:-.02em;margin:0}.section p{margin:4px 0 0;color:var(--muted);font-size:11px}.layout{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(290px,.8fr);gap:12px}.chart-card{padding:0;overflow:hidden}.chart-head{padding:15px 17px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:12px}.chart-title{font-weight:750;font-size:14px}.chart-title small{display:block;color:var(--muted);font-size:11px;font-weight:400;margin-top:3px}.price-now{font-size:17px;font-weight:800;font-variant-numeric:tabular-nums}.chart-wrap{height:385px;position:relative;padding:8px 10px 7px}.chart-wrap canvas{width:100%;height:100%;display:block}.chart-foot{display:flex;gap:16px;flex-wrap:wrap;padding:10px 17px;border-top:1px solid var(--line);color:var(--muted);font-size:11px}.legend{display:inline-flex;align-items:center;gap:6px}.swatch{height:7px;width:7px;border-radius:2px;background:var(--green)}.swatch.red{background:var(--red)}.aside{display:flex;flex-direction:column;gap:12px}.signal-card{background:linear-gradient(140deg,#151f30,#101621);border:1px solid #26364e;border-radius:15px;padding:17px}.signal-top{display:flex;justify-content:space-between;gap:10px;align-items:center}.signal-state{font-size:21px;font-weight:850;letter-spacing:-.04em;margin:12px 0 2px}.reason{color:#afbdd0;font-size:12px;line-height:1.5}.meta-row{display:flex;justify-content:space-between;gap:10px;padding-top:10px;margin-top:10px;border-top:1px solid #263144;color:var(--muted);font-size:11px}.model-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.model{padding:14px}.model-head{display:flex;justify-content:space-between;align-items:center;gap:5px}.model h3{font-size:12px;margin:0}.model small{display:block;color:var(--muted);font-size:10px;margin-top:5px}.model-value{font-size:17px;font-weight:800;margin-top:14px;letter-spacing:-.03em;overflow-wrap:anywhere}.status-tag{font-size:9px;border-radius:5px;padding:3px 5px;background:#202a39;color:#aab8ca;white-space:nowrap}.status-tag.ok{background:#14342e;color:#6fddb3}.status-tag.no{background:#37242b;color:#ff9ba7}.status-tag.wait{background:#342e20;color:#e8c875}.lower{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:12px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px;min-width:520px}th{text-align:left;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:700}th,td{padding:11px 12px;border-bottom:1px solid #1f2a38;white-space:nowrap}tbody tr:last-child td{border-bottom:0}.num{text-align:right;font-variant-numeric:tabular-nums}.empty{padding:24px;text-align:center;color:var(--muted);font-size:12px}.footnote{margin:20px 2px 8px;color:#718096;font-size:10px;line-height:1.6;display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}.warning{margin-top:12px;padding:11px 14px;border:1px solid #50432b;background:#211d15;border-radius:10px;color:#ddc58d;font-size:11px;display:none}.refresh{color:var(--muted);font-size:11px}.signal-history-card{padding:0;overflow:hidden}.signal-history-head{padding:15px 17px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.signal-history-head h2{font-size:14px;margin:0}.signal-history-head p{font-size:11px;color:var(--muted);margin:4px 0 0}.signal-table{min-width:980px}.action-chip{display:inline-block;padding:4px 7px;border-radius:6px;font-size:10px;font-weight:800}.chip-buy{background:#14342e;color:#6fddb3}.chip-sell{background:#37242b;color:#ff9ba7}.chip-hold{background:#2a2e38;color:#c2ccdc}.chip-open{background:#24354d;color:#a4ccff}.mini-confirm{display:inline-flex;gap:4px;flex-wrap:wrap}.mini-confirm span{display:inline-block;min-width:24px;text-align:center;border-radius:4px;padding:2px 4px;font-size:9px;font-weight:800}.mini-y{background:#14342e;color:#6fddb3}.mini-n{background:#37242b;color:#ff9ba7}.mini-u{background:#342e20;color:#e8c875}.stats-grid{margin-top:12px}.subtle-note{color:var(--muted);font-size:11px;line-height:1.5}.reason-box{margin-top:8px;padding:10px 11px;border-radius:9px;background:#0b111a;border:1px solid #273246;color:#d4e0ef;font-size:12px;line-height:1.55}.status-tag.stale{background:#3a2722;color:#ffb59e}@media(max-width:1050px){.model-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.layout{grid-template-columns:1fr}.aside{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.wrap{padding:12px}.top{align-items:flex-start}.status{font-size:10px}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.model-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.aside,.lower{display:flex;flex-direction:column}.chart-wrap{height:300px}.brand h1{font-size:17px}.pill{font-size:9px}}
</style></head><body><div class="wrap">
<header class="top"><div class="brand"><div class="logo">3P</div><div><div class="eyebrow">Quant research terminal</div><h1>Convergência <span style="color:#78aaff">Pai / Filho / Trindade</span></h1></div></div><div class="status"><span class="dot" id="dot"></span><span id="connection">Conectando ao painel…</span><span class="pill">Shadow only</span></div></header>
<div class="grid">
<div class="card"><div class="klabel">BTC / USDT · preço público</div><div class="big" id="price">—</div><div class="sub" id="change">Cotação pública em atualização</div></div>
<div class="card"><div class="klabel">Patrimônio virtual</div><div class="big" id="equity">1,000000</div><div class="sub" id="equitySub">Capital inicial normalizado = 1,00</div></div>
<div class="card"><div class="klabel">Drawdown máximo</div><div class="big" id="drawdown">0,00%</div><div class="sub">Desde o pico da sessão simulada</div></div>
<div class="card"><div class="klabel">Operações avaliáveis</div><div class="big" id="trades">0</div><div class="sub" id="decisions">0 decisões processadas</div></div>
</div>
<div class="grid stats-grid">
<div class="card"><div class="klabel">Acertos líquidos</div><div class="big positive" id="wins">0</div><div class="sub" id="winsSub">Operações encerradas por sinal da estratégia</div></div>
<div class="card"><div class="klabel">Derrotas líquidas</div><div class="big negative" id="losses">0</div><div class="sub" id="lossesSub">Operações encerradas por sinal da estratégia</div></div>
<div class="card"><div class="klabel">Taxa de acerto</div><div class="big" id="winRate">—</div><div class="sub" id="winRateSub">Sem amostra até fechar operações</div></div>
<div class="card"><div class="klabel">Resultado da sessão</div><div class="big" id="sessionReturn">0,00%</div><div class="sub" id="sessionReturnSub">Patrimônio virtual versus 1,00 inicial</div></div>
</div>
<div class="section"><div><h2>Backtest histórico — estratégia original</h2><p>Relatório dos 90 dias já testados, separado da sessão sombra ao vivo. Resultados exploratórios, não validados fora da amostra.</p></div><div class="refresh" id="histSource">Carregando relatório histórico…</div></div>
<div class="grid">
<div class="card"><div class="klabel">Retorno bruto histórico</div><div class="big" id="histGross">—</div><div class="sub">Antes de taxas e slippage</div></div>
<div class="card"><div class="klabel">Retorno líquido histórico</div><div class="big" id="histNet">—</div><div class="sub" id="histCosts">Custos do relatório</div></div>
<div class="card"><div class="klabel">Operações encerradas</div><div class="big" id="histTrades">—</div><div class="sub" id="histTradeSpan">Backtest histórico</div></div>
<div class="card"><div class="klabel">Drawdown máximo</div><div class="big" id="histDD">—</div><div class="sub">Série histórica recomposta</div></div>
</div>
<div class="grid stats-grid">
<div class="card"><div class="klabel">Acertos líquidos</div><div class="big positive" id="histWins">—</div><div class="sub">Operações históricas após custos</div></div>
<div class="card"><div class="klabel">Derrotas líquidas</div><div class="big negative" id="histLosses">—</div><div class="sub" id="histBreakeven">Empates: —</div></div>
<div class="card"><div class="klabel">Taxa de acerto histórica</div><div class="big" id="histWinRate">—</div><div class="sub">Só operações encerradas</div></div>
<div class="card"><div class="klabel">Exposição histórica</div><div class="big" id="histExposure">—</div><div class="sub" id="histInputInfo">Origem do relatório</div></div>
</div>
<div class="card signal-history-card" style="margin-top:12px"><div class="signal-history-head"><div><h2>Entradas e saídas do backtest histórico</h2><p>As operações abaixo vêm do CSV de resultados históricos, não da sessão sombra atual.</p></div><div class="refresh" id="histTableCount">—</div></div><div class="table-wrap" id="historicalTradeTable"><div class="empty">Carregando operações históricas…</div></div><div class="subtle-note" style="padding:12px 17px" id="histDisclaimer">Os resultados passados são exploratórios. Custos e fills são os do simulador; não são ordens reais.</div></div>
<div class="section"><div><h2>Mercado em tempo real</h2><p>Preço público e candles fechados; decisão do motor tem relógio separado.</p></div><div class="refresh" id="updated">Atualizando…</div></div>
<div class="layout"><div class="card chart-card"><div class="chart-head"><div class="chart-title">BTCUSDT <span style="color:#7d8ba1">/ SPOT</span><small id="chartSub">Velas de 1 minuto · candles fechados</small></div><div class="price-now" id="chartPrice">—</div></div><div class="chart-wrap"><canvas id="chart"></canvas></div><div class="chart-foot"><span class="legend"><span class="swatch"></span> Fechamento acima da abertura</span><span class="legend"><span class="swatch red"></span> Fechamento abaixo da abertura</span><span id="lastCandle">Último candle: —</span></div></div>
<div class="aside"><div class="signal-card"><div class="signal-top"><div class="klabel">Última decisão do motor</div><span class="pill">Sem corretora</span></div><div class="signal-state" id="action">AGUARDANDO</div><div class="reason" id="reason">Aguardando novas decisões da sessão sombra.</div><div class="reason-box" id="whyBox">Aguardando a primeira decisão.</div><div class="meta-row"><span>Posição simulada</span><strong id="position">FLAT</strong></div><div class="meta-row"><span>Última decisão (hora local)</span><strong id="lastDecision">—</strong></div><div class="meta-row"><span>Idade do estado do motor</span><strong id="decisionAge">—</strong></div><div class="meta-row"><span>Taxa / slippage por lado</span><strong id="costs">10 / 5 bps</strong></div></div><div class="card"><div class="klabel">Integridade da sessão</div><div class="model-value" id="sessionStatus">VERIFICANDO</div><div class="sub" id="sessionInfo" style="margin-top:6px">Lendo estado persistido e logs.</div><div class="warning" id="gapWarning"></div></div></div></div>
<div class="section"><div><h2>Convergência dos cinco modelos</h2><p>Valores da última decisão processada, não previsões garantidas.</p></div></div>
<div class="model-grid">
<div class="card model"><div class="model-head"><h3>01 · Fibonacci</h3><span class="status-tag wait" id="fibTag">AGUARDA</span></div><small>Nível 61,8% · reação</small><div class="model-value" id="fibVal">—</div><small id="fibNote">Sem decisão registrada</small></div>
<div class="card model"><div class="model-head"><h3>02 · Fractal</h3><span class="status-tag wait" id="fracTag">AGUARDA</span></div><small>Pai 15m × Filho 1m</small><div class="model-value" id="fracVal">—</div><small id="fracNote">Sem decisão registrada</small></div>
<div class="card model"><div class="model-head"><h3>03 · Regime</h3><span class="status-tag wait" id="regTag">AGUARDA</span></div><small>Z-score estatístico</small><div class="model-value" id="regVal">—</div><small id="regNote">Classificação do regime</small></div>
<div class="card model"><div class="model-head"><h3>04 · Energia</h3><span class="status-tag wait" id="volTag">AGUARDA</span></div><small>Volume relativo</small><div class="model-value" id="volVal">—</div><small id="volNote">Atividade negociada</small></div>
<div class="card model"><div class="model-head"><h3>05 · Momentum</h3><span class="status-tag wait" id="momTag">AGUARDA</span></div><small>Inclinação e aceleração</small><div class="model-value" id="momVal">—</div><small id="momNote">Força direcional normalizada</small></div>
</div>
<div class="section"><div><h2>O que o robô decidiu?</h2><p>Últimas decisões reais da sessão. HOLD não é falha: explica por que uma entrada foi recusada.</p></div><div class="refresh" id="signalCount">0 decisões no log</div></div>
<div class="card signal-history-card"><div class="signal-history-head"><div><h2>Diário de sinais e confirmações</h2><p>B = compra simulada · S = saída simulada · HOLD = sem entrada ou manter posição · resultado só aparece depois do fechamento.</p></div><div class="refresh">Últimas 25 decisões</div></div><div class="table-wrap" id="signalTable"><div class="empty">Aguardando registros da sessão.</div></div></div>
<div class="section"><div><h2>Histórico de operações simuladas</h2><p>Operações encerradas após custos estimados; saídas forçadas por lacuna ficam separadas da taxa de acerto da estratégia.</p></div></div>
<div class="lower"><div class="card"><div class="klabel" style="margin-bottom:8px">Últimas operações encerradas</div><div class="table-wrap" id="tradeTable"><div class="empty">Nenhuma operação encerrada nesta sessão.</div></div></div><div class="card"><div class="klabel" style="margin-bottom:8px">Eventos e observações</div><div class="table-wrap" id="eventTable"><div class="empty">Nenhum evento recente.</div></div></div></div>
<div class="footnote"><span>3 PRO · PAINEL LOCAL DE PESQUISA · SOMENTE SIMULAÇÃO</span><span>Atualização visual a cada 5s · preço e sinal têm relógios separados</span><span>Acertos/derrotas contam apenas operações fechadas pela estratégia; saída por lacuna é excluída. Não é recomendação financeira.</span></div>
</div>
<script>
const $=id=>document.getElementById(id);
const fmt=(v,d=2)=>{if(v===null||v===undefined||v===''||!Number.isFinite(Number(v)))return '—';return Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d})};
const pct=v=>v===null||v===undefined||!Number.isFinite(Number(v))?'—':fmt(Number(v)*100,2)+'%';
const priceFmt=v=>v==null?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const shortTime=s=>{if(!s)return '—';let d=new Date(s);return Number.isNaN(d.getTime())?String(s):d.toLocaleString('pt-BR',{hour12:false,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})};
const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function tag(id,yes,detail){let e=$(id);e.className='status-tag '+(yes===true?'ok':yes===false?'no':'wait');e.textContent=detail||(yes===true?'CONFIRMA':yes===false?'NÃO CONF.':'AGUARDA')}
function direction(v){if(v===1||v==='1')return 'ALTA';if(v===-1||v==='-1')return 'BAIXA';if(v===0||v==='0')return 'NEUTRO';return '—'}
function yesNo(v){return v===true?'OK':v===false?'NÃO':'—'}
function ageText(seconds){if(seconds===null||seconds===undefined||!Number.isFinite(Number(seconds)))return 'desconhecida';const n=Math.max(0,Number(seconds));if(n<60)return `${Math.round(n)} s`;if(n<3600)return `${Math.floor(n/60)} min ${Math.round(n%60)} s`;return `${Math.floor(n/3600)} h ${Math.floor((n%3600)/60)} min`}
function missingConfirmations(sig){const missing=[];if(Number(sig.parent_direction)!==1)missing.push(`Pai: contexto não está em alta (${direction(sig.parent_direction)})`);if(Number(sig.child_direction)!==1)missing.push(`Filho: direção de 1m não confirma alta (${direction(sig.child_direction)})`);if(sig.fibonacci_confirmed!==true)missing.push('Fibonacci: retração/reação de 61,8% não confirmada');if(sig.regime_acceptable!==true)missing.push('Regime: condição estatística não aceita');if(sig.volume_confirmed!==true){const rv=Number(sig.relative_volume);missing.push(`Energia: volume ${Number.isFinite(rv)?fmt(rv,2)+'×':'indisponível'}; precisa confirmar a atividade mínima`)}if(sig.momentum_confirmed!==true)missing.push('Momentum: inclinação/aceleração não confirmadas');return missing}
function reasonLabel(sig){const a=String(sig.action||'').toUpperCase(),r=String(sig.action_reason||'');if(a==='BUY_ENTRY')return 'Todas as confirmações passaram; compra apenas simulada.';if(a==='SELL_EXIT'){const m=[];if(r.includes('PAI_CONTEXT_LOST'))m.push('contexto Pai deixou de estar em alta');if(r.includes('FILHO_TREND_DOWN'))m.push('Filho virou para baixa');if(r.includes('MOMENTUM_SLOPE_NEGATIVE'))m.push('momentum ficou negativo');if(r.includes('DATA_GAP'))m.push('encerramento operacional por lacuna, não por sinal');return m.length?'Saída: '+m.join('; ')+'.':'Regra de saída ativada.'}if(a==='HOLD_POSITION')return 'Posição aberta; regra de saída ainda não confirmou.';if(a==='HOLD')return sig.position_before?'Sem saída confirmada; mantendo posição.':'Entrada não confirmada; veja abaixo quais filtros faltaram.';return r||'Sem decisão registrada.'}
function explainDecision(sig,s){const act=String(sig.action||'').toUpperCase();let message;if(!act)message='Ainda não há decisão registrada nesta sessão.';else if(act==='BUY_ENTRY')message='COMPRA SIMULADA: todos os filtros exigidos passaram. Entrada registrada na abertura seguinte, com custos estimados.';else if(act==='SELL_EXIT'){const r=String(sig.action_reason||''),parts=[];if(r.includes('PAI_CONTEXT_LOST'))parts.push('o contexto Pai deixou de estar em alta');if(r.includes('FILHO_TREND_DOWN'))parts.push('o Filho virou para baixa');if(r.includes('MOMENTUM_SLOPE_NEGATIVE'))parts.push('a inclinação do momentum ficou negativa');message='SAÍDA SIMULADA: '+(parts.length?parts.join('; '):'a regra de saída foi ativada')+'. O resultado final aparece na tabela depois da execução.';}else if(act==='HOLD_POSITION')message='MANTER POSIÇÃO: a posição já está aberta e a regra de saída ainda não foi confirmada.';else if(!Boolean(sig.position_before)){const missing=missingConfirmations(sig);message=missing.length?'SEM COMPRA porque '+missing.join('; ')+'.':'SEM COMPRA: as confirmações da entrada não foram todas atendidas.';}else message='HOLD: nenhuma mudança de posição foi solicitada.';if(!s.monitor_fresh)return 'ATENÇÃO: o último sinal é antigo; confirme se o monitor continua ativo. '+message;return message;}
function drawChart(candles,current,signals){const canvas=$('chart');const rect=canvas.getBoundingClientRect();const dpr=window.devicePixelRatio||1;canvas.width=Math.max(1,Math.floor(rect.width*dpr));canvas.height=Math.max(1,Math.floor(rect.height*dpr));const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);const w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);if(!candles||candles.length<2){ctx.fillStyle='#8b9aaf';ctx.fillText('Aguardando candles suficientes…',20,30);return}const list=candles.slice(-110);let lo=Math.min(...list.map(c=>Number(c.low))),hi=Math.max(...list.map(c=>Number(c.high)));if(current&&current>0){lo=Math.min(lo,current);hi=Math.max(hi,current)}const range=hi-lo||1;lo-=range*.06;hi+=range*.06;const left=8,right=78,top=10,bottom=26;const cw=w-left-right,ch=h-top-bottom;const y=p=>top+(hi-p)/(hi-lo)*ch;ctx.font='10px Segoe UI,Arial';ctx.strokeStyle='#202b3a';ctx.fillStyle='#8190a5';ctx.lineWidth=1;for(let i=0;i<5;i++){const yy=top+ch*i/4;ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(left+cw,yy);ctx.stroke();const p=hi-(hi-lo)*i/4;ctx.fillText(priceFmt(p),left+cw+8,yy+3)}const step=cw/list.length;const body=Math.max(2,Math.min(8,step*.62));list.forEach((c,i)=>{const x=left+step*(i+.5),o=Number(c.open),hig=Number(c.high),low=Number(c.low),cl=Number(c.close),col=cl>=o?'#20c997':'#ff6678';ctx.strokeStyle=col;ctx.fillStyle=col;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,y(hig));ctx.lineTo(x,y(low));ctx.stroke();const yy=Math.min(y(o),y(cl)),hh=Math.max(1.5,Math.abs(y(o)-y(cl)));ctx.fillRect(x-body/2,yy,body,hh)});
// BUY/EXIT markers are anchored to the next-open execution candle when present in the cache.
const visibleTimes=new Map(list.map((c,i)=>[Date.parse(c.timestamp),{i,c}]));(signals||[]).forEach(sig=>{const a=String(sig.action||'');if(a!=='BUY_ENTRY'&&a!=='SELL_EXIT')return;const stamp=Date.parse(sig.execution_timestamp_utc||'');const hit=visibleTimes.get(stamp);if(!hit)return;const x=left+step*(hit.i+.5),price=Number(sig.execution_open);if(!Number.isFinite(price))return;const yy=y(price),color=a==='BUY_ENTRY'?'#20c997':'#ff6678';ctx.save();ctx.fillStyle=color;ctx.strokeStyle=color;ctx.beginPath();if(a==='BUY_ENTRY'){ctx.moveTo(x,yy-9);ctx.lineTo(x-6,yy+2);ctx.lineTo(x+6,yy+2)}else{ctx.moveTo(x,yy+9);ctx.lineTo(x-6,yy-2);ctx.lineTo(x+6,yy-2)}ctx.closePath();ctx.fill();ctx.font='bold 9px Segoe UI,Arial';ctx.fillText(a==='BUY_ENTRY'?'B':'S',x+5,yy+(a==='BUY_ENTRY'?-7:12));ctx.restore()});
if(current&&current>lo&&current<hi){const yy=y(current);ctx.save();ctx.strokeStyle='#68a8ff';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(left+cw,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#203854';ctx.fillRect(left+cw+2,yy-9,right-5,18);ctx.fillStyle='#a4ccff';ctx.fillText(priceFmt(current),left+cw+7,yy+4);ctx.restore()}[0,Math.floor(list.length/2),list.length-1].forEach(idx=>{const c=list[idx];const x=left+step*(idx+.5);ctx.fillStyle='#7f8da2';ctx.fillText((c.timestamp||'').slice(11,16),Math.min(x-14,left+cw-35),h-7)});}
function confirmationPills(s){return `<span class="mini-confirm"><span class="${s.fibonacci_confirmed===true?'mini-y':s.fibonacci_confirmed===false?'mini-n':'mini-u'}" title="Fibonacci">FIB</span><span class="${s.regime_acceptable===true?'mini-y':s.regime_acceptable===false?'mini-n':'mini-u'}" title="Regime">REG</span><span class="${s.volume_confirmed===true?'mini-y':s.volume_confirmed===false?'mini-n':'mini-u'}" title="Energia / volume">VOL</span><span class="${s.momentum_confirmed===true?'mini-y':s.momentum_confirmed===false?'mini-n':'mini-u'}" title="Momentum">MOM</span></span>`}
function actionLabel(a){if(a==='BUY_ENTRY')return ['COMPRA','chip-buy'];if(a==='SELL_EXIT')return ['SAÍDA','chip-sell'];if(a==='HOLD_POSITION')return ['MANTER','chip-open'];return ['HOLD','chip-hold']}
function outcomeFor(sig,rows){const ts=Date.parse(String(sig.decision_timestamp_utc||''));const x=(rows||[]).find(t=>Number.isFinite(ts)&&Date.parse(String(t.timestamp||''))===ts);if(x){if(x.open)return 'ABERTA';const ret=Number(x.net_return_on_entry_equity);const v=Number.isFinite(ret)?`${ret>0?'+':''}${pct(ret)}`:'resultado indisponível';if(String(x.exit_reason||'').startsWith('DATA_GAP_'))return `LACUNA · ${v}`;return v}if(sig.action==='BUY_ENTRY'&&sig.position_after)return 'ABERTA';if(sig.action==='HOLD_POSITION')return 'EM POSIÇÃO';if(sig.action==='HOLD')return 'SEM ENTRADA';return '—'}
function tableSignals(rows,trades){if(!rows||!rows.length){$('signalTable').innerHTML='<div class="empty">Nenhuma decisão registrada ainda. O painel só mostra decisões depois do fechamento do candle de 1 minuto.</div>';$('signalCount').textContent='0 decisões no log';return}$('signalCount').textContent=`${rows.length} decisões recentes · total processado na sessão conforme contador superior`;$('signalTable').innerHTML='<table class="signal-table"><thead><tr><th>Hora local</th><th>Decisão</th><th>Pai / Filho</th><th>Filtros</th><th>Motivo registrado</th><th>Resultado da operação</th></tr></thead><tbody>'+rows.slice().reverse().map(s=>{const [label,chip]=actionLabel(String(s.action||''));const parentChild=`${direction(s.parent_direction)} / ${direction(s.child_direction)}`;const why=s.action==='HOLD'&&!s.position_before?'Entrada recusada: confirmações incompletas':s.action==='HOLD_POSITION'?'Posição mantida; saída não confirmada':s.action==='BUY_ENTRY'?'Todas as confirmações de entrada passaram':s.action==='SELL_EXIT'?'Regra de saída ativada':String(s.action_reason||'—');const outcome=outcomeFor(s,trades);const resultClass=outcome.startsWith('+')?'positive':(outcome.startsWith('-')?'negative':(outcome.startsWith('LACUNA')?'gold':''));return `<tr><td>${esc(shortTime(s.decision_timestamp_utc))}</td><td><span class="action-chip ${chip}">${label}</span></td><td>${esc(parentChild)}</td><td>${confirmationPills(s)}</td><td title="${esc(s.action_reason||'')}">${esc(why)}</td><td class="${resultClass}">${esc(outcome)}</td></tr>`}).join('')+'</tbody></table>'}
function tableTrades(rows){if(!rows||!rows.length){$('tradeTable').innerHTML='<div class="empty">Nenhuma operação encerrada nesta sessão. Sem operação encerrada, ainda não existe taxa de acerto ou derrota a calcular.</div>';return}const arr=rows.slice(-12).reverse();$('tradeTable').innerHTML='<table><thead><tr><th>Entrada</th><th>Saída</th><th class="num">Retorno líquido</th><th class="num">Duração</th><th>Classificação</th><th>Motivo de saída</th></tr></thead><tbody>'+arr.map(t=>{let n=Number(t.net_return_on_entry_equity);let forced=String(t.exit_reason||'').startsWith('DATA_GAP_');let label=forced?'ENCERRAMENTO POR LACUNA':(Number.isFinite(n)&&n>1e-12?'ACERTO':(Number.isFinite(n)&&n< -1e-12?'DERROTA':'EMPATE'));let cls=forced?'gold':(label==='ACERTO'?'positive':(label==='DERROTA'?'negative':''));return `<tr><td>${esc(shortTime(t.entry_execution_timestamp_utc))}</td><td>${esc(shortTime(t.exit_execution_timestamp_utc))}</td><td class="num ${Number.isFinite(n)&&n>=0?'positive':'negative'}">${Number.isFinite(n)?pct(n):'—'}</td><td class="num">${fmt(t.holding_minutes,0)} min</td><td class="${cls}">${label}</td><td>${esc(t.exit_reason||'—')}</td></tr>`}).join('')+'</tbody></table>'}
function tableEvents(rows){if(!rows||!rows.length){$('eventTable').innerHTML='<div class="empty">Nenhum evento recente.</div>';return}const arr=rows.slice(-7).reverse();$('eventTable').innerHTML='<table><thead><tr><th>Horário</th><th>Evento</th><th>Nota</th></tr></thead><tbody>'+arr.map(e=>`<tr><td>${esc(shortTime(e.event_timestamp_utc))}</td><td>${esc(e.event_type||'—')}</td><td>${esc(String(e.note||'—').slice(0,130))}</td></tr>`).join('')+'</tbody></table>'}
function renderHistoricalBacktest(h){
  const ids=['histGross','histNet','histTrades','histDD','histWins','histLosses','histWinRate','histExposure'];
  if(!h||!h.available){for(const id of ids)$(id).textContent='—';$('histSource').textContent='Relatório histórico não encontrado';$('histCosts').textContent='Execute o backtest histórico para gerar o relatório.';$('histTableCount').textContent='0 operações';$('historicalTradeTable').innerHTML='<div class="empty">Nenhum relatório de backtest histórico encontrado em reports/.</div>';return}
  const gross=Number(h.gross_return),net=Number(h.net_return),dd=Number(h.max_drawdown),exposure=Number(h.exposure_fraction);
  $('histGross').textContent=pct(gross);$('histGross').className='big '+(gross>0?'positive':gross<0?'negative':'');
  $('histNet').textContent=pct(net);$('histNet').className='big '+(net>0?'positive':net<0?'negative':'');
  $('histTrades').textContent=fmt(h.trade_count||0,0);$('histDD').textContent=pct(dd);$('histDD').className='big '+(dd<0?'negative':'');
  $('histWins').textContent=fmt(h.wins||0,0);$('histLosses').textContent=fmt(h.losses||0,0);$('histBreakeven').textContent=`Empates: ${fmt(h.breakeven||0,0)}`;
  $('histWinRate').textContent=h.win_rate==null?'—':pct(h.win_rate);$('histExposure').textContent=pct(exposure);
  $('histCosts').textContent=`Taxa ${fmt(h.fee_bps_per_side,0)} + slippage ${fmt(h.slippage_bps_per_side,0)} bps por lado`;
  $('histTradeSpan').textContent=`${fmt(h.rows_backtested||0,0)} intervalos · ${h.input_hash_matches?'hash de entrada confere':'ATENÇÃO: hash diferente'}`;
  $('histInputInfo').textContent=`Fonte: ${h.summary_file||'relatório local'} · ${h.input_hash_matches?'histórico identificado':'verificar origem'}`;
  $('histSource').textContent=`${h.symbol||'BTCUSDT'} · ${h.summary_file||'relatório local'} · ${h.input_hash_matches?'relatório identificado':'verificar origem'}`;
  $('histDisclaimer').textContent=`Status: ${h.status||'EXPLORATORY_NOT_VALIDATED'}. Retorno bruto ${pct(gross)}; líquido ${pct(net)}. A taxa de acerto usa o retorno composto por operação com custos de entrada e saída alocados. Este backtest é separado da sessão sombra e não prova rentabilidade futura.`;
  const rows=h.trades||[];$('histTableCount').textContent=`${rows.length} operações recentes de ${fmt(h.trade_count||0,0)}`;
  if(!rows.length){$('historicalTradeTable').innerHTML='<div class="empty">O relatório existe, mas não foi possível reconstruir as operações encerradas.</div>';return}
  $('historicalTradeTable').innerHTML='<table><thead><tr><th>Entrada (local)</th><th>Saída (local)</th><th class="num">Duração</th><th class="num">Retorno bruto</th><th class="num">Retorno líquido</th><th>Resultado</th></tr></thead><tbody>'+rows.slice().reverse().map(t=>{const n=Number(t.net_return),g=Number(t.gross_return);const label=n>1e-12?'ACERTO':n< -1e-12?'DERROTA':'EMPATE';const cls=label==='ACERTO'?'positive':label==='DERROTA'?'negative':'';return `<tr><td>${esc(shortTime(t.entry_timestamp_utc))}</td><td>${esc(shortTime(t.exit_timestamp_utc))}</td><td class="num">${fmt(t.holding_bars,0)} min</td><td class="num ${g>=0?'positive':'negative'}">${pct(g)}</td><td class="num ${n>=0?'positive':'negative'}">${pct(n)}</td><td class="${cls}">${label}</td></tr>`}).join('')+'</tbody></table>';
}
function render(d){const s=d.session||{},m=d.market||{},sig=d.latest_signal||{},stats=d.trade_stats||{};const p=m.last_price;$('price').textContent=p?priceFmt(p):'—';$('chartPrice').textContent=p?priceFmt(p):'—';$('change').textContent=m.price_change_percent_24h==null?'Cotação pública':`${fmt(m.price_change_percent_24h,2)}% nas últimas 24h`; $('change').className='sub '+(Number(m.price_change_percent_24h)>=0?'positive':'negative');$('equity').textContent=fmt(s.marked_equity??s.equity,6);$('equitySub').textContent=s.open_position_unrealized_display_only?'Marcado pelo último preço · informativo':'Capital inicial normalizado = 1,00';const dd=Number(s.max_drawdown||0);$('drawdown').textContent=pct(dd);$('drawdown').className='big '+(dd<0?'negative':'');$('trades').textContent=fmt(stats.strategy_trades??0,0);$('decisions').textContent=`${fmt(s.decisions_processed||0,0)} decisões processadas`;const mktOk=!!m.last_price;const engineFresh=!!s.monitor_fresh;$('connection').textContent=!mktOk?'Preço público indisponível':(engineFresh?'Mercado conectado · motor atualizado':'Mercado conectado · motor desatualizado');$('dot').style.background=mktOk&&engineFresh?'#20c997':'#efc36a';$('dot').style.boxShadow=mktOk&&engineFresh?'0 0 12px #20c99788':'none';$('updated').textContent='Painel atualizado '+shortTime(d.generated_at_utc);$('sessionStatus').textContent=!engineFresh?'MOTOR SEM ATUALIZAÇÃO':(s.data_gap_count?'MONITOR ATIVO · COM LACUNAS':'MONITOR ATUALIZADO');$('sessionStatus').className='model-value '+(!engineFresh||s.data_gap_count?'gold':'positive');$('sessionInfo').textContent=`Sessão iniciada ${shortTime(s.started_at_utc)} · último heartbeat ${shortTime(s.updated_at_utc)} · há ${ageText(s.monitor_age_seconds)} · ${s.symbol||'BTCUSDT'}`;$('position').textContent=s.position_open?'COMPRADO':'FLAT';$('position').className=s.position_open?'positive':'';$('lastDecision').textContent=shortTime(s.last_decision_timestamp_utc);$('decisionAge').textContent=ageText(s.monitor_age_seconds);$('costs').textContent=`${fmt(s.fee_bps_per_side,0)} / ${fmt(s.slippage_bps_per_side,0)} bps`;
$('wins').textContent=fmt(stats.wins||0,0);$('losses').textContent=fmt(stats.losses||0,0);$('winRate').textContent=stats.win_rate===null||stats.win_rate===undefined?'—':pct(stats.win_rate);$('winsSub').textContent=`De ${fmt(stats.strategy_trades||0,0)} saídas da estratégia`; $('lossesSub').textContent=`Empates: ${fmt(stats.breakeven||0,0)} · forçadas por lacuna: ${fmt(stats.gap_forced_closes||0,0)}`;$('winRateSub').textContent=stats.strategy_trades?`${fmt(stats.wins||0,0)} acertos em ${fmt(stats.strategy_trades,0)} operações elegíveis`:'Sem amostra: nenhuma operação da estratégia encerrada';const sr=Number(s.marked_equity??s.equity??1)-1;$('sessionReturn').textContent=pct(sr);$('sessionReturn').className='big '+(sr>0?'positive':sr<0?'negative':'');$('sessionReturnSub').textContent=s.open_position_unrealized_display_only?'Inclui marcação informativa da posição aberta':'Retorno do patrimônio virtual desde 1,00 inicial';
const warn=$('gapWarning');if(!engineFresh||(s.data_gap_count||0)>0||s.max_drawdown_is_lower_bound_due_to_gap){warn.style.display='block';warn.textContent=`${!engineFresh?'O heartbeat do motor está atrasado ('+ageText(s.monitor_age_seconds)+'). O preço pode estar ao vivo enquanto os sinais estão antigos. ':''}${(s.data_gap_count||0)>0?`Sessão com ${s.data_gap_count||0} lacuna(s), ${s.missed_decision_bars||0} candles de decisão perdidos. Fills retroativos não foram inventados; drawdown pode estar subestimado.`:''}`}else{warn.style.display='none'}
const act=String(sig.action||'AGUARDANDO').toUpperCase();$('action').textContent=act.replaceAll('_',' ');$('action').className='signal-state '+(act.includes('BUY')?'positive':(act.includes('SELL')||act.includes('EXIT')?'negative':''));$('reason').textContent=reasonLabel(sig);$('whyBox').textContent=explainDecision(sig,s);tag('fibTag',sig.fibonacci_confirmed===true,sig.fibonacci_confirmed===true?'CONFIRMA':sig.fibonacci_confirmed===false?'NÃO CONF.':'AGUARDA');$('fibVal').textContent=sig.fib_618!=null?priceFmt(sig.fib_618):'—';$('fibNote').textContent=sig.fib_618!=null?'Nível de retração observado':'Sem nível nesta decisão';tag('fracTag',sig.parent_direction!=null&&sig.child_direction!=null&&Number(sig.parent_direction)===Number(sig.child_direction)&&Number(sig.parent_direction)!==0,sig.parent_direction==null?'AGUARDA':`${direction(sig.parent_direction)} / ${direction(sig.child_direction)}`);$('fracVal').textContent=`${direction(sig.parent_direction)} · ${direction(sig.child_direction)}`;$('fracNote').textContent='Pai 15m / Filho 1m';tag('regTag',sig.regime_acceptable===true,sig.regime_acceptable===true?'ACEITÁVEL':sig.regime_acceptable===false?'REJEITADO':'AGUARDA');$('regVal').textContent=sig.regime_zscore==null?'—':fmt(sig.regime_zscore,2);$('regNote').textContent='Z-score da última decisão';tag('volTag',sig.volume_confirmed===true,sig.volume_confirmed===true?'CONFIRMA':sig.volume_confirmed===false?'NÃO CONF.':'AGUARDA');$('volVal').textContent=sig.relative_volume==null?'—':`${fmt(sig.relative_volume,2)}×`;$('volNote').textContent='Volume relativo; verificar regra mínima na estratégia';tag('momTag',sig.momentum_confirmed===true,sig.momentum_confirmed===true?'CONFIRMA':sig.momentum_confirmed===false?'NÃO CONF.':'AGUARDA');$('momVal').textContent=sig.normalized_slope==null?'—':fmt(sig.normalized_slope,3);$('momNote').textContent=`Inclinação · acel. ${sig.normalized_acceleration==null?'—':fmt(sig.normalized_acceleration,3)}`;
$('lastCandle').textContent='Último candle fechado: '+shortTime((d.candles||[]).length?d.candles[d.candles.length-1].timestamp:null)+' · hora local';drawChart(d.candles||[],p,d.signals||[]);tableSignals(d.signals||[],d.signal_outcomes||[]);tableTrades(d.trades||[]);tableEvents(d.events||[]);renderHistoricalBacktest(d.historical_backtest||{})}
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


def read_csv_records(path: Path) -> list[dict]:
    """Read all records from a small append-only execution log (e.g. closed trades)."""
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def canonical_timestamp(value: Any) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return str(value)


def calculate_trade_stats(trade_rows: list[dict]) -> dict:
    """Count only strategy exits for win rate; operational gap exits are reported separately."""
    wins, losses, breakeven, forced = 0, 0, 0, 0
    win_returns: list[float] = []
    loss_returns: list[float] = []
    eligible_returns: list[float] = []
    for row in trade_rows:
        reason = str(row.get("exit_reason") or "")
        try:
            ret = float(row.get("net_return_on_entry_equity"))
            if not math.isfinite(ret):
                continue
        except (TypeError, ValueError):
            continue
        if reason.startswith("DATA_GAP_"):
            forced += 1
            continue
        eligible_returns.append(ret)
        if ret > 1e-12:
            wins += 1
            win_returns.append(ret)
        elif ret < -1e-12:
            losses += 1
            loss_returns.append(ret)
        else:
            breakeven += 1
    total = len(eligible_returns)
    return {
        "strategy_trades": total,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate": (wins / total) if total else None,
        "gap_forced_closes": forced,
        "average_win_return": (sum(win_returns) / len(win_returns)) if win_returns else None,
        "average_loss_return": (sum(loss_returns) / len(loss_returns)) if loss_returns else None,
        "average_strategy_trade_return": (sum(eligible_returns) / total) if total else None,
    }


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


def latest_report_file(folder: Path, pattern: str) -> Path | None:
    matches = [p for p in folder.glob(pattern) if p.is_file()]
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def _safe_num(row: dict, key: str, default: float = 0.0) -> float:
    try:
        value = float(row.get(key, default))
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def historical_backtest_report(root: Path) -> dict:
    """Load the baseline historical backtest report and reconstruct round trips."""
    reports = root / "reports"
    summary_path = latest_report_file(reports, "backtest_summary_BTCUSDT_1m_*.json")
    if not summary_path:
        return {"available": False, "message": "Nenhum backtest_summary_BTCUSDT_1m_*.json encontrado."}
    summary = read_json(summary_path)
    result_path = Path(str(summary.get("backtest_csv") or ""))
    if not result_path.is_file():
        result_path = latest_report_file(reports, "backtest_BTCUSDT_1m_*.csv")
    if not result_path or not result_path.is_file():
        return {"available": False, "message": "O resumo existe, mas o CSV de resultados não foi encontrado.", "summary_file": summary_path.name}
    try:
        rows = read_csv_records(result_path)
        required = {"timestamp", "position", "gross_return", "net_return", "costs"}
        if not rows or not required.issubset(set(rows[0])):
            return {"available": False, "message": "CSV histórico vazio ou com colunas ausentes.", "summary_file": summary_path.name, "result_file": result_path.name}
        positions = [_safe_num(r, "position") > 0.5 for r in rows]
        starts = [i for i, p in enumerate(positions) if p and (i == 0 or not positions[i - 1])]
        ends = [i for i, p in enumerate(positions) if p and (i == len(positions) - 1 or not positions[i + 1])]
        if len(starts) != len(ends):
            return {"available": False, "message": "Entradas e saídas não formam pares completos no CSV histórico.", "summary_file": summary_path.name, "result_file": result_path.name}
        trades = []
        for s, e in zip(starts, ends):
            gross_factor = math.prod(1.0 + _safe_num(r, "gross_return") for r in rows[s:e + 1])
            lo = max(s - 1, 0)  # includes the entry cost posted on the prior return interval
            net_factor = math.prod(1.0 + _safe_num(r, "net_return") for r in rows[lo:e + 1])
            cost_sum = sum(_safe_num(r, "costs") for r in rows[lo:e + 1])
            exit_idx = min(e + 1, len(rows) - 1)
            trades.append({
                "entry_timestamp_utc": rows[s].get("timestamp", ""),
                "exit_timestamp_utc": rows[exit_idx].get("timestamp", ""),
                "holding_bars": e - s + 1,
                "gross_return": gross_factor - 1.0,
                "net_return": net_factor - 1.0,
                "allocated_cost_sum": cost_sum,
            })
        trade_returns = [t["net_return"] for t in trades]
        wins = sum(x > 1e-12 for x in trade_returns)
        losses = sum(x < -1e-12 for x in trade_returns)
        breakeven = len(trade_returns) - wins - losses
        gross = math.prod(1.0 + _safe_num(r, "gross_return") for r in rows) - 1.0
        net = math.prod(1.0 + _safe_num(r, "net_return") for r in rows) - 1.0
        eq = 1.0
        peak = 1.0
        max_dd = 0.0
        for row in rows:
            eq *= 1.0 + _safe_num(row, "net_return")
            peak = max(peak, eq)
            if peak > 0:
                max_dd = min(max_dd, eq / peak - 1.0)
        source_csv = root / "data" / "raw" / "BTCUSDT_1m.csv"
        actual_hash = ""
        if source_csv.is_file():
            import hashlib
            actual_hash = hashlib.sha256(source_csv.read_bytes()).hexdigest().lower()
        expected_hash = str(summary.get("input_sha256") or "").lower()
        hash_matches = bool(actual_hash and expected_hash and actual_hash == expected_hash)
        # Only the most recent 25 closed historical trades are sent to the page.
        return {
            "available": True,
            "validated": False,
            "status": summary.get("status", "EXPLORATORY_NOT_VALIDATED"),
            "symbol": summary.get("symbol", "BTCUSDT"),
            "timeframe": summary.get("timeframe", "1m"),
            "summary_file": summary_path.name,
            "result_file": result_path.name,
            "rows_backtested": int(summary.get("rows_backtested", len(rows)) or len(rows)),
            "input_hash_matches": hash_matches,
            "expected_input_sha256": expected_hash,
            "actual_input_sha256": actual_hash,
            "gross_return": gross,
            "net_return": net,
            "max_drawdown": max_dd,
            "exposure_fraction": (sum(positions) / len(positions)) if positions else 0.0,
            "trade_count": len(trades),
            "wins": wins,
            "losses": losses,
            "breakeven": breakeven,
            "win_rate": wins / len(trades) if trades else None,
            "fee_bps_per_side": _safe_num(summary, "fee_bps_per_side"),
            "slippage_bps_per_side": _safe_num(summary, "slippage_bps_per_side"),
            "buy_and_hold_return_net_estimate": finite_float(summary.get("buy_and_hold_return_net_estimate")),
            "trades": trades[-25:],
        }
    except (OSError, csv.Error, ValueError, OverflowError) as exc:
        return {"available": False, "message": f"Falha ao ler backtest histórico: {type(exc).__name__}: {exc}", "summary_file": summary_path.name}


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
        # Historical backtest files are immutable during dashboard use; load once
        # instead of rereading/recomputing 129k bars every five-second refresh.
        self._historical_backtest = historical_backtest_report(self.root)

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
        # Show the recent decision tape, but calculate win/loss statistics from the full closed-trade ledger.
        signals_raw = read_csv_tail(self.session / "shadow_signals.csv", max_rows=25, max_bytes=1048576)
        trade_rows_all = read_csv_records(self.session / "shadow_trades.csv")
        trades_raw = trade_rows_all[-12:]
        events_raw = read_csv_tail(self.session / "shadow_events.csv", max_rows=10, max_bytes=262144)
        candles = read_csv_tail(self.cache_path, max_rows=180, max_bytes=524288)
        candles_clean = []
        for row in candles:
            item = clean_row(row, {"open", "high", "low", "close", "volume", "quote_volume", "trades"})
            if all(item.get(k) is not None for k in ("open", "high", "low", "close")):
                candles_clean.append(item)
        signals_clean = [clean_row(row, SIGNAL_NUMERIC) for row in signals_raw]
        latest_signal = signals_clean[-1] if signals_clean else {}
        trades_clean = [clean_row(row, TRADE_NUMERIC) for row in trades_raw]
        events_clean = [clean_row(row, EVENT_NUMERIC) for row in events_raw]
        stats = calculate_trade_stats(trade_rows_all)
        outcomes: dict[str, dict] = {}
        for trade in trade_rows_all:
            reason = str(trade.get("exit_reason") or "")
            try:
                ret = float(trade.get("net_return_on_entry_equity"))
                if not math.isfinite(ret):
                    ret = None
            except (TypeError, ValueError):
                ret = None
            item = {"net_return_on_entry_equity": ret, "exit_reason": reason}
            entry_key = canonical_timestamp(trade.get("entry_signal_timestamp_utc"))
            exit_key = canonical_timestamp(trade.get("exit_signal_timestamp_utc"))
            if entry_key:
                outcomes[entry_key] = item
            if exit_key:
                outcomes[exit_key] = item
        state_open_trade = state.get("open_trade") if isinstance(state.get("open_trade"), dict) else None
        open_entry_key = canonical_timestamp(state_open_trade.get("entry_signal_timestamp_utc")) if state_open_trade else ""
        signal_outcomes = []
        for signal in signals_clean:
            decision_key = canonical_timestamp(signal.get("decision_timestamp_utc"))
            outcome = outcomes.get(decision_key)
            if outcome:
                signal_outcomes.append({"timestamp": signal.get("decision_timestamp_utc"), **outcome})
            elif open_entry_key and decision_key == open_entry_key:
                signal_outcomes.append({"timestamp": signal.get("decision_timestamp_utc"), "open": True})
        mkt = self.market()
        fallback_close = finite_float(candles_clean[-1].get("close")) if candles_clean else None
        if mkt.get("last_price") is None:
            mkt["last_price"] = fallback_close
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
            "signals": signals_clean,
            "signal_outcomes": signal_outcomes,
            "trades": trades_clean,
            "trade_stats": stats,
            "events": events_clean,
            "historical_backtest": self._historical_backtest,
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
        with (session / "shadow_signals.csv").open("a", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["2026-10-21T03:20:00+00:00", "2026-10-21T03:21:00+00:00", "101", "HOLD", "ENTRY_CONFIRMATIONS_NOT_ALL_MET", "False", "False", "0", "1", "100", "False", "-0.1", "True", "0.48", "False", "0.447", "0.418", "True", "False", "False", "1.0", "10", "5"])
        (session / "shadow_trades.csv").write_text(
            "entry_signal_timestamp_utc,entry_execution_timestamp_utc,entry_price,exit_signal_timestamp_utc,exit_execution_timestamp_utc,exit_price,holding_minutes,gross_price_return,net_return_on_entry_equity,entry_equity_before_cost,equity_after_exit,fee_bps_per_side,slippage_bps_per_side,exit_reason\n"
            "2026-10-21T03:00:00+00:00,2026-10-21T03:01:00+00:00,100,2026-10-21T03:10:00+00:00,2026-10-21T03:11:00+00:00,101,10,0.01,0.006,1,1.006,10,5,MOMENTUM_SLOPE_NEGATIVE\n",
            encoding="utf-8",
        )
        provider = SnapshotProvider(root, session, "BTCUSDT")
        provider.market = lambda: {"last_price": 101.0, "price_change_percent_24h": 1.0, "source": "self-test"}
        snap = provider.snapshot()
        assert snap["session"]["orders_sent"] == 0
        assert len(snap["candles"]) == 1 and snap["market"]["last_price"] == 101.0
        assert snap["session"]["position_open"] is False
        assert len(snap["signals"]) == 1 and snap["latest_signal"]["action"] == "HOLD"
        assert snap["trade_stats"]["wins"] == 1 and snap["trade_stats"]["losses"] == 0
        assert snap["trade_stats"]["win_rate"] == 1.0
    assert calculate_trade_stats([{"exit_reason": "DATA_GAP_FORCED_EXIT_NOT_STRATEGY_SIGNAL", "net_return_on_entry_equity": "-0.2"}])["strategy_trades"] == 0
    print("SELF-TEST PASSED: recent decisions, trade win/loss stats, CSV tail header, candles and no-order status.")


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
    parser.add_argument("--port", type=int, default=8766)
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
    print("PAINEL 3 PRO V3 — BACKTEST HISTÓRICO + SESSÃO SOMBRA")
    print("URL:", url)
    print("Sessao observada:", session)
    print("Modo: somente leitura + cotacao publica. Nenhuma ordem real pode ser enviada.")
    print("Atualizacao visual: 5s; histórico do backtest separado do diário sombra.")
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
