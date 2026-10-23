"""Offline audit of existing requests; never imports credentials or calls an API."""
import argparse
import copy
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from compact_prompt import pack_observations, unpack_observations
from concise_wire import extract_data, render_concise_data
from llm_client import estimated_input_tokens
from memory_policy import LEGACY, ROLLING, retained_memory
from model import digest, dump
from comment_policy import LATEST_FEED_POLICY, PARTICIPATION_POLICY


def inspect_request(record):
    d = extract_data(record['base_prompt'])
    full = {**d['libraries'], 'current_posts':d['current']['posts'], 'memory':d['memory']}
    feed, memory = unpack_observations(full)
    physical = {'feed_policy':LATEST_FEED_POLICY, 'comment_participation_policy':PARTICIPATION_POLICY,
                'memory_retention_policy':LEGACY, 'memory_window_ticks':None,
                'comment_window_limit':next((p['comment_window_limit'] for p in feed if 'comment_window_limit' in p),100)}
    before = render_concise_data(d, SimpleNamespace(local_physical=physical))
    policy = {'memory_retention_policy':ROLLING,'memory_window_ticks':3}
    shorter = retained_memory(memory, record['tick'], policy)
    packed = pack_observations(feed, shorter)
    assert unpack_observations(packed) == (feed, shorter)
    changed = copy.deepcopy(d)
    changed['libraries'] = {k:packed[k] for k in ('encoding','texts','comments','relays')}
    changed['current']['posts'] = packed['current_posts']
    changed['memory'] = packed['memory']
    h = changed['conditions']['history_and_memory']
    h.update(memory_ticks=[m['tick'] for m in shorter], memory_sha256=digest(shorter),
             retention_policy=ROLLING, window_ticks=3)
    changed['condition_context_ref'] = digest(changed['conditions'])[:16]
    physical.update(policy)
    ob = SimpleNamespace(local_physical=physical)
    after = render_concise_data(changed, ob)
    cached_style = render_concise_data(changed, ob, shared_prefix=True)
    return dict(tick=record['tick'], agent_id=record['agent_id'],
                actual_input_tokens=record.get('actual_input_tokens'),
                actual_output_tokens=record.get('actual_output_tokens'),
                memory_ticks_before=[m['tick'] for m in memory], memory_ticks_after=[m['tick'] for m in shorter],
                visible_posts=len(feed), visible_comments=sum(len(p['comments']) for p in feed),
                input_body_proxy_before=estimated_input_tokens(before),
                input_body_proxy_three_ticks=estimated_input_tokens(after),
                input_body_proxy_three_ticks_shared_prefix=estimated_input_tokens(cached_style),
                comment_table_proxy=estimated_input_tokens(json.dumps(d['libraries']['comments'],ensure_ascii=False,separators=(',',':'))),
                relay_table_proxy=estimated_input_tokens(json.dumps(d['libraries']['relays'],ensure_ascii=False,separators=(',',':'))),
                memory_frame_proxy=estimated_input_tokens(json.dumps(d['memory'],ensure_ascii=False,separators=(',',':'))),
                _new_body=cached_style)


def audit(folder, output):
    status=Counter(); first={}; usage=Counter(); cache_known=0; cache_tokens=0
    for path in sorted(Path(folder).glob('request-*.json')):
        r=json.loads(path.read_text(encoding='utf-8'))
        status[r.get('status')]+=1
        if r.get('status')!='response_received':continue
        for field in ('actual_input_tokens','actual_output_tokens'):
            if type(r.get(field)) is int:usage[field]+=r[field]
        if type(r.get('cached_input_tokens')) is int:
            cache_known+=1;cache_tokens+=r['cached_input_tokens']
        first.setdefault((r['tick'],r['agent_id']),path)
    groups=defaultdict(list); examples=[];previous={}
    for i,path in enumerate(first.values()):
        record=json.loads(path.read_text(encoding='utf-8'));row=inspect_request(record)
        new_body=row.pop('_new_body');slot=record.get('api_key_slot','unknown')
        if slot in previous:
            old_prompt,last_body=previous[slot]
            row['prior_same_slot_common_prefix_proxy_before']=estimated_input_tokens(os.path.commonprefix([old_prompt,record['prompt']]))
            row['prior_same_slot_common_prefix_proxy_after']=estimated_input_tokens(os.path.commonprefix([last_body,new_body]))
        previous[slot]=(record['prompt'],new_body)
        groups[row['tick']].append(row)
        if row['tick']>=7 and len(examples)<3:examples.append(row)
        if i and i%250==0:print(f'Offline token audit: {i}/{len(first)}',flush=True)
    rows=[]
    for tick,values in sorted(groups.items()):
        b=sum(v['input_body_proxy_before'] for v in values)
        a=sum(v['input_body_proxy_three_ticks'] for v in values)
        rows.append(dict(tick=tick,unique_agent_requests=len(values),before_proxy=b,three_tick_proxy=a,
                         body_reduction_percent=round(100*(b-a)/b,3),
                         mean_visible_comments=round(sum(v['visible_comments'] for v in values)/len(values),2),
                         mean_comment_table_proxy=round(sum(v['comment_table_proxy'] for v in values)/len(values)),
                         mean_relay_table_proxy=round(sum(v['relay_table_proxy'] for v in values)/len(values)),
                         mean_memory_frame_proxy=round(sum(v['memory_frame_proxy'] for v in values)/len(values)),
                         mean_common_prefix_proxy_before=round(sum(v.get('prior_same_slot_common_prefix_proxy_before',0) for v in values)/len(values)),
                         mean_common_prefix_proxy_after=round(sum(v.get('prior_same_slot_common_prefix_proxy_after',0) for v in values)/len(values))))
    b=sum(r['before_proxy'] for r in rows);a=sum(r['three_tick_proxy'] for r in rows)
    result=dict(source_audit=str(Path(folder).resolve()),paid_requests_made=0,request_statuses=dict(status),
                measured_usage=dict(usage),provider_cache_usage_known_requests=cache_known,
                provider_cache_tokens=cache_tokens if cache_known else None,
                comparison_scope='First received response per user/tick; input body proxy only, fixed observed content/decisions, no output-protocol suffix. Same-slot consecutive common prefixes are offline opportunities, NOT measured server cache hits, quota discounts or billing. Not a counterfactual behavior run.',
                per_tick=rows,examples=examples,
                total_body_reduction_percent=round(100*(b-a)/b,3) if b else None)
    dump(output,result);print(json.dumps({k:v for k,v in result.items() if k not in ('per_tick','examples')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();audit(a.audit,a.output)
