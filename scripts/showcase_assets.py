"""Read-only, allowlisted assets for the standalone research workbench."""
import base64
import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results/v7_20261030'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def report_blocks(path):
    """Extract document-order paragraphs and tables without editing the DOCX."""
    with ZipFile(path) as z:
        body = ET.fromstring(z.read('word/document.xml')).find(W + 'body')
    blocks, refs = [], []
    in_refs = False
    for el in body:
        if el.tag == W + 'p':
            text = ''.join(el.itertext()).strip()
            if not text:
                continue
            style = el.find(f'{W}pPr/{W}pStyle')
            style = style.get(W + 'val', '') if style is not None else ''
            heading = 'heading' in style.lower() or text in ('Abstract', 'References', 'Conclusion')
            in_refs = in_refs or text == 'References'
            blocks.append({'kind': 'heading' if heading else 'paragraph', 'text': text})
            if in_refs and text != 'References':
                refs.append({'text': text, 'doi': re.search(r'https://doi\.org/\S+', text).group(0) if re.search(r'https://doi\.org/\S+', text) else None})
        elif el.tag == W + 'tbl':
            blocks.append({'kind': 'table', 'rows': [[''.join(c.itertext()).strip() for c in r.findall(W + 'tc')] for r in el.findall(W + 'tr')]})
    assert blocks and refs
    return blocks, refs


def load_assets(cases):
    paths = []
    materials = ROOT / 'v7/materials_v7'
    config_keys = ('runtime_version', 'model', 'population_n', 'inside_n', 'outside_n', 'government_tick', 'government_reach', 'targeting_inside_ratio', 'government_trust_mean', 'source_trust_gap', 'comment_window_limit', 'memory_window_ticks', 'behavior_seed', 'feed_policy', 'belief_measurement_policy')
    for c in cases:
        path = RESULTS / 'run_metadata' / c['id'] / 'provenance.json'
        prov = json.loads(path.read_text(encoding='utf-8'))
        # Never show credentials, local audit paths or arbitrary runtime metadata.
        c['config'] = {k: prov['config'][k] for k in config_keys}
        c['mode'] = prov['mode']
        assert prov['dry_run'] is False
        assert c['config']['government_tick'] == c['summary']['RT']
        for name, expected in prov['input_sha256'].items():
            assert hashlib.sha256((materials / name).read_bytes()).hexdigest() == expected, (c['id'], name)
        paths.append(path)
    event_path = materials / '05_案例与判断对象.json'
    environment_path = materials / '03_新环境设定.md'
    people_path = materials / '01_Agent基础信息表.csv'
    report = next((RESULTS / 'fb').glob('10-30-*.docx'))
    paths += [event_path, environment_path, people_path, report]
    event = json.loads(event_path.read_text(encoding='utf-8'))
    environment = environment_path.read_text(encoding='utf-8')
    sections = re.split(r'^## ', environment, flags=re.M)[1:]
    texts = [{'title': s.split('\n', 1)[0].strip(), 'text': '\n'.join(line[1:].lstrip() if line.startswith('>') else line for line in s.split('\n', 1)[1].splitlines()).strip()} for s in sections]
    fields = ['agent_id', 'group', 'synthetic_age', 'synthetic_region', 'synthetic_occupation', 'synthetic_mbti_type', 'synthetic_personality_description', 'synthetic_role_experience', 'synthetic_demographic_basis', 'synthetic_mbti_basis']
    with people_path.open(encoding='utf-8-sig', newline='') as f:
        personas = [{k: row[k] for k in fields} for row in csv.DictReader(f)]
    assert len(personas) == 300 and {p['agent_id'] for p in personas} == {a[0] for a in cases[0]['agents']}
    by_id = {p['agent_id']: p for p in personas}
    for case in cases:
        for agent in case['agents']:
            p = by_id[agent[0]]
            assert agent == [p[k] for k in ('agent_id', 'group', 'synthetic_age', 'synthetic_region', 'synthetic_occupation', 'synthetic_mbti_type')], (case['id'], agent[0])
    blocks, refs = report_blocks(report)
    figure_defs = [('Figure1_network_access.png', '模型网络接触示意', '模型设定示意，不是该批次的逐次传播路径。'), ('Figure2_FB_framework_preview.png', 'FB 指标定义', '来自现有 FB 报告制图文件。'), ('Figure3_FB_level_differences_preview.png', '参数水平与 FB 时长', '原报告分析图；解释和限制见报告正文。'), ('Figure4_FB_moderation_preview.png', 'DGC 交互分析', '原报告未支持三项 DGC 交互，不据此宣称存在调节效应。'), ('Figure5_FB_time_origin_preview.png', '时间起点与观察窗口', '区分首次相信时点与政府发布时点。')]
    figures = []
    for name, title, note in figure_defs:
        path = RESULTS / 'fb/figures' / name
        figures.append({'title': title, 'note': note, 'path': str(path.relative_to(ROOT / 'results')).replace('\\', '/'), 'uri': 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')})
        paths.append(path)
    analysis_path = RESULTS / 'fb/analysis_FB.json'
    paths.append(analysis_path)
    analysis = json.loads(analysis_path.read_text(encoding='utf-8'))
    return {'event': event, 'environment': texts, 'personas': personas, 'report': blocks, 'references': refs,
            'reportPath': str(report.relative_to(ROOT / 'results')).replace('\\', '/'), 'figures': figures,
            'analysis': {k: analysis[k] for k in ('completed_scenarios', 'scenario_mean', 'observed_updates', 'right_censored_first_episodes', 'resolved_before_release')},
            'assetSources': [{'path': str(p.relative_to(ROOT)).replace('\\', '/'), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}
