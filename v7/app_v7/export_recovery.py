"""Export failure preserves simulation checkpoints and enters the recovery controller."""
from pathlib import Path
import traceback
from model import dump
from recovery import RunPaused


def finalize_exports(run_dir,roster,cfg,state,mode,latest_path,simulation_error=None):
    from csv_io import export_committed_panel
    from measurement_report import write_measurements
    folder=Path(run_dir);state['export_status']='pending'
    try:
        dump(folder/'status.json',state)
        count=export_committed_panel(folder)
        write_measurements(folder,roster,cfg['belief_measurement_policy'])
        report=f'''# V7 本组结果

状态：{state['status']}；完整轮次：{state['last_completed_tick']}。运行模式：{mode}；panel包含{count}行（含初态tick0）。

300名用户全部由LLM决策，圈内48、圈外252。只有完整提交的轮次计入报表，部分轮次缓存用于续跑。

reports/per_tick_results.csv为逐轮人数，binary_results.csv为最后完整轮次；trajectory/belief_measurements.csv为个人评分与接触，condition_applications.csv为条件摘要。

reports/belief_to_reject_events.csv只记录用户评分从>50跨到≤50的实际转换：包括本段相信开始、转换轮次、持续时间、前后分数和实际官方接触。重复相信后再次转换另记；未转换者不填0。时间单位为抽象模拟步。该事件表不同于仅介入前队列完成者平均的TBU。

test_stub仅为离线工程验证，不是研究结果。G001为实验性官方材料。LLM评分是未经外部校准的自报判断；条件摘要不是因果证明。TBU仅为工程口径。
'''
        (folder/'reports/report.md').write_text(report,encoding='utf-8')
    except (Exception,KeyboardInterrupt) as exc:
        state.update(export_status='failed',export_error_type=type(exc).__name__)
        if simulation_error is None:state.update(status='paused_export',error_type='ExportPause')
        dump(folder/'export_failure_diagnostic.json',dict(type=type(exc).__name__,frames=[dict(file=f.filename,line=f.lineno,function=f.name) for f in traceback.extract_tb(exc.__traceback__)]))
        dump(folder/'status.json',state);dump(latest_path,dict(run_dir=str(folder),**state))
        raise RunPaused(folder,state['error_type']) from None
    state['export_status']='complete';state.pop('export_error_type',None)
    dump(folder/'status.json',state);dump(latest_path,dict(run_dir=str(folder),**state))
    print(__import__('json').dumps(dict(run_dir=str(folder),**state),ensure_ascii=False),flush=True)
    if simulation_error is not None:raise RunPaused(folder,state['error_type']) from None
    print(f"[正常完成] V7本组全部{state['last_completed_tick']}轮已完成。结果：{folder}",flush=True)
    return folder
