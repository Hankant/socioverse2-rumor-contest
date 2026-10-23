# 当前 V6 本地模型（2026-10-23）

最新单组入口是 `Run-V6-Latest50-ONE.cmd`，对应 `configs/one_latest50_mbti_test.json`：305 名 LLM 用户＋277 名规则用户，10 轮；网络决定首次接触，每个可见主帖展示截至上一轮最新 50 条评论，个人临时记忆保留过去 3 个模拟轮次。LLM 以 0—100 分判断，>50 相信、≤50 不相信；结合 MBTI 和全部个人条件自主决定评论与转发。政府使用独立账号。

模型为 MiniMax-M3。已支持 Windows 当前用户 DPAPI 加密保存最多四把 Key，按主、副、第三、第四顺序轮询，跳过故障冷却中的 Key；所有 Key 共享每次实验的请求和 token 保护上限。**GitHub 不包含任何真实 Key、加密凭据文件、虚拟环境或当前 `runs/`、`runtime/`。** 克隆到另一台 Windows 电脑后，先运行 `Setup-V6.ps1`，再通过 `python scripts/manage_api_keys.py set` 在本地隐藏输入自己的 Key。

无模型调用的预检：

```powershell
.\.venv\Scripts\python.exe app_v6/local_cli.py preview --config configs/one_latest50_mbti_test.json --steps 10
```

真实单组实验会消耗 API 额度，使用 `Run-V6-Latest50-ONE.cmd`。54 份配置仅用于实验设计，不代表已运行 54 组。变更评论窗口或记忆设定后应新开实验，不把旧检查点混入新条件。

详见[最新50条评论](docs/V6_最新50条评论.md)、[三轮临时记忆与输入节省](docs/V6_三轮临时记忆与API节省.md)和[四密钥轮询](docs/V6_MiniMax四密钥轮询.md)。仓库原有历史结果与审计归档保留；下方说明是此前版本的记录。

---

# 本地V6：启动与检查

当前最新版本：`v6-network-thread-all-conditions-20261022-1`。网络决定首次接触原帖；初始82名SOURCE关注者可见，其他人经关注账号转发接触，接触后可每轮回看完整先前评论。官方独立发帖，定向和转发触达保留。11项个人条件与R/W/L/U/S恢复菜单继续使用。以[网络触达与完整评论](docs/V6_网络触达与完整评论.md)和[最新运行步骤](docs/V6_用户手动运行步骤.md)为准。以下旧版本记录保留。

2026-10-22最新更新：当前版本 `v6-binary-score-key-failover-20261022-1`。两把MiniMax Key已由Windows当前用户加密保存，主Key失败切副Key，每3600秒由下一次正式请求试用主Key，成功后切回。单组启动器无需再手动输入Key。以[最新运行步骤](docs/V6_用户手动运行步骤.md)和[API主副切换说明](docs/V6_API主副切换与密钥管理.md)为准；下方旧版本更新记录保留。

2026-10-22评分二分类更新：当前版本`v6-binary-score-20261022-1`。LLM只给0—100完整说法可信度，程序以`>50`分类为相信、`<=50`分类为不相信，恰好50归不相信。新版不产生或统计uncertain；未判断仍单列且不进入相信率分母。详细规则见[评分二分类说明](docs/V6_评分二分类规则.md)。旧结果不覆盖，新版应新开一组运行，不能接入旧版第5轮检查点。

2026-10-22异质人群更新：当前版本为`v6-heterogeneity-20261022-1`。582名角色已补充合成年龄、地区、职业、MBTI风格偏好与经历；305名LLM新增0—100主观可信度及三个分项评分，277名规则角色的概率公式保持。完整当前设定见[异质人群与主观判断说明](docs/2026-10-22_V6异质人群与主观判断.md)，可修改比例见`materials_v6/06_合成人群分配设定.json`。每次最大输出已设为768 tokens，预算按768预留；输入仍保留32768代理token和最近5次完整经历。当前仅完成离线验收，未启动真实API。旧真实运行仍暂停在第5轮，旧54组批次仍终止；旧检查点须使用原版本，不能与本版中途拼接。

2026-10-22更新：当前素材已改为用户提供的“老旧小区改造预算与安全整改排序”案例，并加入日常刷信息流的Prompt情境。政府回应为实验性情况说明，包含声称核对记录的结论及公开安排，不是真实官方通告或已核实的现实事实。完整说明见 `docs/2026-10-22_V6预算案例与日常浏览提示词.md`，案例和判断对象见 `materials_v6/05_案例与判断对象.json`。此前54组批次仍按用户要求终止，旧案例结果不能作为新案例已完成条件复用；本次修改没有启动真实API调用。

部署位置：`E:\papers\socioverse 2026\socioverse2_v6_local`。

这是基于你提供的最新版 `app_v6` 添加本次参数操作化后的独立本地版本。旧压缩包、旧目录和历史真实实验均保留。本地程序负责仿真、调度和存储；真实LLM推理由MiniMax API提供，不是在电脑上运行MiniMax模型权重。

详细设定、机制、公式、默认值和待检查问题：`docs/V6_模型全部设定与待检查项.md`；可读图文版：`docs/V6_本地部署与设定手册.html`。

## 1. 打开PowerShell进入部署目录

```powershell
cd 'E:\papers\socioverse 2026\socioverse2_v6_local'
```

环境已经安装好，通常不需要重新安装，也不需要激活虚拟环境。

## 2. 先预检你选择的一组参数

```powershell
.\Run-V6.ps1 -Mode Preview -TrustGap 0.4 -GovernmentTick 2 -Targeting 0.8 -GovernmentTrust 0.75
```

这条命令不调用API。程序会输出配置、582人的信任值和投放名单，保存在 `runtime/v6/preflight/`。其中 `agent_parameters.csv` 可用Excel打开，`sample_prompt_tick1.txt` 展示真正传入LLM的提示词构造。

默认条件为D040_T02_C080_G075：圈内外SOURCE初始信任均值差0.4、政府第2轮介入、100名接收者中80名圈内、政府信任均值0.75。

## 3. 离线检查完整10轮

```powershell
.\Run-V6.ps1 -Mode Offline -TrustGap 0.4 -GovernmentTick 2 -Targeting 0.8 -GovernmentTrust 0.75
```

离线模式用固定人工回答替代LLM，只检验工程流程，不能当作研究结果。

## 4. 真实运行一组条件

```powershell
.\Run-V6.ps1 -Mode Live -TrustGap 0.4 -GovernmentTick 2 -Targeting 0.8 -GovernmentTrust 0.75
```

若当前进程未配置 `RUMOR_LLM_API_KEY`，终端会隐藏输入地询问MiniMax Token Plan Key。Key只留在当前运行进程环境中，不写进文件，不要发到聊天里。当前启动链只接受 `sk-cp-` 前缀的订阅Key及仓库指定的中国区MiniMax地址，避免自动切到按量付费。

`Live` 会消耗账户订阅额度。这里配置了每个运行最多12200次请求、输入预留49971200单位、输出预留6246400 tokens；它们不是人民币成本上限，也不保证账号当前额度足够完成10轮。

## 5. 换另一个条件

```powershell
.\Run-V6.ps1 -Mode Live -TrustGap 0.2 -GovernmentTick 4 -Targeting 0.2 -GovernmentTrust 0.5
.\Run-V6.ps1 -Mode Live -TrustGap 0 -GovernmentTick 7 -Targeting 0.8 -GovernmentTrust 0.25
```

每行各启动一个新实验。依次执行；不要同时开多个真实实验。第2、4、7轮是独立条件，每个实验只直接投放一次。

参数取值：TrustGap为0/0.2/0.4；GovernmentTick为2/4/7；Targeting为0.2/0.8；GovernmentTrust为0.25/0.5/0.75。默认10轮、10并发上限。54个配置已生成在 `configs/research54/`，并没有自动启动54个实验。

## 6. 看进度、校验结果与续跑

```powershell
.\Run-V6.ps1 -Mode Status
$latestRun = (Get-Content '.\runs\v6\latest.json' -Raw | ConvertFrom-Json).run_dir
.\Run-V6.ps1 -Mode Verify -RunDir $latestRun
```

`Verify`只接受完整完成的运行；暂停中的运行不能标成完成。

按 `Ctrl+C` 停止后，要继续同一个条件：

```powershell
.\Run-V6.ps1 -Mode Resume -ParentRun $latestRun
```

续跑会新建目录并继承已完整提交的轮次、缓存和预算，不覆盖父运行。不能修改研究参数、代码或人口表后接着续跑，也不能把旧归档TG2结果续接到本次扩展版本。

如果明确因完整记忆超过输入上限暂停，可以只提高执行上限再续跑：

```powershell
.\Run-V6.ps1 -Mode Resume -ParentRun $latestRun -PromptLimit 65536
```

如果确因输入预留上限不足，且你已决定允许使用更多额度，可指定更高的输入上限，例如：

```powershell
.\Run-V6.ps1 -Mode Resume -ParentRun $latestRun -InputBudget 99942400
```

这种受限续跑只允许提高输入/输出/单次提示上限；不能改变四个研究因素，不能减少上限，也不会重发结果未知的请求。

## 7. 文件在哪里

| 内容 | 位置 |
|---|---|
| 默认配置 | `configs/local_defaults.json` |
| 54个条件 | `configs/research54/` |
| 真实或离线结果 | `runs/v6/<运行ID>/` |
| 最近运行指针 | `runs/v6/latest.json` |
| 本次冻结输入与信任值 | `runtime/v6/configs/<运行ID>/` |
| 请求、响应、缓存、错误、预算 | `runtime/v6/logs/<运行ID>/` |
| 参数与机制详细说明 | `docs/V6_模型全部设定与待检查项.md` |
| 安装来源与用户确认设置 | `LOCAL_DEPLOYMENT_PROVENANCE.json` |
| 本地验证记录 | `runtime/local_verification/` |

## 8. 其他启动方式

双击 `Preview-V6.cmd` 可以直接做默认条件预检。若PowerShell脚本被本机策略阻止，不必改系统策略，直接使用Python命令：

```powershell
.\.venv\Scripts\python.exe app_v6\local_cli.py preview --gap 0.4 --tg 2 --target 0.8 --gt 0.75
.\.venv\Scripts\python.exe app_v6\local_cli.py offline --gap 0.4 --tg 2 --target 0.8 --gt 0.75
.\.venv\Scripts\python.exe app_v6\local_cli.py live --gap 0.4 --tg 2 --target 0.8 --gt 0.75
```

直接运行底层入口也会默认读取本次配置：

```powershell
.\.venv\Scripts\python.exe app_v6\run.py --steps 10
```

上面底层命令默认是离线。真实运行建议用 `Run-V6.ps1 -Mode Live`，其参数预检、隐藏Key输入和启动参数已经衔接好。

检查环境或重跑测试：

```powershell
.\Run-V6.ps1 -Mode Doctor
.\Run-V6.ps1 -Mode Tests
```

只有迁移到另一台电脑或删除了 `.venv` 后才需要 `Setup-V6.ps1`。不要单独复制Windows虚拟环境到其他目录或电脑；复制源代码后重新创建虚拟环境。
