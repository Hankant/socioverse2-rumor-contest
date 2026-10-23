# MiniMax 四把 Key：新增主 API（2026-10-23）

新 Key 已通过 Windows 当前用户 DPAPI 加密保存，完整值不进入源代码、配置或实验日志。本次只验证加密读取和路由，没有向供应商发起模型请求，因此不代表已验证其在线认证或剩余额度。

沿用此前的轮流调用规则：新主 Key → 原主 Key → 原副 Key → 原第三 Key → 新主 Key。四个日志槽位依次为 primary、backup、third、fourth；新 Key 位于轮询首位，现有三把完整保留。

可切换的服务拒绝、额度或连接故障会尝试其他可用 Key；已知不可用的 Key 进入冷却。暂时故障默认 60 秒，认证/额度问题 3600 秒，更长的 Retry-After 优先。原有三把 Key 的冷却记录随 Key 身份迁移，没有因换槽位而清零。供应商未返回结果的发送后超时仍暂停确认，不会盲目重发。

全部 Key 共享该次实验的请求、输入和输出预算。新增 Key 不重置旧运行消耗，不提高并发或预算。评论仍为每个主帖最新 50 条，临时记忆仍为过去 3 个模拟轮次。

下次使用项目根目录 Run-V6-Latest50-ONE.cmd 启动单组时，自动读取这四把 Key，无需再次输入。当前没有启动实验。

维护命令（在项目根目录执行；status 不调用模型）：

```powershell
& .\.venv\Scripts\python.exe scripts\manage_api_keys.py status
& .\.venv\Scripts\python.exe scripts\manage_api_keys.py set-slot --slot fourth
```

set-slot 隐藏输入替换指定槽位，保留其他 Key。当前最多支持四个槽位；重复添加同一主 Key 不会再次移位。

凭据文件位于当前用户 LOCALAPPDATA/SocioVerseV6/minimax-keys.dpapi。添加前的密文备份保存在同一目录，文件名含 before-add-primary；备份的 routing.json 只含槽位和冷却状态，不含 Key。

已通过 84 项相关测试，包括三/四槽轮询兼容、并发分配、第四路接替、全路失败暂停、共享预算、缓存复用、DPAPI 读写及冷却状态迁移。旧实验原始请求、有效缓存、预算和检查点哈希保持不变。
