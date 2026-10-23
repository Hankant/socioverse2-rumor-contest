"""Package only a fully completed and verified 54-condition batch; no API calls."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BATCH=ROOT/'runtime/v6/batch54-20261022'
OUT=Path('D:/Codex/outputs/socioverse_v6_research54_20261022')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    m=json.loads((BATCH/'batch_manifest.json').read_text(encoding='utf-8'))
    assert len(m['jobs'])==54 and m['completed_count']==54,'Not all 54 conditions have completed Excel exports'
    files=[];verification={}
    for j in m['jobs']:
        assert j['status']=='completed_exported'
        run=Path(j['run_dir']);state=json.loads((run/'status.json').read_text(encoding='utf-8'))
        assert state['status']=='completed_live' and state['last_completed_tick']==10
        file=Path(j['xlsx_file']);assert file.is_file()
        digest=sha(file);assert digest==j['export_verified']['sha256'],file.name
        files.append(file);verification[file.name]=digest
    for name in ['54组结果总览.xlsx','54组运行进度.csv','运行状态.txt','使用说明.md']:
        file=OUT/name;assert file.is_file();files.append(file)
    manifest=OUT/'结果文件SHA256.json'
    manifest.write_text(json.dumps({'conditions':54,'steps_per_condition':10,'individual_xlsx_sha256':verification},ensure_ascii=False,indent=2),encoding='utf-8')
    files.append(manifest)
    temporary=OUT/'54组完整结果.building.zip'
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as archive:
        for file in files:archive.write(file,file.relative_to(OUT).as_posix())
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None
        assert sum(n.startswith('Excel结果/') and n.endswith('.xlsx') for n in archive.namelist())==54
    result=OUT/'54组完整结果.zip';temporary.replace(result)
    print(json.dumps({'archive':str(result),'condition_workbooks':54,'sha256':sha(result),'bytes':result.stat().st_size},ensure_ascii=False))

if __name__=='__main__':main()
