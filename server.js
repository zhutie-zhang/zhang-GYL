const http = require('http');
const fs = require('fs');
const path = require('path');
const ROOT = 'C:\\Users\\1\\Documents\\Default Project';
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.map': 'application/json', '.csv': 'text/csv; charset=utf-8' };

function decodeEntities(s) {
  return s.replace(/&#(\d+);/g, (m, n) => String.fromCharCode(parseInt(n, 10))).replace(/&#x([0-9a-f]+);/gi, (m, h) => String.fromCharCode(parseInt(h, 16)))
    .replace(/&nbsp;|&#160;/gi, ' ').replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>').replace(/&quot;/gi, '"').replace(/&#39;|&apos;/gi, "'");
}

function parseCurrentWeek(text) {
  try {
    const body = decodeEntities(text.replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ').replace(/<[^>]+>/g, '\n'));
    const lines = body.split(/\n+/).map(l => l.trim()).filter(Boolean);
    const periodRe = /^([A-Z][a-z]{2,8}\.?\s+\d{1,2},\s*\d{4})\s*[–—-]\s*([A-Z][a-z]{2,8}\.?\s+\d{1,2},\s*\d{4})/i;
    const dateRe = /^[A-Z][a-z]{2,8}\.?\s+\d{1,2},\s*\d{4}\s*$/i;
    let periodIdx = -1;
    for (let i = 0; i < lines.length; i++) {
      if (periodRe.test(lines[i])) { periodIdx = i; break; }
    }
    if (periodIdx < 0) return null;
    const pm = lines[periodIdx].match(periodRe);
    const out = { period: lines[periodIdx], periodStart: pm[1], ground: null, package: null, expressFreight: null, export: null };
    for (let i = periodIdx + 1; i < lines.length; i++) {
      const L = lines[i];
      if (periodRe.test(L)) break;
      if (dateRe.test(L)) continue;
      const perc = L.match(/^(\d{1,3}(?:\.\d{1,2})?)\s*%$/i);
      const perLb = L.match(/^\$([\d.]+)\s*per\s*lb/i);
      if (perLb) { out.expressFreight = parseFloat(perLb[1]); continue; }
      if (perc) {
        const v = parseFloat(perc[1]);
        if (out.ground === null) out.ground = v;
        else if (out.package === null) out.package = v;
        else if (out.export === null) out.export = v;
      }
    }
    return out;
  } catch (e) { return null; }
}
function round2(x) { return Math.round(x * 100) / 100; }

function serverZipToZone(tpl, zip) {
  const z = String(zip || '').replace(/[^0-9-]/g, '').slice(0, 5);
  if (!z) return null;
  const zi = parseInt(z.replace(/[^0-9]/g, ''), 10);
  if (isNaN(zi)) return null;
  for (const r of (tpl.zipRules || [])) {
    const f = parseInt(r.from, 10), t2 = parseInt(r.to, 10);
    if (isNaN(f) || isNaN(t2)) continue;
    if (zi >= f && zi <= t2) return r.zone;
  }
  return null;
}

function serverLookUpBase(tpl, weight, zone) {
  const rows = (tpl.rows || []).slice().sort((a, b) => (a.max || 0) - (b.max || 0));
  let price = null;
  for (const r of rows) {
    if (weight <= (r.max || Infinity)) {
      const p = r.prices && r.prices[zone - 1];
      price = (p === null || p === undefined || p === '') ? null : parseFloat(p);
      break;
    }
  }
  if (price === null && rows.length) {
    const last = rows[rows.length - 1];
    const p = last.prices && last.prices[zone - 1];
    price = (p === null || p === undefined || p === '') ? null : parseFloat(p);
  }
  return price;
}

function serverCalcFreight(config, params) {
  try {
    let actualKg = parseFloat(params.weightKg);
    if (isNaN(actualKg) || actualKg <= 0) return { ok: false, error: '实重无效' };
    let volKg = 0;
    if (params.dims) {
      const d = String(params.dims).split(/[xX*×]/).map(s => parseFloat(s));
      if (d.length === 3 && d.every(v => !isNaN(v) && v > 0)) volKg = (d[0] * d[1] * d[2]) / (config.volParam || 6000);
    }
    const chargeBy = config.chargeBy || 'actual';
    let weightKg;
    if (chargeBy === 'volumetric') weightKg = volKg > 0 ? volKg : actualKg;
    else if (chargeBy === 'max') weightKg = Math.max(actualKg, volKg);
    else weightKg = actualKg;
    const zone = serverZipToZone(config, params.zip);
    if (zone === null) return { ok: false, error: '邮编未命中任何分区规则' };
    const pieces = Math.max(1, parseInt(params.pieces, 10) || 1);
    const perPiece = config.calcMode === 'perPiece';
    const unitW = perPiece ? weightKg / pieces : weightKg;
    const unitBase = serverLookUpBase(config, unitW, zone);
    if (unitBase === null) return { ok: false, error: 'Zone' + zone + ' 在重量 ' + unitW + ' 档无报价' };
    const base = perPiece ? round2(unitBase * pieces) : unitBase;
    const items = [];
    let fixedTotal = 0, whopTotal = 0, pctTotal = 0;
    (config.surcharges || []).forEach(s => {
      if (s.enabled === false) return;
      if (s.zones && s.zones.length && s.zones.indexOf(zone) < 0) return;
      if (s.mode !== 'fixed') return;
      if (s.type === 'whop') {
        whopTotal += round2(s.value);
        items.push({ name: s.name || '库内操作费', kind: 'whop', mode: 'fixed', value: s.value, zones: s.zones || [], amount: round2(s.value), note: '不参与百分比基数' });
      } else {
        fixedTotal += round2(s.value);
        items.push({ name: s.name || '附加费', kind: 'normal', mode: 'fixed', value: s.value, zones: s.zones || [], amount: round2(s.value), note: '' });
      }
    });
    const pctBase = round2(base + fixedTotal);
    (config.surcharges || []).forEach(s => {
      if (s.enabled === false) return;
      if (s.zones && s.zones.length && s.zones.indexOf(zone) < 0) return;
      if (s.mode !== 'percent') return;
      let pct = s.value || 0;
      let note = '基准=(基础+' + fixedTotal.toFixed(2) + ')';
      const amt = round2(pctBase * pct / 100);
      pctTotal += amt;
      items.push({ name: s.name || '百分比附加费', kind: s.type || 'normal', mode: 'percent', value: pct, zones: s.zones || [], amount: amt, note });
    });
    const total = round2(base + fixedTotal + pctTotal + whopTotal);
    return { ok: true, zone, actualKg, volKg, chargeBy, weightKg, pieces, perPiece, unitWeight: round2(unitW), base, fixedTotal, pctBase, pctTotal, whopTotal, items, total };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

http.createServer((req, res) => {
  const url = req.url || '/';
  if (req.method === 'POST' && url.startsWith('/api/calc')) {
    let body = '';
    req.on('data', c => { body += c; if (body.length > 5e6) req.destroy(); });
    req.on('end', () => {
      try {
        const p = JSON.parse(body);
        const out = serverCalcFreight(p.config || {}, p);
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify(out));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: false, error: '请求体解析失败：' + e.message }));
      }
    });
    return;
  }
  if (url.startsWith('/api/fuel')) {
    const q = new URL(url, 'http://127.0.0.1:8210').searchParams;
    const target = (q.get('url') || '').trim();
    if (!/^https?:\/\//i.test(target)) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ error: 'url 必须为 http/https' }));
    }
    if (/^https?:\/\/((127\.0\.0\.1)|localhost)/i.test(target)) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ error: '不允许访问本机地址' }));
    }
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), 15000);
    fetch(target, { signal: ac.signal, headers: { 'User-Agent': 'Mozilla/5.0' } })
      .then(r => r.text())
      .then(text => {
        clearTimeout(timer);
        const pcts = [];
        const re = /(\d{1,3}(?:\.\d{1,2})?)\s*%/g;
        let m;
        while ((m = re.exec(text)) !== null) pcts.push(parseFloat(m[1]));
        const uniq = Array.from(new Set(pcts.filter(p => p >= 0.5 && p <= 100)));
        const current = parseCurrentWeek(text);
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: true, percentages: uniq.sort((a, b) => a - b), current, chars: text.length, title: (text.match(/<title>([\s\S]*?)<\/title>/i) || [])[1] || '' }));
      })
      .catch(err => {
        clearTimeout(timer);
        res.writeHead(502, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: '抓取失败：' + (err.message || err) }));
      });
    return;
  }
  let p = decodeURIComponent(url.split('?')[0]);
  if (p === '/') p = '/price-checker.html';
  const fp = path.normalize(path.join(ROOT, p));
  if (!fp.startsWith(ROOT)) { res.writeHead(403); return res.end('403'); }
  fs.readFile(fp, (err, data) => {
    if (err) { res.writeHead(404); return res.end('404'); }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(fp)] || 'application/octet-stream' });
    res.end(data);
  });
}).listen(8210, '127.0.0.1', () => console.log('server on http://127.0.0.1:8210/price-checker.html'));