# SocioVerse V7：300名LLM-Agent

2026-10-27已按每人实际政府信任值加入较高、中等、较低三类角色描述，同时保留连续数值。当前版本为`v7-government-trust-persona-20261027-2`；文案、分档及检查方法见[政府信任角色描述](docs/V7政府信任角色描述.md)。

2026-10-27新增持续信念更新与逐人“相信转不信”事件记录。每轮显式使用上次分数、实际重复接触次数和两类来源信任，保留LLM自主评分，`>50`相信、`≤50`不相信。详见[新机制、字段和运行说明](docs/V7持续信念与相信转不信记录.md)。原54组已完成并保留；本次修订未自动启动新的付费模拟，旧批次的恢复入口不会重跑已完成组。

54组并行运行入口：`Run-V7-Batch54.cmd`。当前批次主API最多4路，三个副API各最多1路；一个副API冷却时实际6路，恢复后最多7路。结果保存到`E:\papers\socioverse 2026\socioverse2_v6_local\Results_V7`，每组一个Excel，按完整轮次更新。下文的`Run-V7.cmd`仍是单组入口。

失败API单独冷却10分钟后测试恢复，其他API继续处理；不会因为一个副API限流而削减健康主API的4路上限。实时调度由当前批次的`request_controls.json`控制，详见[当前批次API调度](docs/V7当前批次API空位调度.md)。

2026-10-26已修复普通PowerShell读取Codex包隔离目录中加密Key的路径问题。双击批次入口会打开真正承载模拟的独立PowerShell窗口，并从已有检查点和缓存恢复；已完成组自动跳过。请保留运行窗口，暂停用`Pause-V7-Batch54.cmd`。原始加密Key没有复制成明文，详见[独立窗口恢复说明](docs/V7独立窗口与断点恢复.md)。

独立目录：`E:\papers\socioverse 2026\socioverse2_v7_local`。V6代码和已有实验记录保留。

V7取消规则用户，只保留300名LLM用户：茧房内48人、茧房外252人。没有PB/RC/RF概率判断、规则用户自动纠正、规则用户替补或相关分类报表。未接触帖子时用户不调用LLM，保持未判断；接口失败时保留缓存并暂停，不能用程序生成回答替代。

## 启动

1. 双击 **Preview-V7.cmd**：验证设定并生成一名用户的实际发送提示预览，不调用API。
2. 双击 **Run-V7.cmd**：运行`configs/v7/one_condition.json`这一组，10个时间步。默认参数：来源信任均值差0.4、第2轮政府介入、圈内投放比例80%、政府信任均值0.75。
3. 发生暂停后按窗口菜单操作；关闭后双击 **Resume-V7.cmd** 接续最新V7实验。完整轮次回放，未提交轮次复用已校验缓存；不重复生成已完成决策。已经完成的实验不会再次调用API。

本机入口优先使用V7自己的`.venv`；尚未安装时，使用旁边V6已经安装的Python依赖。应用、资料、结果、冻结配置和自带SocioVerse框架均来自V7目录，不读取V6实验结果。需要独立安装时运行：

```powershell
cd 'E:\papers\socioverse 2026\socioverse2_v7_local'
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-V7.ps1
```

也可从PowerShell运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-V7.ps1 -Mode preview
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-V7.ps1 -Mode live -Steps 10
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-V7.ps1 -Mode status
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-V7.ps1 -Mode resume
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-V7.ps1 -Mode verify
```

## 设定与检查入口

- [详细设定与迁移说明](docs/V7模型设定与迁移说明.md)
- [当前参数](configs/v7/one_condition.json)
- [300名用户资料](materials_v7/01_Agent基础信息表.csv)
- [人口选择和圈层映射](materials_v7/06_人群选择与圈层映射.json)
- [提示模板](materials_v7/02_Prompt固定提示词.md)，动态信任要求在`app_v7/decision_conditions.py`，精简发送模板在`app_v7/concise_wire.py`。
- [原帖与官方帖](materials_v7/03_新环境设定.md)，两帖为研究情景。
- `configs/v7/research54/`保存54组设计，均投放50人。单组启动入口不会批量启动这54组。

提示全文预览在`runtime/v7/preview/first_agent_wire_prompt.txt`。正式结果在`runs/v7/`，逐轮人数表在每次结果的`reports/per_tick_results.csv`，个人评分在`trajectory/belief_measurements.csv`。CSV采用UTF-8 BOM，可以用Excel打开。

已有4个API密钥继续从本Windows用户的DPAPI加密库读取，密钥不写进V7代码或配置。本54组批次当前采用4:1:1:1加权调度及独立并发上限；明确拒绝后尝试其他可用槽。失败槽冷却10分钟后用一条正常待办决策测试恢复，所有槽都冷却时原地等待；供应商要求更长等待时遵守其期限。未知请求状态需人工确认，以免重复扣费。

原54组已完成真实API实验。新提示词需从新运行开始，不能拼接进旧版本实验的中间轮次；旧结果可以离线补导实际转换记录。离线测试的固定回答不属于研究结果。V6检查点不能载入V7：人口、网络和投放人数已改变。
