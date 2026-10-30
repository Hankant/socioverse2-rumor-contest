# V7 API自动接管（2026-10-27）

当前批次总并发上限8路：原7路加1条在三个副API间轮换的流动槽位。54组实验和累计预算保持原设定；科学输入、提示词、模型、记忆、评分及已保存回答保持不变。

所有API健康时，主API4路、三个副API各1路，另1路在backup→third→fourth之间轮换；同一时刻只有一个副API临时多承接1路。每次流动请求结束后选择下一个健康副API。冷却中的Key会跳过。某个基础API槽位不可用时，仍沿用弹性接管机制。例如（表中展示流动槽位某一时刻的分配）：

|可用情况|主API|副API1|副API2|副API3|总上限|
|---|---:|---:|---:|---:|---:|
|全部健康，流动槽位在副API1|4|2|1|1|8|
|全部健康，流动槽位转到副API2|4|1|2|1|8|
|副API1冷却，流动槽位在副API2|5|0|2|1|8|
|两个副API冷却|6|0|0|2|8|
|只有主API健康|8|0|0|0|8|
|主API冷却，流动槽位在副API1|0|6|1|1|8|

主API不可用时，也会自动交给其他健康API。三个副API均不可用时，流动槽位也可转给健康主API。实际并发仍取决于供应商是否接受请求。每个Key的弹性上限为8，但所有Key合计最多8，不是每个Key都同时发送8个请求。

限流Key按现有10分钟间隔恢复探测；供应商要求更长Retry-After时遵守较长时间。探测使用一个真实排队决策，不另发空测试请求。探测期间只允许该Key一条请求，通过后恢复正常分配。在途请求不会为重新分配被取消。

所有Key均冷却时，队列等待到恢复时点，不把失败请求当作结果。网络结局未知、错误输出、额度和请求预算仍沿用原来的有界恢复与保护机制。

配置位于当前批次 `request_controls.json`：

```json
{
  "max_global_concurrency": 8,
  "api_slot_concurrency": {"primary":4,"backup":1,"third":1,"fourth":1},
  "api_capacity_policy":"elastic_failover_v1",
  "api_spillover_max_concurrency":{"primary":8,"backup":8,"third":8,"fourth":8},
  "api_floating_lane_slots":["backup","third","fourth"]
}
```

`api-capacity-state.json` 中的 `slot_limits` 是基础分配，`effective_slot_limits` 是包含流动槽位的当前弹性分配，`active_by_slot` 是正在执行的请求，`floating_lane_active_slot` 是当前流动请求使用的Key。已启用该程序版本后，可热更新这些控制字段；API限流和恢复会自动重新分配，无须手动调整或重启。

当前结果路径：`D:\Codex\runs\V7_Optimized_20261027_145124`。
