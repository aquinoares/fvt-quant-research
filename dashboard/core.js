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

  function nonnegativeInteger(value) {
    return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null;
  }

  function evaluateIncidentTiming(incident) {
    const source = incident && typeof incident === 'object' && !Array.isArray(incident) ? incident : {};
    const toleranceSeconds = nonnegativeInteger(source.tolerance_seconds);
    const delaySeconds = nonnegativeInteger(source.delay_seconds);
    let exceedsTolerance = null;
    let comparison = 'unknown';
    if (toleranceSeconds !== null && delaySeconds !== null) {
      exceedsTolerance = delaySeconds > toleranceSeconds;
      comparison = exceedsTolerance ? 'exceeds' : 'within';
    }
    return {
      toleranceSeconds: toleranceSeconds,
      delaySeconds: delaySeconds,
      exceedsTolerance: exceedsTolerance,
      comparison: comparison,
      toleranceReason: toleranceSeconds === null
        ? 'Tolerância não informada no feed.'
        : 'Tolerância lida do código existente do coletor e publicada no feed.',
      delayReason: delaySeconds === null
        ? 'Atraso não informado no feed.'
        : 'Atraso recebido como valor estruturado no feed.'
    };
  }

  function evaluateCollectorRun(lastRun, nowMs, cron) {
    const now = isFiniteNumber(nowMs) ? nowMs : Date.now();
    const run = lastRun && typeof lastRun === 'object' && !Array.isArray(lastRun) ? lastRun : {};
    const createdAtMs = parseTimestamp(run.created_at);
    const intervalMinutes = deriveIntervalMinutes(cron);
    if (createdAtMs === null) {
      return {
        status: 'unknown',
        ageMinutes: null,
        stale: null,
        createdAtMs: null,
        intervalMinutes: intervalMinutes,
        thresholdMinutes: intervalMinutes === null ? null : intervalMinutes * 1.5,
        reason: 'audit.collector_last_run.created_at ausente ou inválido no feed.'
      };
    }
    if (createdAtMs > now) {
      return {
        status: 'unknown',
        ageMinutes: null,
        stale: null,
        createdAtMs: createdAtMs,
        intervalMinutes: intervalMinutes,
        thresholdMinutes: intervalMinutes === null ? null : intervalMinutes * 1.5,
        reason: 'created_at da execução do coletor está no futuro em relação ao relógio atual.'
      };
    }
    const ageMinutes = (now - createdAtMs) / 60000;
    if (intervalMinutes === null || intervalMinutes <= 0) {
      return {
        status: 'unknown',
        ageMinutes: ageMinutes,
        stale: null,
        createdAtMs: createdAtMs,
        intervalMinutes: null,
        thresholdMinutes: null,
        reason: 'Não é possível avaliar a idade sem o cron real do coletor no feed.'
      };
    }
    const thresholdMinutes = intervalMinutes * 1.5;
    const stale = ageMinutes > thresholdMinutes;
    return {
      status: stale ? 'stale' : 'recent',
      ageMinutes: ageMinutes,
      stale: stale,
      createdAtMs: createdAtMs,
      intervalMinutes: intervalMinutes,
      thresholdMinutes: thresholdMinutes,
      reason: stale
        ? 'A última execução passou de 1,5× o intervalo derivado do cron do coletor.'
        : 'A última execução está dentro de 1,5× o intervalo derivado do cron do coletor.'
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

  function computeOtherTradesReturn(bestNetTrade,totalNetReturn,trades) {
    if (!isFiniteNumber(bestNetTrade) || !isFiniteNumber(totalNetReturn) || !isFiniteNumber(trades) ||
        bestNetTrade <= -1 || totalNetReturn <= -1 || trades <= 1) return null;
    const value = (1 + totalNetReturn) / (1 + bestNetTrade) - 1;
    return Number.isFinite(value) ? value : null;
  }

  function computeOperationsProjection(referenceTrades,referenceDays,targetDays) {
    if (!isFiniteNumber(referenceTrades) || !isFiniteNumber(referenceDays) || !isFiniteNumber(targetDays) ||
        referenceTrades < 0 || referenceDays <= 0 || targetDays < 0) return null;
    const value = referenceTrades / referenceDays * targetDays;
    return Number.isFinite(value) ? value : null;
  }

  function computeCoveragePercentage(minutesPresent,minutesExpected) {
    if (!isFiniteNumber(minutesPresent) || !isFiniteNumber(minutesExpected) ||
        minutesPresent < 0 || minutesExpected <= 0 || minutesPresent > minutesExpected) return null;
    return minutesPresent / minutesExpected * 100;
  }

  function learningReportView(learning) {
    const source = learning && typeof learning === 'object' && !Array.isArray(learning) ? learning : {};
    const available = source.report_available === true;
    const reason = available ? null : (
      typeof source.quality_report_reason === 'string' && source.quality_report_reason.trim()
        ? source.quality_report_reason
        : 'Relatório de qualidade ausente na branch learning-state; métricas não disponíveis.'
    );
    function metric(key, integerOnly) {
      const value = source[key];
      if (!available || !isFiniteNumber(value) || value < 0 || (integerOnly && !Number.isInteger(value))) return null;
      if (key === 'coverage_percent' && value > 100) return null;
      return value;
    }
    return {
      available: available,
      reason: reason,
      candleCount: metric('candle_count_1m', true),
      newCandles: metric('new_candles', true),
      gapsFound: metric('gaps_found', true),
      gapsFilled: metric('gaps_filled', true),
      gapsRemaining: metric('gaps_remaining', true),
      duplicatesRemoved: metric('duplicates_removed', true),
      ageLastCandleSeconds: metric('age_last_candle_seconds', true),
      pendingBackfillCandles: metric('pending_backfill_candles', true),
      coveragePercent: metric('coverage_percent', false),
      coverageMinutesPresent: metric('coverage_minutes_present', true),
      coverageMinutesExpected: metric('coverage_minutes_expected', true),
      firstCandleOpenTimeUtc: available && typeof source.first_candle_open_time_utc === 'string' && source.first_candle_open_time_utc.trim()
        ? source.first_candle_open_time_utc : null,
      latestCandleOpenTimeUtc: available && typeof source.latest_candle_open_time_utc === 'string' && source.latest_candle_open_time_utc.trim()
        ? source.latest_candle_open_time_utc : null,
      latestRunAtUtc: available && typeof source.latest_run_at_utc === 'string' && source.latest_run_at_utc.trim()
        ? source.latest_run_at_utc : null,
      dailyGaps: available && Array.isArray(source.daily_gaps) ? source.daily_gaps : [],
      message: available && typeof source.message === 'string' ? source.message : reason
    };
  }

  function freshnessStatus(updatedAt,nowMs,staleAfterMinutes,hasError) {
    if (hasError) return {status:'error',ageMinutes:null,reason:'Consulta do feed falhou; métricas anteriores devem ser ocultadas.'};
    const timestamp = parseTimestamp(updatedAt);
    if (timestamp === null || !isFiniteNumber(nowMs) || !isFiniteNumber(staleAfterMinutes) || staleAfterMinutes < 0) {
      return {status:'unknown',ageMinutes:null,reason:'Timestamp de atualização ausente ou inválido.'};
    }
    const ageMinutes=(nowMs-timestamp)/60000;
    if (ageMinutes < 0) return {status:'error',ageMinutes:null,reason:'Timestamp do feed está no futuro.'};
    if (ageMinutes > staleAfterMinutes) return {status:'stale',ageMinutes:ageMinutes,reason:'Feed antigo; não há confirmação de atualização recente.'};
    return {status:'current',ageMinutes:ageMinutes,reason:'Timestamp dentro do limite de frescor.'};
  }

  return {
    parseTimestamp: parseTimestamp,
    deriveIntervalMinutes: deriveIntervalMinutes,
    classifyAge: classifyAge,
    evaluateHealth: evaluateHealth,
    evaluateIncidentTiming: evaluateIncidentTiming,
    evaluateCollectorRun: evaluateCollectorRun,
    drawdownState: drawdownState,
    numericField: numericField,
    verifyHashChain: verifyHashChain,
    computeOtherTradesReturn: computeOtherTradesReturn,
    computeOperationsProjection: computeOperationsProjection,
    computeCoveragePercentage: computeCoveragePercentage,
    learningReportView: learningReportView,
    freshnessStatus: freshnessStatus
  };
});