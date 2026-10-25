"""Desktop-friendly local launcher, used by the one-click Windows batch file."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import webbrowser

from review_library import library
from serve_review import Handler, ReviewServer, ROOT


def choose_playable_track(root,catalog,requested):
    """A clean clone intentionally lacks large local performance videos."""
    order=list(dict.fromkeys([requested,catalog['default_track'],*[t['id'] for t in catalog['tracks']]]))
    for identifier in order:
        track=next((t for t in catalog['tracks'] if t['id']==identifier),None)
        if not track:continue
        directory=(Path(root)/track['data_root']).resolve()
        if not directory.is_relative_to(Path(root).resolve()):continue
        try:
            alignment=json.loads((directory/'alignment.json').read_text(encoding='utf-8'))
            entry=alignment['audio']
            path=Path(root)/entry['path']
            if path.is_file() and (not entry.get('bytes') or path.stat().st_size==entry['bytes']):return identifier
        except (OSError,ValueError,KeyError,TypeError):continue
    raise RuntimeError('尚未找到本机可播放的素材，请按 AGENTS.md 放置录音或视频后重试。')


def workspace_id(root):
    return hashlib.sha256(str(Path(root).resolve()).casefold().encode('utf-8')).hexdigest()[:24]


def find_running(root,ports):
    expected=workspace_id(root)
    for port in ports:
        try:
            with urlopen(f'http://127.0.0.1:{port}/api/health',timeout=.15) as response:
                data=json.load(response)
            if isinstance(data,dict) and data.get('app')=='Ariadne' and data.get('workspace_id')==expected:
                return port
        except (URLError,OSError,ValueError):
            pass
    return None


def bind_available(ports):
    for port in ports:
        try:return ReviewServer(('127.0.0.1',port),Handler)
        except OSError:continue
    raise RuntimeError('本地播放端口已被占用，请关闭旧的播放器窗口后重试。')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--track',default='mahler-4')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--check',action='store_true',help='Check startup/reuse without launching a browser or blocking')
    args=parser.parse_args()
    catalog=library(ROOT)
    track=choose_playable_track(ROOT,catalog,args.track)
    if track!=args.track:print('所选曲目的本地媒体尚未提供，先打开材料齐全的曲目；马勒视频不随仓库分发。',flush=True)
    ports=range(8765,8786)
    active=find_running(ROOT,ports)
    server=None
    if active is None:
        server=bind_available(ports);active=server.server_port
    url=f'http://127.0.0.1:{active}/?'+urlencode({'track':track})
    print(('复用已启动的播放器：' if server is None else '播放器地址：')+url,flush=True)
    if args.check:
        if server:server.server_close()
        print('启动检查通过。',flush=True)
        return
    if not args.no_browser:
        try:webbrowser.open(url,new=2)
        except OSError:print('浏览器未能自动打开，请复制上方地址打开。',flush=True)
    if server is None:return
    print('关闭此窗口即可停止播放器。素材只在本机读取。',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
