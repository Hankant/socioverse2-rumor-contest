import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
d=root/'results/completed_run'
rows=json.loads((d/'metrics_history.json').read_text(encoding='utf-8'))['rows']
assert rows[-1]['step']==40 and rows[-1]['remaining_agents']==581
assert rows[-1]['technical_dropout_count']==1
counts={}
for line in (d/'actions.jsonl').read_text(encoding='utf-8').splitlines():
    a=json.loads(line);counts.setdefault(a['tick'],set()).add(a['agent_id'])
assert set(counts)==set(range(1,41)) and all(len(v)==582 for v in counts.values())
for name,expected in json.loads((root/'MANIFEST.json').read_text()).items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected, name
print('40 completed ticks, 582 identities/tick, 1 dropout; package hashes verified')
