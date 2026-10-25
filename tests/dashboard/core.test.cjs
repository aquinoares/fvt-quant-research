'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { webcrypto } = require('node:crypto');
const vm = require('node:vm');
const Core = require('../../dashboard/core.js');

const fixtureDir = path.join(__dirname, 'fixtures');
const healthFixture = JSON.parse(fs.readFileSync(path.join(fixtureDir, 'health-cases.json'), 'utf8'));
const brokenChainFixture = JSON.parse(fs.readFileSync(path.join(fixtureDir, 'broken-hash-chain.json'), 'utf8'));
const drawdownFixture = JSON.parse(fs.readFileSync(path.join(fixtureDir, 'drawdown-cases.json'), 'utf8'));
const dashboardHtml = fs.readFileSync(path.join(__dirname, '../../dashboard/index.html'), 'utf8');
const nowMs = Date.parse(healthFixture.now_utc);

test('deriva 30 minutos dos dois crons reais e rejeita cron desconhecido', function () {
  assert.equal(Core.deriveIntervalMinutes(healthFixture.health_schedule.collector_cron), 30);
  assert.equal(Core.deriveIntervalMinutes(healthFixture.health_schedule.dashboard_cron), 30);
  assert.equal(Core.deriveIntervalMinutes(''), null);
  assert.equal(Core.deriveIntervalMinutes('0 0 * * *'), null);
});

for (const fixture of healthFixture.cases) {
  test('saúde de coleta: ' + fixture.name, function () {
    const feed = {
      updated_at_utc: fixture.updated_at_utc,
      health_schedule: Object.prototype.hasOwnProperty.call(fixture, 'health_schedule')
        ? fixture.health_schedule : healthFixture.health_schedule,
      collection_health: fixture.collection_health,
      shadow: fixture.shadow,
      audit: fixture.audit
    };
    assert.equal(Core.evaluateHealth(feed, nowMs).status, fixture.expected);
  });
}

test('candles e lacunas ausentes são null, não zero', function () {
  const feed = {
    updated_at_utc: '2026-10-24T23:58:00.000Z',
    health_schedule: healthFixture.health_schedule,
    collection_health: { last_open_time: null, server_time_ms: 1792886400000 },
    shadow: { status: 'awaiting' }
  };
  const result = Core.evaluateHealth(feed, nowMs);
  assert.equal(result.candles48h, null);
  assert.equal(result.gaps48h, null);
});

test('campo numérico ausente não vira zero; zero real é preservado', function () {
  assert.equal(Core.numericField({}, 'candles_observed'), null);
  assert.equal(Core.numericField({ candles_observed: null }, 'candles_observed'), null);
  assert.equal(Core.numericField({ candles_observed: 0 }, 'candles_observed'), 0);
});

for (const fixture of drawdownFixture.cases) {
  test('drawdown fixture: ' + fixture.name, function () {
    const state = Core.drawdownState(fixture.drawdown, fixture.breached);
    assert.equal(state.status, fixture.expected);
    if (fixture.expected === 'critical') assert.match(state.reason, /não retomar automaticamente/i);
  });
}
test('drawdown ausente permanece desconhecido, nunca 0%', function () {
  assert.equal(Core.drawdownState(null, false).status, 'unknown');
  assert.match(Core.drawdownState(null, false).reason, /não contém/i);
});
test('flag real breached aciona parada mesmo sem número, mas o valor continua ausente', function () {
  assert.equal(Core.drawdownState(null, true).status, 'critical');
});

test('timeline sem algoritmo documentado fica não verificada', async function () {
  const result = await Core.verifyHashChain({ records: [{ at_utc: '2026-10-25T00:00:00Z' }] }, webcrypto.subtle);
  assert.equal(result.status, 'not_verified');
});
test('cadeia SHA-256 declarada mas quebrada é marcada quebrada', async function () {
  const result = await Core.verifyHashChain(brokenChainFixture.signal_timeline, webcrypto.subtle);
  assert.equal(result.status, 'broken');
  assert.match(result.reason, /Hash divergente/i);
});

test('painel destaca incidente, pendência humana e origem de auditoria', function () {
  assert.match(dashboardHtml, /id="incidentBanner"/);
  assert.match(dashboardHtml, /Workflow verde não significa sessão válida/i);
  assert.match(dashboardHtml, /não retomar automaticamente/i);
  assert.match(dashboardHtml, /decisão pendente do responsável/i);
  assert.match(dashboardHtml, /Timeline não verificada/i);
  assert.match(dashboardHtml, /não disponível no manifesto congelado/i);
  assert.match(dashboardHtml, /id="panelRun"/);
});

test('JavaScript embutido no HTML passa pelo parser do Node.js', function () {
  const scripts = Array.from(dashboardHtml.matchAll(/<script\\b[^>]*>([\\s\\S]*?)<\\/script>/gi));
  assert.ok(scripts.length >= 1, 'deve existir ao menos um script inline');
  scripts.forEach(function (match) { new vm.Script(match[1]); });
});
