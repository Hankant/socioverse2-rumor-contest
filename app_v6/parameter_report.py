from pathlib import Path
import json

def write_parameters(run_dir, cfg, steps):
    ratio=cfg['targeting_inside_ratio'];mu=cfg['government_trust_mean']
    target=f"{ratio:g}" if ratio is not None else f"null；使用strategy={cfg['strategy']}"
    trust=f"{mu:g}" if mu is not None else f"null；规则GT={cfg['gt']}，LLM沿用既有persona，不代表统一均值"
    from model import feed_description
    from memory_policy import memory_description
    rows=[('输入编码','prompt_encoding',cfg.get('prompt_encoding','full_json_v1'),'lossless_thread_refs_v1：全文按库去重，历史保留索引和时序；所有内容可逆还原，无评论抽样'),
          ('API调度','api_routing_policy',cfg.get('api_routing_policy','primary_first_v1'),'round_robin_v1：按加密槽位主/副/第三/第四（如有）逐请求循环；明确失败后尝试其他可用路；共享请求与token预算'),
          ('API临时故障冷却','api_key_cooldown_seconds',cfg.get('api_key_cooldown_seconds',60),'临时故障默认60秒，认证/额度问题3600秒；更长Retry-After优先；无请求时不主动探测'),
          ('评论展示上限','comment_window_limit',cfg.get('comment_window_limit'),f"每个可见主帖取截至上一轮最新{cfg.get('comment_window_limit')}条；同轮以行为种子散列打破并列，非热度排序；旧版null为全量"),
          ('自愿评论机制','comment_participation_policy',cfg.get('comment_participation_policy','legacy'),'LLM结合MBTI四维及强度和全部个人条件，先决定评论/沉默；不强制比例；规则用户仍不评论'),
          ('临时记忆到期策略','memory_retention_policy',cfg.get('memory_retention_policy','last_five_experiences_v1'),memory_description(cfg)+'；不删除本地原始日志，不重置当前信念与传播状态'),
          ('临时记忆轮数','memory_window_ticks',cfg.get('memory_window_ticks'),'rolling策略按模拟轮次到期；null为历史版本最近5次经历'),
          ('历史评论策略','memory_comment_policy',cfg.get('memory_comment_policy','complete_observed_v1'),'新版仅保留记忆窗口内个人评分/行动和接触记录，不重新输入旧评论全文；原始决策日志仍留档'),
          ('发送表达','wire_prompt_style',cfg.get('wire_prompt_style','standard'),'shared_prefix版把共同规则和实际可见材料库前置以增加前缀缓存机会；精简说明和可逆元数据保留完整原文与条件；命中不代表已验证订阅额度折扣'),
          ('阅读策略','feed_policy',cfg.get('feed_policy','legacy'),feed_description(cfg.get('feed_policy','legacy'),cfg.get('comment_window_limit'))),
          ('个人条件逐项应用','decision_condition_policy',cfg.get('decision_condition_policy','legacy'),'all_conditions_v1：11项输入与逐项应用摘要必填；校验结构覆盖，不证明每项的因果效应'),
          ('评论对象','comment_target',cfg.get('comment_target','first_displayed_post'),'explicit_visible_root：LLM显式选择当前实际展示的主帖；不再自动挂在第一帖'),
          ('初始来源信任均值差','source_trust_gap',cfg.get('source_trust_gap'),'LLM角色的初始SOURCE信任；不是初始相信比例；null保留旧persona'),
          ('来源信任分配中心','source_trust_center',cfg.get('source_trust_center',.5),'圈内均值=center+gap/2；圈外=center-gap/2'),
          ('来源信任分布尺度','source_trust_sd',cfg.get('source_trust_sd',.1),'对称截断正态分位点；实际标准差以冻结分配摘要为准'),
          ('规则组来源信任映射','rule_source_trust_mode',cfg.get('rule_source_trust_mode','legacy_pb'),'本研究选择legacy_pb：规则PB=.579、RC=.1；分配的SOURCE信任不直接控制规则抽样'),
          ('旧PBd参数','pbd',cfg['pbd'],'历史规则PB/RC表参数；本地54条件固定为0，不与来源信任差混用'),
          ('政府介入轮次','government_tick',cfg['government_tick'],'该轮启用政府纠正'),
          ('定位能力','targeting_inside_ratio',target,'控制直接接收者圈内比例；不筛选是否已相信'),
          ('政府信任均值','government_trust_mean',trust,'显式设置均值时：规则用于GT抽样，LLM用于来源评价提示'),
          ('直接接触人数','government_reach',cfg['government_reach'],'固定100人；80%/20%对应圈内80/20人；不筛选当前信念'),
          ('输入长度上限','prompt_input_token_limit',cfg.get('prompt_input_token_limit',4096),'代理估算token，非MiniMax官方计数；与模型上下文能力不同'),
          ('输入记忆策略','prompt_memory_policy',cfg.get('prompt_memory_policy','trim_oldest'),'preserve保留当前全部观察及设定窗口内完整经历，超限在调用前暂停；trim_oldest保留旧行为')]
    lines=['# 实验参数记录','',f'运行：{Path(run_dir).name}', '', '| 参数 | 字段 | 本次值 | 作用边界 |','|---|---|---|---|']
    lines += ['| '+' | '.join(map(str,r))+' |' for r in rows]
    lines += ['',f"总轮数：{steps}；模型：{cfg['model']}；RF：{cfg['rf']}；行为seed：{cfg['behavior_seed']}。",
              f"判断测量策略：{cfg.get('belief_measurement_policy','legacy')}；每次最大输出：{cfg.get('llm_max_output_tokens',512)} tokens。",
              "异质人群：新增年龄、合成地区、职业、MBTI风格偏好及经历见冻结人口CSV与06设定；均非真实账户已核实属性。规则角色资料不改变其概率公式。",
              ("LLM只自报评分，程序以完整说法主观可信度>50记believe、<=50记reject；分项不参与最终分类。相信率分母为believe+reject，未判断单列。规则角色继续原二分类概率公式。" if cfg.get('belief_measurement_policy')=='binary_score_gt50_v1' else "主观可信度及3个分项仅由LLM自报，不是校准概率，不用阈值重写belief；规则角色缺失分数保持空白。"),
              f"并发上限：{cfg['max_concurrency']}（实际可自适应下降）；运行版本：{cfg['runtime_version']}；请求总预算：{cfg['max_requests']}。",
              f"输入预留上限：{cfg.get('max_input_reserved_units',49971200)}；输出预留上限：{cfg.get('max_output_reserved_tokens',6246400)}。",
              '', '上述为本次配置，不表示所有参数组合已运行。研究参数相同不保证随机LLM输出一致；调度版本及失败处理差异须在比较时保留。',
              '当前MiniMax官方文档注明M3使用temperature=1、top_p=.95，忽略自行传入的其他取值。来源：https://platform.minimax.io/docs/api-reference/text-openai-api',
              '', '## 全部有效配置（复核用）', '', '```json', json.dumps(cfg,ensure_ascii=False,indent=2), '```']
    Path(run_dir,'实验参数.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    Path(run_dir,'experiment_parameters.json').write_text(json.dumps({'total_steps':steps,'config':cfg,'scope_notes':{r[1]:r[3] for r in rows}},ensure_ascii=False,indent=2),encoding='utf-8')
