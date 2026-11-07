import json
import unittest
from portfolio import devops_apps as d
from portfolio.validation import ValidationError

def plan(jobs, workers=2):
    return d.pipeline({'text': json.dumps({'jobs': jobs}), 'workers': workers})

def manifest():
    return {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'spec': {'replicas': 2, 'selector': {'matchLabels': {'app': 'demo'}}, 'template': {'metadata': {'labels': {'app': 'demo'}}, 'spec': {'securityContext': {'runAsNonRoot': True, 'seccompProfile': {'type': 'RuntimeDefault'}}, 'containers': [{'name': 'api', 'image': 'example.invalid/api@sha256:' + 'a' * 64, 'resources': {'requests': {'cpu': '100m', 'memory': '64Mi'}, 'limits': {'cpu': '500m', 'memory': '128Mi'}}, 'readinessProbe': {'httpGet': {}}, 'livenessProbe': {'exec': {}}, 'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}}}]}}}}

class DevOpsTests(unittest.TestCase):

    def test_embedded_documents_reject_duplicate_and_nonfinite_json(self):
        for text in ['{"jobs":[],"jobs":[]}', '{"metadata":{"x":NaN}}', '{"metadata":{"x":1e999}}', '{"x":' + '[' * 100 + '0' + ']' * 100 + '}']:
            with self.subTest(text=text[:50]), self.assertRaises(ValidationError):
                d.document({'text': text})

    def test_parallel_scheduling_and_critical_path(self):
        jobs = [{'id': 'a', 'duration': 10}, {'id': 'b', 'duration': 20}, {'id': 'c', 'needs': ['a', 'b'], 'duration': 5}]
        parallel = plan(jobs)
        self.assertEqual((parallel['elapsed'], parallel['ideal_critical_path']), (25, 25))
        self.assertEqual(plan(jobs, 1)['elapsed'], 35)
        self.assertEqual(parallel['jobs'][-1]['start'], 20)

    def test_queue_time_excludes_dependencies_and_separates_retries(self):
        jobs = [{'id': 'a', 'duration': 10, 'retries': 1, 'fail_attempts': 1}, {'id': 'b', 'duration': 5}, {'id': 'c', 'needs': ['a'], 'duration': 6}]
        serial = plan(jobs, 1)
        parallel = plan(jobs, 2)
        records = {job['id']: job for job in serial['jobs']}
        self.assertEqual(serial['ideal_critical_jobs'], ['a', 'c'])
        self.assertEqual(serial['ideal_critical_path'], 16)
        self.assertEqual((serial['elapsed'], serial['work_seconds'], serial['retry_job_seconds']), (31, 31, 10))
        self.assertEqual((records['b']['ready_at'], records['b']['queue_wait']), (0, 20))
        self.assertEqual((records['c']['ready_at'], records['c']['queue_wait']), (20, 5))
        self.assertEqual(serial['queued_job_seconds'], 25)
        self.assertEqual((parallel['elapsed'], parallel['queued_job_seconds'], parallel['work_seconds']), (26, 0, 31))

    def test_critical_chain_ties_are_deterministic_and_skips_have_no_wait(self):
        jobs = [{'id': 'z', 'duration': 10}, {'id': 'a', 'duration': 10}, {'id': 'last', 'needs': ['z', 'a'], 'duration': 5}]
        self.assertEqual(plan(jobs)['ideal_critical_jobs'], ['a', 'last'])
        self.assertEqual(plan(list(reversed(jobs)))['ideal_critical_jobs'], ['a', 'last'])
        failed = plan([{'id': 'a', 'duration': 10, 'fail_attempts': 1}, {'id': 'b', 'needs': ['a'], 'duration': 5}])
        skipped = next((job for job in failed['jobs'] if job['id'] == 'b'))
        self.assertIsNone(skipped['ready_at'])
        self.assertIsNone(skipped['queue_wait'])
        self.assertEqual(skipped['execution_seconds'], 0)

    def test_retry_success_and_exhaustion_skip(self):
        jobs = [{'id': 'build', 'duration': 10, 'retries': 1, 'fail_attempts': 1}, {'id': 'deploy', 'needs': ['build'], 'duration': 5}]
        r = plan(jobs)
        self.assertEqual((r['elapsed'], r['status'], r['jobs'][0]['attempts']), (25, 'passed', 2))
        jobs[0]['fail_attempts'] = 2
        r = plan(jobs)
        self.assertEqual((r['elapsed'], r['status'], r['jobs'][1]['status']), (20, 'failed', 'skipped'))

    def test_failure_propagates_transitively_but_independent_job_finishes(self):
        r = plan([{'id': 'a', 'duration': 1, 'fail_attempts': 1}, {'id': 'b', 'needs': ['a'], 'duration': 2}, {'id': 'c', 'needs': ['b'], 'duration': 2}, {'id': 'z', 'duration': 8}])
        states = {j['id']: j['status'] for j in r['jobs']}
        self.assertEqual(states, {'a': 'failed', 'b': 'skipped', 'c': 'skipped', 'z': 'passed'})
        self.assertEqual(r['elapsed'], 8)

    def test_cycles_missing_dependencies_duplicate_ids_and_bool_rejected(self):
        invalid = [[{'id': 'a', 'duration': 1, 'needs': ['a']}], [{'id': 'a', 'duration': 1, 'needs': ['missing']}], [{'id': 'a', 'duration': 1}, {'id': 'a', 'duration': 2}], [{'id': 'a', 'duration': True}]]
        for jobs in invalid:
            with self.assertRaises(ValidationError):
                plan(jobs)

    def test_worker_capacity_never_exceeded(self):
        r = plan([{'id': f'job-{i}', 'duration': i + 1} for i in range(10)], 3)
        for time in range(r['elapsed']):
            self.assertLessEqual(sum((j['start'] <= time < j['end'] for j in r['jobs'])), 3)
