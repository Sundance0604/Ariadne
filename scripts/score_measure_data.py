"""PDF-bound physical measure identities and reversible numbering corrections."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json


def geometry_digest(measures):
    geometry=[{k:m[k] for k in ['region_id','movement','page_number','system_index','rect_pt']}
              for m in measures]
    return hashlib.sha256(json.dumps(geometry,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def timing_source_digest(mapping):
    regions=[{k:r.get(k) for k in ['region_id','rect_pt','midi_start_seconds','midi_end_seconds']}
             for r in mapping.get('score_regions',[])+mapping.get('bar_regions',[])]
    return hashlib.sha256(json.dumps(regions,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def apply_numbering(document, corrections=None):
    result=deepcopy(document)
    if corrections and (corrections.get('pdf_sha256')!=document['pdf_sha256'] or
                        corrections.get('geometry_sha256')!=document['geometry_sha256']):
        raise ValueError('已保存编号校正与当前 PDF 或小节边界不匹配')
    overrides={a['region_id']:a for a in (corrections or {}).get('anchors',[])}
    number=1;movement=None;anchor=None
    for region in result['measures']:
        if region['movement']!=movement:
            movement=region['movement'];number=1;anchor=None
        override=overrides.get(region['region_id'])
        if override:
            number=override['start_number'];anchor=override['region_id']
        span=override['count_span'] if override else 1
        region.update(score_measure_number=number,count_span=span,
                      numbering_status='corrected' if override else 'inferred',
                      numbering_anchor_id=anchor,
                      numbering_method='manual_anchor' if override else 'counted_detected_barlines')
        number+=span
    result['corrections']=corrections
    return result


def load_score_measures(directory,mapping):
    path=directory/'score-measures.json'
    if not path.exists():return None
    data=json.loads(path.read_text(encoding='utf-8'))
    if data['pdf_sha256']!=mapping['pdf_sha256']:
        raise ValueError('小节编号属于另一 PDF，请重新识图')
    if data.get('symbolic_reference_sha256')!=mapping.get('symbolic_reference_sha256'):
        raise ValueError('小节编号的 MIDI 时间参考已变化，请重新建立关联')
    if data.get('timing_source_sha256') and data['timing_source_sha256']!=timing_source_digest(mapping):
        raise ValueError('原谱匹配已更新，请重新建立小节编号与时间关联')
    if geometry_digest(data['measures'])!=data['geometry_sha256']:
        raise ValueError('小节边界已变化，请重新建立编号索引')
    corrections=directory/'score-measure-corrections.json'
    return apply_numbering(data,json.loads(corrections.read_text(encoding='utf-8')) if corrections.exists() else None)


def update_numbering(document,old,request):
    if request.get('pdf_sha256')!=document['pdf_sha256'] or request.get('geometry_sha256')!=document['geometry_sha256']:
        raise ValueError('编号校正所属 PDF 或边界版本不匹配')
    if request.get('region_id') not in {r['region_id'] for r in document['measures']}:
        raise ValueError('未知谱面小节')
    for key,maximum in [('start_number',10000),('count_span',100)]:
        value=request.get(key)
        if not isinstance(value,int) or isinstance(value,bool) or not 0<=value<=maximum:
            raise ValueError('小节号和本框小节数须为范围内的非负整数')
    reason=request.get('reason')
    if not isinstance(reason,str) or not reason.strip() or request.get('confirmed') is not True:
        raise ValueError('请核对原谱编号与边界，勾选确认并填写依据')
    old=deepcopy(old) if old else {'pdf_sha256':document['pdf_sha256'],
        'geometry_sha256':document['geometry_sha256'],'anchors':[],'history':[]}
    apply_numbering(document,old)  # Reject stale corrections before writing anything.
    anchor={k:request[k] for k in ['region_id','start_number','count_span']}
    anchor.update(reason=reason.strip(),source='human_review_ui',review_status='corrected',
                  modified_at=datetime.now(timezone.utc).isoformat())
    previous=next((a for a in old['anchors'] if a['region_id']==anchor['region_id']),None)
    old['anchors']=[a for a in old['anchors'] if a['region_id']!=anchor['region_id']]+[anchor]
    # Distinct confirmed anchors must not number backwards. A zero-span
    # continuation may intentionally share its number with the next measure.
    numbers={a['region_id']:a for a in old['anchors']}
    minimum={}
    for region in document['measures']:
        a=numbers.get(region['region_id'])
        movement=region['movement']
        if a:
            if movement in minimum and a['start_number']<minimum[movement]:
                raise ValueError('与前面已确认编号之间的计数冲突，请先核对弱起、跨行或合并小节')
            minimum[movement]=a['start_number']+a['count_span']
        elif movement in minimum:minimum[movement]+=1
    old['history'].append({'modified_at':anchor['modified_at'],'old_anchor':previous,'new_anchor':anchor})
    return old
