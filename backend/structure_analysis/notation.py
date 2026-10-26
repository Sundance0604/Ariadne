"""Small notation rules, independent of MIDI pitches or musicological claims."""

OCTAVES={0xE510:1,0xE511:1,0xE512:1,0xE513:1,0xE514:2,0xE515:2,
         0xE516:2,0xE517:3,0xE518:3,0xE519:3,0xE51C:1,0xE51D:2,0xE51E:3}
BASSA={0xE512,0xE513,0xE516,0xE519,0xE51C,0xE51D,0xE51E}
ALTA={0xE511,0xE515,0xE518}


def octave_assignment(character,characters,staves):
    code=character['code']
    if code not in OCTAVES:return None
    suffix=''.join(c['text'] for c in sorted(characters,key=lambda c:c['x'])
        if character['x']<c['x']<character['x']+18 and abs(c['y']-character['y'])<3
        and c['text'].isascii() and c['text'].isalpha()).lower()
    down=code in BASSA or suffix in {'b','ba','vb','bassa'}
    up=code in ALTA or suffix in {'va','ma'}
    eligible=([s for s in staves if s['lines_pt'][-1]<character['y']] if down else
              [s for s in staves if s['lines_pt'][0]>character['y']] if up else staves)
    staff=min(eligible or staves,key=lambda s:min(abs(character['y']-y) for y in s['lines_pt']))
    direction=-1 if down else 1 if up else -1 if character['y']>staff['lines_pt'][-1] else 1
    return {'staff':staff,'suffix':suffix,'octave_count':OCTAVES[code],
            'direction':direction,'assignment_status':'explicit_suffix_staff_side_candidate' if down or up else 'staff_side_candidate'}


def octave_for_head(head,staff,marks,lines,spacing):
    candidates=[]
    for mark in marks:
        if mark.get('kind')!='octave_sign' or mark['staff_id']!=staff['id'] or not mark.get('octave_count'):continue
        dashed=[l for l in lines if l.get('dash',([],0))[0] and l['height']<.1
            and abs(l['top']-mark['y_pt'])<6 and 0<=l['x0']-mark['x_pt']<20]
        extended=any(mark['x_pt']-spacing*.5<=head['x']<=l['x1']+.2 for l in dashed)
        # Without a continuation line, restrict to the adjacent note/chord.
        # Do not extend a bare sign to all remaining notes or to a new system.
        isolated=not dashed and abs(head['x']-mark['x_pt'])<=spacing*2
        if extended or isolated:
            candidates.append((mark['x_pt'],mark['direction']*12*mark['octave_count'],mark['id'],
                'dashed_line_candidate' if extended else 'isolated_chord_candidate'))
    if not candidates:return 0,[],None
    _,shift,id,basis=max(candidates)
    return shift,[id],basis


def barline_positions(lines,staff_lines):
    # Supplied edition: stems are about .405pt, barlines .8pt. Overlap
    # with all five lines alone does not distinguish a long stem from a bar.
    spacing=(staff_lines[-1]-staff_lines[0])/4
    return sorted({round(l['x0'],2) for l in lines if l['width']<.05 and l.get('linewidth',0)>=.6
        and l['height']>=spacing*3.8 and l['top']<=staff_lines[0]+1 and l['bottom']>=staff_lines[-1]-1})


def tremolo_bridges(page,heads,staves,lines,curves):
    """Half-note heads linked by multiple beam polygons, not fast black notes."""
    output=[]
    for staff in staves:
        spacing=(staff['lines_pt'][-1]-staff['lines_pt'][0])/4
        white=[h for h in heads if h['staff_id']==staff['id'] and h['head_class']=='half']
        stems=[l for l in lines if l['width']<.05 and .3<l.get('linewidth',0)<.6 and l['height']>spacing*2]
        groups={}
        for head in white:
            related=[s for s in stems if s['top']-.8<=head['y_pt']<=s['bottom']+.8 and
                min(abs(s['x0']-head['x_pt']),abs(s['x0']-head['x_pt']-head['rect_pt'][2]))<.8]
            if not related:continue
            stem=min(related,key=lambda s:min(abs(s['x0']-head['x_pt']),abs(s['x0']-head['x_pt']-head['rect_pt'][2])))
            key=(round(stem['x0'],2),round(stem['top'],2),round(stem['bottom'],2))
            groups.setdefault(key,[]).append(head)
        ordered=sorted(groups)
        for left,right in zip(ordered,ordered[1:]):
            if not spacing*3<right[0]-left[0]<spacing*50:continue
            polygons=[c for c in curves if c.get('fill') and not c.get('stroke') and len(c.get('pts',[]))>=4
                and abs(c['x0']-left[0])<spacing*2 and abs(c['x1']-right[0])<spacing*2
                and c['height']<spacing*3 and min(left[1],right[1])-spacing<c['top']<min(left[1],right[1])+spacing*4]
            if len(polygons)<2:continue
            a,b=groups[left],groups[right]
            candidates=sorted(set(a[0]['midi_measure_candidates'])&set(b[0]['midi_measure_candidates']))
            if not candidates:continue
            output.append({'id':f'pdf-tremolo-{page}-{len(output):03d}','kind':'two_note_tremolo_candidate',
                'value':f'{len(polygons)}-beam tremolo candidate','page':page,'part_id':staff['part_id'],
                'staff_id':staff['id'],'physical_system_index':staff['physical_system_index'],
                'x_pt':min(h['x_pt'] for h in a),'y_pt':min(c['top'] for c in polygons),
                'left_head_ids':[h['id'] for h in a],'right_head_ids':[h['id'] for h in b],
                'left_pitches':sorted({h['concert_pitch_candidate'] for h in a}),
                'right_pitches':sorted({h['concert_pitch_candidate'] for h in b}),
                'midi_measure_candidates':candidates,'beam_polygons_pt':[c['pts'] for c in polygons],
                'assignment_status':'half_heads_and_multiple_native_beam_polygons_candidate'})
    return output


def alternating_runs(notes,left,right):
    groups={}
    for n in notes:groups.setdefault(n['start_tick'],[]).append(n)
    found=[];run=[];last=None
    for tick,values in sorted(groups.items()):
        pitches={n['pitch'] for n in values}
        side=0 if pitches==set(left) else 1 if pitches==set(right) else None
        if side is None or side==last:
            if len(run)>=4:found.append([n for values in run for n in values])
            run=[];last=None
        if side is not None:run.append(values);last=side
    if len(run)>=4:found.append([n for values in run for n in values])
    return found


def single_tremolo_marks(page,heads,staves,lines,curves):
    output=[]
    for staff in staves:
        spacing=(staff['lines_pt'][-1]-staff['lines_pt'][0])/4
        local=[h for h in heads if h['staff_id']==staff['id']]
        for stem in lines:
            if not (stem['width']<.05 and .3<stem.get('linewidth',0)<.6 and stem['height']>spacing*2):continue
            slashes=[c for c in curves if c.get('fill') and not c.get('stroke') and len(c.get('pts',[]))==5
                and spacing*.7<c['width']<spacing*2.5 and c['x0']+spacing*.2<stem['x0']<c['x1']-spacing*.2
                and stem['top']<=c['top'] and c['bottom']<=stem['bottom']]
            if len(slashes)<2:continue
            associated=[h for h in local if stem['top']-.8<=h['y_pt']<=stem['bottom']+.8
                and min(abs(stem['x0']-h['x_pt']),abs(stem['x0']-h['x_pt']-h['rect_pt'][2]))<.8]
            if not associated:continue
            output.append({'id':f'pdf-single-tremolo-{page}-{len(output):03d}','kind':'single_chord_tremolo_candidate',
                'value':f'{len(slashes)}-stroke stem tremolo candidate','page':page,'part_id':staff['part_id'],
                'staff_id':staff['id'],'physical_system_index':staff['physical_system_index'],
                'x_pt':min(h['x_pt'] for h in associated),'y_pt':min(c['top'] for c in slashes),
                'head_ids':[h['id'] for h in associated],'pitches':sorted({h['concert_pitch_candidate'] for h in associated}),
                'midi_measure_candidates':associated[0]['midi_measure_candidates'],
                'beam_polygons_pt':[c['pts'] for c in slashes],'assignment_status':'multiple_native_slashes_cross_attached_stem_candidate'})
    return output
