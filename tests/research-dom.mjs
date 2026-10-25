// Deliberately small in-memory DOM fixture. This is not browser playback QA.
export class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.scrollTop=0;this.hidden=false;this.value='';this.checked=false;this.attributes={};this._text='';this.replacements=0;}
  append(...children){for(const child of children){this.children.push(child);child.parentElement=this;}}
  replaceChildren(...children){this.replacements++;this.children=[];this.append(...children);}
  set textContent(value){this._text=value;}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join(' ');}
  set innerHTML(value){this._text=value;this.children=[];}
  querySelectorAll(){return [];}
  setAttribute(key,value){this.attributes[key]=value;}
}
export function makeDOM(){
  const ids=['structural-hud','hud-position','hud-detail','essay-select','essay-body','essay-follow','research-state'];
  const nodes=new Map(ids.map(id=>[id,new Element()]));
  globalThis.document={getElementById:id=>nodes.get(id),createElement:tag=>new Element(tag)};
  return id=>nodes.get(id);
}
export function fixture(){
  const verify={score:'pending',literature:'abstract_checked',location:'page_range',timing:'candidate_alignment'};
  const span=(a,b=a)=>({pdf_page_start:a,pdf_page_end:b,precision:'page_range'});
  return {available:true,sources:[],events:[
    {id:'a',dimension:'harmony',short_label:'hypothesis A',claim_level:'theoretical_analysis',html:'A',verification:verify,score_spans:[span(1)],related_essay_ids:['essay-a']},
    {id:'b',dimension:'harmony',short_label:'hypothesis B',claim_level:'theoretical_analysis',html:'B',verification:{...verify,score:'disputed'},score_spans:[span(1)]},
    {id:'c',dimension:'orchestration',short_label:'instrument C',claim_level:'score_observation',html:'C',verification:verify,score_spans:[span(1,3)]}],
    essays:[{id:'essay-a',title:'essay A',claim_level:'hermeneutic_interpretation',verification:verify,score_spans:[span(1),span(3),span(8)],html:'long prose A'},
            {id:'essay-b',title:'essay B',claim_level:'hermeneutic_interpretation',verification:verify,score_spans:[span(5)],html:'long prose B'}]};
}
