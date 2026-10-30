# V7 最新结果（2026-10-30）

批次：V7_Optimized_20261027_145124。54 个条件全部完成，300 人 × 11 个状态记录（含第 0 轮）× 54 组，共 178,200 行。仅同步已有结果，没有新增模拟或模型请求。

| 目录 | 内容 |
| --- | --- |
| workbooks | 最新批次 54 份逐组 Excel |
| run_metadata | 各组运行版本、配置、状态和原始汇总报表 |
| fb | 当前采用的 FB 定义、54 组及逐人结果、统计检验、5 幅图和最新报告 |
| dual_tbu | 同一 757 个事件的 FB / POST 对照、统计 Excel、数据与图表 |
| complete54 | 54 份原始逐人轨迹 CSV、合并状态、TBU9 / PRUD3 补充分析、19 页报告与图表 |

最新报告是 fb/10-30-SocioVerse-研究报告_FB口径8页版.docx，逐字节复制自本机 2026-10-30 14:29 的用户编辑文件。fb/SocioVerse-研究报告_FB口径8页版.docx 是此前自动生成并核验的版本，两份分别保留。delivery_verification.json 记录原生成版本的检查，不代表对后续用户编辑稿重复进行了排版检查。

FB 定义：b 为首次观察到评分 >50 的轮次，r 为政府发布轮 RT 当轮或之后首次实际“相信→不相信”轮次，TBU_FB=r-b。政府发布先于同轮决策，因此 r=RT 合格。54 个情景均值等权，757 个合格更新（发布当轮 282、之后 475），222 个首次相信片段右删失，1 个发布前已解决。删失者不填造完成时间。各情景 FB 均值的平均为 4.55684896011148 轮。报告保留探索时已使用的多重校正族；不把不显著的 DGC 调节写成显著。

RT 为政府回应时间；TC 为固定 50 名直接投放者中的圈内比例；GC 为政府来源主观信任均值；DGC 为圈内外来源信任均值差，网络拓扑固定。政府发布不等于每名用户首次接触政府帖，时间关系不直接证明个人因果纠正。

核验（仓库根目录，标准库即可）：

```sh
python scripts/verify_v7_results.py
```

数值分析入口已调整为仓库内相对路径。先安装分析依赖（complete54/requirements-analysis.txt 记录原环境版本），然后依次运行：

```sh
python results/v7_20261030/complete54/analysis54.py
python results/v7_20261030/dual_tbu/analyze_dual.py
python results/v7_20261030/fb/prepare_fb.py
```

完整数据已经提取，无需重跑 extract.py。其他原始制图、Word/Excel 构建与原项目核验脚本作为方法记录保留，部分仍依赖原 Windows 路径、Word 和工作区专用库；它们不是上述便携数值复现步骤的一部分。分析输出版本详见 analysis.json。raw 和 run_metadata 中的数据保持原始内容，所有来源文件复制哈希与便携脚本改动记录在 PUBLICATION_MANIFEST.json。API 请求缓存、密钥与临时恢复目录未包含。
