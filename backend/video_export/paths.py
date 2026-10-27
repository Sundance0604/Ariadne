"""One portable location map; user captions and media remain local."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
CONFIG=ROOT/'config/video-export.json'
DEFAULTS={
    'sample_package':'output/video-export/ravel-demo',
    'sample_document':'local/video-export/ravel-sample.json',
    'font_settings':'local/video-export/font-sizes.json',
    'latest_video':'local/video-export/latest-video.txt',
    'full_package':'output/video-export/ravel-full-001',
    'full_document':'output/video-export/ravel-full-001/captions-editable.json',
}


def settings():
    values=json.loads(CONFIG.read_text(encoding='utf-8-sig')) if CONFIG.exists() else {}
    return {**DEFAULTS,**values}


def configured_path(key):
    path=(ROOT/settings()[key]).resolve()
    if not path.is_relative_to(ROOT):raise ValueError('导出配置须使用项目内路径：'+key)
    return path


def full_paths():
    return configured_path('full_package'),configured_path('full_document')


def editor_projects():
    """Resolve each caption document together with its own export package."""
    values=settings()
    projects=[]
    for item in values.get('editor_projects',[]):
        entry=dict(item)
        for field in ('package','document'):
            value=entry.get(field)
            if not isinstance(value,str) or not value:
                raise ValueError('字幕项目缺少路径：'+field)
            path=(ROOT/value).resolve()
            if not path.is_relative_to(ROOT):raise ValueError('字幕项目须使用项目内路径：'+field)
            entry[field]=path
        projects.append(entry)
    if not projects:
        package,document=full_paths()
        projects=[{'id':'ravel-full','title':'拉威尔左手钢协 · 完整版','package':package,'document':document}]
    ids=[p.get('id') for p in projects]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('字幕项目ID须为互不重复的非空文字。')
    if any(not isinstance(p.get('title'),str) or not p['title'].strip() for p in projects):
        raise ValueError('字幕项目须填写名称。')
    return projects


def remember_full(package,document):
    values=settings()
    values['full_package']=Path(package).resolve().relative_to(ROOT).as_posix()
    values['full_document']=Path(document).resolve().relative_to(ROOT).as_posix()
    for item in values.get('editor_projects',[]):
        if item.get('id')=='ravel-full':
            item.update(package=values['full_package'],document=values['full_document'])
    CONFIG.parent.mkdir(parents=True,exist_ok=True)
    CONFIG.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
