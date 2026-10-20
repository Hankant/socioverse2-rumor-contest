# SocioVerse2 政府谣言辟谣模拟（参赛交付）

基于官方 SocioVerse2 引擎的582人混合模拟：305名LLM用户、277名规则用户。实现稳定个人资料、最近5次成功经历、累计接触记录、政府回应及技术失败退出。官方代码固定版本保存在 vendor/SocioVerse2，保留 Apache-2.0 LICENSE/NOTICE；项目适配层在 app。

## 裁判先看结果（无需Key、无需安装模型依赖）

仓库：https://github.com/Hankant/socioverse2-rumor-contest （初始为私有，所有者需邀请裁判/合作者）。

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

## 数据和复现边界

**materials中的582人表是合成演示输入，不含原账号资料。** ID、组别和LLM/规则分配保留；个人属性移除或生成。已发布结果来自原始资料的历史运行，不能声称用合成人群可精确重现。本地完整原始档案未上传。

results保留原聚合指标和去除提示词、记忆、账号资料、自由文本后的行动轨迹。docs/DATA_USE.md说明处理。哈希清单用于检查交付完整性。原运行中经断点修复和退出机制迁移，属于工程连续运行，非单一冻结版本从0独立运行。

## 合作开发

见 CONTRIBUTING.md。不要直接修改历史results；用新分支改app代码、补测试，单独新跑结果。变更研究规则时记录参数和版本。CI仅离线测试，不配置模型Key。
