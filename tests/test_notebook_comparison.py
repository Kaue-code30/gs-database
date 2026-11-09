"""Regressões do comparador incorporado no notebook, sem depender de Spark."""
import ast
import csv
import tempfile
import textwrap
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


class NotebookComparisonTests(unittest.TestCase):
    def compare(self, actual, expected):
        # Executar a própria função incluída no notebook, não uma cópia do algoritmo.
        builder = ast.parse((ROOT/'spark/build_notebook.py').read_text(encoding='utf-8'))
        cell = next(node.args[0].value for node in ast.walk(builder)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'code' and node.args and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str) and 'def compare_reference(' in node.args[0].value)
        parsed = ast.parse(textwrap.dedent(cell))
        parsed.body = [node for node in parsed.body if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'reference').mkdir()
            with (root/'reference/monthly.csv').open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(expected))
                writer.writeheader()
                writer.writerow(expected)
            scope = {'run_root': root}
            exec(compile(parsed, '<notebook-comparator>', 'exec'), scope)
            frame, row = Mock(), Mock()
            row.asDict.return_value = actual
            frame.select.return_value.collect.return_value = [row]
            return scope['compare_reference'](frame, 'monthly.csv', ('municipality_id', 'month'))

    def test_spark_decimals_match_reference_with_rounding(self):
        expected = {'municipality_id': '3548500', 'month': '2023-02',
            'coverage_pct': '100.0', 'heavy_days_pct': '7.142857142857143'}
        actual = dict(expected, municipality_id=3548500, coverage_pct=Decimal('100.00000000000000'),
            heavy_days_pct=Decimal('7.14285714285714'))
        self.assertEqual(self.compare(actual, expected)['differences'], 0)

    def test_decimal_zero_and_null_are_distinct(self):
        expected = {'municipality_id': '3548500', 'month': '2023-01', 'heavy_days_pct': '0.0'}
        actual = dict(expected, municipality_id=3548500, heavy_days_pct=Decimal('0E-14'))
        self.assertEqual(self.compare(actual, expected)['differences'], 0)
        actual['heavy_days_pct'] = None
        with self.assertRaises(AssertionError):
            self.compare(actual, expected)

    def test_numeric_difference_outside_tolerance_still_rejected(self):
        expected = {'municipality_id': '3548500', 'month': '2023-01', 'coverage_pct': '100.0'}
        actual = dict(expected, municipality_id=3548500, coverage_pct=Decimal('99.9'))
        with self.assertRaises(AssertionError):
            self.compare(actual, expected)


if __name__ == '__main__':
    unittest.main()
