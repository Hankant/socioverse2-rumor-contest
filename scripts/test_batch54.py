"""Execution safety checks; none makes a model request."""
import importlib.util
import itertools
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('batch54_test_target',Path(__file__).with_name('batch54.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def test_exact_factorial_design_and_reuse():
    m=b.prepare()
    assert len(m['jobs'])==54
    assert {tuple(j['config'][k] for k in b.FACTORS) for j in m['jobs']}==set(itertools.product([0,.2,.4],[2,4,7],[.2,.8],[.25,.5,.75]))
    reused=[j for j in m['jobs'] if j.get('reused_existing')]
    assert len(reused)==1 and reused[0]['condition_id']=='D040_T02_C080_G075'
    assert b.hashes()==m['signature']

@pytest.mark.parametrize('status,tick',[('running',5),('interrupted',10),('completed_offline',10),('completed_live',9)])
def test_incomplete_or_offline_run_is_not_exported(tmp_path,status,tick):
    (tmp_path/'status.json').write_text(json.dumps({'status':status,'last_completed_tick':tick}),encoding='utf-8')
    assert not b.complete(tmp_path)
    with pytest.raises(AssertionError,match='Only completed live'):
        b.prepare_payload({'run_dir':str(tmp_path)})

def test_modified_code_cannot_start_a_paid_run(monkeypatch):
    monkeypatch.setattr(b,'hashes',lambda:{'changed':True})
    with pytest.raises(AssertionError,match='Frozen research code'):
        b.start_job({'signature':{'original':True}}, {})

def test_credential_removed_from_export_environment(monkeypatch):
    monkeypatch.setenv('RUMOR_LLM_API_KEY','test-synthetic-not-real')
    assert 'RUMOR_LLM_API_KEY' not in b.public_env()
    assert b.os.environ['RUMOR_LLM_API_KEY']=='test-synthetic-not-real'

def test_output_filenames_identify_all_four_factors():
    m=b.prepare();names=[b.xlsx_name(j['config']) for j in m['jobs']]
    assert len(set(names))==54
    assert b.xlsx_name(m['jobs'][0]['config'])=='信任差0.0_介入2_圈内比例0.2_政府信任0.25.xlsx'
