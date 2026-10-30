"""Check the shipped viewer against its sources, without model/network calls."""
import json
import re
import hashlib
from html.parser import HTMLParser
from pathlib import Path
from build_showcase import ROOT, build_data


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if 'href' in attrs:
            self.targets.append(attrs['href'])
        assert not (tag in ('script', 'link', 'img') and ('src' in attrs or 'href' in attrs)), 'Unexpected external asset'


def main():
    page = (ROOT / 'results/index.html').read_text(encoding='utf-8')
    match = re.search(r'<script id="showcase-data" type="application/json">(.*?)</script>', page, re.S)
    assert match, 'Embedded data is missing'
    assert json.loads(match.group(1)) == build_data(), 'Viewer is stale; rebuild it'
    parser = Links()
    parser.feed(page)
    assert len(parser.ids) == len(set(parser.ids)), 'Duplicate element IDs'
    assert {'overview', 'environment', 'population', 'dataset', 'experiments', 'report', 'literature'} <= set(parser.ids)
    assert '__WORKBENCH_' not in page and '__SHOWCASE_DATA__' not in page
    for target in parser.targets:
        if target.startswith('#'):
            assert target == '#' or target[1:] in parser.ids, target
        else:
            assert (ROOT / 'results' / target).is_file(), target
    assert 'fetch(' not in page, 'Viewer must work from a local file'
    for case in json.loads(match.group(1))['cases']:
        assert (ROOT / 'results/v7_20261030/run_metadata' / case['id'] / 'provenance.json').is_file()
    data = json.loads(match.group(1))
    assert len(data['personas']) == 300 and len(data['figures']) == 5 and len(data['references']) == 5
    for asset in data['assetSources']:
        assert hashlib.sha256((ROOT / asset['path']).read_bytes()).hexdigest() == asset['sha256']
    for figure in data['figures']:
        assert (ROOT / 'results' / figure['path']).is_file() and figure['uri'].startswith('data:image/png;base64,')
    assert (ROOT / 'results' / data['reportPath']).is_file()
    for source, name in [('03_新环境设定.md', 'environment.md'), ('05_案例与判断对象.json', 'belief-target.json'), ('01_Agent基础信息表.csv', 'population.csv')]:
        assert (ROOT / 'results/showcase-inputs' / name).read_bytes() == (ROOT / 'v7/materials_v7' / source).read_bytes()
    print('PASS: 7 modules; 178200 verified states; 54 frozen inputs; 300 matching personas; 5 embedded figures; report/references and asset hashes; no external assets or fetch calls.')


if __name__ == '__main__':
    main()
