"""Explicit episodic-memory lifetime, measured in simulation ticks."""

LEGACY = 'last_five_experiences_v1'
ROLLING = 'rolling_simulation_ticks_v1'


def validate_memory_policy(cfg):
    policy = cfg.get('memory_retention_policy', LEGACY)
    window = cfg.get('memory_window_ticks')
    if policy == LEGACY and window is None:
        return
    if policy != ROLLING or type(window) is not int or not 1 <= window <= 10:
        raise ValueError('rolling memory requires memory_window_ticks integer in 1..10; legacy requires null')


def retained_memory(experiences, tick, cfg):
    if cfg.get('memory_retention_policy', LEGACY) == ROLLING:
        window = cfg['memory_window_ticks']
        return [m for m in experiences if tick-window <= m['tick'] < tick]
    return experiences[-5:]


def memory_description(cfg):
    if cfg.get('memory_retention_policy', LEGACY) == ROLLING:
        n = cfg['memory_window_ticks']
        return f'过去{n}个模拟轮次的个人经历；更早经历到期移出LLM输入，未行动轮次也计时'
    return '最近5次成功经历'
