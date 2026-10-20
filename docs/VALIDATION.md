# 交付验证

- Windows / Python 3.12，全新.venv，从requirements.txt安装成功。官方runtime使用仓库内vendor代码安装。
- python -m pytest app -q：40 passed。
- python app/run.py --steps 40：完成离线40轮，无API调用（固定测试回答，不是新真实实验）。
- 独立结果查看器HTTP 200；读取已发布40轮指标和退出记录。
- 结果导出核对：40轮、每轮582个假名ID，最终剩余581人，1人技术退出。
- 未重新执行真实付费运行；模型服务可用性与预算由使用者提供。
- Linux执行由GitHub CI验证；本地仅完成Windows验证。

## 实际输入与审计扩展验证

使用--materials research_archive/inputs离线运行3轮成功；未发起新付费调用。实际CSV与原冻结文件哈希一致。疑似手机号模式核验仅出现在SHA256字符串字段，不是联系方式。完整审计导出与40轮检查点逐文件哈希验证。
