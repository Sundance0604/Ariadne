// One controller owns both elements. Public time is always the alignment clock.
export function validateAnchors(anchors, masterDuration=Infinity, videoDuration=Infinity) {
  if(!Array.isArray(anchors)||anchors.length<2)throw Error('至少需要两个音画锚点');
  let previous=[-1,-1];
  for(const anchor of anchors){
    const {masterTime:m,videoTime:v}=anchor;
    if(!Number.isFinite(m)||!Number.isFinite(v)||m<0||v<0||m>masterDuration||v>videoDuration||m<=previous[0]||v<=previous[1])
      throw Error('音画锚点必须在两条时间轴内严格递增');
    previous=[m,v];
  }
  return anchors;
}

export function mapTime(anchors,time,inverse=false){
  if(!Number.isFinite(time)||anchors.length<2)return null;
  const x=inverse?'videoTime':'masterTime',y=inverse?'masterTime':'videoTime';
  if(time<anchors[0][x]||time>anchors.at(-1)[x])return null;
  let low=0,high=anchors.length-1;
  while(high-low>1){const mid=(low+high)>>1;if(anchors[mid][x]<=time)low=mid;else high=mid;}
  const a=anchors[low],b=anchors[high];
  return a[y]+(time-a[x])/(b[x]-a[x])*(b[y]-a[y]);
}

export class PlaybackController extends EventTarget {
  constructor(audio,video,onMessage=()=>{}){
    super();this.audio=audio;this.video=video;this.master=audio;this.onMessage=onMessage;
    this.media=null;this.rate=1;this.loop=null;this.lastCorrection=-Infinity;this.generation=0;
    for(const element of [audio,video]){
      for(const name of ['timeupdate','play','pause','ended','seeking','seeked','loadedmetadata','durationchange']){
        element.addEventListener(name,()=>{
          if(element!==this.master)return;
          if(name==='play')this.startSlave();
          if(['pause','ended','seeking'].includes(name))this.slave?.pause();
          if(name==='seeked'){this.syncSlave(true);if(!this.paused)this.startSlave();}
          this.emit(name);
        });
      }
      element.addEventListener('error',()=>{if(element.getAttribute('src')){this.pause();this.onMessage('媒体无法播放，请检查本地文件及浏览器编码支持。');}});
      element.addEventListener('waiting',()=>{
        if(element===this.master)this.slave?.pause();
        this.onMessage('正在缓冲媒体…');
      });
      element.addEventListener('canplay',()=>{if(element===this.master&&!this.paused)this.startSlave();});
    }
  }
  emit(name){this.dispatchEvent(new Event(name));this['on'+name]?.();}
  get slave(){return this.dual&&this.master===this.audio?this.video:null;}
  get dual(){return Boolean(this.media?.masterClock==='audio'&&this.media?.video);}
  get anchors(){return this.media?.anchors||[];}
  get currentTime(){return this.dual&&this.master===this.video?(mapTime(this.anchors,this.video.currentTime,true)??this.lastTime??0):this.master.currentTime;}
  set currentTime(value){
    if(!Number.isFinite(value))return;
    value=Math.max(0,Math.min(this.duration||Infinity,value));
    const mapped=this.dual&&this.master===this.video?mapTime(this.anchors,value):value;
    if(mapped===null){this.onMessage('当前位置超出已核验的音画区间，请切回音频。');return;}
    this.lastTime=value;this.master.currentTime=mapped;this.syncSlave(true);
  }
  get duration(){return this.timelineDuration||this.master.duration||0;}
  get paused(){return this.master.paused;}
  get ended(){return this.master.ended;}
  get playbackRate(){return this.rate;}
  set playbackRate(value){this.rate=value;this.audio.playbackRate=value;this.video.playbackRate=this.videoRate(value);}
  videoRate(value){
    if(!this.dual||this.master!==this.audio)return value;
    const time=this.currentTime,a=this.anchors;
    const i=a.findIndex((p,index)=>index<a.length-1&&p.masterTime<=time&&time<=a[index+1].masterTime);
    return i<0?value:Math.max(.1,Math.min(4,value*(a[i+1].videoTime-a[i].videoTime)/(a[i+1].masterTime-a[i].masterTime)));
  }
  get volume(){return this.master.volume;}
  set volume(value){this.audio.volume=value;this.video.volume=value;}
  configure(media,urls,duration){
    this.reset();this.media=media;this.timelineDuration=duration;this.master=media?.masterClock==='video'?this.video:this.audio;
    if(this.dual){
      try{
        validateAnchors(this.anchors,duration,media.video.duration_seconds);
        if(!['same_performance_reviewed','matched_same_recording','manual_reviewed'].includes(media.matchStatus))throw Error('尚未确认同一演出，音画同步已停用');
        this.dualReady=true;
      }catch(error){this.dualReady=false;this.onMessage(error.message);}
    }
    if(this.master===this.audio)this.audio.src=urls.audio;
    if(media?.video)this.video.src=urls.video;
    this.audio.muted=this.master!==this.audio;this.video.muted=this.master!==this.video;
    this.master.load();if(this.slave)this.video.load();this.playbackRate=this.rate;
  }
  reset(){
    this.generation++;this.audio.pause();this.video.pause();
    for(const element of [this.audio,this.video]){element.removeAttribute('src');element.load();}
    this.loop=null;this.media=null;this.dualReady=false;this.timelineDuration=0;this.lastTime=0;this.lastCorrection=-Infinity;
  }
  async play(){
    const version=this.generation;
    try{await this.master.play();}catch(error){if(version===this.generation){this.pause();this.onMessage('播放未开始，请点击播放重试：'+error.message);}}
  }
  pause(){this.audio.pause();this.video.pause();}
  async startSlave(){
    if(!this.slave||!this.dualReady)return;
    if(this.syncSlave(true)===false)return;
    const version=this.generation;
    try{await this.slave.play();}
    catch{if(version===this.generation)this.onMessage('静音视频未开始，点击播放重试。');}
  }
  syncSlave(force=false){
    const slave=this.slave;
    if(!slave||!this.dualReady)return false;
    slave.muted=true;
    const target=mapTime(this.anchors,this.currentTime);
    if(target===null){slave.pause();this.onMessage('超出音画锚点覆盖区间，视频已暂停；音频继续。');return false;}
    const drift=target-slave.currentTime,now=performance.now();
    if(force){slave.currentTime=target;this.lastCorrection=now;}
    else if(Math.abs(drift)>2){slave.pause();this.onMessage('音画偏移超过 2 秒，请暂停并检查锚点或重新跳转。');return false;}
    else if(Math.abs(drift)>.4&&now-this.lastCorrection>2500){slave.currentTime=target;this.lastCorrection=now;}
    slave.playbackRate=Math.max(.1,Math.min(4,this.videoRate(this.rate)+(force?0:Math.max(-.04,Math.min(.04,drift*.06)))));
    return true;
  }
  async selectSource(kind){
    const next=kind==='video'?this.video:this.audio;
    if(next===this.master)return true;
    if(!this.dual||!this.dualReady){this.onMessage('缺少经核验的音画映射，不能切换音源。');return false;}
    const time=this.currentTime;
    if(mapTime(this.anchors,time)===null){this.onMessage('当前位置不在已核验的音画区间内');return false;}
    const playing=!this.paused;this.pause();this.master=next;
    this.audio.muted=next!==this.audio;this.video.muted=next!==this.video;
    this.currentTime=time;this.playbackRate=this.rate;if(playing)await this.play();this.emit('timeupdate');return true;
  }
  tick(){
    const time=this.currentTime;this.lastTime=time;
    if(this.loop&&time>=this.loop[1])this.currentTime=this.loop[0];
    this.syncSlave();
    if(this.dual&&this.master===this.video&&mapTime(this.anchors,this.video.currentTime,true)===null){this.pause();this.onMessage('已到音画映射边界，请切回音频。');}
  }
  setLoop(start,end){
    if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start||end>this.duration)throw Error('循环起止时间无效');
    this.loop=[start,end];
  }
}
