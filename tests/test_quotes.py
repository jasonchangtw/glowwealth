import datetime as dt
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('quotes', Path(__file__).resolve().parents[1] / 'scripts/update_quotes.py')
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


class QuotesTest(unittest.TestCase):
    def daily(self):
        return [{'Code': '2330', 'Name': '台積電', 'Date': '1151008', 'ClosingPrice': '2,550.00'}]

    def yahoo(self, symbol='VOO', currency='USD'):
        return {'chart': {'result': [{'meta': {'symbol': symbol, 'currency': currency,
                'regularMarketPrice': 100.25, 'regularMarketTime': int(dt.datetime.now(q.UTC).timestamp())}}], 'error': None}}

    def test_daily_date_and_numeric(self):
        item = q.daily_quotes(self.daily(), 'TWSE', q.stamp())['TW:2330']
        self.assertEqual(item['price'], 2550)
        self.assertEqual(item['quoteTime'], '2026-10-08T13:30:00+08:00')
        self.assertEqual(item['kind'], 'close')

    def test_invalid_daily_prices(self):
        for price in ['-', 'NaN', 'Infinity', '-5', '0', None]:
            rows = self.daily()
            rows[0]['ClosingPrice'] = price
            with self.assertRaises(ValueError):
                q.daily_quotes(rows, 'TWSE', q.stamp())

    def test_mis_does_not_use_bid_or_yesterday(self):
        raw = {'msgArray': [{'c': '2330', 'z': '-', 'y': '2585', 'b': '2550', 'd': '20261008', 't': '13:30:00'}]}
        self.assertEqual(q.mis_quotes(raw, q.stamp()), {})
        raw['msgArray'][0]['z'] = '2550'
        self.assertEqual(q.mis_quotes(raw, q.stamp())['TW:2330']['price'], 2550)

    def test_yahoo_symbol_and_currency(self):
        self.assertEqual(q.yahoo_quote(self.yahoo(), 'VOO', q.stamp())['price'], 100.25)
        for raw in [self.yahoo('VT'), self.yahoo(currency='EUR'), {'chart': {'error': {'code': 'Not Found'}}}]:
            with self.assertRaises(ValueError):
                q.yahoo_quote(raw, 'VOO', q.stamp())

    def test_never_roll_back_quote_time(self):
        old = q.yahoo_quote(self.yahoo(), 'VOO', q.stamp())
        quotes = {'US:VOO': old}
        earlier = {**old, 'price': 99, 'quoteTime': '2020-01-01T00:00:00+00:00'}
        q.merge_quote(quotes, 'US:VOO', earlier)
        self.assertEqual(quotes['US:VOO']['price'], 100.25)

    def test_failure_preserves_last_good_and_marks_stale(self):
        old = q.yahoo_quote(self.yahoo(), 'VOO', q.stamp())
        previous = {'schemaVersion': 1, 'quotes': {'US:VOO': old}}
        def failed(_):
            raise RuntimeError('HTTP 429')
        result = q.collect({'us': ['VOO'], 'tw': []}, previous, failed)
        self.assertEqual(result['quotes']['US:VOO']['price'], old['price'])
        self.assertEqual(result['quotes']['US:VOO']['status'], 'stale')
        self.assertEqual(result['successfulSources'], 0)
        self.assertEqual(result['errors']['US:VOO'], 'HTTP 429')

    def test_fx_failure_does_not_block_stocks(self):
        def fake(url):
            if 'query1.finance' in url:
                return self.yahoo()
            raise RuntimeError('network failure')
        result = q.collect({'us': ['VOO'], 'tw': []}, {}, fake)
        self.assertEqual(result['quotes']['US:VOO']['status'], 'ok')
        self.assertIn('FX', result['errors'])

    def test_private_fields_not_published(self):
        old = q.yahoo_quote(self.yahoo(), 'VOO', q.stamp())
        old['transactions'] = [{'shares': 42}]
        clean = q.clean_previous({'schemaVersion': 1, 'quotes': {'US:VOO': old}})
        self.assertNotIn('transactions', clean['US:VOO'])


if __name__ == '__main__':
    unittest.main()
