"""Verificação local das proteções de gravação, sem simular execução Spark."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from spark.experiment import write_parquet_outputs


class StorageTests(unittest.TestCase):
    def test_existing_output_is_preserved_even_if_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'previous'
            destination.mkdir()
            sentinel = destination / 'keep.txt'
            sentinel.write_text('previous result', encoding='utf-8')
            daily, monthly = Mock(), Mock()
            with self.assertRaises(FileExistsError):
                write_parquet_outputs(daily, monthly, destination)
            daily.write.mode.assert_not_called()
            monthly.write.mode.assert_not_called()
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'previous result')

    def test_partial_failure_requires_new_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'new'
            daily, monthly = Mock(), Mock()
            daily.write.mode.return_value.parquet.side_effect = RuntimeError('write failed')
            with self.assertRaises(RuntimeError):
                write_parquet_outputs(daily, monthly, destination)
            self.assertTrue(destination.is_dir())
            monthly.write.mode.assert_not_called()
            with self.assertRaises(FileExistsError):
                write_parquet_outputs(Mock(), Mock(), destination)

    def test_supported_mode_is_scoped_to_new_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            previous = parent / 'previous'
            previous.mkdir()
            sentinel = previous / 'data.txt'
            sentinel.write_text('keep', encoding='utf-8')
            destination = parent / 'new'
            daily, monthly = Mock(), Mock()
            write_parquet_outputs(daily, monthly, destination)
            daily.write.mode.assert_called_once_with('overwrite')
            monthly.write.mode.assert_called_once_with('overwrite')
            daily.write.mode.return_value.parquet.assert_called_once_with(str(destination/'gold_daily'))
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'keep')


if __name__ == '__main__':
    unittest.main()
