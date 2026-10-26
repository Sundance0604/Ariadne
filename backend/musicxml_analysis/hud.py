"""Small HUD evidence overlay over immutable XML/interpretation snapshots.

Build-time Roman reconstruction uses optional music21; playback uses stdlib.
This does not rerun note extraction, harmony inference, OMR or alignment.
"""
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path
from backend.structure_analysis.common import read,write,digest,bounded_path
import json


def roman_token(context,figure,pcs):
    return json.dumps([context,figure,sorted(pcs)],ensure_ascii=True,separators=(',',':'))


def audited_functions(reading,overlay):
    checks=overlay['roman']['checks'] if overlay else {}
    return [{**f,**checks.get(roman_token(f['context'],f['figure'],reading['description'].get('pitch_classes',[])),
        {'pitch_classes_agree':False,'validation_status':'not_checked'})} for f in reading['functions']]


def build(root,output):
    from music21 import roman,key
    from .store import load_bundle
    from .live_store import load_live
    root,output=Path(root).resolve(),Path(output).resolve()
    if output.exists() or not output.is_relative_to(root/'analysis/hud'):raise ValueError('Use a new HUD overlay directory')
    base=load_bundle(root,root);live=load_live(root,root,base);tables=base['tables']
    windows=tables['harmony']['windows'];notes={e['id']:e for e in tables['events']['events']}
    measures={m['number']:m for m in tables['measures']['measures']};cases=[]
    def window(number,onset):
        return next(w for w in windows if w['measure_id']==f'xml-m{number:04d}' and F(w['onset_q'])==F(onset))
    def add(id,number,onset,label,explanation,**extra):
        w=window(number,onset)
        case={'id':id,'measure_id':w['measure_id'],'window_id':w['id'],
            'start_q':w['start_q'],'end_q':w['end_q'],'label':label,'explanation':explanation,
            'event_ids':w['event_ids'],'global_bass':w['sonority']['bass'],
            'interval_ids':[r['id'] for r in base['indices']['intervals'].get(w['measure_id'],[])
                if F(r['start_q'])<=F(w['start_q'])<F(r['end_q'])][:4],
            'status':'agent_source_evidence_checked_human_pending','dimensions':['harmony','counterpoint'],**extra}
        cases.append(case);return case
    add('m11-layers',11,'1','持续低音与上层和声分开',
        '全体最低音E1；除E音级层外为G–B♭–D–F，上层低音D2、第二转位。弦乐层另成E半减七，分析对象不同，允许并列。',
        related_essay_ids=['ravel-harmonic-ledger','ravel-texture-counterpoint'])
    add('m58-open-fifth',58,'13/8','开放五度与独奏内部分层',
        'G♭／D♭仅两个音级，多八度加倍；未出现三音，不据此确定主属功能。钢琴同一分部包含不同谱表／声部，不能由一个分部推出单线织体。',
        related_essay_ids=['ravel-harmonic-ledger','ravel-texture-counterpoint'],dimensions=['harmony','orchestration'])
    add('m63-upbeat',63,'7/4','D/A乐队弱起层',
        '当前记谱音D–F♯–A，最低A3，第二转位。D调下I64是条件性读法；此处不能自动称终止四六，也不把录音踏板余响并入XML时值。',
        related_essay_ids=['ravel-harmonic-ledger','ravel-form-functions'])
    add('m64-upper-A',64,'0','E上层与A持续层',
        '全体包含A–B–E–G♯，最低A3；所选E三和弦层的最低音另列。后续低音在3/4处到A1，再在1处到D1，不能合并为整小节同一纵向和弦。',
        related_essay_ids=['ravel-harmonic-ledger'])
    add('m64-low-A',64,'3/4','深低音A加入',
        '低音巴松、低音提琴等在3/4处加入A低音区；这是新的记谱时点，尚未到D低音。')
    add('m64-low-D',64,'1','D低音随后到达',
        '小节内1处D1成为全体最低音；此前的E上层读法不直接继承为此刻全体和弦。')
    add('m520-strings',520,'2','钢琴与低弦重建',
        '中提琴B3/D4与大提琴B2/D3作八度加倍，G1低音支撑；钢琴有自身多声部。当前尚无低音单簧管。',
        related_essay_ids=['ravel-texture-counterpoint','ravel-form-functions'],dimensions=['orchestration','counterpoint','form'])
    add('m520-bass-clarinet',520,'11/4','低音单簧管后进入',
        '低音单簧管D2在11/4处加入；活跃分部由钢琴及三个低弦分部增加为五个分部，不把小节活动并集当作当前状态。',dimensions=['orchestration','counterpoint','form'])
    # Assertions bind these editorial demonstrations to observed source content,
    # rather than displaying a prescribed label merely because a bar number matches.
    def require(condition,message):
        if not condition:raise ValueError('Demonstration evidence changed: '+message)
    r11=live['tables']['harmonic-readings']['readings'][window(11,'1')['id']]
    upper=next(r for r in r11 if r['kind']=='bass_pitch_class_layer_reduction')
    require(upper['description']['chord']['root']=='G' and upper['description']['chord']['quality']=='minor seventh chord' and
        upper['description']['bass']['name']=='D2' and window(11,'1')['sonority']['bass']['name']=='E1','m11 layers')
    require(set(window(58,'13/8')['sonority']['spelled_pitches'])=={'Gb1','Gb2','Db4','Gb4'},'m58 open fifth')
    require(window(63,'7/4')['sonority']['chord']['root']=='D' and window(63,'7/4')['sonority']['bass']['name']=='A3','m63 upbeat')
    require([window(64,t)['sonority']['bass']['name'] for t in ['0','3/4','1']]==['A3','A1','D1'],'m64 bass stages')
    require(any(r['kind']=='bass_pitch_class_layer_reduction' and r['description']['chord']['root']=='E'
        for r in live['tables']['harmonic-readings']['readings'][window(64,'0')['id']]),'m64 E upper layer')
    for onset,expected in [('2',{'P23','P30','P32','P35'}),('11/4',{'P23','P30','P32','P35','P7'})]:
        frame=next(f for f in live['tables']['activation']['frames'] if f['measure_id']=='xml-m0520' and f['onset_q']==onset)
        require({p['part_id'] for p in frame['active_instruments']}==expected,'m520 staggered entry')
    pedal=notes['P9-xml-m0011-n0001']
    contexts=[{'id':'m11-E-pedal','start_q':pedal['score_start_q'],'end_q':pedal['score_end_q'],
        'measure_id':pedal['measure_id'],'label':'E1持续低音；上层和声另作局部分析',
        'event_ids':[pedal['id']],'status':'source_supported_pedal_not_final_harmonic_function'}]
    cache={};counts={'checked':0,'compatible':0,'withheld':0}
    for id,readings in live['tables']['harmonic-readings']['readings'].items():
        for reading in readings:
            pcs=sorted(reading['description'].get('pitch_classes',[]))
            for f in reading['functions']:
                token=roman_token(f['context'],f['figure'],pcs)
                if token not in cache:
                    try:
                        mode='minor' if f['context'].endswith('小调') else 'major'
                        tonic=f['context'][:-2].replace('b','-')
                        reconstructed=sorted(set(roman.RomanNumeral(f['figure'],key.Key(tonic,mode)).pitchClasses))
                        cache[token]={'pitch_classes_agree':reconstructed==pcs,'reconstructed_pitch_classes':reconstructed}
                    except (ValueError,TypeError,AttributeError) as error:
                        cache[token]={'pitch_classes_agree':False,'reason':type(error).__name__}
                counts['checked']+=1;counts['compatible' if cache[token]['pitch_classes_agree'] else 'withheld']+=1
                cache[token]['validation_status']='pitch_classes_checked_not_function_verified' if cache[token]['pitch_classes_agree'] else 'withheld_reconstruction_mismatch'
    counts['unique_checks']=len(cache)
    document={'schema_version':'1.0.0','cases':cases,'contexts':contexts,
        'human_signoffs':0,'expert_signoffs':0,'scope':'Four demonstration groups; not full-score background harmony'}
    output.mkdir(parents=True);write(output/'cases.json',document)
    write(output/'roman-audit.json',{'checks':cache,'counts':counts,
        'basis':'Reconstruct each existing figure in its named key and compare the selected layer pitch-class set; function remains conditional.'})
    manifest={'base_manifest_sha256':digest(bounded_path(root,base['run_path'])/'manifest.json'),
        'interpretation_manifest_sha256':digest(bounded_path(root,live['path'])/'manifest.json'),
        'build_code_sha256':digest(Path(__file__)),
        'files':{n:digest(output/n) for n in ['cases.json','roman-audit.json']},'counts':counts}
    write(output/'manifest.json',manifest)
    write(root/'analysis/hud/current.json',{'path':output.relative_to(root).as_posix(),'manifest_sha256':digest(output/'manifest.json')})
    return counts


@lru_cache(maxsize=1)
def _load(root_text,work_text,pointer_text,base_hash,interpretation_hash,token):
    import json
    root,work=Path(root_text),Path(work_text);pointer=json.loads(pointer_text)
    run=bounded_path(root,pointer['path'])
    if not run.is_relative_to(work/'analysis/hud'):raise ValueError('HUD overlay outside work')
    if digest(run/'manifest.json')!=pointer['manifest_sha256']:raise ValueError('HUD manifest changed')
    manifest=read(run/'manifest.json')
    if manifest['base_manifest_sha256']!=base_hash or manifest['interpretation_manifest_sha256']!=interpretation_hash:
        raise ValueError('HUD evidence belongs to another score snapshot')
    for name,sha in manifest['files'].items():
        if digest(bounded_path(run,name))!=sha:raise ValueError('HUD evidence changed')
    return {'manifest':manifest,'cases':read(run/'cases.json'),'roman':read(run/'roman-audit.json')}


def load_hud(root,work,base):
    root,work=Path(root).resolve(),Path(work).resolve();path=work/'analysis/hud/current.json'
    if not path.exists():return None
    pointer=read(path);run=bounded_path(root,pointer['path']);manifest=read(run/'manifest.json')
    interpretation=read(work/'analysis/musicxml/interpretation-current.json')
    paths=[path,run/'manifest.json',*[bounded_path(run,n) for n in manifest['files']]]
    token=tuple((p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
    return _load(str(root),str(work),path.read_text(encoding='utf-8'),
        digest(bounded_path(root,base['run_path'])/'manifest.json'),interpretation['manifest_sha256'],token)


def live_payload(base,live,overlay):
    compact={}
    for id,readings in live['tables']['harmonic-readings']['readings'].items():
        compact[id]=[{k:r[k] for k in ['id','kind','label','basis']}|
            {'functions':audited_functions(r,overlay),
             'included_note_count':len(r['event_ids']),'excluded_note_count':len(r['omitted_event_ids']),
             'layer_bass':r['description'].get('bass'),'chord':r['description'].get('chord'),
             'pitches':r['description'].get('spelled_pitches',[])} for r in readings]
    return {'available':True,'summary':live['manifest']['summary'],
        'projection':live['tables']['recording-projection'],
        'frames':[{**f,'active_instruments':[{k:v for k,v in p.items() if k!='event_ids'} for p in f['active_instruments']]} for f in live['tables']['activation']['frames']],
        'windows':{w['id']:{'id':w['id'],'measure_id':w['measure_id'],'event_count':len(w['event_ids']),
            'pitches':w['sonority']['spelled_pitches'],'pitch_classes':w['sonority']['pitch_classes'],
            'bass':w['sonority'].get('bass'),'chord':w['sonority'].get('chord'),
            'structures':w['sonority'].get('structures',[])} for w in base['tables']['harmony']['windows']},
        'readings':compact,'form':live['tables']['form-synthesis'],
        'hud_cases':overlay['cases'] if overlay else None,
        'roman_audit':overlay['manifest']['counts'] if overlay else None}


if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(build(Path.cwd(),args.output)))
