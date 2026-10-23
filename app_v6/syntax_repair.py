"""Bounded delimiter-only repair. Never infer a string, key, score or action."""
import hashlib
import json
import re

VERSION='json-delimiters-v1'
ROOT_KEYS={'belief','subjective_credibility','component_credibility','comment','repost',
           'evidence_ids','condition_application','condition_context_ref'}
REQUIRED={'subjective_credibility','component_credibility','comment','repost',
          'evidence_ids','condition_application'}


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


def repair_document(text,max_edits=3):
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
