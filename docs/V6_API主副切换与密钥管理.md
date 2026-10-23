# V6 MiniMax主副API与密钥管理

密钥功能发布版本：`v6-binary-score-key-failover-20261022-1`；当前运行版本为 `v6-shared-thread-all-conditions-20261022-1`，密钥策略保持。当前阅读和个人条件合同见 [全评论说明](V6_全评论与逐项条件决策说明.md)。人群仍为582人、305名LLM用户、277名规则用户，评分仍为>50相信、≤50不相信。

## 本机已经配置

两把Key保存在：

```text
C:\Users\Administrator\AppData\Local\SocioVerseV6\minimax-keys.dpapi
```

此文件为Windows DPAPI CurrentUser加密数据，由当前Windows账户解密；不能把它当作可跨电脑使用的明文配置。源码、普通JSON配置、命令行参数、实验备份和日志不包含Key。普通配置只记录 `api_key_mode=windows_dpapi_failover` 和 `api_primary_retry_seconds=3600`。

主Key是用户指定的订阅Key，副Key是用户指定的备用Key。两者均只发送到 `https://api.minimax.cn/v1`，模型保持 `MiniMax-M3`，请求采样设置一致，不切换模型。环境变量 `RUMOR_LLM_API_KEY` 在当前保存密钥模式下不覆盖这两个槽位。

2026-10-22 21:27北京时间的两次真实小型连接检查均成功，返回模型均为MiniMax-M3，每次实际使用187输入token和6输出token。这只确认检查时能使用，不保证后续余额和额度持续充足。连接检查记录保存在 `runtime/v6/connection_checks/dual-keys-*.json`；它们不是研究结果。

## 切换规则

1. 初始状态优先主Key。正常成功不调用副Key。
2. 主Key出现明确的限流、额度、余额、认证或服务异常，当前请求按相同模型、相同prompt和参数改投副Key。失败的尝试也占总请求和token预留预算，不重置预算。
3. 从首次主Key失败起等待3600秒。这期间的新请求使用副Key。其他已在途的主请求可以完成，不会被强制取消。
4. 到达3600秒后的**下一次正式请求**试用主Key。多线程中只允许一个这样的主Key探测，其余请求继续用副Key。探测本身就是该用户的真实决策请求，不额外生成一个研究样本。
5. 主Key成功，后续新请求切回主Key，已在途的副请求正常完成；主Key仍失败，该用户的请求改投副Key，并从这次失败起再等3600秒，循环执行。
6. 空闲、实验结束或程序关闭期间不发探测请求。下一次启动读取本机非敏感 `routing-state.json`，沿用未到期的等待时间；已到期则在下一次正式请求探测。密钥重新保存时重置为优先主Key。
7. 副Key也出现上述可用性故障，暂停实验并保存已完成轮次及成功响应缓存，避免在两个不可用Key间无限切换。查看 `status.json` 和审计日志。不要反复启动多个副本。

这里的一小时是本程序的重试间隔，不表示MiniMax五小时窗口一定已恢复；若还受周额度等限制，每小时仍会失败并继续使用副Key。

## 哪些错误会切换

以[MiniMax官方错误码](https://platform.minimax.cn/docs/api-reference/errorcode)为依据：

- HTTP 401/402、429/529和500/502/503/504；包括1004/2049认证、1008/2053余额积分、1002/1041/1045/2045/2046/2047频率并发、2056/2062/2067订阅资源、1000/1001/1024/1033/2064/2066服务故障。
- 已确定发生在连接建立前的ConnectTimeout、PoolTimeout或ConnectError可以切换。
- HTTP 200正文里携带上述非零 `base_resp.status_code` 同样属于失败，不会误当作成功。
- 参数错误、上下文或max_tokens错误、模型不存在/套餐不支持模型、内容拒绝和JSON不合格不会靠换Key掩盖。JSON格式重试沿用原有上限。
- 如果请求可能已被处理，但读响应超时或连接中断，不能判断是否已完成/扣费，则保留 `pending_usage_unknown` 并暂停，需核查后明确授权重发，避免无记录的重复调用。此类错误不会转换成用户相信/不相信。

主副Key仍共用原有并发上限、总请求上限12200及输入/输出保护预算。故障切换没有新增实验组，也不保证突破同账户或全平台的限流。默认单组启动器的API并发上限仍是2。

## 运行一组

双击根目录 `Run-V6-Heterogeneity-Test.cmd`，或在PowerShell执行：

```powershell
Set-Location -LiteralPath 'E:\papers\socioverse 2026\socioverse2_v6_local'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -u scripts/run_live_checked.py --gap 0.4 --tg 2 --target 0.8 --gt 0.75 --steps 10 --concurrency 2
```

这个命令每执行一次都新建一组10轮实验。本次配置工作没有启动实验或恢复已取消的54组队列。

## 查看、检查与更换Key

以下命令均在项目根目录执行：

```powershell
# 查看加密凭据是否可读以及当前路由状态，不显示Key，不调用API
.\.venv\Scripts\python.exe scripts/manage_api_keys.py status

# 分别检查主副Key：总共至多两次真实小请求，不运行实验
.\.venv\Scripts\python.exe scripts/manage_api_keys.py check

# 隐藏输入新的主Key和副Key；保存后恢复主Key优先
.\.venv\Scripts\python.exe scripts/manage_api_keys.py set
```

请在实验停止时更换Key。旧实验的配置/代码哈希保持原样；不能把本次新版代码直接强行续接旧版结果。新版本自身暂停后的续跑仍须通过原有一致性和未知请求检查。

## 记录和费用

运行日志 `request-*.json` 记录 `api_key_slot=primary/backup`、`primary_probe=true/false`、请求编号、模型、使用量和安全错误码；`request-events.jsonl` 记录 `primary_unavailable_using_backup`、`primary_probe_started`、`primary_restored`。不会记录实际Key或原始异常正文。代码主要位于 `app_v6/credentials.py`、`app_v6/api_router.py` 和 `app_v6/llm_client.py`。

副Key若属于按量付费账户，其调用会消耗余额或资源包，并非免费扩展订阅额度。MiniMax[官方说明](https://platform.minimax.io/docs/m-plan/faq)区分了订阅Key与按量付费Key。程序保留的是请求/token上限，没有新增人民币硬上限；实际账单以MiniMax控制台为准。用户已明确授权主Key失败后使用指定副Key。
