"""Latest comment window, voluntary participation and memory tests."""
import copy
from types import SimpleNamespace
import pytest
from comment_policy import LATEST_FEED_POLICY,PARTICIPATION_POLICY,MEMORY_POLICY,recent_comments
from test_network_thread import setup as network_setup,act,roots
from test_shared_thread import answer,fake_action
from run import make_bundles,SOURCE
from model import V4Environment,V4Decision,digest
from llm_client import LiveClient,prepare_prompt,validate_response
from decision_conditions import validate_condition_application
from response_contract import wire_prompt
from concise_wire import extract_data
from test_recovery import response


def setup(tmp_path,tg=2):
    cfg,_,_=network_setup(tmp_path,tg)
    cfg.update(feed_policy=LATEST_FEED_POLICY,comment_window_limit=100,
        comment_participation_policy=PARTICIPATION_POLICY,memory_comment_policy=MEMORY_POLICY,
        prompt_encoding='lossless_thread_refs_v1',wire_prompt_style='concise_lossless_v1')
    b=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',cfg,tmp_path/'audit')
    e=V4Environment(b[1]);e.reset(cfg['behavior_seed']);e.advance_to(1)
    return cfg,b,e


def comment(i,tick=1,root='P001'):
    return dict(comment_id=f'X-{root}-{tick}-{i:04d}',author_id=f'A{i%582+1:04d}',
        published_tick=tick,target_content_id=root,text=f'完整原文第{i}条，轮次{tick}，主帖{root}。')


def test_network_restriction_unchanged(tmp_path):
    _,_,e=setup(tmp_path)
    assert sum(bool(o.local_information['posts']) for o in e.observe_batch(list(e.by_id),1))==82
    for i in range(200):e.comments[str(i)]=comment(i)
    e.advance_to(3)
    assert not roots(e.observe('A0084',3))


def test_latest100_no_future_and_full_archive_preserved(tmp_path):
    cfg,_,e=setup(tmp_path)
    for tick in (1,2,3,4):
        for i in range(150):e.comments[f'{tick}-{i}']=comment(i,tick)
    before=digest(e.comments);e.advance_to(3)
    p=e.observe('A0002',3).local_information['posts'][0]
    assert len(p['comments'])==100 and all(c['published_tick']==2 for c in p['comments'])
    assert p['comments']==recent_comments([c for c in e.comments.values() if c['published_tick']<3],100,cfg['behavior_seed'])
    assert digest(e.comments)==before and len(e.comments)==600


def test_ties_reproducible_not_insertion_or_account_order():
    cs=[comment(i) for i in range(250)]
    assert recent_comments(cs,100,42)==recent_comments(list(reversed(cs)),100,42)
    assert recent_comments(cs,100,42)!=recent_comments(cs,100,43)
    chosen={c['comment_id'] for c in recent_comments(cs,100,42)}
    assert chosen!={c['comment_id'] for c in cs[:100]}
    assert chosen!={c['comment_id'] for c in cs[-100:]}


def test_less_than100_shows_all():
    cs=[comment(i) for i in range(17)];shown=recent_comments(cs,100,42)
    assert len(shown)==17 and {c['comment_id'] for c in shown}=={c['comment_id'] for c in cs}


def test_separate_windows_and_repost_comments_in_correct_root(tmp_path):
    _,_,e=setup(tmp_path);e.advance_to(2)
    aid=next(a for a in e.direct_targets if e.by_id[a]['group']=='inside')
    e.apply([act(e,aid,repost=True,root='P001')]);relay=f'RP02-{aid}'
    for i in range(170):
        e.comments['p'+str(i)]=comment(i,1)
        e.comments['g'+str(i)]=comment(i,2,'G001')
    c=comment(1000,2,relay);e.comments['relay-comment']=c
    e.advance_to(3);views={p['content_id']:p for p in e.observe(aid,3).local_information['posts']}
    assert len(views['P001']['comments'])==len(views['G001']['comments'])==100
    assert c in views['P001']['comments'] and c not in views['G001']['comments']
    assert all(x['target_content_id']=='G001' for x in views['G001']['comments'])


def test_personal_memory_keeps_own_decisions_not_old_comment_transcripts(tmp_path):
    _,_,e=setup(tmp_path,7)
    for tick in range(1,7):
        e.advance_to(tick)
        for i in range(110):e.comments[f'{tick-1}:{i}']=comment(i,tick-1)
        a=act(e,'A0002',comment=tick==1);raw=copy.deepcopy(a.payload['answer']);e.apply([a])
        m=e.memory['A0002'][-1]
        assert m['comment']==raw['comment'] and m['repost']==raw['repost']
        assert m['subjective_credibility_after']==raw['subjective_credibility']
        assert m['observed_posts'][0]['comments']==[]
        assert m['observed_posts'][0]['observed_comment_count']==100
        assert m['observed_posts'][0]['comment_memory_policy']==MEMORY_POLICY
        assert len(a.payload['observed_posts'][0]['comments'])==100
    assert len(e.memory['A0002'])==5


def template():
    return (SOURCE/'02_Prompt固定提示词.md').read_text(encoding='utf-8').split(chr(96)*3+'text',1)[1].split(chr(96)*3,1)[0].strip()


def test_prompts_require_mbti_comment_choice_and_only_window(tmp_path):
    cfg,_,e=setup(tmp_path)
    for i in range(250):e.comments[str(i)]=comment(i)
    e.advance_to(2);ob=e.observe('A0002',2)
    for encoding in ('full_json_v1','lossless_thread_refs_v1'):
        base,feed,mem,_=prepare_prompt(template(),ob,limit=1_000_000,encoding=encoding)
        assert '只阅读、形成评分而不评论是完整且正常的参与' in base
        assert '最新100条评论' in base and '先决定本轮是否愿意公开评论' in base
        assert len(next(p for p in feed if p['root_content_id']=='P001')['comments'])==100
        if encoding=='lossless_thread_refs_v1':
            sent=wire_prompt(base,ob,1536,style='concise_lossless_v1')
            assert '在mbti_preferences的affects中必须包含comment' in sent
            assert '接触后可回看原帖和截至上一轮全部评论' not in sent
            assert len(extract_data(base)['libraries']['comments']['rows'])==100


def test_mbti_application_must_include_comment_even_when_abstaining(tmp_path):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(ob)
    raw['condition_application']['mbti_preferences']['affects']=['credibility']
    with pytest.raises(ValueError,match='condition coverage'):validate_condition_application(raw,ob)
    raw['condition_application']['mbti_preferences']['affects']=['comment']
    raw['condition_application']['mbti_preferences']['note']='本人倾向先独自消化，这轮不评论'
    validate_response(raw,ob,ob.local_information['posts'],[])


def test_live_abstention_respected_no_comment_added(tmp_path,monkeypatch):
    cfg,_,e=setup(tmp_path);monkeypatch.setenv('RUMOR_LLM_API_KEY','offline-test-key')
    ob=e.observe('A0002',1);c=LiveClient(cfg,tmp_path/'mock-audit');calls=[]
    def create(**kw):calls.append(kw);return response(answer(ob,60))
    c.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    raw,feed,meta=c.decide(ob,template())
    assert raw['comment']['enabled'] is False and len(calls)==1
    e.apply([fake_action(ob,raw)])
    assert not e.comments and e.beliefs[ob.agent_id]=='believe'


def test_rule_users_still_never_comment_and_draws_unchanged(tmp_path):
    cfg,b,e=setup(tmp_path);oldcfg,oldb,oldenv=network_setup(tmp_path/'old')
    new=V4Decision(cfg,SOURCE/'02_Prompt固定提示词.md',tmp_path/'d')
    old=V4Decision(oldcfg,SOURCE/'02_Prompt固定提示词.md',tmp_path/'old-d')
    for aid,row in e.by_id.items():
        if row['decision_mode']=='rule' and row['group']=='inside':
            a,draws=new._rule(e.observe(aid,1));other,old_draws=old._rule(oldenv.observe(aid,1))
            assert a==other and draws==old_draws and not a['comment']['enabled']


@pytest.mark.parametrize('field,value',[('comment_window_limit',99),('comment_window_limit',True),
    ('memory_comment_policy','complete_observed_v1'),('comment_participation_policy','legacy')])
def test_new_policy_explicit_and_validated(tmp_path,field,value):
    from experiment import validate_experiment
    cfg,_,_=setup(tmp_path);cfg[field]=value
    with pytest.raises(ValueError):validate_experiment(cfg)
