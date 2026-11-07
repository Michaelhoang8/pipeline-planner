import heapq
from .json_input import decode
import re
from .validation import ValidationError, integer

def document(data):
    text = data.get('text')
    if not isinstance(text, str) or not text.strip() or len(text.encode()) > 200000:
        raise ValidationError('Provide a JSON object of 1–200,000 bytes')
    try:
        value = decode(text)
    except (ValueError, RecursionError):
        raise ValidationError('Input must be valid JSON') from None
    if not isinstance(value, dict):
        raise ValidationError('Input must be a JSON object')
    return value

def obj(value, name):
    if not isinstance(value, dict):
        raise ValidationError(f'{name} must be an object')
    return value

def pipeline(data):
    doc = document(data)
    workers = integer(data, 'workers', 1, 8) if 'workers' in data else 2
    items = doc.get('jobs')
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        raise ValidationError('Provide 1–50 jobs')
    jobs = {}
    for item in items:
        item = obj(item, 'job')
        name = item.get('id')
        if not isinstance(name, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,60}', name) or name in jobs:
            raise ValidationError('Job IDs must be unique, 1–60 letters/digits/underscores/hyphens')
        needs = item.get('needs', [])
        if not isinstance(needs, list) or any((not isinstance(n, str) for n in needs)) or len(set(needs)) != len(needs):
            raise ValidationError('needs must contain unique job ID strings')
        duration = integer(item, 'duration', 1, 3600)
        retries = integer(item, 'retries', 0, 3) if 'retries' in item else 0
        failures = integer(item, 'fail_attempts', 0, 4) if 'fail_attempts' in item else 0
        jobs[name] = {'needs': needs, 'duration': duration, 'retries': retries, 'fail_attempts': failures}
    if any((dep not in jobs for job in jobs.values() for dep in job['needs'])):
        raise ValidationError('Every dependency must name an existing job')
    ordered = []
    while len(ordered) < len(jobs):
        ready = sorted((name for name, job in jobs.items() if name not in ordered and all((dep in ordered for dep in job['needs']))))
        if not ready:
            raise ValidationError('Pipeline contains a dependency cycle')
        ordered.extend(ready)
    critical = {}
    predecessor = {}
    for name in ordered:
        parent = min(jobs[name]['needs'], key=lambda dep: (-critical[dep], dep), default=None)
        predecessor[name] = parent
        critical[name] = jobs[name]['duration'] + (critical[parent] if parent else 0)
    terminal = min(critical, key=lambda name: (-critical[name], name))
    chain = []
    while terminal is not None:
        chain.append(terminal)
        terminal = predecessor[terminal]
    chain.reverse()
    pending = set(jobs)
    results = {}
    running = []
    now = 0
    while pending or running:
        while running and running[0][0] <= now:
            _, name = heapq.heappop(running)
            results[name]['status'] = 'failed' if jobs[name]['fail_attempts'] > jobs[name]['retries'] else 'passed'
        changed = True
        while changed:
            changed = False
            for name in sorted(pending):
                if any((results.get(dep, {}).get('status') in ('failed', 'skipped') for dep in jobs[name]['needs'])):
                    results[name] = {'id': name, 'status': 'skipped', 'start': None, 'end': None, 'attempts': 0, 'needs': jobs[name]['needs']}
                    pending.remove(name)
                    changed = True
        ready = sorted((name for name in pending if all((results.get(dep, {}).get('status') == 'passed' for dep in jobs[name]['needs']))))
        for name in ready[:workers - len(running)]:
            job = jobs[name]
            attempts = min(job['fail_attempts'] + 1, job['retries'] + 1)
            end = now + job['duration'] * attempts
            results[name] = {'id': name, 'status': 'running', 'start': now, 'end': end, 'attempts': attempts, 'needs': job['needs']}
            heapq.heappush(running, (end, name))
            pending.remove(name)
        if running:
            now = running[0][0]
        elif pending:
            raise ValidationError('Pipeline cannot progress')
    timeline = sorted(results.values(), key=lambda r: (r['start'] is None, r['start'] or 0, r['id']))
    for job in timeline:
        if job['start'] is None:
            job.update(ready_at=None, queue_wait=None, execution_seconds=0, retry_seconds=0)
        else:
            ready_at = max((results[dep]['end'] for dep in job['needs']), default=0)
            execution = job['end'] - job['start']
            job.update(ready_at=ready_at, queue_wait=job['start'] - ready_at, execution_seconds=execution, retry_seconds=execution - jobs[job['id']]['duration'])
    return {'jobs': timeline, 'workers': workers, 'elapsed': now, 'ideal_critical_path': max(critical.values()), 'ideal_critical_jobs': chain, 'work_seconds': sum((j['execution_seconds'] for j in timeline)), 'queued_job_seconds': sum((j['queue_wait'] or 0 for j in timeline)), 'retry_job_seconds': sum((j['retry_seconds'] for j in timeline)), 'status': 'failed' if any((r['status'] == 'failed' for r in timeline)) else 'passed', 'note': 'Deterministic simulation only. No commands execute. Alphabetical scheduling; retries hold a worker without backoff. Ideal critical path assumes unlimited workers and first-attempt success.'}
