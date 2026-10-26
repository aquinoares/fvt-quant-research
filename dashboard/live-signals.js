'use strict';

(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.FVTLiveSignals = api;
  if (typeof document !== 'undefined') api.boot();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  var CANDLE_MS = 4 * 60 * 60 * 1000;
  var LOOKBACK_A = 20;
  var LOOKBACK_B = 96;
  var THRESHOLD_B = 0.005;
  var COST_BPS_PER_SIDE = 15;
  var MAX_CANDLES = 2500;
  var STORE_KEY = 'fvt-live-signals-v1';
  var SVG_NS = 'http://www.w3.org/2000/svg';

  function finite(value) {
    return typeof value === 'number' && Number.isFinite(value);
  }

  function number(value) {
    var parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function validCandle(candle) {
    return Boolean(candle && finite(candle.t) && finite(candle.o) &&
      finite(candle.h) && finite(candle.l) && finite(candle.c) &&
      candle.t >= 0 && candle.o > 0 && candle.h > 0 &&
      candle.l > 0 && candle.c > 0);
  }

  function normalizeRestKline(row) {
    if (!Array.isArray(row) || row.length < 7) return null;
    var candle = {
      t: number(row[0]),
      o: number(row[1]),
      h: number(row[2]),
      l: number(row[3]),
      c: number(row[4]),
      v: number(row[5]),
      closeTime: number(row[6]),
      closed: false
    };
    return validCandle(candle) && finite(candle.closeTime) ? candle : null;
  }

  function normalizeStreamKline(kline) {
    if (!kline || typeof kline !== 'object') return null;
    var candle = {
      t: number(kline.t),
      o: number(kline.o),
      h: number(kline.h),
      l: number(kline.l),
      c: number(kline.c),
      v: number(kline.v),
      closeTime: number(kline.T),
      closed: kline.x === true
    };
    return validCandle(candle) && finite(candle.closeTime) ? candle : null;
  }

  function mergeCandles(existing, incoming, limit) {
    var byTime = new Map();
    (Array.isArray(existing) ? existing : []).forEach(function (candle) {
      if (validCandle(candle)) byTime.set(candle.t, candle);
    });
    (Array.isArray(incoming) ? incoming : []).forEach(function (candle) {
      if (validCandle(candle)) byTime.set(candle.t, candle);
    });
    var merged = Array.from(byTime.values()).sort(function (a, b) { return a.t - b.t; });
    var maxItems = Number.isInteger(limit) && limit > 0 ? limit : MAX_CANDLES;
    return merged.length > maxItems ? merged.slice(merged.length - maxItems) : merged;
  }

  function continuous(candles, start, end) {
    if (start < 0 || end >= candles.length || start > end) return false;
    for (var index = start + 1; index <= end; index += 1) {
      if (candles[index].t - candles[index - 1].t !== CANDLE_MS) return false;
    }
    return true;
  }

  function targetAtOpen(candles, index, lane) {
    if (!Array.isArray(candles) || index < 1 || index >= candles.length) return null;
    var previous = candles[index - 1];
    if (!validCandle(previous)) return null;

    if (lane === 'A') {
      if (index < LOOKBACK_A || !continuous(candles, index - LOOKBACK_A, index)) return null;
      var closes = candles.slice(index - LOOKBACK_A, index).map(function (candle) { return candle.c; });
      var average = closes.reduce(function (sum, close) { return sum + close; }, 0) / LOOKBACK_A;
      return previous.c > average ? 1 : 0;
    }

    if (lane === 'B') {
      var start = index - LOOKBACK_B - 1;
      if (index < LOOKBACK_B + 1 || !continuous(candles, start, index)) return null;
      var referenceClose = candles[start].c;
      if (!(referenceClose > 0)) return null;
      var roc = previous.c / referenceClose - 1;
      return roc > THRESHOLD_B ? 1 : 0;
    }

    throw new Error('Faixa inválida; use A ou B.');
  }

  function eventKey(event) {
    return event.lane + '|' + String(event.timestamp) + '|' + event.action;
  }

  function tradeReturnPct(entryPrice, exitPrice) {
    if (!(entryPrice > 0) || !(exitPrice > 0)) return null;
    return ((exitPrice / entryPrice) - 1) * 100 - (2 * COST_BPS_PER_SIDE / 100);
  }

  function simulateLane(candles, lane) {
    var events = [];
    var trades = [];
    var inPosition = false;
    var activeTrade = null;

    for (var index = 1; index < candles.length; index += 1) {
      var desired = targetAtOpen(candles, index, lane);
      if (desired === null) continue;
      if (desired === (inPosition ? 1 : 0)) continue;

      var candle = candles[index];
      if (desired === 1) {
        activeTrade = {
          lane: lane,
          entryTime: candle.t,
          entryPrice: candle.o,
          exitTime: null,
          exitPrice: null,
          netReturnPct: null,
          result: 'OPEN'
        };
        events.push({
          lane: lane,
          timestamp: candle.t,
          action: 'BUY',
          price: candle.o,
          netReturnPct: null,
          result: 'OPEN',
          tradeEntryTime: candle.t
        });
        inPosition = true;
      } else if (activeTrade) {
        var net = tradeReturnPct(activeTrade.entryPrice, candle.o);
        var outcome = net === null ? 'UNKNOWN' : net > 0.0000001 ? 'WIN' : net < -0.0000001 ? 'LOSS' : 'FLAT';
        var completed = {
          lane: lane,
          entryTime: activeTrade.entryTime,
          entryPrice: activeTrade.entryPrice,
          exitTime: candle.t,
          exitPrice: candle.o,
          netReturnPct: net,
          result: outcome
        };
        trades.push(completed);
        events.push({
          lane: lane,
          timestamp: candle.t,
          action: 'EXIT',
          price: candle.o,
          netReturnPct: net,
          result: outcome,
          tradeEntryTime: activeTrade.entryTime
        });
        activeTrade = null;
        inPosition = false;
      } else {
        inPosition = false;
      }
    }

    var wins = trades.filter(function (trade) { return trade.result === 'WIN'; }).length;
    var losses = trades.filter(function (trade) { return trade.result === 'LOSS'; }).length;
    var flats = trades.filter(function (trade) { return trade.result === 'FLAT'; }).length;

    return {
      lane: lane,
      events: events,
      trades: trades,
      signalCount: events.length,
      entryCount: events.filter(function (event) { return event.action === 'BUY'; }).length,
      exitCount: events.filter(function (event) { return event.action === 'EXIT'; }).length,
      wins: wins,
      losses: losses,
      flats: flats,
      openTrade: activeTrade
    };
  }

  function summarizeLiveEvents(events, lane) {
    var filtered = (Array.isArray(events) ? events : []).filter(function (event) {
      return event && event.lane === lane;
    });
    var exits = filtered.filter(function (event) { return event.action === 'EXIT'; });
    return {
      signals: filtered.length,
      entries: filtered.filter(function (event) { return event.action === 'BUY'; }).length,
      exits: exits.length,
      wins: exits.filter(function (event) { return event.result === 'WIN'; }).length,
      losses: exits.filter(function (event) { return event.result === 'LOSS'; }).length,
      flats: exits.filter(function (event) { return event.result === 'FLAT'; }).length
    };
  }

  function countGaps(candles) {
    var gaps = 0;
    for (var index = 1; index < candles.length; index += 1) {
      var delta = candles[index].t - candles[index - 1].t;
      if (delta > CANDLE_MS && delta % CANDLE_MS === 0) gaps += (delta / CANDLE_MS) - 1;
    }
    return gaps;
  }

  function readStore() {
    var empty = { candles: [], liveEvents: [] };
    try {
      var raw = window.localStorage.getItem(STORE_KEY);
      if (!raw) return empty;
      var parsed = JSON.parse(raw);
      return {
        candles: Array.isArray(parsed.candles) ? parsed.candles.filter(validCandle).slice(-MAX_CANDLES) : [],
        liveEvents: Array.isArray(parsed.liveEvents) ? parsed.liveEvents.slice(-5000) : []
      };
    } catch (error) {
      return empty;
    }
  }

  function saveStore(context) {
    try {
      window.localStorage.setItem(STORE_KEY, JSON.stringify({
        candles: context.closedCandles.slice(-MAX_CANDLES),
        liveEvents: context.liveEvents.slice(-5000)
      }));
    } catch (error) {
      setText('liveStatusHint', 'Armazenamento local indisponível; contadores ao vivo podem não persistir neste navegador.');
    }
  }

  function setText(id, value) {
    var element = document.getElementById(id);
    if (element) element.textContent = value;
  }

  function fmtPrice(value) {
    if (!finite(value)) return '—';
    return value.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtPct(value) {
    if (!finite(value)) return '—';
    return (value > 0 ? '+' : '') + value.toFixed(2).replace('.', ',') + '%';
  }

  function fmtCount(value) {
    return Number(value || 0).toLocaleString('pt-BR');
  }

  function fmtTime(value) {
    if (!finite(value)) return '—';
    return new Date(value).toLocaleString('pt-BR', {
      timeZone: 'America/Sao_Paulo',
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  }

  function createSvg(tag, attributes) {
    var element = document.createElementNS(SVG_NS, tag);
    Object.keys(attributes || {}).forEach(function (key) {
      element.setAttribute(key, String(attributes[key]));
    });
    return element;
  }

  function boot() {
    if (!document.getElementById('liveSignals')) return;

    var stored = readStore();
    var context = {
      closedCandles: mergeCandles([], stored.candles, MAX_CANDLES),
      currentCandle: null,
      bars: [],
      liveEvents: stored.liveEvents.filter(function (event) {
        return event && (event.lane === 'A' || event.lane === 'B') &&
          finite(event.timestamp) && (event.action === 'BUY' || event.action === 'EXIT');
      }),
      seenEventKeys: new Set(),
      initialCurrentStart: Math.floor(Date.now() / CANDLE_MS) * CANDLE_MS,
      initialized: false,
      simulations: {},
      price: null,
      priceTimestamp: null,
      lastPricePaint: 0,
      socket: null,
      retryCount: 0,
      retryTimer: null,
      closedBarsReceived: 0,
      restError: null
    };

    function modelBars() {
      return mergeCandles(context.closedCandles, context.currentCandle ? [context.currentCandle] : [], MAX_CANDLES);
    }

    function persistClosed(candle) {
      if (!validCandle(candle)) return;
      var closed = Object.assign({}, candle, { closed: true });
      context.closedCandles = mergeCandles(context.closedCandles, [closed], MAX_CANDLES);
      context.closedBarsReceived += 1;
      saveStore(context);
    }

    function calculate() {
      context.bars = modelBars();
      context.simulations = {
        A: simulateLane(context.bars, 'A'),
        B: simulateLane(context.bars, 'B')
      };
      if (context.initialized) {
        ['A', 'B'].forEach(function (lane) {
          context.simulations[lane].events.forEach(function (event) {
            var key = eventKey(event);
            if (context.seenEventKeys.has(key)) return;
            context.seenEventKeys.add(key);
            if (event.timestamp >= context.initialCurrentStart) {
              context.liveEvents.push({
                lane: event.lane,
                timestamp: event.timestamp,
                action: event.action,
                price: event.price,
                netReturnPct: event.netReturnPct,
                result: event.result,
                tradeEntryTime: event.tradeEntryTime
              });
            }
          });
        });
        context.liveEvents = context.liveEvents.filter(function (event, index, array) {
          return array.findIndex(function (other) { return eventKey(other) === eventKey(event); }) === index;
        }).slice(-5000);
        saveStore(context);
      }
      renderAll();
    }

    function allEvents() {
      var byKey = new Map();
      Object.keys(context.simulations).forEach(function (lane) {
        context.simulations[lane].events.forEach(function (event) { byKey.set(eventKey(event), event); });
      });
      context.liveEvents.forEach(function (event) { byKey.set(eventKey(event), event); });
      return Array.from(byKey.values()).sort(function (a, b) {
        if (a.timestamp !== b.timestamp) return b.timestamp - a.timestamp;
        return a.lane.localeCompare(b.lane);
      });
    }

    function renderLane(lane) {
      var simulation = context.simulations[lane];
      var live = summarizeLiveEvents(context.liveEvents, lane);
      var prefix = 'live' + lane;
      if (!simulation) return;

      setText(prefix + 'Signals', fmtCount(simulation.signalCount));
      setText(prefix + 'Wins', fmtCount(simulation.wins));
      setText(prefix + 'Losses', fmtCount(simulation.losses));
      setText(prefix + 'State', simulation.openTrade
        ? 'COMPRADO · desde ' + fmtTime(simulation.openTrade.entryTime)
        : 'FORA · sem posição aberta');

      var pnl = null;
      if (simulation.openTrade && finite(context.price)) {
        pnl = ((context.price / simulation.openTrade.entryPrice) - 1) * 100 - (2 * COST_BPS_PER_SIDE / 100);
      }
      var pnlElement = document.getElementById(prefix + 'OpenPnl');
      if (pnlElement) {
        pnlElement.textContent = simulation.openTrade
          ? fmtPct(pnl) + ' · não realizado'
          : '0,00% · fora do mercado';
        pnlElement.classList.toggle('value-green', finite(pnl) && pnl > 0);
        pnlElement.classList.toggle('value-red', finite(pnl) && pnl < 0);
      }

      setText(prefix + 'LiveCount', fmtCount(live.signals) + ' sinais · ' + fmtCount(live.entries) + ' BUY / ' + fmtCount(live.exits) + ' EXIT');
      setText(prefix + 'LiveWins', fmtCount(live.wins));
      setText(prefix + 'LiveLosses', fmtCount(live.losses));
    }

    function renderTable(events) {
      var body = document.getElementById('liveSignalRows');
      if (!body) return;
      body.textContent = '';
      if (!events.length) {
        var emptyRow = document.createElement('tr');
        var emptyCell = document.createElement('td');
        emptyCell.colSpan = 7;
        emptyCell.textContent = 'Nenhum sinal nesta janela; aguardando candles suficientes e uma mudança de estado da estratégia.';
        emptyRow.appendChild(emptyCell);
        body.appendChild(emptyRow);
        return;
      }
      var liveKeys = new Set(context.liveEvents.map(eventKey));
      events.slice(0, 24).forEach(function (event) {
        var row = document.createElement('tr');
        var cells = [
          fmtTime(event.timestamp),
          event.lane === 'A' ? 'A · SMA-20' : 'B · P6-MOM',
          event.action === 'BUY' ? 'BUY' : 'EXIT',
          fmtPrice(event.price),
          liveKeys.has(eventKey(event)) ? 'AO VIVO' : 'HISTÓRICO',
          event.action === 'EXIT' ? event.result : 'ABERTA',
          event.action === 'EXIT' ? fmtPct(event.netReturnPct) : '—'
        ];
        cells.forEach(function (value, index) {
          var cell = document.createElement('td');
          cell.textContent = value;
          if (index === 3 || index === 6) cell.className = 'num';
          row.appendChild(cell);
        });
        row.className = event.action === 'BUY' ? 'live-row-buy' : 'live-row-exit';
        body.appendChild(row);
      });
    }

    function drawChart() {
      var svg = document.getElementById('liveSignalChart');
      if (!svg) return;
      while (svg.firstChild) svg.removeChild(svg.firstChild);

      var bars = context.bars.slice(-120);
      if (bars.length < 2) {
        var message = createSvg('text', { x: 450, y: 145, 'text-anchor': 'middle', 'class': 'live-chart-empty' });
        message.textContent = 'Aguardando histórico público de candles BTCUSDT 4h…';
        svg.appendChild(message);
        return;
      }

      var width = 900, height = 300;
      var padding = { left: 54, right: 18, top: 18, bottom: 30 };
      var plotWidth = width - padding.left - padding.right;
      var plotHeight = height - padding.top - padding.bottom;
      var low = Math.min.apply(null, bars.map(function (bar) { return bar.l; }));
      var high = Math.max.apply(null, bars.map(function (bar) { return bar.h; }));
      if (finite(context.price)) {
        low = Math.min(low, context.price);
        high = Math.max(high, context.price);
      }
      var spread = high - low;
      if (!(spread > 0)) spread = Math.max(1, high * 0.001);
      low -= spread * 0.06;
      high += spread * 0.06;
      spread = high - low;

      function xAt(index) {
        return padding.left + (index / Math.max(1, bars.length - 1)) * plotWidth;
      }
      function yAt(price) {
        return padding.top + ((high - price) / spread) * plotHeight;
      }

      for (var lineIndex = 0; lineIndex < 4; lineIndex += 1) {
        var ratio = lineIndex / 3;
        var y = padding.top + ratio * plotHeight;
        svg.appendChild(createSvg('line', { x1: padding.left, y1: y, x2: width - padding.right, y2: y, 'class': 'live-grid-line' }));
        var label = createSvg('text', { x: padding.left - 8, y: y + 4, 'text-anchor': 'end', 'class': 'live-axis-label' });
        label.textContent = fmtPrice(high - ratio * spread);
        svg.appendChild(label);
      }

      var pathData = bars.map(function (bar, index) {
        var price = index === bars.length - 1 && finite(context.price) ? context.price : bar.c;
        return (index === 0 ? 'M ' : ' L ') + xAt(index).toFixed(2) + ' ' + yAt(price).toFixed(2);
      }).join('');
      svg.appendChild(createSvg('path', { d: pathData, 'class': 'live-price-line' }));

      var indexByTime = new Map();
      bars.forEach(function (bar, index) { indexByTime.set(bar.t, index); });
      var events = allEvents().filter(function (event) { return indexByTime.has(event.timestamp); });
      events.forEach(function (event) {
        var index = indexByTime.get(event.timestamp);
        var x = xAt(index) + (event.lane === 'A' ? -3 : 3);
        var y = yAt(event.price);
        if (event.action === 'BUY') {
          svg.appendChild(createSvg('circle', {
            cx: x, cy: y, r: 5,
            'class': event.lane === 'A' ? 'live-marker live-marker-a live-marker-buy' : 'live-marker live-marker-b live-marker-buy',
            'aria-label': event.lane + ' BUY'
          }));
        } else {
          svg.appendChild(createSvg('rect', {
            x: x - 4, y: y - 4, width: 8, height: 8,
            'class': event.lane === 'A' ? 'live-marker live-marker-a live-marker-exit' : 'live-marker live-marker-b live-marker-exit',
            'aria-label': event.lane + ' EXIT'
          }));
        }
      });

      var firstLabel = createSvg('text', { x: padding.left, y: height - 8, 'class': 'live-axis-label' });
      firstLabel.textContent = fmtTime(bars[0].t);
      svg.appendChild(firstLabel);
      var lastLabel = createSvg('text', { x: width - padding.right, y: height - 8, 'text-anchor': 'end', 'class': 'live-axis-label' });
      lastLabel.textContent = fmtTime(bars[bars.length - 1].t);
      svg.appendChild(lastLabel);
    }

    function renderAll() {
      var bars = context.bars;
      var gaps = countGaps(bars);
      setText('livePrice', fmtPrice(context.price));
      setText('liveTickTime', finite(context.priceTimestamp) ? fmtTime(context.priceTimestamp) : 'Aguardando primeira cotação');
      setText('liveCandleCount', fmtCount(bars.length));
      setText('liveGapCount', fmtCount(gaps));
      setText('liveLastBar', bars.length ? fmtTime(bars[bars.length - 1].t) : '—');
      setText('liveStatusHint', context.restError
        ? 'REST indisponível: ' + context.restError + '. Tentando manter o fluxo WebSocket e o histórico local.'
        : 'Cotação atualizada em tempo real; os motores avaliam condições em candles de 4h. O contador da sessão só muda quando a regra gera BUY/EXIT. Ainda não há captura do WIL nem ordens executadas.');

      renderLane('A');
      renderLane('B');
      renderTable(allEvents());
      drawChart();
    }

    function updatePrice(price, timestamp) {
      if (!(price > 0) || !finite(price)) return;
      context.price = price;
      context.priceTimestamp = finite(timestamp) ? timestamp : Date.now();
      var now = Date.now();
      if (now - context.lastPricePaint < 400) return;
      context.lastPricePaint = now;
      setText('livePrice', fmtPrice(context.price));
      setText('liveTickTime', fmtTime(context.priceTimestamp));
      renderLane('A');
      renderLane('B');
      drawChart();
    }

    async function fetchHistory() {
      var urls = [
        'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=500',
        'https://api1.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=500',
        'https://api2.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=500',
        'https://api3.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=500',
        'https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=500'
      ];
      var failures = [];
      for (var index = 0; index < urls.length; index += 1) {
        var controller = new AbortController();
        var timer = window.setTimeout(function () { controller.abort(); }, 8000);
        try {
          var response = await fetch(urls[index], {
            cache: 'no-store',
            signal: controller.signal,
            headers: { Accept: 'application/json' }
          });
          if (!response.ok) throw new Error('HTTP ' + response.status);
          var payload = await response.json();
          if (!Array.isArray(payload)) throw new Error('resposta fora do formato de klines');
          window.clearTimeout(timer);
          return payload.map(normalizeRestKline).filter(function (candle) {
            return validCandle(candle) && candle.closeTime < Date.now() - 1000;
          });
        } catch (error) {
          window.clearTimeout(timer);
          failures.push(error && error.message ? error.message : 'falha de rede');
        }
      }
      throw new Error(failures.join(' · '));
    }

    function handleMarketMessage(message) {
      if (!message || typeof message !== 'object') return;
      var data = message.data && typeof message.data === 'object' ? message.data : message;
      if (data.e === 'trade') {
        updatePrice(number(data.p), number(data.T));
        return;
      }
      if (data.e !== 'kline' || !data.k) return;
      var candle = normalizeStreamKline(data.k);
      if (!candle) return;

      if (context.currentCandle && candle.t > context.currentCandle.t) {
        persistClosed(context.currentCandle);
      }
      if (candle.closed) persistClosed(candle);
      context.currentCandle = candle;
      if (!candle.closed && finite(context.price)) candle.c = context.price;
      calculate();
    }

    function connectionStatus(text, mode) {
      var status = document.getElementById('liveConnection');
      if (!status) return;
      status.textContent = text;
      status.className = 'tag live-connection ' + mode;
    }

    function connectSocket() {
      if (typeof WebSocket === 'undefined') {
        connectionStatus('WebSocket indisponível neste navegador', 'live-disconnected');
        return;
      }
      var stream = 'btcusdt@kline_4h/btcusdt@trade';
      var endpoints = [
        'wss://stream.binance.com:9443/stream?streams=' + stream,
        'wss://stream.binance.com:443/stream?streams=' + stream,
        'wss://data-stream.binance.vision/stream?streams=' + stream
      ];
      var url = endpoints[context.retryCount % endpoints.length];
      connectionStatus('Conectando ao feed público…', 'live-connecting');
      try {
        context.socket = new WebSocket(url);
      } catch (error) {
        scheduleReconnect();
        return;
      }

      context.socket.onopen = function () {
        context.retryCount = 0;
        connectionStatus('AO VIVO · Binance Spot', 'live-connected');
      };
      context.socket.onmessage = function (event) {
        try {
          handleMarketMessage(JSON.parse(event.data));
        } catch (error) {
          setText('liveStatusHint', 'Mensagem de mercado inválida; ignorada sem interromper o painel.');
        }
      };
      context.socket.onerror = function () {
        connectionStatus('Feed instável · reconectando', 'live-disconnected');
      };
      context.socket.onclose = function () {
        connectionStatus('Desconectado · reconectando', 'live-connecting');
        scheduleReconnect();
      };
    }

    function scheduleReconnect() {
      if (context.retryTimer) window.clearTimeout(context.retryTimer);
      var delay = Math.min(30000, 1000 * Math.pow(2, Math.min(context.retryCount, 5)));
      context.retryCount += 1;
      context.retryTimer = window.setTimeout(connectSocket, delay);
    }

    async function start() {
      setText('liveStatusHint', 'Conectando ao preço público e carregando o histórico para calcular os motores A/B…');
      try {
        var fetched = await fetchHistory();
        context.closedCandles = mergeCandles(context.closedCandles, fetched, MAX_CANDLES);
        context.price = context.closedCandles.length
          ? context.closedCandles[context.closedCandles.length - 1].c
          : null;
        context.priceTimestamp = Date.now();
        context.restError = null;
      } catch (error) {
        context.restError = error && error.message ? error.message : 'falha ao buscar histórico público';
      }

      context.initialCurrentStart = Math.floor(Date.now() / CANDLE_MS) * CANDLE_MS;
      context.currentCandle = null;
      context.bars = modelBars();
      context.simulations = {
        A: simulateLane(context.bars, 'A'),
        B: simulateLane(context.bars, 'B')
      };
      ['A', 'B'].forEach(function (lane) {
        context.simulations[lane].events.forEach(function (event) {
          context.seenEventKeys.add(eventKey(event));
        });
      });
      context.initialized = true;
      renderAll();
      connectSocket();
    }

    start();
  }

  return {
    CANDLE_MS: CANDLE_MS,
    LOOKBACK_A: LOOKBACK_A,
    LOOKBACK_B: LOOKBACK_B,
    THRESHOLD_B: THRESHOLD_B,
    COST_BPS_PER_SIDE: COST_BPS_PER_SIDE,
    normalizeRestKline: normalizeRestKline,
    normalizeStreamKline: normalizeStreamKline,
    mergeCandles: mergeCandles,
    targetAtOpen: targetAtOpen,
    simulateLane: simulateLane,
    summarizeLiveEvents: summarizeLiveEvents,
    countGaps: countGaps,
    boot: boot
  };
});