"""Verify the published V7 snapshot using only the standard library; no API calls."""
from collections import defaultdict
from pathlib import Path
import csv, hashlib, json, math, statistics, zipfile

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results/v7_20261030'

def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

def close(a, b):
    assert math.isclose(float(a), float(b), abs_tol=1e-10), (a, b)

def verify():
    manifest = json.loads((RESULTS / 'PUBLICATION_MANIFEST.json').read_text(encoding='utf-8'))
    source = json.loads((ROOT / 'v7/MANIFEST.json').read_text(encoding='utf-8'))
    for base, files in ((RESULTS, manifest['files']), (ROOT / 'v7', source)):
        for name, expected in files.items():
            assert hashlib.sha256((base / name).read_bytes()).hexdigest() == expected, name
    cases = rows(RESULTS / 'fb/data/FB_scenarios.csv')
    people = rows(RESULTS / 'fb/data/FB_users.csv')
    assert len(cases) == 54 and len({r['case_id'] for r in cases}) == 54
    published = {(r['case_id'], r['agent_id']): r for r in people}
    assert len(people) == len(published) == 980
    nrows = events = eligible_count = same_round = censored = before = 0
    means = []
    books = list((RESULTS / 'workbooks').glob('*.xlsx'))
    assert len(books) == 54
    for path in books:
        with zipfile.ZipFile(path) as book:
            assert book.testzip() is None and 'xl/workbook.xml' in book.namelist(), path.name
    for case in cases:
        tag, rt = case['case_id'], int(case['RT'])
        data = rows(RESULTS / 'complete54/raw' / (tag + '.csv'))
        assert len(data) == 3300, tag
        nrows += len(data)
        agents = defaultdict(list)
        for row in data:
            agents[row['agent_id']].append(row)
            if row['subjective_credibility']:
                assert row['belief'] == ('believe' if float(row['subjective_credibility']) > 50 else 'reject')
        assert len(agents) == 300
        durations = []
        local_censored = local_before = 0
        for aid, trajectory in agents.items():
            trajectory.sort(key=lambda r: int(r['step']))
            assert [int(r['step']) for r in trajectory] == list(range(11))
            starts = [int(r['step']) for r in trajectory if r['belief'] == 'believe']
            updates = [int(b['step']) for a, b in zip(trajectory, trajectory[1:])
                       if a['belief'] == 'believe' and b['belief'] == 'reject']
            for row in trajectory:
                assert row['believe_to_reject_event'].lower() == str(int(row['step']) in updates).lower()
            events += len(updates)
            if not starts:
                assert (tag, aid) not in published
                continue
            person = published[tag, aid]
            b = min(starts)
            assert int(person['first_belief_tick']) == b
            eligible = [tick for tick in updates if tick >= rt]
            if eligible:
                r = min(eligible)
                assert person['state'] == 'observed_post_release'
                close(person['reject_tick'], r)
                close(person['TBU_FB'], r - b)
                durations.append(r - b)
                eligible_count += 1
                same_round += r == rt
            elif updates:
                assert person['state'] == 'resolved_before_release' and not person['TBU_FB']
                before += 1
                local_before += 1
            else:
                assert person['state'] == 'right_censored' and not person['TBU_FB']
                censored += 1
                local_censored += 1
        assert len(durations) == int(case['matched_n'])
        assert local_censored == int(case['censored_n']) and local_before == int(case['pre_release_resolved_n'])
        mean = statistics.mean(durations)
        close(mean, case['TBU_FB'])
        means.append(mean)
        status = json.loads((RESULTS / 'run_metadata' / tag / 'status.json').read_text(encoding='utf-8'))
        assert status['last_completed_tick'] == 10 and status['status'] == 'completed_live'
    assert (nrows, events, eligible_count, same_round, censored, before) == (178200, 758, 757, 282, 222, 1)
    close(statistics.mean(means), 4.55684896011148)
    combined = rows(RESULTS / 'complete54/data/all_committed_user_states.csv')
    assert len(combined) == nrows
    assert len({(r['case_id'], r['agent_id'], r['step']) for r in combined}) == nrows
    fb = json.loads((RESULTS / 'fb/analysis_FB.json').read_text(encoding='utf-8'))
    close(fb['scenario_mean'], statistics.mean(means))
    print('V7 verified: 54 completed scenarios, 54 workbooks, 178200 states; '
          '758 transitions, 757 FB updates, 222 censored; source/result hashes verified.')

if __name__ == '__main__':
    verify()
