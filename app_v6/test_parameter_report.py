from run import defaults
from parameter_report import write_parameters
import json

def test_parameter_labels_preserve_null_semantics(tmp_path):
    cfg=defaults();cfg.update(government_tick=5,max_concurrency=10)
    write_parameters(tmp_path,cfg,10)
    text=(tmp_path/'实验参数.md').read_text(encoding='utf-8')
    assert 'null；使用strategy=inside' in text and '不代表统一均值' in text
    assert json.loads((tmp_path/'experiment_parameters.json').read_text(encoding='utf-8'))['config']==cfg
