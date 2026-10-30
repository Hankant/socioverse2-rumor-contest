# V7 本组结果

状态：completed_live；完整轮次：10。运行模式：openai；panel包含3300行（含初态tick0）。

300名用户全部由LLM决策，圈内48、圈外252。只有完整提交的轮次计入报表，部分轮次缓存用于续跑。

reports/per_tick_results.csv为逐轮人数，binary_results.csv为最后完整轮次；trajectory/belief_measurements.csv为个人评分与接触，condition_applications.csv为条件摘要。

reports/belief_to_reject_events.csv只记录用户评分从>50跨到≤50的实际转换：包括本段相信开始、转换轮次、持续时间、前后分数和实际官方接触。重复相信后再次转换另记；未转换者不填0。时间单位为抽象模拟步。该事件表不同于仅介入前队列完成者平均的TBU。

test_stub仅为离线工程验证，不是研究结果。G001为实验性官方材料。LLM评分是未经外部校准的自报判断；条件摘要不是因果证明。TBU仅为工程口径。
