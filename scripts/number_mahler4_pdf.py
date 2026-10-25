"""Pre-read the scan and publish editable, explicitly inferred measure numbers.

Original PDF and alignment are never rewritten. Rehearsal figures in its OCR
layer are landmarks, not automatically trusted printed measure numbers.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from scipy import ndimage as ndi

from score_measure_data import geometry_digest,apply_numbering,timing_source_digest

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'works/mahler-4'


def runs(values,gap=2):
    return [g for g in np.split(values,np.where(np.diff(values)>gap)[0]+1) if len(g)]


def unique_systems(systems):
    kept=[];duplicates=[]
    for system in sorted(systems,key=lambda s:(s['page'],s['top'],s['system'])):
        duplicate=next((s for s in kept if s['page']==system['page'] and
            min(s['bottom'],system['bottom'])-max(s['top'],system['top'])>
            .9*max(s['bottom']-s['top'],system['bottom']-system['top']) and
            abs(s['boundaries'][0]-system['boundaries'][0])<12 and
            abs(s['boundaries'][-1]-system['boundaries'][-1])<12),None)
        if duplicate:duplicates.append({'page':system['page'],'system':system['system'],'kept_system':duplicate['system']})
        else:kept.append(system)
    return kept,duplicates


def observed_boundaries(array,system):
    ink=array<150
    horizontal=ndi.binary_opening(ink,structure=np.ones((1,45)))
    wide=ndi.maximum_filter(ink,size=(1,5))
    left,right=system['boundaries'][0],system['boundaries'][-1]
    rows=horizontal[:,left:right].sum(axis=1)
    ys=np.flatnonzero(rows>(right-left)*.35)
    ys=ys[(ys>=system['top']-10)&(ys<=system['bottom']+10)]
    lines=[int(g[np.argmax(rows[g])]) for g in runs(ys)]
    groups=[]
    for y in lines:
        if groups and y-groups[-1][-1]<12:groups[-1].append(y)
        else:groups.append([y])
    staffs=[g for g in groups if 4<=len(g)<=6]
    votes=np.zeros(array.shape[1])
    for staff in staffs:
        vertical=wide[staff[0]:staff[-1]+1].mean(axis=0)>=.88
        votes+=ndi.maximum_filter(vertical,size=5)
    support=votes/max(1,len(staffs))
    # A high cross-staff vote rejects aligned stems, beams and time signatures.
    xs=[int(g[np.argmax(votes[g])]) for g in runs(np.flatnonzero(support>=.85),7)]
    xs=[x for x in xs if left+105<x<right-15]
    old=system['boundaries']
    additions=[x for x in xs if all(abs(x-y)>12 for y in old)]
    boundaries=sorted(old+additions)
    return boundaries,[round(float(support[x]),4) for x in boundaries],len(staffs),additions


def ocr_landmarks(page,systems):
    text=page.get_textpage();value=text.get_text_range();height=page.get_height()
    result=[];index=0
    while index<len(value):
        if not value[index].isdigit():index+=1;continue
        start=index
        while index<len(value) and value[index].isdigit():index+=1
        token=value[start:index]
        if len(token)>3:continue
        boxes=[text.get_charbox(i) for i in range(start,index)]
        left=min(b[0] for b in boxes);top=height-max(b[3] for b in boxes)
        for system in systems:
            # Only the space immediately above a system, never page footers,
            # meter digits inside staves or numbers in instrument labels.
            if system['top']/2-30<=top<=system['top']/2-2 and left>=system['boundaries'][0]/2:
                result.append({'text':token,'x_pt':left,'y_pt':top,'system_index':system['system'],
                    'kind':'unclassified_numeric_landmark','is_measure_number_anchor':False,
                    'evidence':'existing_scan_ocr_layer; rehearsal/meter/measure classification requires review'})
    text.close()
    return result


def label_position(array,rect,previous_bottom=0):
    """Find whitespace above the staff instead of obscuring tempo/flag text."""
    left,top,width,_=rect
    box_width=min(36,width-2);max_height=min(13,max(7,top-previous_bottom-3))
    ink=array<185
    best=None
    for box_height in sorted({max_height,max(7,max_height-2),7},reverse=True):
        for bottom in np.arange(top-2,max(previous_bottom+box_height+1,top-65)-.5,-1):
            for fraction in [.5,.32,.68,.2,.8]:
                center=left+width*fraction
                center=max(left+box_width/2,min(left+width-box_width/2,center))
                x0,x1=round((center-box_width/2)*2),round((center+box_width/2)*2)
                y0,y1=round((bottom-box_height)*2),round(bottom*2)
                if y0<0 or x0<0:continue
                density=float(ink[y0:y1,x0:x1].mean())
                score=density*1000+(top-bottom)*.01+abs(fraction-.5)*.1+(13-box_height)*.02
                if best is None or score<best[0]:best=(score,center,float(bottom),box_height)
                if density==0:return [center,float(bottom),box_height,box_width]
    # In a tightly packed system gap, use nearby whitespace within the same
    # bar instead of painting over original tempo words, notes or lyrics.
    for bottom in np.arange(top+15,min(top+90,top+rect[3]-2),1):
        for fraction in [.5,.32,.68,.2,.8]:
            center=max(left+box_width/2,min(left+width-box_width/2,left+width*fraction))
            patch=ink[round((bottom-13)*2):round(bottom*2),
                      round((center-box_width/2)*2):round((center+box_width/2)*2)]
            if patch.size and not patch.any():return [center,float(bottom),13,box_width]
    for compact_width in [min(26,width-4),min(20,width-4),min(16,width-4)]:
        for compact_height in [10,7]:
            above=np.arange(top-2,max(previous_bottom+compact_height+1,top-65)-.5,-1)
            below=np.arange(top+compact_height+2,min(top+90,top+rect[3]-2),1)
            for bottom in np.r_[above,below]:
                for fraction in [.5,.32,.68,.2,.8]:
                    center=max(left+compact_width/2+1,min(left+width-compact_width/2-1,left+width*fraction))
                    patch=ink[round((bottom-compact_height)*2):round(bottom*2),
                              round((center-compact_width/2)*2):round((center+compact_width/2)*2)]
                    if patch.size and not patch.any():return [center,float(bottom),compact_height,compact_width]
    x0,x1=round((left+1)*2),round((left+width-1)*2)
    y0,y1=round((top+1)*2),round(min(top+160,top+rect[3]-1)*2)
    crop=ink[y0:y1,x0:x1].astype(np.int32)
    integral=np.pad(crop,((1,0),(1,0))).cumsum(0).cumsum(1)
    for compact_width,compact_height in [(26,10),(20,9),(16,7)]:
        W,H=round(compact_width*2),round(compact_height*2)
        if crop.shape[0]<H or crop.shape[1]<W:continue
        sums=integral[H:,W:]-integral[:-H,W:]-integral[H:,:-W]+integral[:-H,:-W]
        rows,columns=np.nonzero(sums==0)
        if len(rows):
            scores=rows+abs(columns-(crop.shape[1]-W)/2)*.1
            i=int(np.argmin(scores))
            return [(x0+columns[i]+W/2)/2,(y0+rows[i]+H)/2,compact_height,compact_width]
    return [best[1],best[2],best[3],box_width] if best else [left+width/2,max(max_height,top-2),max_height,box_width]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,help='Fingerprint-bound cache from map_mahler4_pdf.py')
    args=parser.parse_args()
    mapping=json.loads((DATA/'measure-map.json').read_text(encoding='utf-8'))
    if args.cache is None:
        matches=[p.parent for p in sorted((ROOT/'.tools/mahler4-score').glob('*/inputs.json'))
                 if json.loads(p.read_text(encoding='utf-8')).get('pdf_sha256')==mapping['pdf_sha256']
                 and (p.parent/'metric-alignment.json').exists()]
        if not matches:raise ValueError('请先运行 map_mahler4_pdf.py，建立本版谱面的识图与音符匹配缓存')
        args.cache=matches[-1]
    inputs=json.loads((args.cache/'inputs.json').read_text(encoding='utf-8'))
    with (ROOT/mapping['pdf_path']).open('rb') as stream:pdf_hash=hashlib.file_digest(stream,'sha256').hexdigest()
    if pdf_hash!=mapping['pdf_sha256'] or inputs['pdf_sha256']!=pdf_hash:raise ValueError('识图缓存 PDF 指纹不匹配')
    for item in inputs['midis']:
        with (ROOT/item['path']).open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=item['sha256']:raise ValueError('识图缓存的 MIDI 已变化，请重新处理音符匹配')
    systems,duplicates=unique_systems(json.loads((args.cache/'metric-alignment.json').read_text(encoding='utf-8')))
    parents={r['region_id']:r for r in mapping['score_regions']}
    offsets={};offset=0
    for m in json.loads((DATA/'midi-movements.json').read_text(encoding='utf-8')):
        offsets[len(offsets)+1]=offset;offset+=m['duration_seconds']
    measures=[];landmarks=[];added=[]
    with pdfium.PdfDocument(ROOT/mapping['pdf_path']) as pdf:
        for page_number in sorted({s['page'] for s in systems}):
            page=pdf[page_number-1];width,height=page.get_size()
            array=np.asarray(page.render(scale=2).to_pil().convert('L'))
            page_systems=[s for s in systems if s['page']==page_number]
            landmarks.extend({'page_number':page_number,**m} for m in ocr_landmarks(page,page_systems))
            previous_bottom=0
            for system in page_systems:
                boundaries,votes,staffs,additions=observed_boundaries(array,system)
                parent_id=f"pdf-{page_number:03d}-system-{system['system']}";parent=parents[parent_id]
                added.extend({'page':page_number,'system':system['system'],'x_pt':x/2} for x in additions)
                for i,(left,right) in enumerate(zip(boundaries,boundaries[1:])):
                    source=next((b for b in system['match']['bars'] if b['x0']<=left+8 and b['x1']>=right-8),None)
                    matched=source is not None
                    if source:
                        fraction=lambda x:(x-source['x0'])/(source['x1']-source['x0'])
                        reference=lambda x:source['start']+max(0,min(1,fraction(x)))*(source['end']-source['start'])+offsets[system['movement']]
                        start,end=reference(left),reference(right)
                        original_index=system['match']['bars'].index(source)
                        fine=next((r for r in mapping.get('bar_regions',[]) if r.get('parent_region_id')==parent_id and r['image_bar_index']==original_index),None)
                    else:
                        start=end=None;fine=None
                    geometry_stable=min(votes[i:i+2])>=.85 and staffs>=4
                    region={**parent,'region_id':parent_id+f'-measure-{i}',
                        'parent_region_id':parent_id,'image_bar_index':i,
                        'rect_pt':[left/2,parent['rect_pt'][1],(right-left)/2,parent['rect_pt'][3]],
                        'resolution':'numbered_bar_candidate','printed_measure_number':None,
                        'geometry_status':'cross_staff_supported' if geometry_stable else 'needs_review',
                        'geometry_evidence':{'left_staff_vote':votes[i],'right_staff_vote':votes[i+1],
                            'staff_count':staffs,'double_barlines_count_as_one':True},
                        'midi_start_seconds':start,'midi_end_seconds':end,
                        'timing_method':'existing_note_match' if matched else 'unlocated',
                        'stable_candidate':geometry_stable and bool(fine),
                        'review_status':'unreviewed' if geometry_stable and fine else 'needs_review'}
                    measures.append(region)
                    region['label_position_pt']=label_position(array,region['rect_pt'],previous_bottom)
                    cx,bottom,height,width=region['label_position_pt']
                    patch=array[round((bottom-height)*2):round(bottom*2),round((cx-width/2)*2):round((cx+width/2)*2)]
                    region['label_ink_density']=round(float((patch<185).mean()),4)
                previous_bottom=parent['rect_pt'][1]+parent['rect_pt'][3]
            page.close()
            print(f'Numbering geometry: PDF {page_number}',flush=True)
    result={'format_version':'1.0.0','pdf_sha256':pdf_hash,
        'symbolic_reference_sha256':mapping.get('symbolic_reference_sha256'),
        'timing_source_sha256':timing_source_digest(mapping),
        'geometry_sha256':geometry_digest(measures),'method':'observed_barlines_with_cross_staff_consensus',
        'measures':measures,'landmarks':landmarks,'suppressed_duplicate_systems':duplicates,
        'additional_boundaries':added,
        'limitations':['生成号码是逐乐章识图计数候选，不是识别出的印刷小节号。',
            '弱起、跨行续段、多小节休止与漏检边界需要复核；可设置本框小节数。',
            '排练号与拍号不自动作为小节编号锚点。',
            '时间沿用已有音符匹配候选；编号本身不证明录音时间准确。']}
    result=apply_numbering(result)
    corrections=DATA/'score-measure-corrections.json'
    if corrections.exists():apply_numbering(result,json.loads(corrections.read_text(encoding='utf-8')))
    output=DATA/'score-measures.json';pending=output.with_suffix('.json.tmp')
    pending.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');pending.replace(output)
    report={'pdf_sha256':pdf_hash,'geometry_sha256':result['geometry_sha256'],
        'measures':len(measures),'pages':len({r['page_number'] for r in measures}),
        'movement_counts':dict(Counter(r['movement'] for r in measures)),
        'cross_staff_supported':sum(r['geometry_status']=='cross_staff_supported' for r in measures),
        'stable_timing_candidates':sum(r['stable_candidate'] for r in measures),
        'suppressed_duplicate_systems':duplicates,'additional_boundaries':added,
        'ocr_landmarks':len(landmarks),'trusted_printed_measure_anchors':0,'limitations':result['limitations']}
    report['label_overlap_warnings']=sum(r['label_ink_density']>0 for r in measures)
    report['labels_in_nearby_bar_whitespace']=sum(r['label_position_pt'][1]>r['rect_pt'][1] for r in measures)
    (DATA/'reports/score-measure-numbering.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    project_path=DATA/'project.json'
    if project_path.exists():
        project=json.loads(project_path.read_text(encoding='utf-8'))
        project.setdefault('processing_status',{})['score_measure_numbers']='editable_scan_count_candidates'
        project['score_measure_numbering']={k:report[k] for k in ['measures','pages','movement_counts',
            'stable_timing_candidates','trusted_printed_measure_anchors','label_overlap_warnings']}
        project_path.write_text(json.dumps(project,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
