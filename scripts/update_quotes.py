#!/usr/bin/env python3
"""Public quotes only. No account, API key, holdings, or transaction input."""
import argparse
import concurrent.futures
import datetime as dt
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, urlencode

UTC = dt.timezone.utc
TAIPEI = dt.timezone(dt.timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
TWSE = 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'
TPEX = 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes'


def stamp():
    return dt.datetime.now(UTC).isoformat(timespec='seconds')


def positive(value):
    try:
        number = float(str(value).replace(',', '').strip())
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def date_stamp(value):
    text = str(value).replace('/', '').replace('-', '')
    if len(text) == 7 and text.isdigit():
        text = str(int(text[:3]) + 1911) + text[3:]
    if len(text) != 8 or not text.isdigit():
        raise ValueError('Invalid quote date')
    value = dt.datetime.strptime(text, '%Y%m%d').replace(hour=13, minute=30, tzinfo=TAIPEI)
    return value.isoformat()


def valid_quote(key, value):
    if not isinstance(value, dict) or not isinstance(key, str):
        return False
    market = value.get('market')
    if market not in ('TW', 'US') or key != market + ':' + str(value.get('symbol', '')):
        return False
    if value.get('currency') != ('TWD' if market == 'TW' else 'USD') or not positive(value.get('price')):
        return False
    try:
        date = dt.datetime.fromisoformat(value['quoteTime'].replace('Z', '+00:00'))
        return date.tzinfo is not None and date <= dt.datetime.now(UTC) + dt.timedelta(minutes=5)
    except (ValueError, KeyError, TypeError):
        return False


def fetch_json(url):
    # curl verifies TLS using the host certificate store; Ubuntu runner includes it.
    proc = subprocess.run([
        'curl', '--silent', '--show-error', '--location', '--max-time', '18',
        '--retry', '1', '--retry-delay', '2', '--retry-max-time', '25',
        '--user-agent', 'Mozilla/5.0 (compatible; GlowWealthQuoteCollector/1.0)',
        '--write-out', '\n%{http_code}', url
    ], capture_output=True, text=True, timeout=45)
    if proc.returncode:
        raise RuntimeError('Network request failed or timed out')
    body, _, code = proc.stdout.rpartition('\n')
    if code != '200':
        raise RuntimeError('HTTP ' + code)
    try:
        return json.loads(body)
    except ValueError as exc:
        raise RuntimeError('Invalid JSON from provider') from exc


def daily_quotes(rows, source, fetched_at):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Empty or invalid daily response')
    result = {}
    for row in rows:
        symbol = str(row.get('Code' if source == 'TWSE' else 'SecuritiesCompanyCode', '')).upper()
        # Stock/ETF symbols (including A/B tails). Exclude warrants and malformed IDs.
        if not re.fullmatch(r'\d{4,6}[A-Z]?', symbol):
            continue
        price = positive(row.get('ClosingPrice' if source == 'TWSE' else 'Close'))
        if price is None:
            continue
        try:
            quote_time = date_stamp(row.get('Date', ''))
        except ValueError:
            continue
        item = {'symbol': symbol, 'market': 'TW', 'currency': 'TWD', 'price': price,
                'name': row.get('Name' if source == 'TWSE' else 'CompanyName', ''),
                'venue': 'tse' if source == 'TWSE' else 'otc',
                'quoteTime': quote_time, 'fetchedAt': fetched_at,
                'source': source + ' OpenAPI', 'kind': 'close', 'status': 'ok'}
        if valid_quote('TW:' + symbol, item):
            result['TW:' + symbol] = item
    if not result:
        raise ValueError('No valid daily quotes')
    return result


def mis_quotes(payload, fetched_at):
    if not isinstance(payload, dict) or not isinstance(payload.get('msgArray'), list):
        raise ValueError('Invalid MIS response')
    result = {}
    for row in payload['msgArray']:
        symbol = str(row.get('c', '')).upper()
        if not re.fullmatch(r'\d{4,6}[A-Z]?', symbol):
            continue
        # '-' means no last trade; never substitute bid, ask, or yesterday's price.
        price = positive(row.get('z'))
        if price is None:
            continue
        try:
            date = date_stamp(row.get('d', ''))
            clock = row.get('t', '')
            if not re.fullmatch(r'\d{2}:\d{2}:\d{2}', clock):
                continue
            quote_time = date[:11] + clock + '+08:00'
            dt.datetime.fromisoformat(quote_time)
        except ValueError:
            continue
        item = {'symbol': symbol, 'market': 'TW', 'currency': 'TWD', 'price': price,
                'name': row.get('n', ''), 'venue': row.get('ex', ''),
                'quoteTime': quote_time, 'fetchedAt': fetched_at,
                'source': 'TWSE MIS', 'kind': 'trade', 'status': 'ok'}
        if valid_quote('TW:' + symbol, item):
            result['TW:' + symbol] = item
    return result


def yahoo_quote(payload, symbol, fetched_at):
    chart = payload.get('chart', {}) if isinstance(payload, dict) else {}
    if chart.get('error') or not chart.get('result'):
        raise ValueError('Yahoo missing result or chart.error')
    meta = chart['result'][0].get('meta', {})
    if meta.get('symbol', '').upper() != symbol or meta.get('currency') != 'USD':
        raise ValueError('Yahoo symbol/currency mismatch')
    price = positive(meta.get('regularMarketPrice'))
    timestamp = positive(meta.get('regularMarketTime'))
    if price is None or timestamp is None:
        raise ValueError('Yahoo missing price/time')
    item = {'symbol': symbol, 'market': 'US', 'currency': 'USD', 'price': price,
            'name': meta.get('shortName') or meta.get('longName') or symbol,
            'quoteTime': dt.datetime.fromtimestamp(timestamp, UTC).isoformat(),
            'fetchedAt': fetched_at, 'source': 'Yahoo chart', 'kind': 'trade', 'status': 'ok'}
    if not valid_quote('US:' + symbol, item):
        raise ValueError('Invalid Yahoo quote')
    return item


def merge_quote(quotes, key, new):
    old = quotes.get(key)
    if old and valid_quote(key, old):
        before = dt.datetime.fromisoformat(old['quoteTime'].replace('Z', '+00:00'))
        after = dt.datetime.fromisoformat(new['quoteTime'].replace('Z', '+00:00'))
        if before > after:
            return
    quotes[key] = new


def clean_previous(payload):
    if not isinstance(payload, dict) or payload.get('schemaVersion') != 1:
        return {}
    raw = payload.get('quotes', {})
    if not isinstance(raw, dict):
        return {}
    allowed = ('symbol', 'market', 'currency', 'price', 'name', 'venue', 'quoteTime',
               'fetchedAt', 'source', 'kind', 'status', 'error')
    # Whitelist fields so old public snapshots cannot carry private ledger data.
    return {k: {field: v[field] for field in allowed if field in v}
            for k, v in raw.items() if valid_quote(k, v)}


def collect(config, previous, get=fetch_json):
    now = stamp()
    quotes = clean_previous(previous)
    for item in quotes.values():
        item['status'] = 'stale'
        item['error'] = 'No successful update in this collection'
    errors = {}
    successes = 0
    for source, url in [('TWSE', TWSE), ('TPEx', TPEX)]:
        try:
            items = daily_quotes(get(url), source, now)
            for key, item in items.items():
                merge_quote(quotes, key, item)
            successes += 1
        except Exception as exc:
            errors[source] = str(exc)

    tw_symbols = sorted(set(config.get('tw', [])))
    for start in range(0, len(tw_symbols), 40):
        batch = tw_symbols[start:start + 40]
        channels = []
        for symbol in batch:
            known = quotes.get('TW:' + symbol, {})
            venues = [known['venue']] if known.get('venue') in ('tse', 'otc') else ['tse', 'otc']
            channels.extend(venue + '_' + symbol + '.tw' for venue in venues)
        try:
            items = mis_quotes(get('https://mis.twse.com.tw/stock/api/getStockInfo.jsp?' +
                                  urlencode({'ex_ch': '|'.join(channels), 'json': '1', 'delay': '0'})), now)
            for key, item in items.items():
                merge_quote(quotes, key, item)
            if items:
                successes += 1
            for symbol in batch:
                if 'TW:' + symbol not in items:
                    errors['TW:' + symbol] = 'No valid MIS last trade; using daily/previous quote if available'
        except Exception as exc:
            errors['MIS'] = str(exc)

    def get_us(symbol):
        return yahoo_quote(get('https://query1.finance.yahoo.com/v8/finance/chart/' +
                               quote(symbol, safe='') + '?interval=1d&range=5d'), symbol, now)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(get_us, symbol): symbol for symbol in sorted(set(config.get('us', [])))}
        for job in concurrent.futures.as_completed(jobs):
            symbol = jobs[job]
            try:
                merge_quote(quotes, 'US:' + symbol, job.result())
                successes += 1
            except Exception as exc:
                errors['US:' + symbol] = str(exc)

    fx = previous.get('fx') if isinstance(previous, dict) else None
    fx = {key: fx[key] for key in ('rate', 'quoteTime', 'fetchedAt', 'source', 'status') if key in fx} if isinstance(fx, dict) and positive(fx.get('rate')) else None
    if fx:
        fx['status'] = 'stale'
    try:
        data = get('https://open.er-api.com/v6/latest/USD')
        rate = positive(data.get('rates', {}).get('TWD'))
        epoch = positive(data.get('time_last_update_unix'))
        if data.get('result') != 'success' or rate is None or epoch is None:
            raise ValueError('Invalid FX response')
        fx = {'rate': rate, 'quoteTime': dt.datetime.fromtimestamp(epoch, UTC).isoformat(),
              'fetchedAt': now, 'source': 'ExchangeRate-API public', 'status': 'ok'}
    except Exception as exc:
        errors['FX'] = str(exc)

    return {'schemaVersion': 1, 'generatedAt': now, 'quotes': dict(sorted(quotes.items())),
            'fx': fx, 'errors': errors, 'successfulSources': successes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(ROOT / 'quote-symbols.json'))
    parser.add_argument('--output', default=str(ROOT / 'quotes.json'))
    parser.add_argument('--previous-url', default='')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    for market, pattern in [('tw', r'\d{4,6}[A-Z]?'), ('us', r'[A-Z][A-Z0-9.\-^=]{0,19}')]:
        values = config.get(market, [])
        if not isinstance(values, list) or len(values) > 200 or any(not isinstance(v, str) or not re.fullmatch(pattern, v) for v in values):
            raise SystemExit('Invalid or excessive symbols in quote-symbols.json')
    out = Path(args.output)
    previous = {}
    if out.exists():
        try:
            previous = json.loads(out.read_text())
        except ValueError:
            pass
    if args.previous_url:
        try:
            remote = fetch_json(args.previous_url)
            if clean_previous(remote):
                # Merge instead of erasing valid bundled fallback quotes.
                prior = clean_previous(previous)
                for key, value in clean_previous(remote).items():
                    merge_quote(prior, key, value)
                previous = {**remote, 'quotes': prior}
        except Exception:
            print('Previous published snapshot unavailable; using bundled snapshot.', file=sys.stderr)
    payload = collect(config, previous)
    if not payload['quotes']:
        for key, message in payload['errors'].items():
            print(key + ': ' + message, file=sys.stderr)
        raise SystemExit('No valid quotes; refusing to publish an empty snapshot.')
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
    temporary.replace(out)
    print('Saved', len(payload['quotes']), 'public quotes;', payload['successfulSources'], 'successful sources;', len(payload['errors']), 'warnings.')
    for key, message in payload['errors'].items():
        print(key + ': ' + message, file=sys.stderr)


if __name__ == '__main__':
    main()
