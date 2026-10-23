"""Exports cannot hide the simulation pause or bypass its recovery controller."""
import traceback
from pathlib import Path
from model import dump
from recovery import RunPaused


def finalize_exports(run_dir,roster,cfg,state,mode,latest_path,simulation_error=None):
    from csv_io import export_committed_panel
    from measurement_report import write_measurements
    folder=Path(run_dir);state['export_status']='pending'
    try:
        dump(folder/'status.json',state);dump(latest_path,{'run_dir':str(folder),**state})
        count=export_committed_panel(folder)
        write_measurements(folder,roster,cfg.get('belief_measurement_policy','legacy'))
        report=(f"# V6 本地运行\n\n状态：{state['status']}。最后完整轮次：{state['last_completed_tick']}。\n\n"
            f"582人，305名LLM角色、277名规则角色。运行模式：{mode}；panel共{count}行（含tick0）。\n\n"
            "离线模式使用固定测试回答，不代表真实LLM行为。G001是研究者脚本，不是真实官方通告。\n\n"
            f"规则合同状态：{cfg.get('contract_status','unknown')}。TBU仅按工程候选口径输出。\n\n"
            "原始素材及哈希、边表、投放名单和初态已冻结；provenance.json记录位置。只导出已提交的完整轮次，不将部分轮次缓存当作结果。\n")
        (folder/'reports').mkdir(exist_ok=True)
        (folder/'reports/report.md').write_text(report,encoding='utf-8')
    except (Exception,KeyboardInterrupt) as exc:
        state['export_status']='failed';state['export_error_type']=type(exc).__name__
        if simulation_error is None:
            state['status']='paused_by_user' if isinstance(exc,KeyboardInterrupt) else 'paused_export'
            state['error_type']='KeyboardInterrupt' if isinstance(exc,KeyboardInterrupt) else 'ExportPause'
        diagnostic={'type':type(exc).__name__,'simulation_error_type':state.get('error_type'),
            'last_completed_tick':state['last_completed_tick'],
            'frames':[{'file':f.filename,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)],
            'note':'Committed checkpoints, request cache and spending ledger remain authoritative; export may be retried without regenerating decisions.'}
        try:
            dump(folder/'export_failure_diagnostic.json',diagnostic)
            dump(folder/'status.json',state);dump(latest_path,{'run_dir':str(folder),**state})
        except OSError:
            print('Export diagnostic could not be written; inspect existing checkpoints and filesystem.',flush=True)
        print(f"结果导出未完成：{type(exc).__name__}；模拟暂停原因={state.get('error_type')}；完整轮次和API缓存保留，进入恢复菜单。",flush=True)
        raise RunPaused(folder,state['error_type']) from None
    state['export_status']='complete';state.pop('export_error_type',None)
    dump(folder/'status.json',state);dump(latest_path,{'run_dir':str(folder),**state})
    print(__import__('json').dumps({'run_dir':str(folder),**state},ensure_ascii=False),flush=True)
    if simulation_error is not None:raise RunPaused(folder,state['error_type']) from None
    return folder
