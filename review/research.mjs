import {createStructuralHUD} from './structural-hud.mjs';
import {createHermeneutics} from './hermeneutics.mjs';
import {spanNavigation} from './research-model.mjs';

export function createResearchPanel({onNavigate,onSelectTab,getRegions}){
  let version=0,context={};
  const essays=createHermeneutics({onNavigate:(span,verification)=>{
    const navigation=spanNavigation(span,verification,getRegions());onNavigate(navigation);
  }});
  const hud=createStructuralHUD({onEssay:id=>{essays.show(id);onSelectTab('research');}});
  function reset(){version++;context={};hud.reset();essays.reset();}
  return {reset,update(next){context=next;hud.update(next);essays.update(next);},async load(track,pdfHash){
    reset();const current=version;
    try{
      const response=await fetch(`/api/research?track=${encodeURIComponent(track)}`,{cache:'no-store'}),data=await response.json();
      if(current!==version)return;
      if(!response.ok)throw Error(data.error||'读取失败');
      if(data.available&&data.edition.pdf_sha256!==pdfHash)throw Error('研究版次与当前谱面不同');
      hud.load(data);essays.load(data);hud.update(context);essays.update(context);
    }catch(error){if(current===version){hud.reset();essays.error(error.message);}}
  }};
}
