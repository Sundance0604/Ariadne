"""Locate bars in the supplied vector PDF; this is geometry extraction, not OMR."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import pdfplumber

ROOT=Path(__file__).resolve().parents[1]


def merged(intervals,gap=.8):
    result=[]
    for start,end in sorted(intervals):
        if result and start<=result[-1][1]+gap:
            result[-1][1]=max(result[-1][1],end)
        else: result.append([start,end])
    return result


def extract_page(page,number):
    horizontal=[l for l in page.lines if l['height']<.05 and l['width']>100]
    if not horizontal: return [],[{'page':number,'reason':'no_long_staff_lines'}]
    # Hairpins can extend left of the staves. Select the predominant staff-line
    # stroke width instead of treating every long horizontal mark as a staff.
    stroke=Counter(round(l.get('linewidth',0),3) for l in horizontal).most_common(1)[0][0]
    horizontal=[l for l in horizontal if abs(l.get('linewidth',0)-stroke)<.002]
    starts=Counter(round(l['x0'],2) for l in horizontal)
    most=max(starts.values())
    left=min(x for x,count in starts.items() if count>=most*.8)
    right=max(l['x1'] for l in horizontal)
    vertical=[l for l in page.lines if l['width']<.05 and l['height']>10
              and .6<=l.get('linewidth',0)<=3]
    systems=merged([(l['top'],l['bottom']) for l in vertical if abs(l['x0']-left)<.8])
    systems=[(t,b) for t,b in systems if b-t>30]
    words=page.extract_words()
    output,issues=[],[]
    for system_index,(top,bottom) in enumerate(systems):
        system_staff=[l for l in horizontal if top-1<=l['top']<=bottom+1]
        system_right=max(l['x1'] for l in system_staff)
        groups=defaultdict(list)
        for line in vertical:
            if line['top']>=top-1 and line['bottom']<=bottom+1:
                groups[round(line['x0'],1)].append((line['top'],line['bottom']))
        candidates=[]
        for x,intervals in groups.items():
            length=sum(b-t for t,b in merged(intervals))
            if length>(bottom-top)*.35:
                candidates.append(x)
        # Double/final bars are one boundary, not additional measures.
        boundaries=[]
        for x in sorted(candidates):
            if boundaries and x-boundaries[-1][-1]<5:
                boundaries[-1].append(x)
            else: boundaries.append([x])
        xs=[sum(group)/len(group) for group in boundaries]
        labels=[w for w in words if w['text'].isdigit() and
                abs(w['x0']-left)<5 and top-30<w['top']<top-3]
        if number==1 and system_index==0:
            printed_start=1
        elif len(labels)==1:
            printed_start=int(labels[0]['text'])
        else:
            printed_start=None
            issues.append({'page':number,'system':system_index,'reason':'ambiguous_system_start_number',
                           'candidates':[w['text'] for w in labels]})
        if not xs or abs(xs[0]-left)>2:
            issues.append({'page':number,'system':system_index,'reason':'boundary_extent_mismatch','xs':xs})
        output.append({'page_number':number,'system_index':system_index,
            'top':top,'bottom':bottom,'left':left,'right':system_right,
            'page_width':page.width,'page_height':page.height,
            'printed_start_measure':printed_start,'boundaries':xs})
    return output,issues


def main():
    pdf=next(p for p in (ROOT/'resource').rglob('*.pdf') if not p.name.startswith('IMSLP'))
    systems,issues=[],[]
    with pdfplumber.open(pdf) as document:
        for index,page in enumerate(document.pages):
            found,errors=extract_page(page,index+1)
            systems.extend(found); issues.extend(errors)
            if (index+1)%10==0: print(f'Mapped {index+1} pages',flush=True)
    measures=[]
    for i,system in enumerate(systems):
        count=len(system['boundaries'])-1
        start=system['printed_start_measure']
        next_start=systems[i+1]['printed_start_measure'] if i+1<len(systems) else None
        # Courtesy clefs and key signatures can extend beyond a final barline.
        # Append an unbarred system end only when the next printed number also
        # requires more bars; otherwise this space must not become a fake bar.
        if (start is not None and next_start is not None and next_start-start>count
                and system['right']-system['boundaries'][-1]>5):
            system['boundaries'].append(system['right'])
            count+=1
        if start is not None and next_start is not None and next_start-start!=count:
            issues.append({'page':system['page_number'],'system':system['system_index'],
                'reason':'barline_count_does_not_match_next_printed_number',
                'printed_start':start,'next_start':next_start,'bar_count':count})
        if start is None: continue
        for offset,(x0,x1) in enumerate(zip(system['boundaries'],system['boundaries'][1:])):
            n=start+offset
            spans=[n]
            # Visual inspection of page 10 found one unbarred cadenza region.
            # MIDI bars 33-36 share this box; never invent equal-width PDF bars.
            grouped=system['page_number']==10 and n==33 and count==2
            if grouped: spans=list(range(33,37))
            for mapped_number in spans:
                raw_rect=[x0,system['top'],x1-x0,system['bottom']-system['top']]
                clipped_bottom=min(system['bottom'],system['page_height'])
                clipped_top=max(0,system['top'])
                measures.append({'measure_id':f'midi-m{mapped_number:04d}',
                'printed_measure_number':None if grouped else str(n),
                'candidate_sequence_number':mapped_number,
                'page_number':system['page_number'],'system_index':system['system_index'],
                'rect_pt':[x0,clipped_top,x1-x0,clipped_bottom-clipped_top],
                'source_rect_pt':raw_rect,
                'geometry_clipped_to_page':clipped_bottom!=system['bottom'] or clipped_top!=system['top'],
                'page_width_pt':system['page_width'],'page_height_pt':system['page_height'],
                'coordinate_origin':'top_left','review_status':'unreviewed',
                'resolution':'candidate_cadenza_group_33_36' if grouped else 'bar',
                'method':'vector_barlines_and_printed_system_number',
                'score_event_correspondence':'midi_bar_number_candidate_not_note_verified'})
    with pdf.open('rb') as stream: fingerprint=hashlib.file_digest(stream,'sha256').hexdigest()
    result={'format_version':'1.0.0','pdf_path':pdf.relative_to(ROOT).as_posix(),
        'pdf_sha256':fingerprint,'is_omr':False,'systems':systems,'measures':measures,'issues':issues,
        'limitations':['Geometry and printed numbering do not establish note-level MIDI/PDF equivalence.',
            'Only the supplied vector PDF is supported; scanned PDF needs a separate mapping.']}
    output=ROOT/'measure-map.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(systems)} systems; {len(measures)} bars; {len(issues)} issues',flush=True)


if __name__=='__main__': main()
