"""One scheduled independent government account; no automatic belief updates."""
import math
import numpy as np
from experiment import validate_experiment,_symmetric_quantiles

GOVERNMENT_PERSONA_POLICY='individual_three_level_v1'
GOVERNMENT_PERSONA_DESCRIPTIONS={
    'low':'你对官方自述较谨慎，仅凭官方身份或一句否认较难改变原判断，但仍会考虑具体核查材料。',
    'medium':'你对政府有一定信任，但是否接受回应，取决于其具体解释与当前可见材料。',
    'high':'你通常认为政府较专业、发布信息较可靠，愿意给予官方回应较高权重。',
}


def government_trust_role(value):
    """Synthetic wording from individual trust, not a calibrated belief model.

    Equal thirds are a transparent wording convention. The original continuous
    value remains authoritative; no trust assignment or belief score changes.
    """
    if type(value)not in(int,float)or not math.isfinite(value)or not 0<=value<=1:
        raise ValueError('invalid individual government trust for persona')
    level='low'if value<1/3 else'medium'if value<2/3 else'high'
    label={'low':'较低','medium':'中等','high':'较高'}[level]
    description=GOVERNMENT_PERSONA_DESCRIPTIONS[level]
    text=(f'你对政府的日常来源信任为{value:.6f}（0低1高，属于{label}）。'+description+
          '本实验分配覆盖资料表默认政府倾向。保留本人的具体信任数值，同档用户也可有不同反应。这是角色态度，不保证本次官方回应必然正确。'
          '只有实际读到官方回应后，才结合上次信念分和当前已见材料判断是否接受；未读时不能预知回应内容或结论。')
    return dict(policy=GOVERNMENT_PERSONA_POLICY,level=level,label=label,description=description,prompt=text)


def validate(cfg):validate_experiment(cfg)


def select_targets(rows,cfg):
    validate_experiment(cfg);rng=np.random.Generator(np.random.PCG64(cfg['government_target_seed']))
    n=cfg['government_reach'];inside=round(n*cfg['targeting_inside_ratio']);chosen=[]
    for group,size in [('inside',inside),('outside',n-inside)]:
        pool=sorted(r['agent_id'] for r in rows if r['group']==group)
        if size>len(pool):raise ValueError('target pool smaller than requested contact count')
        chosen.extend(map(str,rng.choice(pool,size,replace=False)))
    return sorted(chosen)


def trust_values(rows,cfg):
    validate_experiment(cfg);rng=np.random.Generator(np.random.PCG64(cfg['government_trust_seed']))
    ids=sorted(r['agent_id'] for r in rows)
    return {a:float(v) for a,v in zip(ids,rng.permutation(_symmetric_quantiles(len(ids),cfg['government_trust_mean'],cfg['government_trust_sd'])))}
