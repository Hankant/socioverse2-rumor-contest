import copy
import pytest
from socioverse.schemas import Action
from model import V7Metrics,normalize_answer
from conftest import answer


def action(env,aid,**kw):
    ob=env.observe(aid,env.t);raw=answer(ob,**kw)
    return Action(agent_id=aid,step=env.t,kind='decide',source='llm',payload=dict(answer=normalize_answer(raw,ob.local_information['posts'],ob.local_physical['memory'],ob.local_physical['already_reposted']),observed_posts=ob.local_information['posts'],used_memory_ticks=[m['tick'] for m in ob.local_physical['memory']]))


def insider(env):return next(a for a,r in env.by_id.items() if r['group']=='inside')


def test_first_exposure_requires_network_and_repost_next_tick(setup):
    cfg,env=setup;ob=env.observe_batch(list(env.by_id),1)
    assert sum(bool(o.local_information['posts']) for o in ob)==48
    aid=insider(env);outside=next(a for a,r in env.by_id.items() if r['group']=='outside' and aid in env.following[a] and a not in env.direct_targets)
    env.apply([action(env,aid,repost=True,comment=True)])
    assert env.observe(outside,1).local_information['posts']==[]
    env.advance_to(2);feed=env.observe(outside,2).local_information['posts']
    assert [p['content_id'] for p in feed]==['P001'] and len(feed[0]['comments'])==1
    assert feed[0]['relay_context'][0]['author_id']==aid


def test_official_post_does_not_unlock_original(setup):
    cfg,env=setup;env.advance_to(2)
    outside=next(a for a in env.direct_targets if env.by_id[a]['group']=='outside')
    assert [p['content_id'] for p in env.observe(outside,2).local_information['posts']]==['G001']
    env.apply([action(env,outside,comment=True)])
    env.advance_to(3);feed=env.observe(outside,3).local_information['posts']
    assert [p['content_id'] for p in feed]==['G001']


def test_latest_30_public_comments_and_complete_archive(setup):
    cfg,env=setup;ids=[a for a,r in env.by_id.items() if r['group']=='inside']
    env.apply([action(env,a,comment=True) for a in ids])
    assert len(env.comments)==48 and env.observe(ids[0],1).local_information['posts'][0]['comments']==[]
    env.advance_to(2);feed=env.observe(ids[0],2).local_information['posts'];p=next(p for p in feed if p['content_id']=='P001')
    assert len(p['comments'])==30 and all(c['published_tick']<2 for c in p['comments'])
    assert p['comments']==next(p for p in env.observe(ids[-1],2).local_information['posts'] if p['content_id']=='P001')['comments']
    env.apply([action(env,a,comment=True) for a in ids])
    env.advance_to(3);assert len(env.comments)==96
    for p in env.observe(ids[0],3).local_information['posts']:assert len(p['comments'])<=30


def test_memory_expires_after_three_simulation_ticks(setup):
    cfg,env=setup;aid=insider(env)
    env.apply([action(env,aid,comment=True,repost=True)])
    for t in (2,3,4):
        env.advance_to(t);assert [m['tick'] for m in env.observe(aid,t).local_physical['memory']]==[1]
    env.advance_to(5);assert env.observe(aid,5).local_physical['memory']==[]
    assert env.beliefs[aid]=='believe' and env.reposted[aid]=={'P001'} and 'P001' in env.seen[aid]


def test_atomic_validation_idempotence_and_duplicate_repost(setup):
    cfg,env=setup;ids=[a for a,r in env.by_id.items() if r['group']=='inside'][:2];one=action(env,ids[0],comment=True,repost=True);two=action(env,ids[1])
    two.payload['answer']['subjective_credibility']=None;before=copy.deepcopy(env.snapshot())
    with pytest.raises(ValueError):env.apply([one,two])
    assert env.snapshot()==before
    env.apply([one]);before=copy.deepcopy(env.snapshot());env.apply([one]);assert env.snapshot()==before
    env.advance_to(2);again=action(env,ids[0],repost=True)
    again.payload['answer']['repost']=dict(enabled=True,target_content_id='P001',text='重复转发测试')
    env.apply([again]);assert len([p for p in env.posts.values() if p['content_id'].startswith('RP')])==1


def test_no_idle_for_exposed_and_no_uncertain_state(setup):
    cfg,env=setup;aid=insider(env)
    with pytest.raises(ValueError):env.apply([Action(agent_id=aid,step=1,kind='idle',source='llm',payload={})])
    a=action(env,aid,score=50);env.apply([a]);metrics=V7Metrics().collect(env,[a],1)
    assert metrics['all_reject']==1 and metrics['all_unjudged']==299 and metrics['all_believe']==0
    assert not any('rule' in k or 'uncertain' in k or 'dropout' in k for k in metrics)
