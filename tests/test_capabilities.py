import json
import csv
import io
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from portfolio import capabilities as c, devops_apps as ops
from portfolio.db import initialize, connect, SCHEMA
from portfolio.validation import ValidationError, NotFoundError

def enhanced(path, data, function):
    return c.enrich(path, data, function(data))

class AnalysisCapabilities(unittest.TestCase):

    def test_worker_capacity_and_retry_utilization(self):
        data = {'text': json.dumps({'jobs': [{'id': 'a', 'duration': 10}, {'id': 'b', 'duration': 10, 'retries': 1, 'fail_attempts': 1}]}), 'workers': 2}
        rows = enhanced('/api/devops/pipeline', data, ops.pipeline)['capabilities']['tables'][0]['rows']
        self.assertEqual(rows[0], [1, 30, 100.0, 'passed'])
        self.assertEqual(rows[1], [2, 20, 75.0, 'passed'])
if __name__ == '__main__':
    unittest.main()
