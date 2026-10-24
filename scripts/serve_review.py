"""Serve the local sync review at 127.0.0.1; no external uploads or accounts."""
import argparse
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import shutil
import socket
import threading
from urllib.parse import urlparse,parse_qs
from review_library import library,track_context,page_count
from pdf_render import render_page

ROOT=Path(__file__).resolve().parents[1]
LOCK=threading.Lock()


class ReviewServer(ThreadingHTTPServer):
    allow_reuse_address=False

    def server_bind(self):
        # Windows otherwise permits two development servers on the same port,
        # which can leave the browser talking to stale code after a restart.
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


def read_json(path): return json.loads(path.read_text(encoding='utf-8'))


class Handler(BaseHTTPRequestHandler):
    def send_file(self,path,content_type):
        self.send_response(200)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(path.stat().st_size))
        self.end_headers()
        with path.open('rb') as stream: shutil.copyfileobj(stream,self.wfile)

    def send_json(self,data,status=200):
        payload=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.end_headers(); self.wfile.write(payload)

    def do_GET(self):
        route=urlparse(self.path).path
        if route=='/': return self.send_file(ROOT/'review/index.html','text/html; charset=utf-8')
        if route=='/playhead.mjs': return self.send_file(ROOT/'review/playhead.mjs','text/javascript; charset=utf-8')
        if route=='/analysis.mjs': return self.send_file(ROOT/'review/analysis.mjs','text/javascript; charset=utf-8')
        if route=='/app.mjs': return self.send_file(ROOT/'review/app.mjs','text/javascript; charset=utf-8')
        if route=='/api/library':
            catalog=library(ROOT)
            return self.send_json({'default_track':catalog['default_track'],
                'tracks':[{'id':t['id'],'title':t['title']} for t in catalog['tracks']]})
        try:
            query=parse_qs(urlparse(self.path).query)
            track,directory=track_context(ROOT,query.get('track',[None])[0])
        except ValueError as error:
            return self.send_json({'error':str(error)},404)
        if route=='/api/analysis':
            try:
                from analysis_data import load_analysis
                return self.send_json(load_analysis(ROOT,directory))
            except (OSError,ValueError,KeyError,ImportError) as error:
                return self.send_json({'error':str(error)},422)
        if route=='/api/project':
            try:
                anchors=directory/'review-anchors.json'
                alignment=read_json(directory/'alignment.json')
                mapping=read_json(directory/'measure-map.json')
                saved=read_json(anchors) if anchors.exists() else None
                if saved and (saved.get('audio_sha256')!=alignment['audio']['sha256'] or
                              saved.get('score_sha256')!=alignment['symbolic_reference']['sha256']):
                    raise ValueError('已保存锚点与当前素材不匹配，请先检查')
                return self.send_json({'track':{'id':track['id'],'title':track['title']},
                    'page_count':page_count(mapping),'alignment':alignment,'mapping':mapping,'anchors':saved})
            except (OSError,ValueError,KeyError) as error:
                return self.send_json({'error':str(error)},422)
        if route=='/audio':
            document=read_json(directory/'alignment.json')
            path=(ROOT/document['audio']['path']).resolve()
            if not path.is_relative_to((ROOT/'resource').resolve()):
                return self.send_error(403)
            length=path.stat().st_size
            requested=self.headers.get('Range')
            match=re.fullmatch(r'bytes=(\d+)-(\d*)',requested or '')
            start,end=0,length-1
            if match:
                start=int(match[1]); end=min(int(match[2]) if match[2] else end,end)
                if start>end:
                    self.send_response(416); self.send_header('Content-Range',f'bytes */{length}')
                    self.end_headers(); return
            self.send_response(206 if match else 200)
            self.send_header('Content-Type','audio/mpeg')
            self.send_header('Accept-Ranges','bytes')
            self.send_header('Content-Length',str(end-start+1))
            if match: self.send_header('Content-Range',f'bytes {start}-{end}/{length}')
            self.end_headers()
            with path.open('rb') as stream:
                stream.seek(start); remaining=end-start+1
                try:
                    while remaining:
                        chunk=stream.read(min(65536,remaining))
                        if not chunk: break
                        self.wfile.write(chunk); remaining-=len(chunk)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
            return
        match=re.fullmatch(r'/page/(\d+)\.png',route)
        if match:
            n=int(match[1]); mapping=read_json(directory/'measure-map.json')
            if not 1<=n<=page_count(mapping): return self.send_error(404)
            pdf=(ROOT/mapping['pdf_path']).resolve()
            if not pdf.is_relative_to((ROOT/'resource').resolve()): return self.send_error(403)
            directory=ROOT/'tmp/review-pages/pdfium-v1'/mapping['pdf_sha256'][:12]
            prefix=directory/f'page-{n:03d}'; image=prefix.with_suffix('.png')
            with LOCK:
                if not image.exists():
                    directory.mkdir(parents=True,exist_ok=True)
                    try:
                        render_page(pdf,n,image)
                    except ImportError:
                        return self.send_json({'error':'请先运行 python -m pip install -r requirements.txt'},503)
                    except (OSError,ValueError,RuntimeError):
                        return self.send_error(500,'PDF rendering failed')
            return self.send_file(image,'image/png')
        self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path!='/api/anchors': return self.send_error(404)
        origin=self.headers.get('Origin')
        if origin and origin!=f'http://{self.headers.get("Host")}': return self.send_error(403)
        try:
            query=parse_qs(urlparse(self.path).query)
            track,directory=track_context(ROOT,query.get('track',[None])[0])
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1000000: raise ValueError('Invalid request size')
            request=json.loads(self.rfile.read(length))
            project=read_json(directory/'alignment.json')
            if query.get('track') and (request.get('track_id')!=track['id'] or
                    request.get('audio_sha256')!=project['audio']['sha256'] or
                    request.get('score_sha256')!=project['symbolic_reference']['sha256']):
                raise ValueError('锚点所属曲目或素材不匹配，请重新载入当前曲目')
            by_id={m['measure_id']:m for m in project['measures']}
            anchors=request['anchors']
            if not isinstance(anchors,list): raise ValueError('锚点格式无效')
            seen=set(); previous=(-1,-1)
            for a in anchors:
                m=by_id[a['measure_id']]
                if not all(isinstance(a.get(k),(int,float)) and not isinstance(a[k],bool) and math.isfinite(a[k])
                           for k in ['midi_seconds','audio_seconds']): raise ValueError('锚点时间必须为有限数值')
                if a['measure_id'] in seen: raise ValueError('同一小节出现重复锚点')
                seen.add(a['measure_id'])
                if abs(a['midi_seconds']-m['midi_start_seconds'])>.001: raise ValueError('谱面时间不匹配')
                if not 0<a['audio_seconds']<project['audio']['duration_seconds'] or not a['midi_seconds']>0:
                    raise ValueError('锚点必须在音频和谱面时间轴内部')
                if a['midi_seconds']<=previous[0] or a['audio_seconds']<=previous[1]:
                    raise ValueError('锚点在两条时间轴上都必须递增')
                if not isinstance(a.get('reason'),str) or not a['reason'].strip():
                    raise ValueError('每个锚点需要填写修改依据')
                previous=(a['midi_seconds'],a['audio_seconds'])
            path=directory/'review-anchors.json'
            with LOCK:
                old=read_json(path) if path.exists() else {}
                if old and (old.get('audio_sha256')!=project['audio']['sha256'] or
                            old.get('score_sha256')!=project['symbolic_reference']['sha256']):
                    raise ValueError('已有锚点属于其他素材，拒绝覆盖')
                history=old.get('history',[])
                history.append({'modified_at':datetime.now(timezone.utc).isoformat(),
                    'source':'human_review_ui','old_anchors':old.get('anchors',[]),'new_anchors':anchors})
                document={'format_version':'1.0.0','audio_sha256':project['audio']['sha256'],
                    'score_sha256':project['symbolic_reference']['sha256'],
                    'anchors':anchors,'history':history}
                pending=path.with_suffix('.json.tmp')
                pending.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
                pending.replace(path)
            self.send_json({'saved':True,'anchors':len(anchors)})
        except (OSError,ValueError,TypeError,KeyError) as error:
            self.send_json({'error':str(error)},400)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    server=ReviewServer(('127.0.0.1',args.port),Handler)
    print(f'Local review: http://127.0.0.1:{args.port}',flush=True)
    server.serve_forever()
