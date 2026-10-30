"""V7 settings and reproducible trust assignments for an all-LLM population."""
from statistics import NormalDist,mean,pstdev
import math
import numpy as np

VERSION='v7-government-trust-persona-20261027-2'


def defaults():
    return dict(runtime_version=VERSION,population_n=300,inside_n=48,outside_n=252,
        contract_status='authorized_engineering_run',model='MiniMax-M3',base_url='https://api.minimax.cn/v1',api_profile='minimax_m3',
        source_trust_gap=.4,source_trust_center=.5,source_trust_sd=.1,source_trust_seed=20261023,
        government_tick=2,government_reach=50,targeting_inside_ratio=.8,government_trust_mean=.75,government_trust_sd=.1,
        government_target_seed=20261019,government_trust_seed=20261022,behavior_seed=20261020,
        prompt_encoding='lossless_thread_refs_v1',wire_prompt_style='concise_shared_prefix_v1',
        feed_policy='network_rumor_latest_comments_v1',comment_window_limit=30,
        comment_participation_policy='mbti_voluntary_comment_v1',memory_comment_policy='personal_actions_no_comment_transcripts_v1',
        memory_retention_policy='rolling_simulation_ticks_v1',memory_window_ticks=3,decision_condition_policy='all_conditions_v1',
        belief_measurement_policy='binary_score_gt50_v1',comment_target='explicit_visible_root',
        belief_update_policy='autonomous_belief_reinforcement_v1',belief_transition_policy='believe_to_reject_episodes_v1',
        government_trust_prompt_policy='individual_three_level_v1',
        prompt_input_token_limit=524288,prompt_memory_policy='preserve',llm_max_output_tokens=1536,
        max_input_reserved_units=750000000,max_output_reserved_tokens=6246400,max_requests=12200,
        api_key_mode='windows_dpapi_failover',api_routing_policy='round_robin_v1',api_primary_retry_seconds=3600,api_key_cooldown_seconds=60,
        rate_recovery_successes=20,rate_recovery_seconds=60.,rate_limit_max_retries=6,rate_limit_wait_seconds=2.,
        rate_limit_max_wait_seconds=60.,rate_limit_spacing_seconds=1.,max_concurrency=2,format_max_attempts=4)


def validate_experiment(cfg):
    required=defaults()
    if set(cfg)!=set(required):raise ValueError('V7 configuration fields differ: '+str(sorted(set(cfg)^set(required))))
    for key in ('population_n','inside_n','outside_n','runtime_version','feed_policy','comment_window_limit','comment_participation_policy',
                'memory_comment_policy','memory_retention_policy','memory_window_ticks','decision_condition_policy','belief_measurement_policy','comment_target',
                'belief_update_policy','belief_transition_policy','government_trust_prompt_policy'):
        if type(cfg[key]) is not type(required[key]) or cfg[key]!=required[key]:raise ValueError('V7 fixed setting mismatch: '+key)
    from memory_policy import validate_memory_policy
    validate_memory_policy(cfg)
    if cfg['model']!='MiniMax-M3' or cfg['api_profile']!='minimax_m3' or cfg['base_url']!='https://api.minimax.cn/v1':raise ValueError('V7 uses the configured official MiniMax-M3 endpoint')
    for key in ('source_trust_gap','source_trust_center','source_trust_sd','government_trust_mean','government_trust_sd','targeting_inside_ratio'):
        v=cfg[key]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError('invalid numeric setting: '+key)
    if cfg['source_trust_gap'] not in (0,.2,.4) or cfg['targeting_inside_ratio'] not in (.2,.8) or cfg['government_trust_mean'] not in (.25,.5,.75):raise ValueError('invalid V7 experimental factor')
    if not 0<=cfg['source_trust_center']-cfg['source_trust_gap']/2<=cfg['source_trust_center']+cfg['source_trust_gap']/2<=1:raise ValueError('invalid source trust means')
    for key in ('source_trust_sd','government_trust_sd'):
        if not 0<=cfg[key]<=.5:raise ValueError('invalid trust spread')
    if type(cfg['government_tick']) is not int or cfg['government_tick'] not in (2,4,7):raise ValueError('invalid intervention tick')
    if type(cfg['government_reach']) is not int or not 0<=cfg['government_reach']<=300:raise ValueError('invalid government reach')
    n=cfg['government_reach'];ratio=cfg['targeting_inside_ratio']
    if abs(n*ratio-round(n*ratio))>1e-9 or round(n*ratio)>48 or n-round(n*ratio)>252:raise ValueError('Government targeting cannot be satisfied by 48 inside /252 outside users')
    for key in ('source_trust_seed','government_target_seed','government_trust_seed','behavior_seed'):
        if type(cfg[key]) is not int or cfg[key]<0:raise ValueError('invalid seed')
    if cfg['prompt_encoding'] not in ('full_json_v1','lossless_thread_refs_v1') or cfg['wire_prompt_style'] not in ('standard','concise_lossless_v1','concise_shared_prefix_v1'):raise ValueError('invalid input encoding')
    if cfg['wire_prompt_style']!='standard' and cfg['prompt_encoding']!='lossless_thread_refs_v1':raise ValueError('concise prompts require lossless encoding')
    if cfg['prompt_memory_policy']!='preserve':raise ValueError('V7 does not silently trim observations')
    ceiling=524288 if cfg['prompt_encoding']=='lossless_thread_refs_v1' else 131072
    for key,lo,hi in [('prompt_input_token_limit',512,ceiling),('llm_max_output_tokens',1536,4096),('max_requests',1,12200),('max_concurrency',1,10),('format_max_attempts',1,4)]:
        if type(cfg[key]) is not int or not lo<=cfg[key]<=hi:raise ValueError('invalid execution limit: '+key)
    for key in ('max_input_reserved_units','max_output_reserved_tokens'):
        if type(cfg[key]) is not int or cfg[key]<512:raise ValueError('invalid spending guard')
    if cfg['api_key_mode'] not in ('environment','windows_dpapi_failover') or cfg['api_routing_policy']!='round_robin_v1':raise ValueError('invalid API key policy')
    for key in ('api_primary_retry_seconds','api_key_cooldown_seconds','rate_recovery_successes','rate_limit_max_retries'):
        if type(cfg[key]) is not int or cfg[key]<1:raise ValueError('invalid retry setting')
    for key in ('rate_recovery_seconds','rate_limit_wait_seconds','rate_limit_max_wait_seconds','rate_limit_spacing_seconds'):
        if isinstance(cfg[key],bool) or not isinstance(cfg[key],(int,float)) or not math.isfinite(cfg[key]) or cfg[key]<0:raise ValueError('invalid rate setting')


def _symmetric_quantiles(n,mu,sd):
    if not n:return []
    if sd==0 or mu in (0,1):return [float(mu)]*n
    normal=NormalDist(mu,sd);width=min(mu,1-mu);lo,hi=normal.cdf(mu-width),normal.cdf(mu+width)
    return [normal.inv_cdf(lo+(i+.5)/n*(hi-lo)) for i in range(n)]


def source_trust_values(rows,cfg):
    validate_experiment(cfg);rng=np.random.Generator(np.random.PCG64(cfg['source_trust_seed']));out={}
    for group,sign in [('inside',1),('outside',-1)]:
        ids=sorted(r['agent_id'] for r in rows if r['group']==group);mu=cfg['source_trust_center']+sign*cfg['source_trust_gap']/2
        out.update((aid,float(v)) for aid,v in zip(ids,rng.permutation(_symmetric_quantiles(len(ids),mu,cfg['source_trust_sd']))))
    return out


def assignment_summary(rows,source,government):
    out={}
    for key,values in [('source_trust',source),('government_trust',government)]:
        out[key]={}
        for group in ('all','inside','outside'):
            xs=[values[r['agent_id']] for r in rows if group=='all' or r['group']==group]
            out[key][group]=dict(n=len(xs),mean=mean(xs),population_sd=pstdev(xs),min=min(xs),max=max(xs))
    return out
