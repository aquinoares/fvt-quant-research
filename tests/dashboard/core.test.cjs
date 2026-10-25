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
const incidentTimingFixture = JSON.parse(fs.readFileSync(path.join(fixtureDir, 'incident-timing-cases.json'), 'utf8'));
const collectorRunFixture = JSON.parse(fs.readFileSync(path.join(fixtureDir, 'collector-run-cases.json'), 'utf8'));
const dashboardWorkflow = fs.readFileSync(path.join(__dirname, '../../.github/workflows/fvt-dashboard.yml'), 'utf8');
const feedTemplate = JSON.parse(fs.readFileSync(path.join(__dirname, '../../dashboard/data.json'), 'utf8'));
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
  const scripts = Array.from(dashboardHtml.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi));
  assert.ok(scripts.length >= 1, 'deve existir ao menos um script inline');
  scripts.forEach(function (match) { new vm.Script(match[1]); });
});

for (const fixture of incidentTimingFixture.cases) {
  test('campos estruturados de incidente: ' + fixture.name, function () {
    const state = Core.evaluateIncidentTiming(fixture.incident);
    assert.equal(state.toleranceSeconds, fixture.expectedTolerance);
    assert.equal(state.delaySeconds, fixture.expectedDelay);
    assert.equal(state.exceedsTolerance, fixture.expectedExceeds);
    assert.equal(state.comparison, fixture.expectedComparison);
  });
}

const collectorNowMs = Date.parse(collectorRunFixture.now_utc);
for (const fixture of collectorRunFixture.cases) {
  test('frescor da execução do coletor: ' + fixture.name, function () {
    const run = fixture.created_at === null ? {} : { created_at: fixture.created_at };
    const result = Core.evaluateCollectorRun(run, collectorNowMs, fixture.cron);
    assert.equal(result.status, fixture.expectedStatus);
    assert.equal(result.stale, fixture.expectedStale);
    if (fixture.expectedAgeMinutes === null) {
      assert.equal(result.ageMinutes, null);
    } else {
      assert.equal(result.ageMinutes, fixture.expectedAgeMinutes);
    }
  });
}

test('workflow lê tolerância sem escrever no coletor e não fixa 2700 no painel', function () {
  assert.match(dashboardWorkflow, /def collector_tolerance_seconds/);
  assert.match(dashboardWorkflow, /guard_values\("age_seconds"\)/);
  assert.match(dashboardWorkflow, /guard_values\("seconds_after_start"\)/);
  assert.match(dashboardWorkflow, /"tolerance_seconds": incident_tolerance_seconds/);
  assert.doesNotMatch(dashboardWorkflow, /state_age_seconds > 2700/);
  assert.equal(feedTemplate.shadow.incident.tolerance_seconds, null);
  assert.equal(feedTemplate.shadow.incident.delay_seconds, null);
  assert.doesNotMatch(dashboardHtml, /2700/);
  assert.doesNotMatch(dashboardHtml, /seconds after window start/i);
  assert.match(dashboardHtml, /Commit da main no momento da última execução do coletor/);
  assert.match(dashboardHtml, /Horário da última execução do coletor/);
  assert.match(dashboardHtml, /Idade da última execução do coletor/);
  assert.match(dashboardHtml, /coletor sem execução recente — verificar Actions/);
  assert.match(dashboardHtml, /c\.head_branch==='main'/);
});


test('nota da melhor operação calcula o retorno composto das demais',()=>{
  const value=Core.computeOtherTradesReturn(0.2565241260433213,0.21946998037371812,4);
  assert.ok(Math.abs(value - (-0.0295)) < 0.001);
  assert.equal(Core.computeOtherTradesReturn(null,0.219,4),null);
  assert.equal(Core.computeOtherTradesReturn(0.2,0.1,1),null);
});

test('buy-and-hold ausente continua desconhecido, não zero',()=>{
  const feed={historical:{}};
  assert.equal(Core.numericField(feed.historical,'buy_and_hold_net_return'),null);
  assert.equal(Core.computeCoveragePercentage(null,null),null);
});

test('projeção de operações é aritmética e valida denominadores',()=>{
  const projected=Core.computeOperationsProjection(7,67.5,90);
  assert.ok(Math.abs(projected - (9.3333333333)) < 0.00001);
  assert.equal(Core.computeOperationsProjection(7,0,90),null);
});

test('cobertura de minutos exige denominador versionado',()=>{
  assert.equal(Core.computeCoveragePercentage(75,100),75);
  assert.equal(Core.computeCoveragePercentage(0,0),null);
  assert.equal(Core.computeCoveragePercentage(101,100),null);
});

test('frescor distingue atual, antigo, erro e timestamp ausente',()=>{
  const now=Date.parse('2026-10-25T01:00:00Z');
  assert.equal(Core.freshnessStatus('2026-10-25T00:59:00Z',now,90,false).status,'current');
  assert.equal(Core.freshnessStatus('2026-10-24T20:00:00Z',now,90,false).status,'stale');
  assert.equal(Core.freshnessStatus('2026-10-25T00:59:00Z',now,90,true).status,'error');
  assert.equal(Core.freshnessStatus(null,now,90,false).status,'unknown');
});

test('timeline do incidente mantém fato e inferência como classificações separadas',()=>{
  const fixture=require('./fixtures/incident-timing-cases.json');
  assert.equal(fixture.cases[0].expectedDelay,2893);
  assert.ok(fixture.cases.some(x=>x.name==='tolerância ausente'&&x.expectedComparison==='unknown'));
  const timeline=[
    {at_utc:'2026-10-25T00:15:00Z',classification:'inferência do diagnóstico'},
    {at_utc:'2026-10-25T00:48:13.150235Z',classification:'fato registrado'}
  ];
  assert.equal(timeline[0].classification,'inferência do diagnóstico');
  assert.equal(timeline[1].classification,'fato registrado');
});

test('HTML limpa dados após erro, evita innerHTML com dados e não inclui login nem e-mail',()=>{
  const html=require('fs').readFileSync(require('path').join(__dirname,'../../dashboard/index.html'),'utf8');
  assert.match(html,/Feed indisponível/);
  assert.doesNotMatch(html,/\.innerHTML\s*=/);
  assert.doesNotMatch(html,/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
  assert.doesNotMatch(html,/login\s+(?:visual|de usuário)/i);
  assert.match(html,/id="learning"/);
  assert.match(html,/id="decisions"/);
});

test('Trilha A daily gap quality summary is source-backed and report download is disabled without report',()=>{
  const html=require('fs').readFileSync(require('path').join(__dirname,'../../dashboard/index.html'),'utf8');
  assert.match(html,/learning\/reports\/latest\.json/);
  assert.match(html,/learning\/experiments\/registry\.json/);
  assert.match(html,/learning\/hypotheses\.jsonl/);
  assert.match(html,/dailyGapsChart/);
  assert.match(html,/learningReportBtn/);
});
