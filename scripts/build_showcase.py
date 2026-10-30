"""Build the offline contest viewer from committed V7 results (stdlib only).

No model calls. Inputs and derived counts are validated before replacing the page.
"""
from pathlib import Path
import csv
import hashlib
import json
from collections import Counter
from showcase_assets import load_assets

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results/v7_20261030'
SOURCES = {
    'scenarios': 'fb/data/FB_scenarios.csv',
    'states': 'complete54/data/all_committed_user_states.csv',
    'counts': 'complete54/data/per_tick_counts.csv',
    'users': 'fb/data/FB_users.csv',
}


def rows(name):
    with (RESULTS / SOURCES[name]).open(encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def number(value):
    return float(value) if value else None


def build_data():
    cases = {}
    for row in rows('scenarios'):
        cid = row.pop('case_id')
        assert cid not in cases, cid
        cases[cid] = {'id': cid, 'summary': {k: number(v) for k, v in row.items()},
                      'agents': {}, 'ticks': [[] for _ in range(11)], 'fb': {}}
    assert len(cases) == 54
    total = 0
    for row in rows('states'):
        case = cases[row['case_id']]
        assert row['complete'] == 'True'
        tick, aid = int(row['step']), row['agent_id']
        assert 0 <= tick <= 10
        agent = [aid, row['group'], row['synthetic_age'], row['synthetic_region'],
                 row['synthetic_occupation'], row['synthetic_mbti_type']]
        if aid in case['agents']:
            assert case['agents'][aid] == agent
        case['agents'][aid] = agent
        belief = {'unjudged': 0, 'believe': 1, 'reject': 2}[row['belief']]
        score = number(row['subjective_credibility'])
        assert (score is None and belief == 0) or (score is not None and 0 <= score <= 100 and belief == (1 if score > 50 else 2))
        case['ticks'][tick].append([aid, belief, score, int(row['rumor_seen'] == 'True'), int(row['official_seen'] == 'True')])
        total += 1
    for case in cases.values():
        case['agents'] = sorted(case['agents'].values())
        ids = [a[0] for a in case['agents']]
        assert len(ids) == 300
        for i, tick in enumerate(case['ticks']):
            tick.sort()
            assert [r[0] for r in tick] == ids, (case['id'], i)
            case['ticks'][i] = [r[1:] for r in tick]
    # Independently reconcile every plotted state count against published aggregates.
    aggregate_rows = 0
    for row in rows('counts'):
        case = cases[row['case_id']]
        state = case['ticks'][int(row['tick'])]
        selected = [s for a, s in zip(case['agents'], state) if row['group'] == 'all' or a[1] == row['group']]
        counts = Counter(s[0] for s in selected)
        assert len(selected) == int(row['n'])
        for code, name in enumerate(('unjudged', 'believe', 'reject')):
            assert counts[code] == int(row[name]), (case['id'], row['tick'], name)
        assert sum(s[2] for s in selected) == int(row['rumor_seen'])
        assert sum(s[3] for s in selected) == int(row['official_seen'])
        aggregate_rows += 1
    assert aggregate_rows == 54 * 11 * 3
    for row in rows('users'):
        cases[row['case_id']]['fb'][row['agent_id']] = {k: number(row[k]) for k in ('first_belief_tick', 'reject_tick', 'TBU_FB')}
        cases[row['case_id']]['fb'][row['agent_id']]['state'] = row['state']
    for case in cases.values():
        summary, fb = case['summary'], list(case['fb'].values())
        observed = [u['TBU_FB'] for u in fb if u['state'] == 'observed_post_release']
        assert len(observed) == summary['matched_n']
        assert sum(u['state'] == 'right_censored' for u in fb) == summary['censored_n']
        assert abs(sum(observed) / len(observed) - summary['TBU_FB']) < 1e-9 if observed else summary['TBU_FB'] is None
        counts = Counter(s[0] for s in case['ticks'][-1])
        assert [counts[i] for i in (1, 2, 0)] == [summary[k] for k in ('final_believe', 'final_reject', 'final_unjudged')]
    assert total == 178200
    assets = load_assets(list(cases.values()))
    return {'cases': list(cases.values()), 'rows': total, **assets, 'sources': [
        {'path': 'v7_20261030/' + path, 'sha256': hashlib.sha256((RESULTS / path).read_bytes()).hexdigest()}
        for path in SOURCES.values()]}


def main():
    data = build_data()
    template = (ROOT / 'scripts/showcase/index.template.html').read_text(encoding='utf-8')
    template = template.replace('__WORKBENCH_CSS__', (ROOT / 'scripts/showcase/workbench.css').read_text(encoding='utf-8'))
    template = template.replace('__WORKBENCH_JS__', (ROOT / 'scripts/showcase/workbench.js').read_text(encoding='utf-8'))
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')
    assert template.count('__SHOWCASE_DATA__') == 1
    output = ROOT / 'results/index.html'
    legacy = ROOT / 'results/legacy-v5.html'
    if not legacy.exists() and output.exists():
        if 'showcase-data' in output.read_text(encoding='utf-8'):
            raise RuntimeError('Missing original V5 page; refusing to archive the new viewer as V5.')
        legacy.write_bytes(output.read_bytes())
    downloads = ROOT / 'results/showcase-inputs'
    downloads.mkdir(exist_ok=True)
    for source, name in [('03_新环境设定.md', 'environment.md'), ('05_案例与判断对象.json', 'belief-target.json'), ('01_Agent基础信息表.csv', 'population.csv')]:
        (downloads / name).write_bytes((ROOT / 'v7/materials_v7' / source).read_bytes())
    output.write_text(template.replace('__SHOWCASE_DATA__', encoded), encoding='utf-8', newline='\n')
    print(f'Built {output}: {len(data["cases"])} cases, {data["rows"]:,} verified states, {output.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
