"""Explicit, frozen initial SOURCE trust assignments for the local V6 design.

Source trust is a synthetic role input, not a pre-sampled belief. The historical
PBd experiment remains available independently for old configuration files.
"""
from statistics import NormalDist, mean, pstdev
import math

import numpy as np


def validate_experiment(cfg):
    from memory_policy import validate_memory_policy
    validate_memory_policy(cfg)
    if cfg.get('api_routing_policy','primary_first_v1') not in ('primary_first_v1','round_robin_v1'):
        raise ValueError('invalid api_routing_policy')
    cooldown=cfg.get('api_key_cooldown_seconds',60)
    if type(cooldown) is not int or not 1<=cooldown<=3600:
        raise ValueError('invalid api_key_cooldown_seconds')
    if cfg.get('api_routing_policy')=='round_robin_v1' and cfg.get('api_key_mode')!='windows_dpapi_failover':
        raise ValueError('Round robin requires encrypted MiniMax credential slots')
    from model import FULL_THREAD_POLICIES
    encoding=cfg.get('prompt_encoding','full_json_v1')
    from comment_policy import LATEST_FEED_POLICY,PARTICIPATION_POLICY,MEMORY_POLICY
    if cfg.get('comment_participation_policy','legacy') not in ('legacy',PARTICIPATION_POLICY):
        raise ValueError('invalid comment_participation_policy')
    if cfg.get('memory_comment_policy','complete_observed_v1') not in ('complete_observed_v1',MEMORY_POLICY):
        raise ValueError('invalid memory_comment_policy')
    if cfg.get('feed_policy')==LATEST_FEED_POLICY:
        from comment_policy import comment_limit
        comment_limit(cfg)
        if cfg.get('comment_participation_policy')!=PARTICIPATION_POLICY or cfg.get('memory_comment_policy')!=MEMORY_POLICY:
            raise ValueError('latest comment policy requires voluntary MBTI comments and personal-action memory')
    elif cfg.get('comment_window_limit') is not None or cfg.get('memory_comment_policy','complete_observed_v1')!= 'complete_observed_v1' or cfg.get('comment_participation_policy','legacy')!='legacy':
        raise ValueError('new comment mechanisms require an explicit latest-comment feed policy')
    style=cfg.get('wire_prompt_style','standard')
    from concise_wire import STYLES
    if style not in ('standard', *STYLES):raise ValueError('invalid wire_prompt_style')
    if style in STYLES and (encoding!='lossless_thread_refs_v1' or
            cfg.get('decision_condition_policy')!='all_conditions_v1' or
            cfg.get('belief_measurement_policy')!='binary_score_gt50_v1'):
        raise ValueError('concise wire style requires lossless, all-condition, binary-score inputs')
    if encoding not in ('full_json_v1','lossless_thread_refs_v1'):raise ValueError('invalid prompt_encoding')
    if encoding=='lossless_thread_refs_v1' and (cfg.get('feed_policy') not in FULL_THREAD_POLICIES or cfg.get('prompt_memory_policy')!='preserve'):
        raise ValueError('lossless encoding requires full-thread preserve policy')
    if cfg.get('feed_policy','legacy') not in ({'legacy'} | FULL_THREAD_POLICIES):
        raise ValueError('invalid feed_policy')
    if cfg.get('decision_condition_policy','legacy') not in ('legacy','all_conditions_v1'):
        raise ValueError('invalid decision_condition_policy')
    if cfg.get('comment_target','first_displayed_post') not in ('first_displayed_post','explicit_visible_root'):
        raise ValueError('invalid comment_target')
    if cfg.get('feed_policy') in FULL_THREAD_POLICIES and (
            cfg.get('prompt_memory_policy')!='preserve' or cfg.get('comment_target')!='explicit_visible_root'):
        raise ValueError('shared thread requires full preserved observations and explicit comment targets')
    if cfg.get('decision_condition_policy')=='all_conditions_v1' and cfg.get('llm_max_output_tokens',512)<1536:
        raise ValueError('all conditions output contract requires at least 1536 output tokens')
    if cfg.get('belief_measurement_policy', 'legacy') not in ('legacy', 'subjective_credibility_v1', 'binary_score_gt50_v1'):
        raise ValueError('invalid belief_measurement_policy')
    tokens=cfg.get('llm_max_output_tokens',512)
    if type(tokens) is not int or not 256<=tokens<=4096:
        raise ValueError('llm_max_output_tokens must be an integer in 256..4096')
    gap = cfg.get('source_trust_gap')
    center = cfg.get('source_trust_center', .5)
    sd = cfg.get('source_trust_sd', .1)
    numbers = [center, sd] + ([] if gap is None else [gap])
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in numbers):
        raise ValueError('SOURCE trust parameters must be finite numbers')
    if gap is not None and gap not in (0, .2, .4):
        raise ValueError('source_trust_gap must be null, 0, 0.2 or 0.4')
    if not 0 <= center <= 1 or not 0 <= sd <= .5:
        raise ValueError('SOURCE trust center must be in [0,1] and sd in [0,.5]')
    if gap is not None and not (0 <= center-gap/2 <= center+gap/2 <= 1):
        raise ValueError('SOURCE trust group means fall outside [0,1]')
    if cfg.get('rule_source_trust_mode', 'legacy_pb') not in ('legacy_pb', 'individual_pb'):
        raise ValueError('rule_source_trust_mode must be legacy_pb or individual_pb')
    if cfg.get('rule_source_trust_mode') == 'individual_pb' and gap is None:
        raise ValueError('individual_pb needs an explicit source_trust_gap')
    if gap is not None and cfg.get('pbd', 0) != 0:
        raise ValueError('Do not combine legacy PBd with the new SOURCE trust-gap factor')
    seed = cfg.get('source_trust_seed', 20261023)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError('source_trust_seed must be a nonnegative integer')
    limit = cfg.get('prompt_input_token_limit', 4096)
    ceiling=524288 if encoding=='lossless_thread_refs_v1' else 131072
    if isinstance(limit, bool) or not isinstance(limit, int) or not 512 <= limit <= ceiling:
        raise ValueError(f'prompt_input_token_limit must be an integer in 512..{ceiling}')
    if cfg.get('prompt_memory_policy', 'trim_oldest') not in ('trim_oldest', 'preserve'):
        raise ValueError('prompt_memory_policy must be trim_oldest or preserve')
    for key, default in [('max_input_reserved_units', 49_971_200), ('max_output_reserved_tokens', 6_246_400)]:
        value=cfg.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 512:
            raise ValueError(key+' must be a positive integer >=512')


def _symmetric_quantiles(n, mu, sd):
    if n == 0:
        return []
    if sd == 0 or mu in (0, 1):
        return [float(mu)]*n
    normal=NormalDist(mu, sd)
    width=min(mu, 1-mu)
    lo,hi=normal.cdf(mu-width), normal.cdf(mu+width)
    return [normal.inv_cdf(lo+(i+.5)/n*(hi-lo)) for i in range(n)]


def source_trust_values(rows, cfg):
    validate_experiment(cfg)
    gap=cfg.get('source_trust_gap')
    if gap is None:
        return {}
    rng=np.random.Generator(np.random.PCG64(cfg.get('source_trust_seed', 20261023)))
    result={}
    # Exact requested means within all four mode/group cells; stable individual
    # ranks across gap levels; no demographic inference or force on LLM output.
    for mode in ('llm','rule'):
        for group, sign in [('inside',1),('outside',-1)]:
            ids=sorted(r['agent_id'] for r in rows if r['decision_mode']==mode and r['group']==group)
            mu=cfg.get('source_trust_center',.5)+sign*gap/2
            values=_symmetric_quantiles(len(ids),mu,cfg.get('source_trust_sd',.1))
            for aid,value in zip(ids,rng.permutation(values)):
                result[aid]=float(value)
    return result


def assignment_summary(rows, source, government):
    result={}
    for name, values in [('source_trust',source),('government_trust',government)]:
        result[name]={}
        for mode in ('all','llm','rule'):
            for group in ('all','inside','outside'):
                ids=[r['agent_id'] for r in rows if (mode=='all' or r['decision_mode']==mode)
                     and (group=='all' or r['group']==group) and r['agent_id'] in values]
                xs=[values[aid] for aid in ids]
                result[name][mode+'/'+group]=dict(n=len(xs),mean=mean(xs) if xs else None,
                    population_sd=pstdev(xs) if xs else None,min=min(xs) if xs else None,max=max(xs) if xs else None)
    return result
