# V7 发布说明（2026-10-30）

本目录同步自 D:/Codex/SocioVerseV7，包含模拟代码、300 人输入表、54 组参数、提示模板、Windows 启动入口、测试和随附 SocioVerse2。此工作区包含比 E 盘本地副本更新的 API 调度、JSON 校验和恢复修复。原始本机使用说明在 README.md；其中 E 盘路径描述历史部署位置。

在本目录执行（Python 3.12）：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app_v7/local_cli.py preview
.\.venv\Scripts\python.exe -m pytest tests -q
```

预检和工程测试不调用 API。Windows 也可运行 Setup-V7.ps1、Preview-V7.cmd。正式运行会使用自己的 API 额度；使用 scripts/manage_api_keys.py 在本机配置密钥，或使用应用支持的环境变量。未包含密钥、DPAPI 凭据、虚拟环境与运行缓存。

完整结果见 ../results/v7_20261030/README.md。该结果来自 2026-10-27 启动、2026-10-29 完成的批次 V7_Optimized_20261027_145124，不是把此前旧批次与新批次拼接而成。每个情景的 provenance.json 保留当次模型版本、配置和哈希。当前源码含后续修订，因此分析既有数据不等于用当前源码重跑；如需精确描述实验，以 run_metadata 中的记录为准。V7_PROVENANCE.json 是原部署维护记录，最新发布校验见根目录脚本 scripts/verify_v7_results.py。

vendor/SocioVerse2 保留原 LICENSE 与 NOTICE。MANIFEST.json 校验本目录发布文件，根目录 MANIFEST.json 校验整个仓库分发文件。

发布适配：test_finalization_repair.py 的退出码测试隔离了本机 workspace_runtime.json 与 Windows 文件锁依赖，使其可在干净克隆和 Linux CI 中运行；模拟行为代码保持源文件内容。

54 组批次控制器沿用本机部署入口，依赖 runtime/v7/workspace_runtime.json 中的 Node 路径和 @oai/artifact-tool Excel 导出环境，Run-V7-Batch54.cmd 还需要已有批次指针。此环境未随源码分发；新电脑可使用上述单组入口，不能直接把原本机的批次恢复入口当作新建实验入口。
