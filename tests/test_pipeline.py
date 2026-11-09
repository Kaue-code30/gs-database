"""Dados sintéticos exclusivamente nos testes; produção só consome fontes reais."""
import contextlib
import copy
import gzip
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pipeline as p


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((p.ROOT / 'config.json').read_text(encoding='utf-8'))
        self.config['start_date'] = '2024-01-01'
        self.config['end_date'] = '2024-01-10'
        self.config['municipalities'] = self.config['municipalities'][:1]
        self.city = self.config['municipalities'][0]
        self.metadata = {'id': self.city['id'], 'nome': 'São Paulo',
            'regiao-imediata': {'nome': 'São Paulo', 'regiao-intermediaria': {'UF': {'sigla': 'SP'}}}}
        self.weather = {'timezone': 'America/Sao_Paulo', 'latitude': -23.5, 'longitude': -46.5,
            'daily_units': {'precipitation_sum': 'mm'}, 'daily': {
                'time': [(date(2024, 1, 1)+timedelta(days=i)).isoformat() for i in range(10)],
                'precipitation_sum': [float(i*10) for i in range(10)]}}

    def rows(self):
        return p.clean_city(self.city, self.metadata, self.weather, self.config)

    def test_join_and_grid_provenance(self):
        rows = self.rows()
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]['uf'], 'SP')
        self.assertEqual(rows[0]['grid_latitude'], -23.5)
        self.assertNotEqual(rows[0]['requested_latitude'], rows[0]['grid_latitude'])

    def test_mismatching_municipality_rejected(self):
        self.metadata['id'] = 1
        with self.assertRaises(ValueError):
            self.rows()

    def test_invalid_values_rejected(self):
        for value in [-1, float('nan'), float('inf'), '12', True]:
            with self.subTest(value=value):
                self.weather['daily']['precipitation_sum'][0] = value
                with self.assertRaises(ValueError):
                    self.rows()

    def test_invalid_units_and_timezone_rejected(self):
        self.weather['daily_units']['precipitation_sum'] = 'inch'
        with self.assertRaises(ValueError):
            self.rows()
        self.weather['daily_units']['precipitation_sum'] = 'mm'
        self.weather['timezone'] = 'UTC'
        with self.assertRaises(ValueError):
            self.rows()

    def test_missing_duplicate_and_misaligned_dates_rejected(self):
        original = copy.deepcopy(self.weather)
        for kind in ('missing', 'duplicate', 'length', 'order'):
            with self.subTest(kind=kind):
                self.weather = copy.deepcopy(original)
                days = self.weather['daily']['time']
                if kind == 'missing':
                    days.pop()
                    self.weather['daily']['precipitation_sum'].pop()
                elif kind == 'duplicate':
                    days[1] = days[0]
                elif kind == 'length':
                    self.weather['daily']['precipitation_sum'].pop()
                else:
                    days.reverse()
                with self.assertRaises(ValueError):
                    self.rows()

    def test_calendar_windows_and_antecedent_excludes_today(self):
        rows = p.features(self.rows(), self.config)
        self.assertIsNone(rows[1]['rain_3d_mm'])
        self.assertEqual(rows[2]['rain_3d_mm'], 30)
        self.assertEqual(rows[6]['rain_7d_mm'], 210)
        self.assertIsNone(rows[6]['antecedent_7d_mm'])
        self.assertEqual(rows[7]['antecedent_7d_mm'], 210)
        self.assertEqual(rows[7]['rain_7d_mm'], 280)
        self.assertEqual(rows[5]['heavy_day'], 1)  # limite inclusivo de 50 mm

    def test_missing_value_propagates_without_turning_into_zero(self):
        self.weather['daily']['precipitation_sum'][1] = None
        rows = p.features(self.rows(), self.config)
        self.assertIsNone(rows[1]['heavy_day'])
        self.assertIsNone(rows[3]['rain_3d_mm'])
        self.assertEqual(rows[4]['rain_3d_mm'], 90)
        monthly = p.aggregate(rows, self.config)[0]
        self.assertEqual(monthly['valid_days'], 9)
        self.assertEqual(monthly['coverage_pct'], 90)
        self.assertAlmostEqual(monthly['heavy_days_pct'], 100*5/9)

    def test_calendar_gap_invalidates_window(self):
        rows = self.rows()
        del rows[1]
        result = p.features(rows, self.config)
        self.assertIsNone(result[1]['rain_3d_mm'])
        self.assertIsNone(result[2]['rain_3d_mm'])
        self.assertEqual(result[3]['rain_3d_mm'], 90)

    def test_windows_never_cross_city_boundary(self):
        rows = self.rows()
        other = [dict(r, municipality_id=999, precipitation_mm=1.0) for r in rows]
        result = p.features(rows+other, self.config)
        group = [r for r in result if r['municipality_id'] == 999]
        self.assertIsNone(group[1]['rain_3d_mm'])
        self.assertEqual(group[2]['rain_3d_mm'], 3)

    def test_all_null_month_has_no_total_or_rate(self):
        self.weather['daily']['precipitation_sum'] = [None]*10
        monthly = p.aggregate(p.features(self.rows(), self.config), self.config)[0]
        self.assertIsNone(monthly['total_mm'])
        self.assertIsNone(monthly['heavy_days_pct'])
        self.assertIsNone(monthly['wilson_low_pct'])
        self.assertEqual(monthly['coverage_pct'], 0)

    def test_wilson_and_percentile_known_values(self):
        self.assertEqual(p.percentile([0, 10, 20], .95), 19)
        self.assertIsNone(p.percentile([], .95))
        low, high = p.wilson(5, 10)
        self.assertAlmostEqual(low, 23.6593, places=4)
        self.assertAlmostEqual(high, 76.3407, places=4)

    def test_gzip_response(self):
        body = gzip.compress(b'{"ok":true}')
        with patch('urllib.request.urlopen', return_value=io.BytesIO(body)):
            raw, value = p.fetch('https://example.test')
        self.assertEqual(raw, body)
        self.assertEqual(value, {'ok': True})

    def snapshot(self, directory):
        entries = []
        for source, value in [('ibge', self.metadata), ('weather', self.weather)]:
            filename = f'{self.city["id"]}_{source}.json'
            p.write_json(directory / filename, value)
            body = (directory / filename).read_bytes()
            (directory / (filename+'.body')).write_bytes(body)
            checksum = hashlib.sha256(body).hexdigest()
            entries.append({'municipality_id': self.city['id'], 'source': source,
                'file': filename, 'body_sha256': checksum, 'json_sha256': checksum})
        p.write_json(directory / 'manifest.json', {'config': self.config, 'sources': entries})

    def test_end_to_end_and_replay_produce_identical_tables(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bronze = root / 'bronze'
            self.snapshot(bronze)
            with contextlib.redirect_stdout(io.StringIO()):
                p.process(bronze, root / 'first')
                p.process(bronze, root / 'second')
            self.assertEqual((root/'first/gold/daily.csv').read_bytes(), (root/'second/gold/daily.csv').read_bytes())
            self.assertEqual((root/'first/gold/monthly.csv').read_bytes(), (root/'second/gold/monthly.csv').read_bytes())
            quality = json.loads((root/'first/quality.json').read_text())
            self.assertEqual(quality['rows'], 10)
            with contextlib.closing(sqlite3.connect(root/'first/analytics.sqlite')) as db, db:
                self.assertEqual(db.execute('SELECT count(*) FROM gold_daily').fetchone()[0], 10)
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute('INSERT INTO gold_daily SELECT * FROM gold_daily LIMIT 1')

    def test_partial_calendar_month_excluded_from_ranking(self):
        monthly = p.aggregate(p.features(self.rows(), self.config), self.config)[0]
        self.assertEqual(monthly['coverage_pct'], 100)
        self.assertEqual(monthly['full_calendar_month'], 0)

    def test_tampered_and_incomplete_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.snapshot(root)
            target = root / f'{self.city["id"]}_weather.json'
            target.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Checksum'):
                p.verify_snapshot(root)
            manifest = json.loads((root/'manifest.json').read_text())
            manifest['sources'].pop()
            p.write_json(root/'manifest.json', manifest)
            with self.assertRaisesRegex(ValueError, 'incompleto'):
                p.verify_snapshot(root)


if __name__ == '__main__':
    unittest.main()
