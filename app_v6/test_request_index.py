import json
from pathlib import Path
from test_recovery import client

def test_index_reads_history_once_and_updates_durably(tmp_path, monkeypatch):
    import llm_client
    p=tmp_path/'request-000001.json'
    p.write_text(json.dumps({'prompt_sha256':'old','status':'request_error'}))
    c=client(tmp_path,monkeypatch)
    original=llm_client.read_json
    reads=[]
    def tracked(path):
        if Path(path).name.startswith('request-'):reads.append(str(path))
        return original(path)
    monkeypatch.setattr(llm_client,'read_json',tracked)
    assert c.request_history('old')[0][1]['status']=='request_error'
    for _ in range(20):assert c.request_history('missing')==[]
    assert len(reads)==1
    c.save_request(p,{'prompt_sha256':'old','status':'response_received'})
    assert c.request_history('old')[0][1]['status']=='response_received'
    assert len(reads)==1
    fresh=client(tmp_path,monkeypatch)
    assert fresh.request_history('old')[0][1]['status']=='response_received'
    assert len(reads)==2

def test_failed_write_does_not_update_index(tmp_path,monkeypatch):
    import llm_client,pytest
    c=client(tmp_path,monkeypatch)
    c.request_history('x')
    def fail(*a,**k):raise PermissionError('test')
    monkeypatch.setattr(llm_client,'dump',fail)
    with pytest.raises(PermissionError):c.save_request(tmp_path/'request-000001.json',{'prompt_sha256':'x'})
    assert c.request_history('x')==[]
