# TG5历史结果归档

运行：government-rumor-v6-openai-20261021-161751-705834，真实LLM，已完成10轮。

该次为三态判断历史版本，不能解释为仓库当前评分二分类、MBTI与最新50评论配置的结果。原始provenance、冻结输入、原始请求审计与结果保持原样；绝对路径属于历史来源证据，不用于新机器运行。

## 参数

```json
{
  "pbd": 0.0,
  "government_tick": 5,
  "government_reach": 40,
  "government_trust_mean": null,
  "targeting_inside_ratio": null,
  "strategy": "inside",
  "gt": 0.6,
  "rf": 0.6,
  "max_concurrency": 10,
  "model": "MiniMax-M3",
  "runtime_version": "v6-adaptive-rolling-6"
}
```

pbd只控制规则用户，定位比例null沿用inside策略，政府信任均值null表示规则GT0.6及LLM原persona，不是统一均值。

## 结果与用量

```json
{
  "final_metrics": {
    "all_unjudged": 6,
    "all_believe": 6,
    "all_uncertain": 57,
    "all_reject": 513,
    "llm_unjudged": 6,
    "llm_believe": 0,
    "llm_uncertain": 57,
    "llm_reject": 242,
    "rule_unjudged": 0,
    "rule_believe": 6,
    "rule_uncertain": 0,
    "rule_reject": 271,
    "remaining_agents": 520,
    "technical_dropout_count": 62,
    "remaining_llm": 243,
    "remaining_rule": 277,
    "remaining_unjudged": 0,
    "remaining_believe": 6,
    "remaining_uncertain": 1,
    "remaining_reject": 513,
    "posts": 860,
    "comments": 1433,
    "reread_presentations": 2356,
    "visible_comment_presentations": 1621,
    "partial_actions": 1,
    "idle_actions": 62,
    "tbu_cohort": 245,
    "tbu_completed": 240,
    "tbu_engineering": 1.8208333333333333,
    "step": 10
  },
  "budget": {
    "requests": 2405,
    "input_reserved_units": 8897233,
    "output_reserved_tokens": 1231360,
    "actual_input_tokens": 5163774,
    "actual_output_tokens": 265555,
    "usage_unknown_requests": 176
  }
}
```

usage_unknown_requests是错误请求用量未知，不代表一定收费或免费。此处不虚构货币费用。完整数据位于research_archive/v6_tg5_completed/{run,audit,frozen_inputs}，EXPORT_MANIFEST.json保存导出文件哈希。
