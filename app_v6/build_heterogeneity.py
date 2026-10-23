"""Versioned, reproducible synthetic demographics and MBTI-style preferences.

All additions are synthetic role attributes. Observed fields and existing
behavioral parameters remain untouched. Personality does not set belief labels.
"""
from collections import Counter
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'materials_v6/01_Agent基础信息表.csv'
CONFIG=ROOT/'materials_v6/06_合成人群分配设定.json'
VERSION='v6-heterogeneity-20261022-1'
DESCRIPTIONS={
 'E':'较常在交流互动中整理想法，愿意把话题带入讨论',
 'I':'较常先独自整理想法，公开表达时有所选择',
 'S':'较常留意具体细节、眼前情境和已有经验',
 'N':'较常留意整体联系、可能解释和后续变化',
 'T':'作判断时较常先组织理由、因果和一致性',
 'F':'作判断时较常先考虑人的处境、关系和价值关切',
 'J':'较偏好有安排、有步骤地处理和表达事情',
 'P':'较偏好保留选择，根据新情况灵活调整处理方式'}
EXPERIENCES={
 '较少接触社区工程信息':'合成事前经历：较少关注社区工程和预算细节，对相关流程不熟悉；未接触本次项目的额外信息。',
 '曾关注延期但未获完整原因':'合成事前经历：以前关注过别的社区工程延期，当时没有得到完整原因说明；不知道本次项目是否存在同样情况。',
 '曾见到项目调整并获得公开解释':'合成事前经历：以前见过别的社区工程调整安排，后来获得了公开解释；不知道本次项目是否存在同样情况。'}

def quotas(n,weights):
    if not weights or any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0 for v in weights.values()) or sum(weights.values())<=0:
        raise ValueError('invalid population weights')
    total=sum(weights.values());exact={k:n*v/total for k,v in weights.items()}
    out={k:math.floor(v) for k,v in exact.items()}
    order=sorted(weights,key=lambda k:-(exact[k]-out[k]))
    for k in order[:n-sum(out.values())]:out[k]+=1
    return out

def pool(counts,rng):
    out=[k for k,n in counts.items() for _ in range(n)];rng.shuffle(out);return out

def generate(rows,cfg):
    rows=sorted([dict(r) for r in rows],key=lambda r:r['agent_id'])
    if len({r['agent_id'] for r in rows})!=len(rows):raise ValueError('duplicate agent')
    seed=cfg['seed']
    if type(seed) is not int or seed<0:raise ValueError('invalid seed')
    weights=cfg['mbti_weights']
    if len(weights)!=16 or any(len(k)!=4 or any(c not in pair for c,pair in zip(k,('EI','SN','TF','JP'))) for k in weights):
        raise ValueError('expected all 16 MBTI-style types')
    rng=random.Random(seed);n=len(rows)
    # Preserve global quotas, then allocate them proportionally in both modes
    # and groups. This avoids losing types in the small first-exposure cohort.
    remaining=quotas(n,weights)
    for mode in ('llm','rule'):
        people=[r for r in rows if r['decision_mode']==mode]
        counts=quotas(len(people),remaining) if mode=='llm' else dict(remaining)
        for k in remaining:remaining[k]-=counts[k]
        inside=[r for r in people if r['group']=='inside']
        ic=quotas(len(inside),counts)
        for group,assigned in [('inside',ic),('outside',{k:counts[k]-ic[k] for k in counts})]:
            people_group=[r for r in people if r['group']==group]
            values=pool(assigned,rng)
            for r,t in zip(people_group,values):r['synthetic_mbti_type']=t
    for key,weights2 in [('synthetic_age_band',{x['label']:x['weight'] for x in cfg['age_bands']}),
                          ('synthetic_region',cfg['region_weights']),('synthetic_settlement',cfg['settlement_weights']),
                          ('synthetic_project_experience',cfg['project_experience_weights'])]:
        for r,v in zip(rows,pool(quotas(n,weights2),rng)):r[key]=v
    bands={b['label']:b for b in cfg['age_bands']}
    for r in rows:
        band=bands[r['synthetic_age_band']]
        if type(band['min']) is not int or type(band['max']) is not int or not 18<=band['min']<=band['max']<=100:raise ValueError('invalid adult age band')
        r['synthetic_age']=str(rng.randint(band['min'],band['max']))
    counts=quotas(n,{x['label']:x['weight'] for x in cfg['occupations']})
    assigned=set()
    for o in cfg['occupations']:
        eligible=[r for r in rows if r['agent_id'] not in assigned and o['min_age']<=int(r['synthetic_age'])<=o['max_age']]
        rng.shuffle(eligible)
        if o.get('prioritize_oldest'):eligible.sort(key=lambda r:-int(r['synthetic_age']))
        if len(eligible)<counts[o['label']]:raise ValueError('occupation/age quotas infeasible: '+o['label'])
        for r in eligible[:counts[o['label']]]:
            r['synthetic_occupation']=o['label'];assigned.add(r['agent_id'])
    if len(assigned)!=n:raise ValueError('incomplete occupation assignment')
    for r in rows:
        t=r['synthetic_mbti_type']
        strength={axis:round(rng.uniform(.55,.90),3) for axis in ['EI','SN','TF','JP']}
        r['synthetic_mbti_preference_strengths']=json.dumps(strength,ensure_ascii=False)
        r['synthetic_personality_description']='；'.join(DESCRIPTIONS[c] for c in t)+'。这些是表达与处理偏好，同型角色仍有差异。'
        r['synthetic_role_experience']=EXPERIENCES[r['synthetic_project_experience']]
        r['synthetic_demographic_basis']=f"研究分配的合成角色，seed={seed}；年龄/地区/职业配额可修改；非原账户已核实信息。"
        r['synthetic_mbti_basis']='研究分配的MBTI风格偏好，非正式测评；不推断智力、职业能力或轻信概率。'
        r['persona_version']=VERSION
    return rows,list(dict.fromkeys(k for r in rows for k in r))

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',default=str(SOURCE));p.add_argument('--output',default=str(SOURCE));p.add_argument('--config',default=str(CONFIG))
    args=p.parse_args();src=Path(args.input);dest=Path(args.output);config=Path(args.config)
    with src.open(encoding='utf-8-sig',newline='') as f:original=list(csv.DictReader(f))
    cfg=json.loads(config.read_text(encoding='utf-8'));rows,fields=generate(original,cfg)
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    summary={'version':VERSION,'seed':cfg['seed'],'synthetic':True,'population_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
     'config_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),'n':len(rows),
     'counts':{k:dict(Counter(r[k] for r in rows)) for k in ['synthetic_mbti_type','synthetic_age_band','synthetic_region','synthetic_settlement','synthetic_occupation','decision_mode','group']},
     'mode_mbti_counts':{m:dict(Counter(r['synthetic_mbti_type'] for r in rows if r['decision_mode']==m)) for m in ['llm','rule']}}
    report=ROOT/'runtime/v6/configs/heterogeneity_generation.json';report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
