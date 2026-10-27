"""Serve the local sync review at 127.0.0.1; no external uploads or accounts."""
import argparse
import hashlib
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import re
import shutil
import socket
import sys
import threading
from urllib.parse import urlparse,parse_qs

# Direct script and one-click launches put scripts/, not the repository, on
# sys.path. Resolve from this file so package imports also work outside the
# repository and without PYTHONPATH (the playback environment needs no music21).
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from review_library import library,track_context,page_count,score_directory
from pdf_render import render_page
from score_measure_data import load_score_measures,update_numbering

LOCK=threading.Lock()
MEDIA_FINGERPRINTS={}


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
    def send_media(self,path,content_type):
        """Bounded streaming is essential for seeking in large local MP4s."""
        length=path.stat().st_size
        requested=self.headers.get('Range')
        start,end=0,length-1
        if requested:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
            if not match or not any(match.groups()):
                start=length
            elif not match[1]:
                start=max(0,length-int(match[2]))
            else:
                start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
            if start>end or start>=length:
                self.send_response(416);self.send_header('Content-Range',f'bytes */{length}')
                self.send_header('Content-Length','0');self.end_headers();return
        self.send_response(206 if requested else 200)
        self.send_header('Content-Type',content_type)
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Length',str(end-start+1))
        if requested:self.send_header('Content-Range',f'bytes {start}-{end}/{length}')
        self.end_headers()
        with path.open('rb') as stream:
            stream.seek(start);remaining=end-start+1
            try:
                while remaining:
                    chunk=stream.read(min(65536,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass

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
        if route=='/playback.mjs': return self.send_file(ROOT/'review/playback.mjs','text/javascript; charset=utf-8')
        if route=='/score-follow.mjs': return self.send_file(ROOT/'review/score-follow.mjs','text/javascript; charset=utf-8')
        if route=='/score-display.mjs': return self.send_file(ROOT/'review/score-display.mjs','text/javascript; charset=utf-8')
        if route=='/movements.mjs': return self.send_file(ROOT/'review/movements.mjs','text/javascript; charset=utf-8')
        if route=='/measure-numbers.mjs': return self.send_file(ROOT/'review/measure-numbers.mjs','text/javascript; charset=utf-8')
        if route in {'/research.mjs','/research-model.mjs','/research-ui.mjs','/structural-hud.mjs','/hermeneutics.mjs','/engine-evidence.mjs','/musicxml-evidence.mjs','/musicxml-live.mjs','/score-analysis-model.mjs','/hud-text.mjs'}:
            return self.send_file(ROOT/'review'/route[1:],'text/javascript; charset=utf-8')
        if route=='/api/library':
            catalog=library(ROOT)
            return self.send_json({'default_track':catalog['default_track'],
                'tracks':[{'id':t['id'],'title':t['title']} for t in catalog['tracks']]})
        if route=='/api/health':
            identity=hashlib.sha256(str(ROOT.resolve()).casefold().encode('utf-8')).hexdigest()[:24]
            return self.send_json({'app':'Ariadne','workspace_id':identity,'format_version':'1.0.0'})
        try:
            query=parse_qs(urlparse(self.path).query)
            track,directory=track_context(ROOT,query.get('track',[None])[0])
            shared=score_directory(ROOT,directory) if route.startswith('/api/') else directory
        except ValueError as error:
            return self.send_json({'error':str(error)},404)
        except (OSError,KeyError,TypeError) as error:
            return self.send_json({'error':str(error)},422)
        if track.get('analysis_adapter')=='prokofiev2-score-review-v1' and route in {'/api/analysis','/api/research','/api/musicxml','/api/musicxml-evidence','/api/musicxml-artifact','/api/musicxml-live'}:
            try:
                from backend.prokofiev2 import endpoint
                return self.send_json(endpoint(ROOT,directory,route,query))
            except (OSError,ValueError,KeyError,TypeError) as error:
                return self.send_json({'error':str(error)},422)
        if track.get('analysis_adapter')=='mother-goose-ballet-v1' and route in {'/api/analysis','/api/research','/api/musicxml','/api/musicxml-evidence','/api/musicxml-artifact','/api/musicxml-live'}:
            try:
                from backend.mother_goose import endpoint
                return self.send_json(endpoint(ROOT,directory,route,query))
            except (OSError,ValueError,KeyError,TypeError) as error:
                return self.send_json({'error':str(error)},422)
        if route=='/api/analysis':
            try:
                from analysis_data import load_analysis
                return self.send_json(load_analysis(ROOT,directory))
            except (OSError,ValueError,KeyError,ImportError) as error:
                return self.send_json({'error':str(error)},422)
        if route=='/api/research':
            try:
                from research_data import load_research
                return self.send_json(load_research(ROOT,directory,track_id=track['id']))
            except (OSError,ValueError,KeyError,TypeError,ImportError) as error:
                return self.send_json({'error':str(error)},422)
        if route in {'/api/musicxml','/api/musicxml-evidence','/api/musicxml-artifact','/api/musicxml-live'}:
            try:
                from backend.musicxml_analysis.store import load_bundle,measure_evidence
                from backend.structure_analysis.common import bounded_path
                bundle=load_bundle(ROOT,shared)
                if bundle is None:return self.send_json({'available':False})
                if route=='/api/musicxml-live':
                    from backend.musicxml_analysis.live_store import load_live
                    from backend.musicxml_analysis.hud import load_hud,live_payload
                    live=load_live(ROOT,directory,bundle,score_work=shared)
                    return self.send_json({'available':False} if not live else live_payload(bundle,live,load_hud(ROOT,shared,bundle)))
                if route=='/api/musicxml-evidence':
                    document=measure_evidence(bundle,query.get('measure_id',[''])[0])
                    from backend.musicxml_analysis.live_store import load_live
                    from backend.musicxml_analysis.hud import load_hud,audited_functions
                    live=load_live(ROOT,directory,bundle,score_work=shared)
                    if live:
                        overlay=load_hud(ROOT,shared,bundle)
                        document['harmonic_readings']={w['id']:[{**r,'functions_original':r['functions'],
                            'functions':audited_functions(r,overlay)}
                            for r in live['tables']['harmonic-readings']['readings'][w['id']]] for w in document['harmony']}
                        document['hud_cases']=[c for c in overlay['cases']['cases'] if c['measure_id']==document['measure']['measure_id']] if overlay else []
                    return self.send_json(document)
                if route=='/api/musicxml-artifact':
                    name=query.get('name',[''])[0]
                    if name not in bundle['manifest']['files']:return self.send_json({'error':'Unknown artifact'},404)
                    return self.send_file(bounded_path(ROOT,bundle['run_path'])/name,'application/json; charset=utf-8')
                return self.send_json({'available':True,'manifest':bundle['manifest'],'summary':bundle['tables']['summary'],
                    'measures':bundle['tables']['measures']['measures'],'edition_audit':bundle['tables']['pdf-map']['edition_audit']})
            except (OSError,ValueError,KeyError,TypeError) as error:
                return self.send_json({'error':str(error)},422)
        if route in {'/api/score-studies','/api/score-study-image'}:
            try:
                from backend.score_studies import load_studies
                study=load_studies(ROOT,shared)
                if route=='/api/score-study-image':
                    from backend.structure_analysis.common import bounded_path
                    window=next((w for w in study['document']['windows'] if w['id']==query.get('window_id',[''])[0]),None) if study else None
                    if not window or not window.get('evidence_image'):return self.send_json({'error':'Unknown score-study image'},404)
                    return self.send_file(bounded_path(ROOT,window['evidence_image']['path']),'image/png')
                return self.send_json({'available':False} if not study else {'available':True,**study})
            except (OSError,ValueError,KeyError,TypeError) as error:
                return self.send_json({'error':str(error)},422)
        if route in {'/api/structure','/api/structure-evidence'}:
            try:
                from backend.structure_analysis.store import load_bundle,event_evidence
                if route=='/api/structure-evidence':
                    return self.send_json(event_evidence(ROOT,shared,query.get('event_id',[''])[0]))
                bundle=load_bundle(ROOT,shared)
                return self.send_json({'available':False} if bundle is None else
                    {'available':True,'manifest':bundle['manifest'],'summary':bundle['summary']})
            except (OSError,ValueError,KeyError,TypeError,ImportError) as error:
                return self.send_json({'error':str(error)},422)
        if route=='/api/project':
            try:
                anchors=directory/'review-anchors.json'
                alignment=read_json(directory/'alignment.json')
                mapping=read_json(directory/'measure-map.json')
                saved=read_json(anchors) if anchors.exists() else None
                media=read_json(directory/'media-sync.json') if (directory/'media-sync.json').exists() else None
                score_anchors_path=directory/'score-region-anchors.json'
                score_anchors=read_json(score_anchors_path) if score_anchors_path.exists() else None
                if score_anchors and (score_anchors.get('audio_sha256')!=alignment['audio']['sha256'] or score_anchors.get('pdf_sha256')!=mapping['pdf_sha256']):
                    raise ValueError('谱面区域人工校正与当前素材不匹配')
                if media and media['masterClock']=='video' and media['video']['sha256']!=alignment['audio']['sha256']:
                    raise ValueError('视频与当前总谱对齐的素材指纹不一致')
                if saved and (saved.get('audio_sha256')!=alignment['audio']['sha256'] or
                              saved.get('score_sha256')!=alignment['symbolic_reference']['sha256']):
                    raise ValueError('已保存锚点与当前素材不匹配，请先检查')
                xml_regions=None;xml_navigation_error=None
                try:
                    from backend.musicxml_analysis.store import load_bundle as load_xml
                    from backend.musicxml_analysis.live_store import load_live
                    xml=load_xml(ROOT,shared,mapping)
                    live=load_live(ROOT,directory,xml,score_work=shared) if xml else None
                    if live:
                        # Runtime geometry adapter only. Source alignment and
                        # the older on-disk PDF map remain untouched.
                        by_id={m['measure_id']:m for m in xml['tables']['measures']['measures']}
                        xml_regions=[]
                        for region in xml['tables']['pdf-map']['measures']:
                            m=by_id[region['measure_id']];reference=alignment['measures'][m['sequence']-1]
                            xml_regions.append({**region,'xml_measure_id':m['measure_id'],
                                'measure_id':reference['measure_id'],'resolution':'bar' if region['precision']=='measure_region_not_notehead' else 'shared_xml_system',
                                'coordinate_origin':'top_left','review_status':'agent_layout_checked_human_pending'})
                except (OSError,ValueError,KeyError,TypeError) as error:xml_navigation_error=str(error)
                return self.send_json({'track':{'id':track['id'],'title':track['title']},
                    'page_count':page_count(mapping),'alignment':alignment,'mapping':mapping,'anchors':saved,'media':media,
                    'score_region_anchors':score_anchors,'score_measures':load_score_measures(directory,mapping),
                    'symbolic_pdf_regions':xml_regions,'xml_navigation_error':xml_navigation_error})
            except (OSError,ValueError,KeyError) as error:
                return self.send_json({'error':str(error)},422)
        if route in {'/audio','/video'}:
          try:
            document=read_json(directory/'alignment.json')
            media=read_json(directory/'media-sync.json') if (directory/'media-sync.json').exists() else None
            if route=='/video':
                if not media:return self.send_error(404)
                entry=media['video']
            else:entry=document['audio']
            path=(ROOT/entry['path']).resolve()
            if not path.is_relative_to((ROOT/'resource').resolve()):
                return self.send_error(403)
            if entry.get('bytes') and path.stat().st_size!=entry['bytes']:
                return self.send_json({'error':'媒体文件已变化，请重新准备和对齐'},409)
            if route=='/video':
                stat=path.stat();key=(str(path),stat.st_size,stat.st_mtime_ns)
                with LOCK:
                    if key not in MEDIA_FINGERPRINTS:
                        with path.open('rb') as stream:MEDIA_FINGERPRINTS[key]=hashlib.file_digest(stream,'sha256').hexdigest()
                    actual=MEDIA_FINGERPRINTS[key]
                if actual!=entry['sha256']:
                    return self.send_json({'error':'视频指纹发生变化，请重新准备和对齐'},409)
            return self.send_media(path,mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
          except (OSError,ValueError,KeyError) as error:
            return self.send_json({'error':f'本地媒体不可用：{error}'},404)
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
        if urlparse(self.path).path=='/api/score-measure-number':return self.save_score_measure_number()
        if urlparse(self.path).path=='/api/score-region-anchor':return self.save_score_region_anchor()
        if urlparse(self.path).path=='/api/media-sync':return self.save_media_sync()
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

    def save_media_sync(self):
        origin=self.headers.get('Origin')
        if origin and origin!=f'http://{self.headers.get("Host")}':return self.send_error(403)
        try:
            from media_sync import validate_anchors
            query=parse_qs(urlparse(self.path).query)
            track,directory=track_context(ROOT,query.get('track',[None])[0])
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=100000:raise ValueError('请求过大或为空')
            request=json.loads(self.rfile.read(length))
            with LOCK:
                path=directory/'media-sync.json'
                media=read_json(path);alignment=read_json(directory/'alignment.json')
                if media['masterClock']!='audio':raise ValueError('仅双媒体项目需要音画锚点')
                if request.get('track_id')!=track['id'] or request.get('master_sha256')!=alignment['audio']['sha256'] or request.get('video_sha256')!=media['video']['sha256']:
                    raise ValueError('锚点与当前曲目或媒体指纹不匹配')
                if request.get('same_performance_confirmed') is not True:
                    raise ValueError('需要先确认音频与视频来自同一演出')
                reason=request.get('reason','').strip()
                if not reason:raise ValueError('请填写核验依据')
                anchors=validate_anchors(request['anchors'],alignment['audio']['duration_seconds'],media['video']['duration_seconds'])
                updated=[{**a,'reviewStatus':'corrected'} for a in anchors]
                media.setdefault('history',[]).append({'modified_at':datetime.now(timezone.utc).isoformat(),
                    'source':'human_review_ui','reason':reason,'old_anchors':media.get('anchors',[]),'new_anchors':updated})
                media.update(anchors=updated,method='manual_piecewise_linear',matchStatus='manual_reviewed',
                    validInterval={'masterStart':updated[0]['masterTime'],'masterEnd':updated[-1]['masterTime']})
                pending=path.with_suffix('.json.tmp');pending.write_text(json.dumps(media,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');pending.replace(path)
            return self.send_json({'saved':True,'media':media})
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
            return self.send_json({'error':str(error)},400)

    def save_score_region_anchor(self):
        origin=self.headers.get('Origin')
        if origin and origin!=f'http://{self.headers.get("Host")}':return self.send_error(403)
        try:
            query=parse_qs(urlparse(self.path).query)
            track,directory=track_context(ROOT,query.get('track',[None])[0])
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=100000:raise ValueError('请求过大或为空')
            request=json.loads(self.rfile.read(length))
            alignment=read_json(directory/'alignment.json');mapping=read_json(directory/'measure-map.json')
            if request.get('track_id')!=track['id'] or request.get('audio_sha256')!=alignment['audio']['sha256'] or request.get('pdf_sha256')!=mapping['pdf_sha256']:
                raise ValueError('谱面校正所属曲目或素材指纹不匹配')
            regions={r['region_id']:r for r in mapping.get('score_regions',[])+mapping.get('bar_regions',[])}
            numbered=load_score_measures(directory,mapping)
            if numbered:regions.update({r['region_id']:r for r in numbered['measures']})
            region_id=request['region_id']
            if region_id not in regions:raise ValueError('未知原谱区域')
            start,end=request['start_seconds'],request['end_seconds']
            if any(not isinstance(t,(int,float)) or isinstance(t,bool) or not math.isfinite(t) for t in [start,end]):
                raise ValueError('时间必须为有限数值')
            if not 0<=start<end<=alignment['audio']['duration_seconds']:raise ValueError('时间须在当前视频内且起点早于终点')
            reason=request.get('reason','').strip()
            if not reason or request.get('confirmed') is not True:raise ValueError('请确认已核对原谱和录音，并填写校正依据')
            anchor={'region_id':region_id,'start_seconds':start,'end_seconds':end,'reason':reason,
                'review_status':'corrected','source':'human_review_ui','modified_at':datetime.now(timezone.utc).isoformat()}
            path=directory/'score-region-anchors.json'
            with LOCK:
                old=read_json(path) if path.exists() else {'audio_sha256':alignment['audio']['sha256'],'pdf_sha256':mapping['pdf_sha256'],'anchors':[],'history':[]}
                if old['audio_sha256']!=alignment['audio']['sha256'] or old['pdf_sha256']!=mapping['pdf_sha256']:
                    raise ValueError('已有人工校正属于其他素材，拒绝覆盖')
                for other in old['anchors']:
                    if other['region_id']==region_id:continue
                    related=regions[region_id].get('parent_region_id')==other['region_id'] or regions.get(other['region_id'],{}).get('parent_region_id')==region_id
                    if not related and max(start,other['start_seconds'])<min(end,other['end_seconds']):
                        raise ValueError('与其他已校正区域的时间重叠，请先核对边界')
                previous=next((a for a in old['anchors'] if a['region_id']==region_id),None)
                old['anchors']=[a for a in old['anchors'] if a['region_id']!=region_id]+[anchor]
                old['history'].append({'modified_at':anchor['modified_at'],'old_anchor':previous,'new_anchor':anchor})
                pending=path.with_suffix('.json.tmp');pending.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');pending.replace(path)
            return self.send_json({'saved':True,'score_region_anchors':old})
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
            return self.send_json({'error':str(error)},400)

    def save_score_measure_number(self):
        origin=self.headers.get('Origin')
        if origin and origin!=f'http://{self.headers.get("Host")}':return self.send_error(403)
        try:
            query=parse_qs(urlparse(self.path).query)
            track,directory=track_context(ROOT,query.get('track',[None])[0])
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=100000:raise ValueError('请求过大或为空')
            request=json.loads(self.rfile.read(length))
            if request.get('track_id')!=track['id']:raise ValueError('编号校正所属曲目不匹配')
            with LOCK:
                mapping=read_json(directory/'measure-map.json')
                document=load_score_measures(directory,mapping)
                if document is None:raise ValueError('当前作品尚未建立小节编号索引')
                path=directory/'score-measure-corrections.json'
                saved=update_numbering(document,read_json(path) if path.exists() else None,request)
                pending=path.with_suffix('.json.tmp')
                pending.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
                pending.replace(path)
                document=load_score_measures(directory,mapping)
            return self.send_json({'saved':True,'score_measures':document})
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
            return self.send_json({'error':str(error)},400)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    server=ReviewServer(('127.0.0.1',args.port),Handler)
    print(f'Local review: http://127.0.0.1:{args.port}',flush=True)
    server.serve_forever()
