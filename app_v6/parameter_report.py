from pathlib import Path
import json

def write_parameters(run_dir, cfg, steps):
    ratio=cfg['targeting_inside_ratio'];mu=cfg['government_trust_mean']
    target=f"{ratio:g}" if ratio is not None else f"null；使用strategy={cfg['strategy']}"
    trust=f"{mu:g}" if mu is not None else f"null；规则GT={cfg['gt']}，LLM沿用既有persona，不代表统一均值"
    rows=[('圈内外相信差异','pbd',cfg['pbd'],'仅规则用户；同时调整PB和RC，不控制LLM初始相信差异'),
          ('政府介入轮次','government_tick',cfg['government_tick'],'该轮启用政府纠正'),
          ('定位能力','targeting_inside_ratio',target,'控制直接接收者圈内比例；不筛选是否已相信'),
          ('政府信任均值','government_trust_mean',trust,'显式设置均值时：规则用于GT抽样，LLM用于来源评价提示'),
          ('直接接触人数','government_reach',cfg['government_reach'],'固定直接接收人数；圈内仅82人，不允许100人全部圈内')]
    lines=['# 实验参数记录','',f'运行：{Path(run_dir).name}', '', '| 参数 | 字段 | 本次值 | 作用边界 |','|---|---|---|---|']
    lines += ['| '+' | '.join(map(str,r))+' |' for r in rows]
    lines += ['',f"总轮数：{steps}；模型：{cfg['model']}；RF：{cfg['rf']}；行为seed：{cfg['behavior_seed']}。",
              f"并发上限：{cfg['max_concurrency']}（实际可自适应下降）；运行版本：{cfg['runtime_version']}；请求总预算：{cfg['max_requests']}。",
              '', '上述为本次配置，不表示所有参数组合已运行。研究参数相同不保证随机LLM输出一致；调度版本及失败处理差异须在比较时保留。']
    Path(run_dir,'实验参数.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    Path(run_dir,'experiment_parameters.json').write_text(json.dumps({'total_steps':steps,'config':cfg,'scope_notes':{r[1]:r[3] for r in rows}},ensure_ascii=False,indent=2),encoding='utf-8')
