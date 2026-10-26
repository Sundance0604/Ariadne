import {createStructuralHUD} from './structural-hud.mjs';
import {createHermeneutics} from './hermeneutics.mjs';
import {spanNavigation,referenceTickAt} from './research-model.mjs';
import {createMusicXMLReader} from './musicxml-evidence.mjs';
import {createMusicXMLLive} from './musicxml-live.mjs';

export function createResearchPanel({onNavigate,onSelectTab,getRegions}){
  let version=0,context={},clock=[],referenceHash=null,activeTrack=null;
  const xmlReader=createMusicXMLReader({onNavigate});
  const xmlLive=createMusicXMLLive({onChange:()=>refresh()});
  const essays=createHermeneutics({onNavigate:(span,verification)=>{
    const navigation=spanNavigation(span,verification,getRegions());onNavigate(navigation);
  }});
  const hud=createStructuralHUD({onEssay:id=>{essays.show(id);onSelectTab('research');},onOpen:()=>onSelectTab('evidence'),
    onMeasure:(id,selection)=>xmlReader.showMeasure(id,selection),
    onNote:(id,measureId)=>xmlReader.showMeasure(id.match(/xml-m\d+/)?.[0]||measureId,{noteId:id}),
    onEvidence:async id=>{
    const expected=version,track=activeTrack;
    const response=await fetch(`/api/structure-evidence?track=${encodeURIComponent(track)}&event_id=${encodeURIComponent(id)}`,{cache:'no-store'});
    const data=await response.json();if(expected!==version)return null;
    if(!response.ok)throw Error(data.error||'证据读取失败');return data;
  }});
  function augmented(next){return {...next,referenceTick:referenceTickAt(clock,next.referenceSeconds),referenceSha256:referenceHash};}
  function refresh(){hud.update(augmented(context),xmlLive.at(context.referenceSeconds));}
  function reset(){version++;context={};clock=[];referenceHash=null;activeTrack=null;hud.reset();essays.reset();xmlReader.reset();xmlLive.reset();}
  return {reset,update(next){context=next;refresh();essays.update(next);},async load(track,pdfHash){
    reset();const current=version;
    try{
      const response=await fetch(`/api/research?track=${encodeURIComponent(track)}`,{cache:'no-store'}),data=await response.json();
      if(current!==version)return;
      if(!response.ok)throw Error(data.error||'读取失败');
      if(data.available&&data.edition.pdf_sha256!==pdfHash)throw Error('研究版次与当前谱面不同');
      activeTrack=track;clock=data.reference_clock||[];referenceHash=data.engine?.reference_sha256||null;
      hud.load(data);essays.load(data);xmlReader.load(data,track);refresh();essays.update(context);
      if(data.musicxml)xmlLive.load(track);
    }catch(error){if(current===version){hud.reset();essays.error(error.message);}}
  }};
}
