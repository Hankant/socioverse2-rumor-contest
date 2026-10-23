"""Reversible, readable observation packing. No summarization or comment cap."""
import copy
import json

ENCODING = 'lossless_thread_refs_v1'
FULL_ENCODING = 'full_json_v1'
REFERENCE_KEYS = {'__text_ref','__comment_refs','__relay_refs'}


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


class Intern:
    def __init__(self):
        self.values=[]
        self.index={}

    def add(self,value):
        key=canonical(value)
        if key not in self.index:
            self.index[key]=len(self.values)
            self.values.append(copy.deepcopy(value))
        return self.index[key]


def table(records):
    columns=list(dict.fromkeys(k for row in records for k in row))
    result={'columns':columns,'rows':[[row.get(k) for k in columns] for row in records]}
    missing={str(i):[j for j,k in enumerate(columns) if k not in row] for i,row in enumerate(records)}
    missing={i:v for i,v in missing.items() if v}
    if missing:result['missing_columns']=missing
    return result


def untabulate(value):
    columns=value['columns'];missing=value.get('missing_columns',{})
    return [{k:copy.deepcopy(v) for j,(k,v) in enumerate(zip(columns,row,strict=True))
             if j not in missing.get(str(i),[])} for i,row in enumerate(value['rows'])]


def pack_observations(feed,memory):
    texts,comments,relays=Intern(),Intern(),Intern()
    def view(post):
        if REFERENCE_KEYS & set(post):raise ValueError('compact input reserved key collision')
        result=copy.deepcopy(post)
        if 'text' in result:result['__text_ref']=texts.add(result.pop('text'))
        if 'comments' in result:result['__comment_refs']=[comments.add(c) for c in result.pop('comments')]
        if 'relay_context' in result:result['__relay_refs']=[relays.add(r) for r in result.pop('relay_context')]
        return result
    packed_feed=[view(p) for p in feed]
    packed_memory=copy.deepcopy(memory)
    for m in packed_memory:
        if 'observed_posts' in m:m['observed_posts']=[view(p) for p in m['observed_posts']]
    return {'encoding':ENCODING,'texts':texts.values,'comments':table(comments.values),
            'relays':table(relays.values),'current_posts':packed_feed,'memory':packed_memory}


def unpack_observations(pack):
    if pack['encoding']!=ENCODING:raise ValueError('unknown observation encoding')
    comments,relays=untabulate(pack['comments']),untabulate(pack['relays'])
    def view(post):
        result=copy.deepcopy(post)
        if '__text_ref' in result:result['text']=copy.deepcopy(pack['texts'][result.pop('__text_ref')])
        if '__comment_refs' in result:result['comments']=[copy.deepcopy(comments[i]) for i in result.pop('__comment_refs')]
        if '__relay_refs' in result:result['relay_context']=[copy.deepcopy(relays[i]) for i in result.pop('__relay_refs')]
        return result
    feed=[view(p) for p in pack['current_posts']]
    memory=copy.deepcopy(pack['memory'])
    for m in memory:
        if 'observed_posts' in m:m['observed_posts']=[view(p) for p in m['observed_posts']]
    return feed,memory


def render_compact_prompt(template,ob,feed,memory):
    from llm_client import render_prompt
    pack=pack_observations(feed,memory)
    if unpack_observations(pack)!=(feed,memory):raise ValueError('lossless input roundtrip failed')
    # Keep the original renderer, all assigned conditions and all decision rules.
    # A library is included INSIDE the observations section, before decisions.
    legend=("【可逆输入格式：全文去重，没有摘要或抽样】下列三个库中的内容均为你实际可读的当前观察或个人记忆。"
        "库内索引从0开始；texts存正文；comments/relays用columns给出列名、rows给出各行完整值。"
        "帖子中的__text_ref指向texts，__comment_refs指向comments行，__relay_refs指向relays行。"
        "请按引用阅读完整正文和全部评论，不把索引数字当成证据ID。引用证据时返回content_id或comment_id原值。"
        "每次历史经历只含当时可见的引用列表；库中后来出现的评论不代表你当时已看到。"
        "当前帖子可见范围、评论顺序、实际转发记录和个人评分及行动均以各帧为准；"
        "missing_columns列出该行原本未提供的列，区别于明确的null。")
    libraries={k:pack[k] for k in ('encoding','texts','comments','relays')}
    library_text=legend+'\n'+json.dumps(libraries,ensure_ascii=False,separators=(',',':'))
    # Replace the observation placeholder first; the trusted template contains it
    # exactly once. Material strings are never searched/replaced after insertion.
    if template.count('{当前观察}')!=1 or template.count('{个人记忆}')!=1:
        raise ValueError('compact encoding requires one observation and one memory section')
    memory_marker='\x00V6_MEMORY_BLOCK\x00'
    observation_marker='\x00V6_OBSERVATION_BLOCK\x00'
    if memory_marker in template or observation_marker in template:raise ValueError('compact template marker collision')
    compact_template=template.replace('{当前观察}',observation_marker).replace('{个人记忆}',memory_marker)
    # No second full evidence-ID whitelist: the same literal IDs already appear
    # in the complete tables. The validator still uses the ORIGINAL full feed.
    prompt=render_prompt(compact_template,ob,pack['current_posts'],pack['memory'],include_evidence=False)
    if prompt.count(memory_marker)!=1 or prompt.count(observation_marker)!=1:
        raise ValueError('compact dynamic block marker collision')
    observed={'posts':pack['current_posts'],'eligible_repost_content_ids':[p['content_id'] for p in feed if p['can_repost']]}
    return prompt.replace(memory_marker,json.dumps(pack['memory'],ensure_ascii=False,separators=(',',':'))).replace(
        observation_marker,library_text+'\n'+json.dumps(observed,ensure_ascii=False,separators=(',',':')))
