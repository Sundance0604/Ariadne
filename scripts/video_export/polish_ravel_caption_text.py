"""Polish the current full-length JSON in place; preserve every timing and ID."""
import copy
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.video_export.content import read,write,FORBIDDEN,normalized
from backend.video_export.editor import (COLUMN_NAMES,column_key,document_names,
    normalized_sizes,prepare,stored_column,stored_sizes)
from backend.video_export.subtitles import analysis_ass
from backend.video_export.paths import full_paths

POLISHED={
 'voices-opening':'持续层与流动层\n大提琴以长音托住背景，低音提琴的六连音在其中流动，两种节奏构成不同层次。',
 'development-intro':'引子：材料的依次引入\n低弦先铺开持续与流动交织的背景，低音巴松随后提出旋律，逐层积累的音响为钢琴登场铺垫。',
 'voices-bassoon':'前景中的旋律\n低音巴松的长句在前景中延伸，低弦则在下方保持长音与快速音型。',
 'voices-horn':'两层不同节奏的线条\n圆号以八度加倍，巴松以平行六度推进；先把各自的加倍合为一层，再听两层如何交错。',
 'development-cadenza-1':'首次华彩：独奏展开\n钢琴从乐队中走向前景，在歌唱线条与快速运动之间展开，为乐队重入蓄势。',
 'voices-single-hand-layers':'一只左手，多层声音\n低音、旋律与和弦填充交替出现。',
 'development-five-origin':'华彩上层：D–D–A–C♯–B，先重复，再跳进、回折。',
 'voices-vivo-contrary-lines':'反向行进的外声\nVivo中高低声部走向相反，两条线在听觉上分离。',
 'development-orchestral-return':'乐队重入：分阶段的到达\n乐队接过陈述，和声、低音与音色层次陆续到位，让到达感逐步显现。',
 'voices-five-doubling':'多件乐器以同度或八度加倍，共同强化一条旋律。',
 'development-five-return':'华彩的五音片段上移两个八度，音程与节奏比例保持。',
 'development-lyric':'抒情对比与连接\n长旋律与流动伴奏，舒展了此前厚重的陈述；新的对比也延续着段落之间的联系。',
 'voices-lyrical-poly-meter':'歌唱长句与伴奏短周期\n旋律舒展成长句，快速伴奏维持较短周期；两层的分句与重音并不总是重合。',
 'development-allegro':'快段：对比与展开\n6/8拍、下行和弦型与反复节奏带来鲜明转折，材料在交替、叠合和织体变化中继续发展。',
 'voices-planing-not-counterpoint':'随旋律移动的和弦\n上声部带着和弦块同向下降，内声随之运动，共同加强旋律轮廓。',
 'development-scene-transition':'展开中的织体转折\n高音短句与分解音型重新组合，快段的展开换了一种面貌。',
 'voices-trombone-ostinato':'长线条与反复背景\n长号拉开长线，低弦与打击乐保持反复节奏。',
 'development-development-continuation':'交替与叠合的展开\n长时值线条与反复伴奏时而交替、时而叠合，不同的运动速度维持着展开的张力。',
 'voices-contrary-return':'高低声部分层\n钢琴与低弦以不同节奏推进，分别追踪高低两条线。',
 'development-retransition':'返回前的逐步聚合\n低声部材料、钢琴的音区跳跃与乐队音响渐渐汇合，为后段华彩准备空间。',
 'development-cadenza-2':'后段华彩：多层声音的重组\n钢琴再次交织旋律、低音与快速音型，与首次华彩形成组织方式上的呼应。',
 'voices-cadenza-melody-layer':'跨越音型的旋律\n较长的旋律音贯穿密集伴奏；旋律的分句与伴奏的音型周期各自延续，形成两层时间感。',
 'voices-cadenza-countermelody':'独立低声部的加入\n较慢的低音线另行进入，与上方旋律和快速音型交织，形成更清楚的多层关系。',
 'development-coda':'6/8快板短促回归，音乐迅速收束。',
}


def main():
    package,document_path=full_paths()
    old=json.loads(document_path.read_text(encoding='utf-8-sig'))
    data=copy.deepcopy(old)
    requests=[]
    for index,row in enumerate(old['字幕']):
        text=row.get('文字','')+'\n'+row.get('标题','')
        if column_key(row.get('栏目')) in ['和弦','配器'] and re.search(r'候选|待复核|非实时时点|待核查|待分析',text):
            requests.append({'index':index,'id':row['编号'],'slot':'harmony' if row['栏目']=='和弦' else 'orchestration',
                             'start':row['开始秒'],'end':row['结束秒']})
    facts=[]
    if requests:
        request_file=package/'caption-facts-requests.json'
        fact_file=package/'caption-facts.json'
        write(request_file,requests)
        result=subprocess.run(['node',str(ROOT/'scripts/video_export/ravel_caption_facts.mjs'),
            str(package/'web-text-source.json'),str(request_file),str(fact_file)],
            capture_output=True,encoding='utf-8',errors='replace')
        if result.returncode:raise RuntimeError(result.stderr)
        facts=read(fact_file)
    facts_by_index={f['index']:f for f in facts}
    changes=[]
    for index,row in enumerate(data['字幕']):
        key=column_key(row.get('栏目'))
        if key in COLUMN_NAMES:
            row['栏目']=COLUMN_NAMES[key]
            if row.get('标题') in (key,''):
                row['标题']=COLUMN_NAMES[key]
            if row.get('研究条目') in POLISHED:
                row['文字']=POLISHED[row['研究条目']]
        elif index in facts_by_index:
            row['文字']=facts_by_index[index]['text']
        else:continue
        changes.append({'index':index,'id':row['编号'],
                        'before':{k:old['字幕'][index].get(k) for k in ['栏目','标题','文字']},
                        'after':{k:row.get(k) for k in ['栏目','标题','文字']}})
    names={**document_names(data),**COLUMN_NAMES}
    data['栏目名称']={stored_column(k,names):v for k,v in names.items()}
    data['字号']=stored_sizes(data['字号'],names)
    if len(old['字幕'])!=len(data['字幕']):raise ValueError('Row count changed')
    untouched=0
    for index,(a,b) in enumerate(zip(old['字幕'],data['字幕'])):
        if column_key(a.get('栏目')) not in COLUMN_NAMES and index not in facts_by_index:
            if a!=b:raise ValueError('Unrelated caption changed')
            untouched+=1
        elif {k:v for k,v in a.items() if k not in ['栏目','标题','文字']}!={k:v for k,v in b.items() if k not in ['栏目','标题','文字']}:
            raise ValueError('A timing, ID, visibility or other field changed')
    if normalized_sizes(data['字号'])!=normalized_sizes(old['字号']):raise ValueError('Font size changed')
    for row in data['字幕']:
        if row.get('显示',True) and FORBIDDEN.search(normalized(row.get('文字','')+'\n'+row.get('标题',''))):
            raise ValueError('Unresolved publication wording: '+row['编号'])
    config,events,excluded=prepare(data,package)
    ass=analysis_ass(events,config)
    backup=package/'caption-backups'/('wording-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True)
    for name in [document_path.name,'字幕编辑.json','annotations.json','analysis.ass','export-manifest.json']:
        source=package/name
        if source.exists():shutil.copy2(source,backup/name)
    write(document_path,data)
    write(package/'字幕编辑.json',data)
    write(package/'annotations.json',{'events':events})
    (package/'analysis.ass').write_text(ass,encoding='utf-8-sig')
    manifest=read(package/'export-manifest.json')
    manifest['caption_update']={'status':'wording_and_category_names_updated_video_not_regenerated',
        'editing_document':document_path.name,'changed_columns':list(COLUMN_NAMES.values()),
        'other_wording_columns':sorted({old['字幕'][f['index']]['栏目'] for f in facts}),
        'preserved':['IDs','row order','start/end times and value types','visibility','font sizes','other columns']}
    write(package/'export-manifest.json',manifest)
    report={'status':'updated_no_video_encoded','file':str(document_path),'backup':str(backup),
        'updated_rows':len(changes),'unrelated_rows_unchanged':untouched,
        'research_status_replaced_with_xml_facts':len(facts),
        'timings_ids_order_visibility_unchanged':True,'font_values_unchanged':True,
        'excluded_by_existing_publication_check':excluded,'changes':changes,'fact_evidence':facts}
    write(package/'caption-wording-update-report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['changes','excluded_by_existing_publication_check','fact_evidence']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
