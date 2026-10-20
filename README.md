# SocioVerse2 政府谣言辟谣模拟（参赛交付）

基于官方 SocioVerse2 引擎的582人混合模拟：305名LLM用户、277名规则用户。实现稳定个人资料、最近5次成功经历、累计接触记录、政府回应及技术失败退出。官方代码固定版本保存在 vendor/SocioVerse2，保留 Apache-2.0 LICENSE/NOTICE；项目适配层在 app。

## 裁判先看结果（无需Key、无需安装模型依赖）

后续开发说明：[V6 实验参数与实现边界](docs/V6_实验参数与实现边界.md)。该文档描述独立本地 V6 开发进展；本仓库现有代码与已完成结果仍为 V5，尚未随文档升级为 V6。

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
