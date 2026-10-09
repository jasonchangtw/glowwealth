// Tests the exact plain-JS quote functions inside index.html; no browser or npm install.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const helper = html.slice(html.indexOf('        // Public quote cache'), html.indexOf('        function App()'));
const fn = html.slice(html.indexOf('            const fetchFinancialData = async () => {'), html.indexOf('            useEffect(() => {\n                fetchFinancialData();'));
const storage = new Map();
const current = { schemaVersion: 1, generatedAt: new Date().toISOString(), quotes: {
    'US:VOO': { symbol: 'VOO', market: 'US', currency: 'USD', price: 123.45,
        quoteTime: new Date().toISOString(), fetchedAt: new Date().toISOString(),
        source: 'Yahoo chart', kind: 'trade', status: 'ok' }
}, fx: { rate: 31.96, quoteTime: new Date().toISOString(), status: 'ok' } };
let mode = 'ok', calls = 0;
const state = {};
const ctx = {
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
    window: { location: { href: 'https://example.github.io/glowwealth/' } },
    Date, Number, URL, AbortController, setTimeout, clearTimeout,
    console: { error() {} },
    quoteRef: { current: { schemaVersion: 1, quotes: {}, fx: null } }, refreshLock: { current: false },
    setPriceStatus: value => state.status = value,
    setQuoteReadState: value => state.read = value,
    setPriceHint: value => state.hint = value,
    setQuoteMeta: value => state.meta = value,
    setPriceData: value => state.prices = value,
    setExchangeRate: value => state.fx = value,
    setNameData: fn => state.names = fn(state.names || {}),
    fetch: async (url, options) => {
        calls++;
        assert.equal(new URL(url).pathname, '/glowwealth/quotes.json');
        assert.equal(options.cache, 'no-store');
        if (mode === 'network') throw new Error('offline');
        if (mode === 'timeout') { const err = new Error('timeout'); err.name = 'AbortError'; throw err; }
        return { ok: mode !== '404', status: mode === '404' ? 404 : 200,
            json: async () => mode === 'malformed' ? {} : current };
    }
};
vm.createContext(ctx);
vm.runInContext(helper + fn + '\nthis.api={ normalizeQuoteSnapshot,mergeQuoteSnapshots,quoteIsOld,pricesFromQuotes,readQuoteCache,fetchFinancialData };', ctx);

(async () => {
    const api = ctx.api;
    await api.fetchFinancialData();
    assert.equal(state.read, 'ok');
    assert.equal(state.prices.VOO, 123.45);
    assert.equal(state.fx, 31.96);
    assert.ok(storage.has('gw_quotes_v1'));
    assert.ok(!storage.has('gw_v15_txs') && !storage.has('gw_v15_divs') && !storage.has('gw_jb_key'));
    for (mode of ['404', 'malformed', 'network', 'timeout']) {
        await api.fetchFinancialData();
        assert.equal(state.read, 'error');
        assert.equal(state.prices.VOO, 123.45);
    }
    const clean = api.normalizeQuoteSnapshot(current);
    assert.equal(clean.quotes['US:VOO'].currency, 'USD');
    for (const altered of [ { price: 0 }, { price: Infinity }, { currency: 'EUR' }, { symbol: 'VT' }, { quoteTime: 'bad' } ]) {
        const bad = { ...current, quotes: { 'US:VOO': { ...current.quotes['US:VOO'], ...altered } } };
        assert.throws(() => api.normalizeQuoteSnapshot(bad));
    }
    const missing = { ...current, quotes: { 'US:QQQ': { ...current.quotes['US:VOO'], symbol: 'QQQ' } } };
    const merged = api.mergeQuoteSnapshots(clean, api.normalizeQuoteSnapshot(missing));
    assert.equal(merged.quotes['US:VOO'].status, 'stale');
    assert.equal(merged.quotes['US:QQQ'].status, 'ok');
    assert.ok(api.quoteIsOld({ ...current.quotes['US:VOO'], fetchedAt: '2020-01-01T00:00:00Z' }));
    storage.set('gw_quotes_v1', 'broken json');
    assert.equal(Object.keys(api.readQuoteCache().quotes).length, 0);
    mode = 'ok';
    ctx.refreshLock.current = true;
    const before = calls;
    await api.fetchFinancialData();
    assert.equal(calls, before);
    console.log('PASS: same-origin fetch, HTTP/JSON/offline/timeout, cache isolation, stale quotes, currency/symbol validation, overlap guard.');
})().catch(error => { console.error(error); process.exitCode = 1; });
