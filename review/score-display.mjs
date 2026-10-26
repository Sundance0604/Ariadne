// Shared display arithmetic only. Timing and region selection stay in their
// existing modules; both the player and offline exporter use these functions.
export function highlightPercent(box){
  const [x,y,w,h]=box.rect_pt;
  return {left:x/box.page_width_pt*100,top:y/box.page_height_pt*100,
    width:w/box.page_width_pt*100,height:h/box.page_height_pt*100};
}

export function revealRegionScroll(pane,target,view){
  let top=pane.top,left=pane.left;
  if(target.top<view.top+12||target.top>view.bottom-60||target.bottom<view.top)
    top+=target.top-view.top-18;
  if(target.right<view.left||target.left>view.right-30)left+=target.left-view.left-18;
  return {top,left};
}

export function measureIndexAt(measures,seconds){
  let lo=0,hi=measures.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(measures[mid].start_seconds<=seconds+.001)lo=mid+1;else hi=mid;}
  return Math.max(0,lo-1);
}
