"""Committed-tick counts for workbook jobs; no partial LLM decisions enter counts."""
from collections import defaultdict,Counter
from model import dump

DIMENSIONS={'圈层':'group','MBTI':'synthetic_mbti_type','年龄段':'synthetic_age_band','职业':'synthetic_occupation','地区':'synthetic_region'}


def count_rows(env,t):
    commenters={c['author_id'] for c in env.comments.values() if c['published_tick']==t}
    reposters={p['author_id'] for p in env.posts.values() if p['content_id'].startswith('RP') and p['published_tick']==t}
    def result(ids,dimension,label):
        counts=Counter(env.beliefs[a] for a in ids);yes=counts['believe'];no=counts['reject']
        return dict(tick=t,dimension=dimension,type=label,population=len(ids),believe=yes,reject=no,unjudged=counts['unjudged'],
            commenting=len(set(ids)&commenters),reposting=len(set(ids)&reposters),
            rumor_seen=sum('P001' in env.seen[a] for a in ids),official_seen=sum('G001' in env.seen[a] for a in ids))
    main=[result(list(env.by_id),'圈层','全体')];detail=[]
    for dimension,field in DIMENSIONS.items():
        groups=defaultdict(list)
        for aid,row in env.by_id.items():groups[row[field]].append(aid)
        for label,ids in sorted(groups.items()):
            if dimension=='圈层':main.append(result(ids,dimension,{'inside':'圈内','outside':'圈外'}[label]))
            else:detail.append(result(ids,dimension,label))
    return main,detail


class WorkbookJob:
    def __init__(self,path,tag,cfg,filename):
        self.path,self.tag,self.cfg,self.filename=path,tag,cfg,filename;self.main={};self.detail={};self.folder=None;self.transitions=None
        self.write('queued',0)
    def write(self,status,last_tick,error=None):
        value=dict(schema_version=1,case=self.tag,filename=self.filename,config=self.cfg,status=status,last_completed_tick=last_tick,
            error_type=error,run_dir=str(self.folder) if self.folder else None,
            rows=[r for t in sorted(self.main) for r in self.main[t]],detail=[r for t in sorted(self.detail) for r in self.detail[t]])
        if self.transitions is not None:value['belief_to_reject_events']=self.transitions
        dump(self.path,value)
    def progress(self,folder,state,cfg,env,t,metrics):
        self.folder=folder;self.main[t],self.detail[t]=count_rows(env,t)
        if getattr(env,'belief_tracker',None)is not None:self.transitions=list(env.belief_tracker.events)
        self.write(state['status'],state['last_completed_tick'])
