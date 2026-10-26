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


def remember_full(package,document):
    values=settings()
    values['full_package']=Path(package).resolve().relative_to(ROOT).as_posix()
    values['full_document']=Path(document).resolve().relative_to(ROOT).as_posix()
    CONFIG.parent.mkdir(parents=True,exist_ok=True)
    CONFIG.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
