"""Replay saved V7 actions without an API and compare every committed state."""
from pathlib import Path
import json
from model import V7Environment,read_json,digest
from socioverse.schemas import Action,EnvironmentBundle
from csv_io import iter_committed_states


def verify(folder):
    folder=Path(folder);prov=read_json(folder/'provenance.json');status=read_json(folder/'status.json')
    if prov.get('version')!='V7':raise ValueError('not a V7 run')
    env=V7Environment(EnvironmentBundle.model_validate(read_json(folder/'environment/environment.json')));env.reset(prov['config']['behavior_seed'])
    expected={(int(r['step']),r['agent_id']):json.loads(r['state']) for r in iter_committed_states(folder)}
    n=status['last_completed_tick']
    if len(expected)!=(n+1)*300:raise ValueError('incomplete panel')
    for t in range(n+1):
        if t:
            env.advance_to(t);checkpoint=read_json(folder/'checkpoints'/f'tick-{t:03d}.json');data=checkpoint['actions']
            if digest(data)!=checkpoint['sha256'] or len(data)!=300 or {a['agent_id'] for a in data}!=set(env.by_id) or any(a['step']!=t for a in data):raise ValueError('invalid checkpoint')
            actions=[Action(agent_id=a['agent_id'],step=t,kind=a['action_kind'],payload=a['action_payload'],source='replay') for a in data]
            env.apply(actions)
        for aid in env.by_id:
            if env.agent_state(aid)!=expected[t,aid]:raise ValueError(f'replay mismatch tick={t}, agent={aid}')
    return dict(version='V7',mode=prov['mode'],last_completed_tick=n,panel_rows=len(expected),replay='exact',api_requests=0)
