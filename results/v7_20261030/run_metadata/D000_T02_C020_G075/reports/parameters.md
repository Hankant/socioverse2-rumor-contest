# V7 本组设定

全部300名用户均由LLM决策：圈内48、圈外252。已接触用户评分>50相信、≤50不相信；未接触者保持未判断。未判断不计入相信率分母。

本组运行10轮。第2轮官方独立账号仅投放一次，50人，其中圈内10人、圈外40人；不按当前是否相信筛选。

每人关注8名同圈用户和2名异圈用户，圈内用户另关注SOURCE。转发下一轮可见；首次接触由网络决定。每个可见主帖只呈现上一轮以前最新30条评论，两主帖最多60条；完整评论仍存档。

记忆保留前三个模拟轮次内的个人经历，不重复保存评论全文。旧评分、已接触记录和已转发标记持续保存。每个主帖每人最多转发一次。评论由LLM结合MBTI和其他条件自主决定。

subjective_credibility是持续的0—100原说法信念值。未首次判断前为null，不虚设50分；LLM每轮结合上次分数、真实重复接触和两种来源信任更新，不用程序固定加减。再次读原帖（直接或经关注者转发）可强化熟悉感；求证/反驳式转发不自动算支持。实际读过官方帖后，政府信任影响其否认的说服力。

每次评分从>50跨到≤50才写入reports/belief_to_reject_events.csv，记录本段相信开始、转换轮次、持续步数、前后评分和官方接触。再次相信后再转换另记一段；未转换者不填0。转换史不随3轮临时记忆清除。时间是抽象模拟步，不是现实分钟，也不自动归因于政府。

来源信任圈内外均值差0.0；均值中心0.5，离散参数0.1。政府信任均值0.75。均采用固定种子的对称截断分位数分配，实际标准差见冻结分配汇总。两种信任作为来源证据权重进入提示，不用程序按比例强行修改评分。

政府角色描述策略为individual_three_level_v1。启用individual_three_level_v1时，根据每人的实际政府信任值而非实验组均值生成角色描述：<1/3较低，1/3至<2/3中等，≥2/3较高。较高者通常认为政府较专业、信息较可靠；中等者结合具体解释判断；较低者对仅凭官方身份或否认较谨慎，但仍考虑具体核查材料。数值持续保留，三档仅是提示措辞的合成分档，不是经调查校准的心理分类。官方内容仍只向实际接触者提供。

LLM必须提交11项个人条件的简短应用摘要。摘要可核验覆盖，不能单独证明因果作用。人群为合成假设，不代表真实公众；官方帖为实验材料。

MiniMax-M3，关闭thinking，最多2路并发。API失败保留预算账本与已校验缓存；可确认属于额度/限流的拒绝每120秒重试。未知请求不自动重发。输出错误有限重试后暂停；不更改用户身份、不伪造回答。

预算是逐请求执行保护阈值，不是一次发送或必然消耗的用量。代理输入估算不是供应商真实token。配置如下：

```json
{
  "runtime_version": "v7-government-trust-persona-20261027-2",
  "population_n": 300,
  "inside_n": 48,
  "outside_n": 252,
  "contract_status": "authorized_engineering_run",
  "model": "MiniMax-M3",
  "base_url": "https://api.minimax.cn/v1",
  "api_profile": "minimax_m3",
  "source_trust_gap": 0.0,
  "source_trust_center": 0.5,
  "source_trust_sd": 0.1,
  "source_trust_seed": 20261023,
  "government_tick": 2,
  "government_reach": 50,
  "targeting_inside_ratio": 0.2,
  "government_trust_mean": 0.75,
  "government_trust_sd": 0.1,
  "government_target_seed": 20261019,
  "government_trust_seed": 20261022,
  "behavior_seed": 20261020,
  "prompt_encoding": "lossless_thread_refs_v1",
  "wire_prompt_style": "concise_shared_prefix_v1",
  "feed_policy": "network_rumor_latest_comments_v1",
  "comment_window_limit": 30,
  "comment_participation_policy": "mbti_voluntary_comment_v1",
  "memory_comment_policy": "personal_actions_no_comment_transcripts_v1",
  "memory_retention_policy": "rolling_simulation_ticks_v1",
  "memory_window_ticks": 3,
  "decision_condition_policy": "all_conditions_v1",
  "belief_measurement_policy": "binary_score_gt50_v1",
  "comment_target": "explicit_visible_root",
  "belief_update_policy": "autonomous_belief_reinforcement_v1",
  "belief_transition_policy": "believe_to_reject_episodes_v1",
  "government_trust_prompt_policy": "individual_three_level_v1",
  "prompt_input_token_limit": 524288,
  "prompt_memory_policy": "preserve",
  "llm_max_output_tokens": 1536,
  "max_input_reserved_units": 750000000,
  "max_output_reserved_tokens": 6246400,
  "max_requests": 12200,
  "api_key_mode": "windows_dpapi_failover",
  "api_routing_policy": "round_robin_v1",
  "api_primary_retry_seconds": 3600,
  "api_key_cooldown_seconds": 60,
  "rate_recovery_successes": 20,
  "rate_recovery_seconds": 60.0,
  "rate_limit_max_retries": 6,
  "rate_limit_wait_seconds": 2.0,
  "rate_limit_max_wait_seconds": 60.0,
  "rate_limit_spacing_seconds": 1.0,
  "max_concurrency": 2,
  "format_max_attempts": 4
}
```
