"""Bounded punctuation repair. Never infer a missing key name, value or action."""
import hashlib
import json
import re

VERSION='json-delimiters-v1'
ROOT_KEYS={'belief','subjective_credibility','component_credibility','comment','repost',
           'evidence_ids','condition_application','condition_context_ref'}
REQUIRED={'subjective_credibility','component_credibility','comment','repost',
          'evidence_ids','condition_application'}
CONDITION_KEYS={'age','region','occupation','community_experience','mbti_preferences',
                'source_trust','government_trust','verification_preference',
                'sharing_propensity','repetition_sensitivity','history_and_memory'}


def schema_keys(path):
    if path==():return ROOT_KEYS
    if path in(('comment',),('repost',)):return {'enabled','target_content_id','text'}
    if path==('component_credibility',):return {'funds_redirected','safety_delayed','causal_link'}
    if path==('condition_application',):return CONDITION_KEYS
    if len(path)==2 and path[0]=='condition_application'and path[1]in CONDITION_KEYS:return {'affects','note'}
    return set()


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON key')
        result[key]=value
    return result


def atoms(text):
    """Return every literal/key verbatim, ignoring delimiters and whitespace."""
    result=[];i=0;decoder=json.JSONDecoder()
    while i<len(text):
        if text[i].isspace() or text[i] in '{}[],:':
            i+=1;continue
        start=i
        if text[i]=='"':
            _,n=decoder.raw_decode(text[i:]);i+=n
        else:
            while i<len(text) and not text[i].isspace() and text[i] not in '{}[],:"':
                i+=1
            if i==start:raise ValueError('invalid lexical token')
        result.append(text[start:i])
    return result


def outside_strings(text):
    result=[];quoted=False;escaped=False
    for i,c in enumerate(text):
        if quoted:
            if escaped:escaped=False
            elif c=='\\':escaped=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        else:result.append((i,c))
    if quoted:raise ValueError('unterminated string cannot be repaired')
    return result


def strict_shape(value):
    if not isinstance(value,dict) or not REQUIRED<=set(value) or not set(value)<=ROOT_KEYS:
        raise ValueError('incomplete or ambiguous repaired root')
    for field in ('comment','repost'):
        if not isinstance(value[field],dict) or set(value[field])!={'enabled','target_content_id','text'}:
            raise ValueError('repaired action structure is ambiguous')


def _repair_v1(text,max_edits=3):
    """Only trailing commas, premature/excess root closes and missing EOF closes.

    Every literal must be byte-for-byte identical and occur in the same order.
    Schema and observation validation are mandatory AFTER this function.
    """
    if not isinstance(text,str):raise ValueError('not JSON text')
    payload=text.strip()
    fence=re.fullmatch(chr(96)*3+r'(?:json)?\s*\n(.*?)\n\s*'+chr(96)*3,payload,re.DOTALL|re.IGNORECASE)
    if fence:payload=fence.group(1).strip()
    if not payload.startswith('{'):raise ValueError('only one root object is repairable')
    original=payload;original_atoms=atoms(original);edits=[]
    decoder=json.JSONDecoder(object_pairs_hook=unique_object)
    for _ in range(max_edits+2):
        # Commas are removed only outside strings before a closing delimiter,
        # or after the whole root. Never strip a literal or quoted punctuation.
        positions=[]
        for i,c in outside_strings(payload):
            if c!=',':continue
            tail=payload[i+1:].lstrip()
            if not tail or tail[0] in '}]':positions.append(i)
        if positions:
            if len(edits)+len(positions)>max_edits:raise ValueError('syntax edit bound exceeded')
            for i in reversed(positions):
                edits.append({'kind':'remove_trailing_comma','offset_at_edit':i})
                payload=payload[:i]+payload[i+1:]
            continue
        try:
            value,end=decoder.raw_decode(payload)
        except json.JSONDecodeError:
            stack=[]
            for _,c in outside_strings(payload):
                if c in '{[':stack.append(c)
                elif c in '}]':
                    if not stack or ('}' if stack[-1]=='{' else ']')!=c:
                        raise ValueError('ambiguous mismatched delimiters')
                    stack.pop()
            if not stack:raise ValueError('not a bounded delimiter error')
            closes=''.join('}' if c=='{' else ']' for c in reversed(stack))
            if len(edits)+len(closes)>max_edits:raise ValueError('syntax edit bound exceeded')
            edits.extend({'kind':'append_eof_close','delimiter':c} for c in closes)
            payload+=closes
            continue
        if end==len(payload):
            if not edits:raise ValueError('no syntax repair needed')
            strict_shape(value)
            if atoms(payload)!=original_atoms:raise ValueError('syntax repair changed a literal')
            return value,{'version':VERSION,'changes':edits,'literal_sequence_unchanged':True,
                'behavioral_fields_changed':False,
                'raw_response_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),
                'repaired_json_sha256':hashlib.sha256(payload.encode('utf-8')).hexdigest()}
        tail=payload[end:]
        follow=re.match(r',\s*"([^"]+)"\s*:',tail)
        if (follow and follow.group(1) in ROOT_KEYS and isinstance(value,dict)
                and follow.group(1) not in value and payload[end-1]=='}'):
            if len(edits)>=max_edits:raise ValueError('syntax edit bound exceeded')
            edits.append({'kind':'remove_premature_root_close','offset_at_edit':end-1})
            payload=payload[:end-1]+payload[end:];continue
        if tail.strip() and all(c.isspace() or c in '}]' for c in tail):
            count=sum(not c.isspace() for c in tail)
            if len(edits)+count>max_edits:raise ValueError('syntax edit bound exceeded')
            edits.extend({'kind':'remove_excess_eof_close','delimiter':c} for c in tail if not c.isspace())
            payload=payload[:end];continue
        raise ValueError('multiple objects or extra non-delimiter content')
    raise ValueError('syntax repair bound exhausted')


def _schema_delimiter_edit(text):
    """Find one unambiguous missing comma or close after a complete action.

    A root-only key inside comment/repost can only follow their three required
    fields. Close the action before its preceding comma; retain every literal.
    Never repair quotes, names, scores, actions or a missing real value.
    """
    decoder=json.JSONDecoder();stack=[];i=0
    action_fields={'enabled','target_content_id','text'}
    while i<len(text):
        c=text[i]
        if c.isspace():i+=1;continue
        current=stack[-1] if stack else None
        if c in '{[':
            if current is None:
                if i!=0 or c!='{':return None
                path=()
            else:
                if current['state']!='value':return None
                path=current['path']+(current.get('key','[]'),);current['state']='comma'
            stack.append(dict(kind=c,path=path,state='key' if c=='{' else 'value',seen=set(),key=None,comma=None));i+=1;continue
        if c in '}]':
            if not current or ('}' if current['kind']=='{' else ']')!=c:return None
            stack.pop();i+=1;continue
        if not current:return None
        if c==',':
            if current['state']!='comma':return None
            current['state']='key' if current['kind']=='{' else 'value';current['comma']=i;i+=1;continue
        if c==':':
            if current['state']!='colon':return None
            current['state']='value';i+=1;continue
        if current['kind']=='{'and current['state']=='key':
            # Only restore the absent opening delimiter of an exact existing
            # schema key: occupation":... . Never infer either a key name or
            # value, quote a bare value/ID, or inspect quoted user prose.
            missing=re.match(r'([A-Za-z_][A-Za-z0-9_]*)"\s*:',text[i:])
            if missing and missing.group(1)in schema_keys(current['path']):
                return dict(kind='insert_missing_schema_key_open_quote',key=missing.group(1),
                    offset_at_edit=i,character='"')
        try:value,n=decoder.raw_decode(text[i:])
        except (ValueError,json.JSONDecodeError):return None
        if current['kind']=='{' and current['state']=='comma' and isinstance(value,str):
            after=text[i+n:].lstrip()
            if after.startswith(':'):return dict(kind='insert_missing_object_comma',offset_at_edit=i,character=',')
        if current['kind']=='{' and current['state']=='key':
            if not isinstance(value,str):return None
            if (current['path'] in (('comment',),('repost',)) and current['seen']==action_fields
                    and value in ROOT_KEYS-action_fields and current['comma'] is not None):
                return dict(kind='close_complete_action_before_root_field',field=current['path'][0],next_root_field=value,offset_at_edit=current['comma'],character='}')
            current['key']=value;current['seen'].add(value);current['state']='colon'
        elif current['state']=='value':current['state']='comma'
        else:return None
        i+=n
    return None


def _repair_delimiters_v2(text,max_edits=3):
    try:return _repair_v1(text,max_edits)
    except ValueError:pass
    if not isinstance(text,str):raise ValueError('not JSON text')
    payload=text.strip();fence=re.fullmatch(chr(96)*3+r'(?:json)?\s*\n(.*?)\n\s*'+chr(96)*3,payload,re.DOTALL|re.IGNORECASE)
    if fence:payload=fence.group(1).strip()
    original_atoms=atoms(payload);edits=[]
    for _ in range(max_edits):
        change=_schema_delimiter_edit(payload)
        if change is None:break
        at=change['offset_at_edit'];payload=payload[:at]+change['character']+payload[at:];edits.append(change)
        try:
            value=json.loads(payload,object_pairs_hook=unique_object);strict_shape(value)
            extra=[]
        except ValueError:
            try:value,meta=_repair_v1(payload,max_edits-len(edits));extra=meta['changes']
            except ValueError:continue
        if atoms(payload)!=original_atoms:raise ValueError('syntax repair changed a literal')
        return value,dict(version='json-delimiters-v2',changes=edits+extra,literal_sequence_unchanged=True,behavioral_fields_changed=False,
            raw_response_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
            repaired_object_sha256=hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest())
    raise ValueError('No unambiguous bounded delimiter repair')


def _accept_punctuation_repair(payload,remaining):
    try:
        value=json.loads(payload,object_pairs_hook=unique_object)
        strict_shape(value)
        return value,[]
    except ValueError:
        value,meta=_repair_delimiters_v2(payload,remaining)
        return value,meta['changes']


def repair_document(text,max_edits=3):
    """Keep prior repairs first; add two narrowly observed MiniMax typos.

    Opening quotes may be inserted only in object-key position before an exact
    known key whose closing quote already exists. One orphan quote/apostrophe/
    pipe/backtick may be removed at EOF only if the remainder is a complete,
    strictly shaped root or needs an already supported bounded delimiter fix.
    Never discard prose, another value/object, or replace malformed decisions.
    Observation/score/action/condition validation is still mandatory afterwards.
    """
    try:return _repair_delimiters_v2(text,max_edits)
    except ValueError:pass
    if not isinstance(text,str):raise ValueError('not JSON text')
    payload=text.strip()
    fence=re.fullmatch(chr(96)*3+r'(?:json)?\s*\n(.*?)\n\s*'+chr(96)*3,payload,re.DOTALL|re.IGNORECASE)
    if fence:payload=fence.group(1).strip()
    if not payload.startswith('{'):raise ValueError('only one root object is repairable')
    edits=[]
    def accepted(value,extra):
        return value,dict(version='json-schema-punctuation-v3',changes=edits+extra,
            literal_sequence_unchanged=True,behavioral_fields_changed=False,
            key_names_inferred=False,value_literals_inferred=False,
            repair_scope='punctuation_only; quoted_values_and_existing_key_characters_preserved',
            raw_response_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
            repaired_object_sha256=hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest())
    for _ in range(max_edits):
        change=_schema_delimiter_edit(payload)
        if change is None:break
        at=change['offset_at_edit'];payload=payload[:at]+change['character']+payload[at:];edits.append(change)
        try:value,extra=_accept_punctuation_repair(payload,max_edits-len(edits))
        except ValueError:continue
        return accepted(value,extra)
    tail=payload.rstrip()
    if len(edits)<max_edits and tail and tail[-1]in ('"',"'",'|','`'):
        candidate=tail[:-1].rstrip()
        if candidate.endswith(('}',']')):
            value,extra=_accept_punctuation_repair(candidate,max_edits-len(edits)-1)
            edits.append(dict(kind='remove_single_orphan_eof_marker',offset_at_edit=len(tail)-1,character=tail[-1]))
            return accepted(value,extra)
    raise ValueError('No unambiguous bounded punctuation repair')
