'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const live = require('../../dashboard/live-signals.js');

function candle(index, open, close) {
  const high = Math.max(open, close) * 1.001;
  const low = Math.min(open, close) * 0.999;
  return {
    t: index * live.CANDLE_MS,
    o: open,
    h: high,
    l: low,
    c: close,
    v: 1,
    closeTime: (index + 1) * live.CANDLE_MS - 1,
    closed: true
  };
}

test('A usa SMA-20 e somente candles anteriores ao open avaliado', function () {
  const bars = [];
  for (let i = 0; i < 20; i += 1) bars.push(candle(i, 100, 100));
  bars.push(candle(20, 100, 110));
  bars.push(candle(21, 110, 1));
  assert.equal(live.targetAtOpen(bars, 20, 'A'), 0);
  assert.equal(live.targetAtOpen(bars, 21, 'A'), 1);
});

test('B só ativa quando ROC de 96 barras supera estritamente 0,5%', function () {
  const bars = [];
  for (let i = 0; i < 96; i += 1) bars.push(candle(i, 100, 100));
  bars.push(candle(96, 100, 100.6));
  bars.push(candle(97, 100.6, 2));
  assert.equal(live.targetAtOpen(bars, 97, 'B'), 1);
  bars[96] = candle(96, 100, 100.5);
  assert.equal(live.targetAtOpen(bars, 97, 'B'), 0);
});

test('B conta uma operação fechada como LOSS quando o preço cai, incluindo custos', function () {
  const bars = [];
  for (let i = 0; i < 96; i += 1) bars.push(candle(i, 100, 100));
  bars.push(candle(96, 100, 100.6));
  bars.push(candle(97, 100.6, 99));
  bars.push(candle(98, 99, 99));
  const result = live.simulateLane(bars, 'B');
  assert.equal(result.entryCount, 1);
  assert.equal(result.exitCount, 1);
  assert.equal(result.wins, 0);
  assert.equal(result.losses, 1);
  assert.ok(result.trades[0].netReturnPct < 0);
  assert.equal(result.openTrade, null);
});

test('merge elimina candles duplicados e prefere a versão mais recente recebida', function () {
  const old = candle(1, 100, 100);
  const revised = candle(1, 100, 101);
  const merged = live.mergeCandles([old], [revised, candle(2, 101, 102)]);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].c, 101);
});

test('contagem de lacunas mede candles de 4h ausentes', function () {
  const bars = [candle(0, 100, 100), candle(1, 100, 100), candle(4, 100, 100)];
  assert.equal(live.countGaps(bars), 2);
});

test('resumo ao vivo separa BUY/EXIT e vitórias/derrotas', function () {
  const events = [
    { lane: 'A', timestamp: 1, action: 'BUY' },
    { lane: 'A', timestamp: 2, action: 'EXIT', result: 'WIN' },
    { lane: 'B', timestamp: 3, action: 'EXIT', result: 'LOSS' }
  ];
  assert.deepEqual(live.summarizeLiveEvents(events, 'A'), {
    signals: 2, entries: 1, exits: 1, wins: 1, losses: 0, flats: 0
  });
});