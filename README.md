# 最新 V7 代码与完整 54 组结果（2026-10-30）

最新模拟代码在 [v7/](v7/)，300 名 LLM 用户（圈内 48、圈外 252），10 轮，54 个实验条件。研究结果在 [results/v7_20261030/](results/v7_20261030/README.md)。

- [最新 FB 口径研究报告](results/v7_20261030/fb/10-30-SocioVerse-研究报告_FB口径8页版.docx)
- [54 组独立实验 Excel](results/v7_20261030/workbooks/)
- [FB 情景汇总 CSV](results/v7_20261030/fb/data/FB_scenarios.csv) 与 [FB 用户事件 CSV](results/v7_20261030/fb/data/FB_users.csv)
- [双 TBU 定义统计结果与数据](results/v7_20261030/dual_tbu/)
- [完整轨迹、补充分析与图表](results/v7_20261030/complete54/)

安装、离线预检和测试见 [V7 发布说明](v7/PUBLICATION.md)。当前代码与完成实验时的冻结配置分别保留，旧实验不冒充新代码的重新运行结果。所有 54 组均已完成至第 10 轮；本次同步没有调用模型。

以下为此前 V6 与参赛版本的历史说明，相关代码和结果继续保留。

---

# 当前 V6 本地模型（2026-10-23）

新增归档：[2026-10-21 TG5完整十轮结果](research_archive/v6_tg5_completed/run/)及[参数与版本说明](docs/V6_TG5历史结果归档.md)。此为此前三态判断版本，不是下述最新评分模型的运行结果。

最新单组入口是 `Run-V6-Latest50-ONE.cmd`，对应 `configs/one_latest50_mbti_test.json`：305 名 LLM 用户＋277 名规则用户，10 轮；网络决定首次接触，每个可见主帖展示截至上一轮最新 50 条评论，个人临时记忆保留过去 3 个模拟轮次。LLM 以 0—100 分判断，>50 相信、≤50 不相信；结合 MBTI 和全部个人条件自主决定评论与转发。政府使用独立账号。

模型为 MiniMax-M3。已支持 Windows 当前用户 DPAPI 加密保存最多四把 Key，按主、副、第三、第四顺序轮询，跳过故障冷却中的 Key；所有 Key 共享每次实验的请求和 token 保护上限。**GitHub 不包含任何真实 Key、加密凭据文件、虚拟环境或当前 `runs/`、`runtime/`。** 克隆到另一台 Windows 电脑后，先运行 `Setup-V6.ps1`，再通过 `python scripts/manage_api_keys.py set` 在本地隐藏输入自己的 Key。

无模型调用的预检：

```powershell
.\.venv\Scripts\python.exe app_v6/local_cli.py preview --config configs/one_latest50_mbti_test.json --steps 10
```

真实单组实验会消耗 API 额度，使用 `Run-V6-Latest50-ONE.cmd`。54 份配置仅用于实验设计，不代表已运行 54 组。变更评论窗口或记忆设定后应新开实验，不把旧检查点混入新条件。

详见[最新50条评论](docs/V6_最新50条评论.md)、[三轮临时记忆与输入节省](docs/V6_三轮临时记忆与API节省.md)和[四密钥轮询](docs/V6_MiniMax四密钥轮询.md)。仓库原有历史结果与审计归档保留；下方说明是此前版本的记录。

---

# 当前本地部署入口（2026-10-21）

当前最新：`v6-network-thread-all-conditions-20261022-1`。初始82名SOURCE关注者看到原帖，其他人经关注账号转发首次接触，接触后可回看完整先前评论；未接触者不提前获得原帖或评论。官方为独立账号，11项条件与按键恢复机制保留。详见 [网络触达与完整评论](docs/V6_网络触达与完整评论.md)。下方旧版本更新记录保留。

2026-10-22最新更新：已启用Windows加密保存的MiniMax主/副Key自动切换，主Key失败后用副Key，每3600秒由下一次正式请求试用主Key；成功后切回。见 [API主副切换与密钥管理](docs/V6_API主副切换与密钥管理.md) 和 [最新手动运行步骤](docs/V6_用户手动运行步骤.md)。当前版本 `v6-binary-score-key-failover-20261022-1`。

本目录已扩展为本次确认的V6研究参数版本。请先阅读 [本地启动说明](README_LOCAL.md) 和 [全部模型设定](docs/V6_模型全部设定与待检查项.md)，图文版为 `docs/V6_本地部署与设定手册.html`。

当前为305名LLM＋277名规则用户、10轮、2/4/7独立介入、100名目标、80%/20%圈内、SOURCE初始信任差0/.2/.4、GT均值.25/.5/.75；默认保留完整最近5次成功经历。启动使用根目录 `Run-V6.ps1`。54个配置已生成，但没有自动运行真实实验。

以下保留来源ZIP中的参赛历史说明；其中旧app入口、2/5/8时点、40名目标和旧实验结论不覆盖本次本地配置。

# 来源包历史说明：SocioVerse2 政府谣言辟谣模拟（参赛交付）

基于官方 SocioVerse2 引擎的582人混合模拟：305名LLM用户、277名规则用户。实现稳定个人资料、最近5次成功经历、累计接触记录、政府回应及技术失败退出。官方代码固定版本保存在 vendor/SocioVerse2，保留 Apache-2.0 LICENSE/NOTICE；项目适配层在 app。

## 裁判先看结果（无需Key、无需安装模型依赖）

新增V6实现位于app_v6，V5代码与40轮结果保留。详见[V6运行与数据入口](docs/V6_运行与数据入口.md)。昨晚TG2的10轮完整结果、原始账号表格和完整审计已纳入仓库；TG5新实验没有作为完成结果发布。


仓库：https://github.com/Hankant/socioverse2-rumor-contest （公开仓库）。

需要Python 3.12。在仓库根目录运行：

```sh
python scripts/serve_results.py
```

打开 http://127.0.0.1:8788/ 。也可直接查看 results/completed_run/metrics_history.json 和 technical_dropout.json。

本次真实实验已完成40轮：A0018在22轮技术退出；剩余581人（304 LLM、277规则），最终569人不相信、2人相信、10人未判断。累计1198次请求，8次超时用量未知。第30轮后没有新行动。结论仅描述该次工程实验，不证明现实辟谣效果。

## 安装和离线运行

```sh
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest app -q
python app/run.py --steps 40
```

默认离线模式使用固定测试回答，不消耗API；其结果不是LLM行为结果。新结果在 runs/，配置及日志在 runtime/，默认不提交Git。

## 使用真实MiniMax（消耗Token Plan额度）

PowerShell中隐藏输入Key，只保留在当前进程环境：

```powershell
$secret = Read-Host 'MiniMax Token Plan Key' -AsSecureString
$env:RUMOR_LLM_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
Remove-Variable secret
python app/run.py --live --config materials/minimax.run.config.json --token-plan-run --max-requests 12200 --steps 40
```

Linux/macOS可用 `read -rs RUMOR_LLM_API_KEY; export RUMOR_LLM_API_KEY` 后执行同一python命令。不要把Key写进代码或提交Git。`--max-requests 20 --steps 2` 可作有预算限制的接口检查；达到预算会暂停，不能保证完成。

同一版本恢复：上面的命令追加 `--resume runs/<运行目录>`，输入和代码哈希必须一致。不能把历史脱敏结果当作可续跑断点。

## 模型边界

全员每轮活跃、最多5帖、同一帖只读一次、同根最多转发一次；关注网络8同圈+2异圈，圈内82人额外关注SOURCE。政府在20轮定向40名圈内用户。PBd=0、GT=.6、RF=.6；规则用户初次PB=.579、RC=.1。V5允许未接受纠正的规则拒绝者在新谣言接触时重新抽样。

超时/连接错误两次，或可重试JSON/证据校验四次耗尽，用户永久技术退出。保留其旧信念和帖子；后续不收取信息、不行动。鉴权、额度、预算和未知程序错误仍停止全局。remaining_*排除退出者，all_*保留旧信念。技术退出可能由服务故障造成，不等同于行为下线。

## 实际输入、完整审计与复现边界

按项目所有者明确要求，`research_archive/` 公开本次实际输入与完整审计，不再只提供合成数据：

- `inputs/01_Agent基础信息表.csv`：实际582人表，包含305份账号资料关联（Pxxxx假名编号、性别、地区、账户计数、来源行号）；与原运行冻结CSV逐字节一致。
- `inputs/`：本次冻结提示词、环境说明、操作指南、概率配置、网络边、政府目标和初始状态。
- `audit/`：全部1198次请求记录、原始提示词与回复、缓存、阶段日志、校验失败、退出及预算记录。继承的失败文件可能已在后续解决，不能仅按文件数统计未解决故障。
- `checkpoints/`：40轮完整已提交行动，用于核查历史轨迹。
- `EXPORT_MANIFEST.json`：原始及发布文件哈希、处理说明。

原始账号资料这里指“本次模型实际使用的账号属性表”，不等于未加工的整份平台抓取Excel。原Excel未作为运行输入，不在此档案中。

默认 `materials/` 仍为合成演示。要使用本次实际人口与事件，新建运行时加：

```sh
python app/run.py --materials research_archive/inputs --steps 40
```

以上是离线工程运行。真实调用须追加前文 `--live --config materials/minimax.run.config.json --token-plan-run --max-requests 12200` 参数并设置Key。不要把离线输出解释为真实LLM结果。

提供相同实际输入不保证生成相同LLM回答；本次结果还包含从旧版本续跑的历史修复和退出策略迁移。档案用于核验原运行，便携版用于新运行；不支持直接将档案的旧绝对路径当作续跑入口。

账号属性与日志中的同一资料保留；凭据和认证头不发布。本机路径如出现会替换成 `${WORKSPACE}` 并列入清单。当前导出未发现凭据模式、无需路径替换。详见 docs/DATA_USE.md。

## 合作开发

见 CONTRIBUTING.md。不要直接修改历史results；用新分支改app代码、补测试，单独新跑结果。变更研究规则时记录参数和版本。CI仅离线测试，不配置模型Key。
