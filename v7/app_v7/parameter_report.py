"""Freeze a readable parameter inventory with each V7 run."""
import json
from pathlib import Path
from model import dump


def write_parameters(folder,cfg,steps):
    folder=Path(folder);n=cfg['government_reach'];inside=round(n*cfg['targeting_inside_ratio'])
    dump(folder/'parameters.json',dict(config=cfg,steps=steps,government_inside=inside,government_outside=n-inside))
    text=f'''# V7 本组设定

全部300名用户均由LLM决策：圈内48、圈外252。已接触用户评分>50相信、≤50不相信；未接触者保持未判断。未判断不计入相信率分母。

本组运行{steps}轮。第{cfg['government_tick']}轮官方独立账号仅投放一次，{n}人，其中圈内{inside}人、圈外{n-inside}人；不按当前是否相信筛选。

每人关注8名同圈用户和2名异圈用户，圈内用户另关注SOURCE。转发下一轮可见；首次接触由网络决定。每个可见主帖只呈现上一轮以前最新30条评论，两主帖最多60条；完整评论仍存档。

记忆保留前三个模拟轮次内的个人经历，不重复保存评论全文。旧评分、已接触记录和已转发标记持续保存。每个主帖每人最多转发一次。评论由LLM结合MBTI和其他条件自主决定。

subjective_credibility是持续的0—100原说法信念值。未首次判断前为null，不虚设50分；LLM每轮结合上次分数、真实重复接触和两种来源信任更新，不用程序固定加减。再次读原帖（直接或经关注者转发）可强化熟悉感；求证/反驳式转发不自动算支持。实际读过官方帖后，政府信任影响其否认的说服力。

每次评分从>50跨到≤50才写入reports/belief_to_reject_events.csv，记录本段相信开始、转换轮次、持续步数、前后评分和官方接触。再次相信后再转换另记一段；未转换者不填0。转换史不随3轮临时记忆清除。时间是抽象模拟步，不是现实分钟，也不自动归因于政府。

来源信任圈内外均值差{cfg['source_trust_gap']}；均值中心{cfg['source_trust_center']}，离散参数{cfg['source_trust_sd']}。政府信任均值{cfg['government_trust_mean']}。均采用固定种子的对称截断分位数分配，实际标准差见冻结分配汇总。两种信任作为来源证据权重进入提示，不用程序按比例强行修改评分。

政府角色描述策略为{cfg.get('government_trust_prompt_policy','legacy_numeric_description')}。启用individual_three_level_v1时，根据每人的实际政府信任值而非实验组均值生成角色描述：<1/3较低，1/3至<2/3中等，≥2/3较高。较高者通常认为政府较专业、信息较可靠；中等者结合具体解释判断；较低者对仅凭官方身份或否认较谨慎，但仍考虑具体核查材料。数值持续保留，三档仅是提示措辞的合成分档，不是经调查校准的心理分类。官方内容仍只向实际接触者提供。

LLM必须提交11项个人条件的简短应用摘要。摘要可核验覆盖，不能单独证明因果作用。人群为合成假设，不代表真实公众；官方帖为实验材料。

MiniMax-M3，关闭thinking，最多{cfg['max_concurrency']}路并发。API失败保留预算账本与已校验缓存；可确认属于额度/限流的拒绝每120秒重试。未知请求不自动重发。输出错误有限重试后暂停；不更改用户身份、不伪造回答。

预算是逐请求执行保护阈值，不是一次发送或必然消耗的用量。代理输入估算不是供应商真实token。配置如下：

```json
{json.dumps(cfg,ensure_ascii=False,indent=2)}
```
'''
    (folder/'reports').mkdir(exist_ok=True);(folder/'reports/parameters.md').write_text(text,encoding='utf-8')
