from . import devops_apps

def table(title, headers, rows):
    return {'title': title, 'headers': headers, 'rows': rows}

def enrich(path, data, result):
    """Attach diagnostics without changing existing response fields."""
    tables, notes = ([], [])
    rows = []
    for workers in range(1, 9):
        run = result if workers == result['workers'] else devops_apps.pipeline({**data, 'workers': workers})
        work = sum((j['end'] - j['start'] for j in run['jobs'] if j['start'] is not None))
        rows.append([workers, run['elapsed'], round(work / (workers * run['elapsed']) * 100, 2), run['status']])
    tables = [table('Worker capacity comparison', ['Workers', 'Elapsed seconds', 'Worker utilization %', 'Outcome'], rows), table('Where job time goes', ['Job', 'Ready at', 'Runner wait', 'Execution', 'Retry time'], [[j['id'], j['ready_at'], j['queue_wait'], j['execution_seconds'], j['retry_seconds']] for j in result['jobs']])]
    notes = ['Uses the same deterministic jobs, retries, and alphabetical scheduling for each capacity. Utilization includes retry time; skipped jobs consume no worker time. This is not a cloud cost prediction.', 'All timing values are seconds. Ready at is when dependencies have passed. Runner wait measures time eligible but waiting for capacity; dependency waiting is excluded. Execution includes retries. Job-seconds overlap across concurrent workers and should not be added to elapsed wall time.']
    if tables or notes:
        result['capabilities'] = {'tables': tables, 'notes': notes}
    return result
