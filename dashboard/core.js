'use strict';

(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.FVTCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const RANK = { green: 0, yellow: 1, red: 2 };

  function isFiniteNumber(value) {
    return typeof value === 'number' && Number.isFinite(value);
  }

  function parseTimestamp(value) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value < 100000000000 ? value * 1000 : value;
    }
    if (typeof value !== 'string' || value.trim() === '') return null;
    const text = value.trim();
    if (/^\d+(\.\d+)?$/.test(text)) {
      const number = Number(text);
      if (!Number.isFinite(number)) return null;
      return number < 100000000000 ? number * 1000 : number;
    }
    const parsed = Date.parse(text);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function deriveIntervalMinutes(cron) {
    if (typeof cron !== 'string') return null;
    const fields = cron.trim().split(/\s+/);
    if (fields.length !== 5 || fields.slice(1).some(function (field) { return field !== '*'; })) return null;
    const minuteField = fields[0];
    let minutes = [];
    if (minuteField === '*') {
      return 1;
    } else if (/^\*\/\d+$/.test(minuteField)) {
      const step = Number(minuteField.slice(2));
      return Number.isInteger(step) && step >= 1 && step <= 60 ? step : null;
    } else if (/^\d+(,\d+)+$/.test(minuteField) || /^\d+$/.test(minuteField)) {
      minutes = minuteField.split(',').map(Number);
      if (minutes.some(function (n) { return !Number.isInteger(n) || n < 0 || n > 59; })) return null;
      minutes = Array.from(new Set(minutes)).sort(function (a, b) { return a - b; });
      if (minutes.length < 2) return null;
      const differences = [];
      for (let i = 1; i < minutes.length; i += 1) differences.push(minutes[i] - minutes[i - 1]);
      differences.push(60 - minutes[minutes.length - 1] + minutes[0]);
      if (differences.some(function (n) { return n <= 0; })) return null;
      return Math.min.apply(null, differences);
    }
    return null;
  }

  function classifyAge(timestamp, nowMs, intervalMinutes, futureReferenceMs) {
    const timestampMs = parseTimestamp(timestamp);
    if (timestampMs === null) {
      return { status: 'red', ageMinutes: null, timestampMs: null, reason: 'Timestamp ausente ou inválido no feed.' };
    }
    if (isFiniteNumber(futureReferenceMs) && timestampMs > futureReferenceMs) {
      return { status: 'red', ageMinutes: null, timestampMs: timestampMs, reason: 'Timestamp futuro em relação ao horário de referência do servidor.' };
    }
    if (!isFiniteNumber(nowMs) || timestampMs > nowMs) {
      return { status: 'red', ageMinutes: null, timestampMs: timestampMs, reason: 'Timestamp futuro em relação ao relógio atual.' };
    }
    if (!isFiniteNumber(intervalMinutes) || intervalMinutes <= 0) {
      return { status: 'red', ageMinutes: (nowMs - timestampMs) / 60000, timestampMs: timestampMs, reason: 'Não foi possível derivar o intervalo do cron do workflow.' };
    }
    const ageMinutes = (nowMs - timestampMs) / 60000;
    if (ageMinutes <= intervalMinutes * 1.5) {
      return { status: 'green', ageMinutes: ageMinutes, timestampMs: timestampMs, reason: 'Idade dentro do limite verde derivado do cron.' };
    }
    if (ageMinutes <= intervalMinutes * 3) {
      return { status: 'yellow', ageMinutes: ageMinutes, timestampMs: timestampMs, reason: 'Idade acima do limite verde, ainda dentro do limite amarelo derivado do cron.' };
    }
    return { status: 'red', ageMinutes: ageMinutes, timestampMs: timestampMs, reason: 'Idade acima de 3× o intervalo derivado do cron.' };
  }

  function worse(a, b) {
    if (!a) return b;
    if (!b) return a;
    return RANK[b.status] > RANK[a.status] ? b : a;
  }

  function evaluateHealth(feed, nowMs) {
    const now = isFiniteNumber(nowMs) ? nowMs : Date.now();
    const record = feed && feed.collection_health && typeof feed.collection_health === 'object' ? feed.collection_health : {};
    const shadow = feed && feed.shadow && typeof feed.shadow === 'object' ? feed.shadow : {};
    const schedule = feed && feed.health_schedule && typeof feed.health_schedule === 'object' ? feed.health_schedule : {};
    const collectorInterval = deriveIntervalMinutes(schedule.collector_cron);
    const feedInterval = deriveIntervalMinutes(schedule.dashboard_cron);
    const serverTime = parseTimestamp(record.server_time_ms);
    const candleTimestamp = record.last_open_time !== undefined && record.last_open_time !== null
      ? record.last_open_time
      : shadow.last_timestamp;
    const candle = classifyAge(candleTimestamp, now, collectorInterval, serverTime);
    const feedAge = classifyAge(feed && feed.updated_at_utc, now, feedInterval, null);
    let overall = worse(candle, feedAge);
    const gaps = record.gaps_48h;
    const gapsKnown = isFiniteNumber(gaps) && gaps >= 0;
    if (gapsKnown && gaps > 0 && RANK[overall.status] < RANK.yellow) {
      overall = { status: 'yellow', ageMinutes: overall.ageMinutes, reason: 'Há lacunas registradas nas últimas 48 horas.' };
    }
    if (shadow.status === 'risk_breach' || shadow.breached === true) {
      overall = { status: 'red', ageMinutes: overall.ageMinutes, reason: 'O feed registra violação do limite de risco.' };
    } else if (shadow.status === 'protocol_stopped') {
      overall = { status: 'red', ageMinutes: overall.ageMinutes, reason: shadow.status_detail || 'O protocolo registra interrupção da sessão.' };
    }
    const candles48h = isFiniteNumber(record.candles_48h) && record.candles_48h >= 0 ? record.candles_48h : null;
    return {
      status: overall.status,
      reason: overall.reason,
      candle: candle,
      feed: feedAge,
      collectorIntervalMinutes: collectorInterval,
      feedIntervalMinutes: feedInterval,
      collectorCron: typeof schedule.collector_cron === 'string' ? schedule.collector_cron : null,
      dashboardCron: typeof schedule.dashboard_cron === 'string' ? schedule.dashboard_cron : null,
      candles48h: candles48h,
      gaps48h: gapsKnown ? gaps : null,
      serverTimeMs: serverTime,
      snapshotAtMs: parseTimestamp(feed && feed.updated_at_utc)
    };
  }

  function drawdownState(drawdown, breached) {
    if (breached === true) return { status: 'critical', reason: 'Protocolo exige interrupção; não retomar automaticamente.' };
    if (!isFiniteNumber(drawdown)) return { status: 'unknown', reason: 'O feed não contém um drawdown prospectivo numérico.' };
    if (drawdown <= -0.10) return { status: 'critical', reason: 'Protocolo exige interrupção; não retomar automaticamente.' };
    if (drawdown <= -0.07) return { status: 'warning', reason: 'Aviso de risco: drawdown em −7% ou pior; acompanhar o protocolo.' };
    return { status: 'normal', reason: 'O valor recebido está acima do limiar de aviso de −7%.' };
  }

  function numericField(object, key) {
    return object && Object.prototype.hasOwnProperty.call(object, key) && isFiniteNumber(object[key])
      ? object[key] : null;
  }

  async function verifyHashChain(timeline, subtleOverride) {
    if (!timeline || !Array.isArray(timeline.records)) {
      return { status: 'not_verified', reason: 'O feed não contém uma timeline de sinais com registros.' };
    }
    const spec = timeline.integrity;
    if (!spec || spec.algorithm !== 'SHA-256' ||
        spec.canonicalization !== 'JSON.stringify(record_without_hash)_UTF8' ||
        spec.hash_field !== 'record_hash' ||
        spec.previous_hash_field !== 'prev_hash' ||
        !Object.prototype.hasOwnProperty.call(spec, 'initial_previous_hash')) {
      return { status: 'not_verified', reason: 'O feed não documenta um algoritmo/canonicalização de hash reconhecidos; imutabilidade depende do backend.' };
    }
    const subtle = subtleOverride || (typeof globalThis !== 'undefined' && globalThis.crypto ? globalThis.crypto.subtle : null);
    if (!subtle || typeof subtle.digest !== 'function') {
      return { status: 'not_verified', reason: 'crypto.subtle não está disponível neste contexto; a cadeia não foi verificada.' };
    }
    const records = timeline.records;
    let previous = spec.initial_previous_hash;
    const encoder = new TextEncoder();
    for (let index = 0; index < records.length; index += 1) {
      const record = records[index];
      if (!record || typeof record !== 'object' || Array.isArray(record)) {
        return { status: 'broken', reason: 'Registro ' + (index + 1) + ' tem formato inválido.' };
      }
      const declaredPrevious = Object.prototype.hasOwnProperty.call(record, spec.previous_hash_field)
        ? record[spec.previous_hash_field] : undefined;
      if (declaredPrevious !== previous) {
        return { status: 'broken', reason: 'Hash anterior divergente no registro ' + (index + 1) + '.' };
      }
      const declaredHash = record[spec.hash_field];
      if (typeof declaredHash !== 'string' || !/^[0-9a-f]{64}$/i.test(declaredHash)) {
        return { status: 'broken', reason: 'Hash ausente ou inválido no registro ' + (index + 1) + '.' };
      }
      const preimage = {};
      Object.keys(record).forEach(function (key) {
        if (key !== spec.hash_field) preimage[key] = record[key];
      });
      const digest = await subtle.digest('SHA-256', encoder.encode(JSON.stringify(preimage)));
      const actualHash = Array.from(new Uint8Array(digest)).map(function (byte) {
        return byte.toString(16).padStart(2, '0');
      }).join('');
      if (actualHash.toLowerCase() !== declaredHash.toLowerCase()) {
        return { status: 'broken', reason: 'Hash divergente no registro ' + (index + 1) + '.' };
      }
      previous = declaredHash;
    }
    return { status: 'verified', reason: 'Cadeia verificada com SHA-256 conforme a especificação documentada no feed.' };
  }

  return {
    parseTimestamp: parseTimestamp,
    deriveIntervalMinutes: deriveIntervalMinutes,
    classifyAge: classifyAge,
    evaluateHealth: evaluateHealth,
    drawdownState: drawdownState,
    numericField: numericField,
    verifyHashChain: verifyHashChain
  };
});