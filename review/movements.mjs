// Movement identity comes from the alignment; never divide the duration evenly.
export function movementChapters(alignment,mapping){
  const groups=new Map();
  for(const measure of alignment.measures||[]){
    if(!Number.isFinite(measure.movement))continue;
    if(!groups.has(measure.movement))groups.set(measure.movement,[]);
    groups.get(measure.movement).push(measure);
  }
  if(groups.size<2)return [];
  return [...groups].sort(([a],[b])=>a-b).map(([movement,measures])=>{
    const meta=(mapping.movements||[]).find(m=>m.movement===movement);
    const page=meta?.first_pdf_page??(mapping.score_regions||[]).find(r=>r.movement===movement)?.page_number;
    return {movement,title:meta?.title||`第 ${movement} 乐章`,first_pdf_page:page,
      start_seconds:Math.min(...measures.map(m=>m.start_seconds))};
  }).filter(item=>Number.isFinite(item.start_seconds)&&Number.isFinite(item.first_pdf_page));
}

export function chapterAtTime(chapters,time){
  return [...chapters].reverse().find(item=>time>=item.start_seconds);
}
