"""Large-cell CSV support and atomic UTF-8/BOM output; never truncate data."""
from contextlib import contextmanager
import csv
import os
from pathlib import Path
import sys
import tempfile
from model import retry_file


def ensure_large_fields():
    limit=sys.maxsize
    while True:
        try:
            if csv.field_size_limit()<limit:csv.field_size_limit(limit)
            return csv.field_size_limit()
        except OverflowError:
            limit//=10
            if limit<131072:raise


@contextmanager
def atomic_csv(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(dir=path.parent,prefix='.csv-',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8-sig',newline='') as stream:
            yield stream
            stream.flush();os.fsync(stream.fileno())
        retry_file(lambda:os.replace(temporary,path))
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def export_committed_panel(run_dir):
    """Stream the existing committed database; avoid one giant pandas frame."""
    import duckdb
    folder=Path(run_dir)/'trajectory'
    con=duckdb.connect(str(folder/'study.duckdb'),read_only=True)
    count=0
    try:
        cursor=con.execute('SELECT * FROM panel ORDER BY step, agent_id')
        columns=[d[0] for d in cursor.description]
        with atomic_csv(folder/'panel.csv') as stream:
            writer=csv.writer(stream);writer.writerow(columns)
            while rows:=cursor.fetchmany(128):writer.writerows(rows);count+=len(rows)
    finally:con.close()
    return count


def iter_committed_states(run_dir):
    """Read only needed DB columns, with a large-field CSV fallback for files."""
    folder=Path(run_dir)/'trajectory';database=folder/'study.duckdb'
    if database.exists():
        import duckdb
        con=duckdb.connect(str(database),read_only=True)
        try:
            cursor=con.execute('SELECT agent_id,step,state FROM panel ORDER BY step,agent_id')
            while rows:=cursor.fetchmany(128):
                for aid,step,state in rows:yield {'agent_id':aid,'step':step,'state':state}
        finally:con.close()
    else:
        ensure_large_fields()
        with (folder/'panel.csv').open(encoding='utf-8-sig',newline='') as stream:
            yield from csv.DictReader(stream)
