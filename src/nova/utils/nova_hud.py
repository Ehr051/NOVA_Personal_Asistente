"""
nova_hud.py — NOVA HUD v10.0
Temas: NEURAL · PLASMA · TORMENTA

Diseño:
  • Modo compacto  (default): solo la animación + tira toggle ▾
  • Modo expandido: animación + log de conversación + campo de texto
  • "Salir" → suspende (ASLEEP). Click en HUD o escribir despierta.
  • Botón × en el panel expandido para cerrar de verdad.
"""

import queue, sys
from PyQt5.QtCore    import Qt, QTimer, QPoint
from PyQt5.QtWidgets import (QApplication, QWidget, QLineEdit, QPushButton,
                             QTextEdit, QLabel)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtGui     import QColor, QTextCursor

# ─── Dimensiones base (escala 1.0) ──────────────────────────────────────────
W_BASE       = 280
H_ANIM_BASE  = 320
H_METRICS    = 30
H_STRIP      = 18
H_LOG_MIN    = 80
H_LOG_MAX    = 500
H_LOG_BASE   = 168
H_INPUT_BASE = 32

# Pasos de escala disponibles (scroll wheel)
_SCALE_STEPS = [0.65, 0.80, 1.0, 1.20, 1.40]

# Calculados en tiempo de ejecución según escala activa (ver _apply_scale)
W         = W_BASE
H_ANIM    = H_ANIM_BASE
H_COMPACT = H_ANIM_BASE + H_METRICS + H_STRIP
H_LOG     = H_LOG_BASE
H_INPUT   = H_INPUT_BASE
H_PANEL   = H_LOG_BASE + 6 + H_INPUT_BASE + 8
H_FULL    = H_COMPACT + H_PANEL

THEME_NAMES = ["NEURAL", "PLASMA", "TORMENTA"]

# ─── HTML / animación (sin cambios) ─────────────────────────────────────────
_HUD_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
*{margin:0;padding:0;}
html,body{width:280px;height:320px;background:transparent;overflow:hidden;}
#wrap{position:relative;width:280px;height:320px;transform-origin:140px 160px;will-change:transform;}
canvas{position:absolute;top:0;left:0;}
#cB{filter:blur(16px) brightness(3.2) saturate(2.2);opacity:.70;}
</style>
</head><body><div id="wrap">
  <canvas id="cB" width="280" height="320"></canvas>
  <canvas id="cS" width="280" height="320"></canvas>
</div><script>
'use strict';
const W=280,H=320,CX=140,CY=155;
let status='IDLE',themeIdx=0,t=0,colorT=1,isDragging=false;
const COLORS={IDLE:{r:20,g:160,b:220},LISTENING:{r:10,g:230,b:90},THINKING:{r:255,g:130,b:0},SPEAKING:{r:50,g:200,b:255},ASLEEP:{r:80,g:90,b:100}};
let cur={...COLORS.IDLE},prev={...COLORS.IDLE},tgt={...COLORS.IDLE};
const lerp=(a,b,f)=>a+(b-a)*f;
const lerpC=(a,b,f)=>({r:lerp(a.r,b.r,f),g:lerp(a.g,b.g,f),b:lerp(a.b,b.b,f)});
const css=(c,a)=>`rgba(${c.r|0},${c.g|0},${c.b|0},${a.toFixed(3)})`;
const W255={r:255,g:255,b:255};
const clamp=(v,a,b)=>v<a?a:v>b?b:v;
function glow(ctx,x,y,r,c,a){
  const g=ctx.createRadialGradient(x,y,0,x,y,r);
  g.addColorStop(0,css(c,a));g.addColorStop(.45,css(c,a*.18));g.addColorStop(1,css(c,0));
  ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();
}
const sm=()=>({IDLE:1,LISTENING:1.9,THINKING:3.0,SPEAKING:1.6,ASLEEP:0.2}[status]||1);
const im=()=>({IDLE:.50,LISTENING:.88,THINKING:.96,SPEAKING:.80,ASLEEP:0.15}[status]||.50);
window.setStatus=s=>{s=s.toUpperCase();if(s===status)return;prev={...cur};tgt=COLORS[s]||COLORS.IDLE;colorT=0;status=s;};
window.setTheme=i=>{themeIdx=((i%6)+6)%6;};
window.nextTheme=()=>{themeIdx=(themeIdx+1)%6;};
window.setDragging=d=>{
  isDragging=d;
  const w=document.getElementById('wrap');
  w.style.transition=d?'transform .08s ease':'transform .6s cubic-bezier(.34,1.56,.64,1)';
  w.style.transform=d?'scale(0.91)':'scale(1)';
};
window.onDragMove=vx=>{
  if(!isDragging)return;
  const tilt=clamp(vx*.9,-9,9);
  const w=document.getElementById('wrap');
  w.style.transition='transform .05s ease';
  w.style.transform=`rotate(${tilt}deg) scale(0.91)`;
};
const bC=document.getElementById('cB').getContext('2d');
const sC=document.getElementById('cS').getContext('2d');
// ── NEURAL ──────────────────────────────────────────────────────────────────
const NP=180;
const np=Array.from({length:NP},()=>({
  x:CX+(Math.random()-.5)*230, y:CY+(Math.random()-.5)*245,
  vx:(Math.random()-.5)*1.2, vy:(Math.random()-.5)*1.2,
  sz:.6+Math.random()*2.4, ph:Math.random()*Math.PI*2, phd:.007+Math.random()*.024,
  active:0,
}));
const npulses=[];
function updateNeural(){
  const speed=sm(),CONN=status==='THINKING'?78:status==='LISTENING'?105:92;
  np.forEach(p=>{
    p.ph+=p.phd*speed; if(p.active>0)p.active--;
    p.x+=p.vx*speed; p.y+=p.vy*speed;
    const dx=CX-p.x,dy=CY-p.y,dist=Math.hypot(dx,dy);
    if(dist>128){p.vx+=dx*.002*speed;p.vy+=dy*.002*speed;}
    p.vx+=(Math.random()-.5)*.08*speed; p.vy+=(Math.random()-.5)*.08*speed;
    const spd=Math.hypot(p.vx,p.vy);
    if(spd>3*speed){p.vx=p.vx/spd*3*speed;p.vy=p.vy/spd*3*speed;}
  });
  const spawnRate=status==='THINKING'?.80:status==='SPEAKING'?.60:status==='LISTENING'?.50:.28;
  if(t%10===0&&Math.random()<spawnRate){
    let best=null,bd=1e9;
    for(let i=0;i<NP;i+=2)for(let j=i+3;j<NP;j+=2){
      const d=Math.hypot(np[i].x-np[j].x,np[i].y-np[j].y);
      if(d<CONN&&d>18&&d<bd){bd=d;best=[i,j];}
    }
    if(best){
      const[a,b]=best;
      npulses.push({x1:np[a].x,y1:np[a].y,x2:np[b].x,y2:np[b].y,p:0,max:16+Math.random()*22,ia:a,ib:b});
    }
  }
}
function drawNeural(ctx,r,c,bloom){
  const CONN=status==='THINKING'?78:status==='LISTENING'?105:92;
  const I=im();
  if(!bloom){
    for(let i=0;i<NP;i++)for(let j=i+1;j<NP;j++){
      const dx=np[i].x-np[j].x,dy=np[i].y-np[j].y,d2=dx*dx+dy*dy;
      if(d2>CONN*CONN)continue;
      const al=(1-Math.sqrt(d2)/CONN)*I*.32*(np[i].active>0||np[j].active>0?2.5:1);
      ctx.beginPath();ctx.moveTo(np[i].x,np[i].y);ctx.lineTo(np[j].x,np[j].y);
      ctx.strokeStyle=css(c,clamp(al,0,.85));ctx.lineWidth=.55+(np[i].active>0?.6:0);ctx.stroke();
    }
  }
  for(let i=npulses.length-1;i>=0;i--){
    const p=npulses[i];p.p++;
    if(p.p>=p.max){npulses.splice(i,1);continue;}
    const pct=p.p/p.max,fade=1-pct;
    p.x1=np[p.ia].x;p.y1=np[p.ia].y;p.x2=np[p.ib].x;p.y2=np[p.ib].y;
    const px=p.x1+(p.x2-p.x1)*pct,py=p.y1+(p.y2-p.y1)*pct;
    if(bloom){glow(ctx,px,py,14,W255,.55*fade);}
    else{
      ctx.beginPath();ctx.moveTo(p.x1,p.y1);ctx.lineTo(px,py);
      ctx.strokeStyle=css(W255,.75*fade);ctx.lineWidth=1.5;ctx.stroke();
      ctx.beginPath();ctx.arc(px,py,3.8,0,Math.PI*2);
      ctx.fillStyle=css(W255,.95*fade);ctx.fill();
      if(pct>.95)np[p.ib].active=12;
    }
  }
  np.forEach(p=>{
    const pulse=.45+.55*(.5+.5*Math.sin(p.ph)),boost=p.active>0?1.8:1;
    if(bloom)glow(ctx,p.x,p.y,p.sz*5,p.active>0?W255:c,pulse*.28*I*boost);
    else{
      ctx.beginPath();ctx.arc(p.x,p.y,p.sz*(p.active>0?1.6:1),0,Math.PI*2);
      ctx.fillStyle=css(p.active>0?W255:c,(.35+.45*pulse)*I*boost);ctx.fill();
    }
  });
  if(status==='LISTENING'){
    const ri=((t*.016)%1),ri2=((t*.016+.5)%1);
    [ri,ri2].forEach(rv=>{
      ctx.beginPath();ctx.arc(CX,CY,rv*138,0,Math.PI*2);
      ctx.strokeStyle=css(c,(1-rv)*.22);ctx.lineWidth=1.4;ctx.stroke();
    });
  }
  if(status==='SPEAKING'){
    const amp=.5+.5*Math.sin(t*.085);
    ctx.beginPath();ctx.arc(CX,CY,42+amp*52,0,Math.PI*2);
    ctx.strokeStyle=css(c,.20*amp);ctx.lineWidth=amp*4;ctx.stroke();
    ctx.beginPath();ctx.arc(CX,CY,(42+amp*52)*1.6,0,Math.PI*2);
    ctx.strokeStyle=css(c,.09*amp);ctx.lineWidth=1;ctx.stroke();
  }
  if(!bloom){glow(ctx,CX,CY,30,c,.72*I);glow(ctx,CX,CY,10,W255,.95*I);}
}
// ── PLASMA ───────────────────────────────────────────────────────────────────
const PLASMA_SEEDS=14;
const pseed=Array.from({length:PLASMA_SEEDS},(_,i)=>({
  angle:i*Math.PI*2/PLASMA_SEEDS+(Math.random()-.5)*.3,
  len:72+Math.random()*52,
  dA:(.008+Math.random()*.014)*(Math.random()<.5?1:-1),
  energy:Math.random(),
}));
let plasmaSnaps=[];
function buildArc(out,x1,y1,x2,y2,depth,alpha){
  if(depth===0||alpha<.018){out.push({x1,y1,x2,y2,alpha,w:.4+alpha*3});return;}
  const mx=(x1+x2)/2+(Math.random()-.5)*28*depth;
  const my=(y1+y2)/2+(Math.random()-.5)*28*depth;
  if(depth>=2&&Math.random()<.38){
    const bx=mx+(Math.random()-.5)*65,by=my+(Math.random()-.5)*65;
    buildArc(out,mx,my,bx,by,depth-1,alpha*.42);
  }
  buildArc(out,x1,y1,mx,my,depth-1,alpha*.82);
  buildArc(out,mx,my,x2,y2,depth-1,alpha*.82);
}
function rebuildPlasmaSnaps(){
  plasmaSnaps=[];
  const I=im();
  pseed.forEach(s=>{
    const snap=[];
    buildArc(snap,CX,CY,CX+s.len*Math.cos(s.angle),CY+s.len*Math.sin(s.angle),3,I*.55);
    plasmaSnaps.push(snap);
  });
}
function drawPlasma(ctx,r,c,bloom){
  const I=im(),speed=sm();
  pseed.forEach(s=>{s.angle+=s.dA*speed;s.energy=.5+.5*Math.sin(t*.04+s.angle*2);});
  const ELEC={r:170,g:110,b:255},WHITE={r:235,g:220,b:255};
  if(t%3===0)rebuildPlasmaSnaps();
  if(bloom){
    pseed.forEach(s=>{
      const tx=CX+s.len*Math.cos(s.angle),ty=CY+s.len*Math.sin(s.angle);
      glow(ctx,tx,ty,20,ELEC,.48*s.energy*I);
    });
    glow(ctx,CX,CY,55,ELEC,.62*I);glow(ctx,CX,CY,20,W255,.95*I);
    return;
  }
  plasmaSnaps.forEach((snap,si)=>{
    const s=pseed[si];
    snap.forEach(seg=>{
      ctx.beginPath();ctx.moveTo(seg.x1,seg.y1);ctx.lineTo(seg.x2,seg.y2);
      ctx.strokeStyle=css(ELEC,seg.alpha*s.energy);ctx.lineWidth=seg.w;ctx.stroke();
    });
    const tx=CX+s.len*Math.cos(s.angle),ty=CY+s.len*Math.sin(s.angle);
    const g=ctx.createLinearGradient(CX,CY,tx,ty);
    g.addColorStop(0,css(WHITE,.90));g.addColorStop(.5,css(WHITE,.35*s.energy));g.addColorStop(1,'rgba(0,0,0,0)');
    ctx.strokeStyle=g;ctx.lineWidth=.7;ctx.beginPath();ctx.moveTo(CX,CY);ctx.lineTo(tx,ty);ctx.stroke();
    ctx.beginPath();ctx.arc(tx,ty,3.8,0,Math.PI*2);
    ctx.fillStyle=css(WHITE,.9*s.energy);ctx.fill();
  });
  if(t%4===0){
    for(let k=0;k<2;k++){
      const si=Math.floor(Math.random()*PLASMA_SEEDS);
      const sj=(si+Math.floor(1+Math.random()*(PLASMA_SEEDS-1)))%PLASMA_SEEDS;
      const ax=CX+pseed[si].len*Math.cos(pseed[si].angle),ay=CY+pseed[si].len*Math.sin(pseed[si].angle);
      const bx=CX+pseed[sj].len*Math.cos(pseed[sj].angle),by=CY+pseed[sj].len*Math.sin(pseed[sj].angle);
      const xsnap=[];buildArc(xsnap,ax,ay,bx,by,2,.28);
      xsnap.forEach(seg=>{
        ctx.beginPath();ctx.moveTo(seg.x1,seg.y1);ctx.lineTo(seg.x2,seg.y2);
        ctx.strokeStyle=css(WHITE,seg.alpha*.6);ctx.lineWidth=seg.w*.7;ctx.stroke();
      });
    }
  }
  if(status==='LISTENING'||status==='SPEAKING'){
    const amp=.5+.5*Math.sin(t*(status==='SPEAKING'?.09:.05));
    for(let k=1;k<=3;k++){
      const rr=22+k*18*amp;
      if(rr>r*1.3)continue;
      ctx.beginPath();ctx.arc(CX,CY,rr,0,Math.PI*2);
      ctx.strokeStyle=css(ELEC,(.18/k)*I*amp);ctx.lineWidth=1.2-k*.2;ctx.stroke();
    }
  }
  glow(ctx,CX,CY,42,ELEC,.72*I);glow(ctx,CX,CY,14,W255,.98*I);
}
// ── TORMENTA ─────────────────────────────────────────────────────────────────
const TSTRIKE_N=220;
const tp=Array.from({length:TSTRIKE_N},()=>({
  x:CX+(Math.random()-.5)*230, y:CY+(Math.random()-.5)*235,
  vx:(Math.random()-.5)*.5,   vy:(Math.random()-.5)*.5,
  charge:Math.random(), lit:0,
}));
const tStrikes=[];
let tCharge=0,tDischarging=false,tDischargeT=0;
function triggerStrike(x2,y2,depth,alpha){
  const segs=[];buildArc(segs,CX,CY,x2,y2,depth,alpha);
  tStrikes.push({segs,life:10+Math.random()*12,x2,y2});
}
function updateTormenta(){
  const speed=sm();
  tCharge+=.004*speed*(status==='THINKING'?2.5:status==='LISTENING'?1.6:1);
  tp.forEach(p=>{
    p.charge=Math.min(1,p.charge+.002*speed);
    if(p.lit>0)p.lit--;
    p.x+=p.vx*speed;p.y+=p.vy*speed;
    const dx=CX-p.x,dy=CY-p.y,dist=Math.hypot(dx,dy);
    if(dist>128){p.vx+=dx*.003;p.vy+=dy*.003;}
    p.vx+=(Math.random()-.5)*.04;p.vy+=(Math.random()-.5)*.04;
    const spd=Math.hypot(p.vx,p.vy);if(spd>1.8){p.vx=p.vx/spd*1.8;p.vy=p.vy/spd*1.8;}
  });
  if(t%22===0&&Math.random()<.55){
    const angle=Math.random()*Math.PI*2,len=80+Math.random()*70;
    triggerStrike(CX+len*Math.cos(angle),CY+len*Math.sin(angle)*.75,3,im()*.65);
  }
  if(tCharge>=1&&!tDischarging){tDischarging=true;tDischargeT=0;tCharge=0;}
  if(tDischarging){
    tDischargeT++;
    if(tDischargeT%4===0){
      const angle=Math.random()*Math.PI*2,len=100+Math.random()*50;
      triggerStrike(CX+len*Math.cos(angle),CY+len*Math.sin(angle)*.75,4,1.0);
    }
    if(tDischargeT>35)tDischarging=false;
  }
  for(let i=tStrikes.length-1;i>=0;i--){
    tStrikes[i].life--;
    if(tStrikes[i].life<=0){tStrikes.splice(i,1);continue;}
    const{x2,y2}=tStrikes[i];
    tp.forEach(p=>{if(Math.hypot(p.x-x2,p.y-y2)<28){p.lit=8;p.charge=0;}});
  }
}
function drawTormenta(ctx,r,c,bloom){
  const I=im();
  const LTNG={r:180,g:130,b:255},FLASH={r:255,g:255,b:220};
  if(bloom){
    tStrikes.forEach(s=>glow(ctx,s.x2,s.y2,22,LTNG,.55*(s.life/15)*I));
    if(tDischarging)glow(ctx,CX,CY,65,FLASH,.70*I);
    glow(ctx,CX,CY,38,LTNG,.60*I);glow(ctx,CX,CY,14,FLASH,.95*I);
    return;
  }
  const cr=55+tCharge*42;
  ctx.setLineDash([3,8]);ctx.beginPath();ctx.arc(CX,CY,cr,0,Math.PI*2*tCharge);
  ctx.strokeStyle=css(LTNG,.28+.18*tCharge);ctx.lineWidth=1.2;ctx.stroke();ctx.setLineDash([]);
  tp.forEach(p=>{
    const bright=p.lit>0?1:p.charge,col=p.lit>0?FLASH:LTNG;
    ctx.beginPath();ctx.arc(p.x,p.y,(.7+bright)*(p.lit>0?2.2:1),0,Math.PI*2);
    ctx.fillStyle=css(col,(.15+.55*bright)*I);ctx.fill();
  });
  tStrikes.forEach(s=>{
    const fade=s.life/15;
    s.segs.forEach(seg=>{
      ctx.beginPath();ctx.moveTo(seg.x1,seg.y1);ctx.lineTo(seg.x2,seg.y2);
      ctx.strokeStyle=css(LTNG,seg.alpha*fade);ctx.lineWidth=seg.w;ctx.stroke();
    });
    s.segs.filter(sg=>sg.alpha>.25).forEach(seg=>{
      ctx.beginPath();ctx.moveTo(seg.x1,seg.y1);ctx.lineTo(seg.x2,seg.y2);
      ctx.strokeStyle=css(FLASH,seg.alpha*.55*fade);ctx.lineWidth=seg.w*.45;ctx.stroke();
    });
  });
  if(tDischarging&&tDischargeT<18){
    const bfade=1-tDischargeT/18;
    ctx.beginPath();ctx.arc(CX,CY,tDischargeT*5.5,0,Math.PI*2);
    ctx.strokeStyle=css(FLASH,.60*bfade);ctx.lineWidth=3*bfade;ctx.stroke();
  }
  glow(ctx,CX,CY,38,LTNG,.68*I);glow(ctx,CX,CY,13,FLASH,.98*I);
}
// ── SHARED ────────────────────────────────────────────────────────────────────
function drawScan(ctx,r,c){
  const ly=CY-r+((t*1.6)%(r*2));
  ctx.save();ctx.beginPath();ctx.arc(CX,CY,r,0,Math.PI*2);ctx.clip();
  ctx.strokeStyle='rgba(255,200,80,.14)';ctx.lineWidth=1.3;
  ctx.beginPath();ctx.moveTo(CX-r,ly);ctx.lineTo(CX+r,ly);ctx.stroke();ctx.restore();
}
function drawCorners(ctx,c){
  const m=80,l=11;
  [[CX-m,CY-m,1,1],[CX+m,CY-m,-1,1],[CX-m,CY+m,1,-1],[CX+m,CY+m,-1,-1]].forEach(([x,y,dx,dy])=>{
    ctx.strokeStyle=css(c,.30);ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+dx*l,y);ctx.moveTo(x,y);ctx.lineTo(x,y+dy*l);ctx.stroke();
  });
}
function drawLabel(ctx,c){
  const NAMES=['NEURAL','PLASMA','TORMENTA'];
  const LAB={IDLE:'N O V A',LISTENING:'ESCUCHANDO',THINKING:'PROCESANDO',SPEAKING:'HABLANDO',ASLEEP:'DURMIENDO'}[status]||status;
  ctx.font='bold 8px "Courier New",monospace';
  ctx.textAlign='center';ctx.textBaseline='top';
  ctx.fillStyle=css(c,.80);ctx.fillText(LAB,CX,250);
  ctx.font='7px "Courier New",monospace';
  ctx.fillStyle=css(c,.28);ctx.fillText(NAMES[themeIdx],CX,262);
}
function tick(){
  t++;
  if(colorT<1){colorT=Math.min(1,colorT+.07);cur=lerpC(prev,tgt,colorT);}
  if(themeIdx===0)updateNeural();
  else if(themeIdx===2)updateTormenta();
  render();
  requestAnimationFrame(tick);
}
function render(){
  const c=cur,r=88;
  bC.clearRect(0,0,W,H);sC.clearRect(0,0,W,H);
  sC.globalCompositeOperation='lighter';
  switch(themeIdx){
    case 0:drawNeural(bC,r,c,true);drawNeural(sC,r,c,false);break;
    case 1:drawPlasma(bC,r,c,true);drawPlasma(sC,r,c,false);break;
    case 2:drawTormenta(bC,r,c,true);drawTormenta(sC,r,c,false);break;
  }
  sC.globalCompositeOperation='source-over';
  if(status==='THINKING')drawScan(sC,r,c);
  drawCorners(sC,c);
  drawLabel(sC,c);
}
requestAnimationFrame(tick);
document.addEventListener('dblclick',e=>{e.preventDefault();window.nextTheme();});
document.addEventListener('selectstart',e=>e.preventDefault());
</script></body></html>"""

# ─── Estilos compartidos ─────────────────────────────────────────────────────
_STYLE_DARK   = "rgba(0,12,28,185)"
_STYLE_BORDER = "rgba(20,140,200,100)"
_STYLE_TEXT   = "rgba(20,200,255,220)"
_STYLE_DIM    = "rgba(20,140,200,130)"

_SS_STRIP = f"""
    QWidget {{
        background: {_STYLE_DARK};
        border-top: 1px solid {_STYLE_BORDER};
    }}
"""
_SS_LOG = f"""
    QTextEdit {{
        background: rgba(0,8,20,190);
        color: rgba(180,220,255,210);
        border: 1px solid {_STYLE_BORDER};
        border-radius: 5px;
        font-family: 'Courier New', monospace;
        font-size: 10px;
        padding: 4px 6px;
        selection-background-color: rgba(20,140,200,120);
    }}
    QScrollBar:vertical {{
        width: 4px; background: transparent; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(20,160,220,110); border-radius: 2px; min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""
_SS_INPUT = f"""
    QLineEdit {{
        background: rgba(0,15,35,190);
        color: {_STYLE_TEXT};
        border: 1px solid {_STYLE_BORDER};
        border-radius: 5px;
        padding: 2px 8px;
        font-family: 'Courier New', monospace;
        font-size: 11px;
    }}
    QLineEdit:focus {{
        border: 1px solid rgba(20,200,255,200);
        background: rgba(0,25,50,210);
    }}
"""
_SS_BTN = f"""
    QPushButton {{
        background: rgba(0,15,35,190);
        color: {_STYLE_TEXT};
        border: 1px solid {_STYLE_BORDER};
        border-radius: 5px;
        font-size: 13px;
    }}
    QPushButton:hover {{ background: rgba(20,140,200,90); }}
    QPushButton:pressed {{ background: rgba(20,180,240,120); }}
"""
_SS_CLOSE = f"""
    QPushButton {{
        background: transparent;
        color: rgba(200,80,80,180);
        border: none;
        font-size: 13px;
        font-weight: bold;
    }}
    QPushButton:hover {{ color: rgba(255,100,100,255); }}
"""
_SS_CHEVRON = f"""
    QLabel {{
        background: transparent;
        color: {_STYLE_DIM};
        font-size: 11px;
    }}
"""
_SS_METRICS = f"""
    QLabel {{
        background: rgba(0,8,20,175);
        color: rgba(20,180,200,180);
        border-top: 1px solid {_STYLE_BORDER};
        font-family: 'Courier New', monospace;
        font-size: 8px;
        padding: 2px 6px;
    }}
"""
_SS_ATTACH_BADGE = f"""
    QLabel {{
        background: rgba(0,60,30,200);
        color: rgba(80,255,140,220);
        border: 1px solid rgba(40,200,100,120);
        border-radius: 3px;
        font-family: 'Courier New', monospace;
        font-size: 8px;
        padding: 1px 5px;
    }}
"""


# ═══════════════════════════════════════════════════════════════════════════════
class NovaWindow(QWidget):

    def __init__(self, state_queue: queue.Queue, stop_event=None):
        super().__init__()
        self._queue         = state_queue
        self._stop_event    = stop_event
        self._ready         = False
        self._pending: list[str] = []
        self._dragging      = False
        self._drag_offset   = QPoint()
        self._drag_target   = QPoint()
        self._drag_start    = QPoint()
        self._text_callback = None
        self._panel_open    = False

        # Escala: índice en _SCALE_STEPS (2 = 1.0 = normal)
        self._scale_idx     = 2
        # Altura del log redimensionable por drag
        self._log_h         = H_LOG_BASE
        # Resize por borde inferior
        self._resizing_log  = False
        self._resize_start_y = 0
        self._resize_start_h = 0

        # Estado de modelos / sesión
        self._session_tokens  = 0
        self._last_tokens     = 0
        self._last_model      = "—"
        self._last_provider   = "—"
        self._last_budget_pct = 100.0
        self._call_count      = 0

        # Archivo pendiente para adjuntar al próximo mensaje
        self._pending_attachment: dict | None = None   # {"name", "type", "content"}

        self.setMouseTracking(True)
        self._setup_window()
        self._setup_webview()
        self._setup_strip()
        self._setup_panel()
        self._start_timers()

    # ── Ventana ───────────────────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.resize(W_BASE, H_ANIM_BASE + H_METRICS + H_STRIP)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - W_BASE - 20, 80)

    # ── WebView ───────────────────────────────────────────────────────────────

    def _setup_webview(self):
        d = self._dims()
        self._view = QWebEngineView(self)
        self._view.setFixedSize(d["w"], d["h_anim"])
        self._view.setStyleSheet("background:transparent;border:none;")
        self._view.page().setBackgroundColor(Qt.transparent)
        self._view.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self._view.loadFinished.connect(self._on_loaded)
        self._view.installEventFilter(self)
        self._view.setHtml(_HUD_HTML)

    def showEvent(self, e):
        super().showEvent(e)
        self._install_view_filter()
        # Retry after Chromium initializes (focusProxy may be None initially)
        QTimer.singleShot(600,  self._install_view_filter)
        QTimer.singleShot(2000, self._install_view_filter)
        # macOS: Qt.WindowStaysOnTopHint doesn't fight other apps — use Cocoa level
        if sys.platform == "darwin":
            QTimer.singleShot(500,  self._set_mac_floating_level)
            QTimer.singleShot(2500, self._set_mac_floating_level)  # retry after WebEngine init

    def _set_mac_floating_level(self):
        """Set NSFloatingWindowLevel (3) so HUD stays above all normal windows on macOS."""
        import ctypes, ctypes.util
        try:
            # ctypes approach — works without PyObjC
            lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
            lib.sel_registerName.restype = ctypes.c_void_p
            lib.sel_registerName.argtypes = [ctypes.c_char_p]
            lib.objc_msgSend.restype = ctypes.c_void_p
            lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

            view_ptr = int(self.winId())
            sel_window = lib.sel_registerName(b"window")
            win_ptr = lib.objc_msgSend(view_ptr, sel_window)
            if win_ptr:
                # setLevel_ takes NSInteger
                lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
                sel_level = lib.sel_registerName(b"setLevel:")
                lib.objc_msgSend(win_ptr, sel_level, 3)  # NSFloatingWindowLevel = 3
                lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                sel_order = lib.sel_registerName(b"orderFrontRegardless")
                lib.objc_msgSend(win_ptr, sel_order)
        except Exception:
            pass

    def _install_view_filter(self):
        from PyQt5.QtWidgets import QWidget
        fp = self._view.focusProxy()
        if fp:
            fp.installEventFilter(self)
        # Install on all internal Chromium child widgets
        for child in self._view.findChildren(QWidget):
            child.installEventFilter(self)

    # ── Tira toggle (▾/▴) ────────────────────────────────────────────────────

    def _setup_strip(self):
        d = self._dims()
        # Barra de métricas (tokens / proveedor / budget)
        self._metrics_bar = QLabel("tokens: — · via: —", self)
        self._metrics_bar.setGeometry(0, d["h_anim"], d["w"], d["h_m"])
        self._metrics_bar.setAlignment(Qt.AlignCenter)
        self._metrics_bar.setStyleSheet(_SS_METRICS)
        self._metrics_bar.installEventFilter(self)

        self._strip = QWidget(self)
        self._strip.setGeometry(0, d["h_anim"] + d["h_m"], d["w"], d["h_st"])
        self._strip.setStyleSheet(_SS_STRIP)
        self._strip.setCursor(Qt.PointingHandCursor)
        self._strip.installEventFilter(self)

        self._chevron = QLabel("▾", self._strip)
        self._chevron.setGeometry(0, 0, d["w"], d["h_st"])
        self._chevron.setAlignment(Qt.AlignCenter)
        self._chevron.setStyleSheet(_SS_CHEVRON)

        self._strip.mousePressEvent = lambda e: self._toggle_panel()

    def _update_metrics(self, tokens: int = 0, provider: str = "", budget_pct: float = -1,
                        model: str = ""):
        """Actualiza la barra de métricas con datos del último LLM call."""
        if tokens:
            self._last_tokens     = tokens
            self._session_tokens += tokens
            self._call_count     += 1
        if provider:
            self._last_provider = provider[:14]
        if budget_pct >= 0:
            self._last_budget_pct = budget_pct
        if model and model != "[SKILL LOCAL]":
            # Acortar: "llama-3.3-70b-versatile" → "llama3.3-70b"
            m = model.replace("llama-", "llama").replace("-versatile", "").replace("-instant", "ᵢ")
            m = m.replace("-preview", "ₚ").replace(":free", "").replace("google/", "")
            self._last_model = m[:18]

        budget_icon = "●" if self._last_budget_pct > 30 else "▲" if self._last_budget_pct > 10 else "▼"
        line1 = f"▸ {self._last_model:<18}  {self._last_provider}"
        line2 = (f"  tk última: {self._last_tokens:,}  sesión: {self._session_tokens:,}  "
                 f"{budget_icon}{self._last_budget_pct:.0f}%  [{self._call_count} calls]")
        self._metrics_bar.setText(f"{line1}\n{line2}")
        self._metrics_bar.setToolTip(
            f"Modelo: {self._last_model}\n"
            f"Proveedor: {self._last_provider}\n"
            f"Tokens esta llamada: {self._last_tokens:,}\n"
            f"Total sesión: {self._session_tokens:,}\n"
            f"Llamadas: {self._call_count}\n"
            f"Budget restante: {self._last_budget_pct:.1f}%"
        )

    # ── Escala y layout dinámico ──────────────────────────────────────────────

    def _dims(self):
        """Retorna dimensiones actuales basadas en escala y log_h."""
        s       = _SCALE_STEPS[self._scale_idx]
        w       = int(W_BASE * s)
        h_anim  = int(H_ANIM_BASE * s)
        h_m     = max(12, int(H_METRICS * s))
        h_st    = max(14, int(H_STRIP * s))
        h_comp  = h_anim + h_m + h_st
        h_inp   = max(24, int(H_INPUT_BASE * s))
        h_log   = max(H_LOG_MIN, min(H_LOG_MAX, self._log_h))
        h_full  = h_comp + 4 + h_log + 6 + h_inp + 8
        return dict(s=s, w=w, h_anim=h_anim, h_m=h_m, h_st=h_st,
                    h_comp=h_comp, h_inp=h_inp, h_log=h_log, h_full=h_full)

    def _relayout(self):
        """Reposiciona todos los widgets según la escala y log_h actuales."""
        d = self._dims()
        s, w = d["s"], d["w"]

        # Animation
        self._view.setFixedSize(w, d["h_anim"])
        self._view.setZoomFactor(s)

        # Metrics
        self._metrics_bar.setGeometry(0, d["h_anim"], w, d["h_m"])

        # Strip
        self._strip.setGeometry(0, d["h_anim"] + d["h_m"], w, d["h_st"])
        self._chevron.setGeometry(0, 0, w, d["h_st"])

        # Panel
        y0   = d["h_comp"]
        pad  = max(3, int(4 * s))
        self._log.setGeometry(pad, y0 + pad, w - pad*2, d["h_log"])
        y_in = y0 + pad + d["h_log"] + max(3, int(6*s))
        btn_w = max(20, int(32*s))
        badge_h = max(14, int(16*s))
        self._attach_badge.setGeometry(pad, y_in - badge_h - 2, w - pad*2, badge_h)
        self._input.setGeometry(pad, y_in, w - btn_w*3 - pad*2, d["h_inp"])
        self._attach_btn.setGeometry(w - btn_w*3, y_in, d["h_inp"], d["h_inp"])
        self._send_btn.setGeometry(w - btn_w*2, y_in, d["h_inp"], d["h_inp"])
        self._close_btn.setGeometry(w - btn_w, y_in, d["h_inp"], d["h_inp"])

        # Window size
        h_total = d["h_full"] if self._panel_open else d["h_comp"]
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.resize(w, h_total)
        self.setFixedWidth(w)

    def _apply_scale(self, delta: int = 0):
        """Cambia el índice de escala y redibuja. delta=+1/-1 o 0 para refresh."""
        self._scale_idx = max(0, min(len(_SCALE_STEPS) - 1, self._scale_idx + delta))
        self._relayout()
        pct = int(_SCALE_STEPS[self._scale_idx] * 100)
        self._metrics_bar.setToolTip(f"Tamaño: {pct}%  (scroll ↕ para cambiar)")

    # ── Panel expandible (log + input) ───────────────────────────────────────

    def _setup_panel(self):
        d = self._dims()

        self._log = QTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setGeometry(6, d["h_comp"] + 4, d["w"] - 12, d["h_log"])
        self._log.setStyleSheet(_SS_LOG)
        self._log.hide()

        y_input = d["h_comp"] + 4 + d["h_log"] + 6
        self._input = QLineEdit(self)
        self._input.setPlaceholderText("▶  escribe un comando...")
        self._input.setGeometry(6, y_input, d["w"] - 78, d["h_inp"])
        self._input.setStyleSheet(_SS_INPUT)
        self._input.returnPressed.connect(self._on_text_submit)
        self._input.hide()

        self._attach_btn = QPushButton("📎", self)
        self._attach_btn.setGeometry(d["w"] - 104, y_input, d["h_inp"], d["h_inp"])
        self._attach_btn.setStyleSheet(_SS_BTN)
        self._attach_btn.setToolTip("Adjuntar archivo (imagen, doc, código…)")
        self._attach_btn.clicked.connect(self._on_attach_click)
        self._attach_btn.hide()

        self._send_btn = QPushButton("→", self)
        self._send_btn.setGeometry(d["w"] - 70, y_input, d["h_inp"], d["h_inp"])
        self._send_btn.setStyleSheet(_SS_BTN)
        self._send_btn.clicked.connect(self._on_text_submit)
        self._send_btn.hide()

        self._close_btn = QPushButton("✕", self)
        self._close_btn.setGeometry(d["w"] - 36, y_input, d["h_inp"], d["h_inp"])
        self._close_btn.setStyleSheet(_SS_CLOSE)
        self._close_btn.setToolTip("Cerrar Nova")
        self._close_btn.clicked.connect(self._request_close)
        self._close_btn.hide()

        # Badge que muestra el archivo adjunto pendiente (oculto por default)
        self._attach_badge = QLabel("", self)
        self._attach_badge.setGeometry(6, y_input - 18, d["w"] - 12, 16)
        self._attach_badge.setStyleSheet(_SS_ATTACH_BADGE)
        self._attach_badge.hide()

    # ── Toggle panel ─────────────────────────────────────────────────────────

    def _toggle_panel(self):
        self._panel_open = not self._panel_open
        visible = self._panel_open
        self._log.setVisible(visible)
        self._input.setVisible(visible)
        self._attach_btn.setVisible(visible)
        self._send_btn.setVisible(visible)
        self._close_btn.setVisible(visible)
        if visible:
            self._chevron.setText("▴")
            self._input.setFocus()
            if self._pending_attachment:
                self._attach_badge.show()
        else:
            self._chevron.setText("▾")
            self._attach_badge.hide()
        self._relayout()

    # ── Log de conversación ───────────────────────────────────────────────────

    def add_log(self, who: str, text: str):
        """Añade una línea al log. who = 'Nova' | 'Tú'"""
        if not text.strip():
            return
        display = text if len(text) <= 140 else text[:137] + "…"
        # Escapar HTML básico
        display = display.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if who == "Nova":
            color = "#14c8ff"
            name  = "Nova"
        else:
            color = "#90e890"
            name  = "Tú"
        html = f'<span style="color:{color};"><b>{name}:</b> {display}</span>'
        self._log.append(html)
        # Auto-scroll
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Input de texto ────────────────────────────────────────────────────────

    # ── Adjuntar archivos ─────────────────────────────────────────────────────

    _TEXT_EXTS = {".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".json",
                  ".yaml", ".yml", ".csv", ".html", ".css", ".xml", ".sh",
                  ".bash", ".c", ".h", ".cpp", ".java", ".go", ".rs", ".sql",
                  ".toml", ".ini", ".env", ".log", ".dockerfile"}
    _IMG_EXTS  = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

    def _on_attach_click(self):
        from PyQt5.QtWidgets import QFileDialog
        exts = ("Todos los soportados (*.txt *.md *.py *.js *.ts *.json *.yaml *.csv "
                "*.html *.c *.h *.cpp *.java *.go *.rs *.sql *.pdf "
                "*.png *.jpg *.jpeg *.webp *.gif);;"
                "Texto / código (*.txt *.md *.py *.js *.ts *.json *.yaml *.csv *.html *.c *.h *.cpp *.java *.go);;"
                "Imágenes (*.png *.jpg *.jpeg *.webp *.gif);;"
                "PDF (*.pdf);;"
                "Todos los archivos (*)")
        path, _ = QFileDialog.getOpenFileName(self, "Adjuntar archivo", "", exts)
        if not path:
            return
        self._load_attachment(path)

    def _load_attachment(self, path: str):
        import os, base64
        ext  = os.path.splitext(path)[1].lower()
        name = os.path.basename(path)

        if ext in self._IMG_EXTS:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp"}.get(ext.lstrip("."), "image/png")
            self._pending_attachment = {"name": name, "type": "image", "mime": mime, "content": b64}
            self.add_log("📎", f"Imagen adjunta: {name}")

        elif ext == ".pdf":
            text = self._read_pdf(path)
            self._pending_attachment = {"name": name, "type": "text", "content": text}
            self.add_log("📎", f"PDF adjunto: {name} ({len(text):,} chars)")

        elif ext in self._TEXT_EXTS or ext == "":
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(20_000)   # máx 20k chars
                self._pending_attachment = {"name": name, "type": "text", "content": content}
                self.add_log("📎", f"Archivo adjunto: {name} ({len(content):,} chars)")
            except Exception as e:
                self.add_log("⚠", f"No pude leer {name}: {e}")
                return
        else:
            self.add_log("⚠", f"Formato no soportado: {ext}")
            return

        # Mostrar badge con nombre del archivo
        self._attach_badge.setText(f"📎 {name}  ✕ clic para quitar")
        self._attach_badge.show()
        self._attach_badge.mousePressEvent = lambda _: self._clear_attachment()

    def _clear_attachment(self):
        self._pending_attachment = None
        self._attach_badge.hide()

    @staticmethod
    def _read_pdf(path: str) -> str:
        try:
            import pdfminer.high_level
            return pdfminer.high_level.extract_text(path)[:20_000]
        except ImportError:
            pass
        try:
            import pypdf
            r = pypdf.PdfReader(path)
            return "\n".join(p.extract_text() or "" for p in r.pages)[:20_000]
        except ImportError:
            return "(PDF: instala pdfminer.six o pypdf para leer PDFs)"
        except Exception as e:
            return f"(PDF error: {e})"

    # ── Input de texto ────────────────────────────────────────────────────────

    def _on_text_submit(self):
        text = self._input.text().strip()
        if not text and not self._pending_attachment:
            return
        self._input.clear()

        attachment = self._pending_attachment
        self._clear_attachment()

        # Construir mensaje final con adjunto si hay
        if attachment and attachment["type"] == "text":
            full = f"[Archivo adjunto: {attachment['name']}]\n{attachment['content']}\n---\n{text}" if text else f"[Archivo adjunto: {attachment['name']}]\n{attachment['content']}"
        elif attachment and attachment["type"] == "image":
            # Protocolo especial — novaesp.py lo intercepta
            full = f"__HUD_IMG__:{attachment['name']}:{attachment['mime']}:{attachment['content']}"
            if text:
                full += f"::{text}"
        else:
            full = text

        if text:
            self.add_log("Tú", text)
        if self._text_callback:
            import threading
            threading.Thread(target=self._text_callback, args=(full,), daemon=True).start()

    def set_text_callback(self, fn):
        self._text_callback = fn

    # ── Cerrar ────────────────────────────────────────────────────────────────

    def _request_close(self):
        if self._stop_event:
            self._stop_event.set()
        QApplication.quit()

    # ── Eventos de ratón (drag + click corto) ─────────────────────────────────

    def _is_bottom_edge(self, local_y: int) -> bool:
        """True si el cursor está en los últimos 6px de la ventana (borde inferior)."""
        return self._panel_open and local_y >= self.height() - 6

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        t = event.type()

        if t == QEvent.MouseButtonDblClick:
            self._js("window.nextTheme();")
            return True

        # Scroll wheel → escalar HUD
        if t == QEvent.Wheel:
            delta = event.angleDelta().y()
            self._apply_scale(1 if delta > 0 else -1)
            return True

        if t == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
            if self._text_callback:
                import threading
                threading.Thread(
                    target=self._text_callback, args=("toggle_mute",), daemon=True
                ).start()
            return True

        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            local_y = event.pos().y()
            if self._is_bottom_edge(local_y):
                # Iniciar resize del log por borde inferior
                self._resizing_log   = True
                self._resize_start_y = event.globalPos().y()
                self._resize_start_h = self._log_h
                self.setCursor(Qt.SizeVerCursor)
                return True
            self._dragging    = True
            self._drag_start  = event.globalPos()
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self._drag_target = self.pos()
            self._js("window.setDragging(true);")
            return False

        if t == QEvent.MouseMove:
            local_y = event.pos().y()
            if self._resizing_log and (event.buttons() & Qt.LeftButton):
                dy = event.globalPos().y() - self._resize_start_y
                self._log_h = max(H_LOG_MIN, min(H_LOG_MAX, self._resize_start_h + dy))
                self._relayout()
                return True
            if (event.buttons() & Qt.LeftButton) and self._dragging:
                self._drag_target = event.globalPos() - self._drag_offset
                return False
            # Cursor dinámico cerca del borde inferior
            if self._is_bottom_edge(local_y):
                self.setCursor(Qt.SizeVerCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            return False

        if t == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._resizing_log:
                self._resizing_log = False
                self.setCursor(Qt.ArrowCursor)
                return True
            if self._dragging:
                self._dragging = False
                self._js("window.setDragging(false);")
                dist = (event.globalPos() - self._drag_start).manhattanLength()
                if dist < 8 and self._text_callback:
                    import threading
                    threading.Thread(
                        target=self._text_callback, args=("wake_up",), daemon=True
                    ).start()
            return False

        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        """Scroll sobre cualquier parte del HUD → escala la ventana."""
        delta = event.angleDelta().y()
        self._apply_scale(1 if delta > 0 else -1)
        event.accept()

    # ── WebEngine ─────────────────────────────────────────────────────────────

    def _on_loaded(self, ok: bool):
        self._ready = ok
        for js in self._pending:
            self._view.page().runJavaScript(js)
        self._pending.clear()

    def _js(self, code: str):
        if self._ready:
            self._view.page().runJavaScript(code)
        else:
            self._pending.append(code)

    # ── Timers ────────────────────────────────────────────────────────────────

    def _start_timers(self):
        QTimer(self, timeout=self._poll_queue, interval=80).start()
        QTimer(self, timeout=self._update_drag, interval=16).start()

    def _update_drag(self):
        if not self._dragging:
            return
        cur = self.pos()
        dx  = self._drag_target.x() - cur.x()
        dy  = self._drag_target.y() - cur.y()
        if abs(dx) + abs(dy) < 1:
            return
        nx = cur.x() + int(dx * 0.28)
        ny = cur.y() + int(dy * 0.28)
        vx = nx - cur.x()
        self.move(nx, ny)
        self._js(f"window.onDragMove({vx});")

    def _poll_queue(self):
        while not self._queue.empty():
            state = self._queue.get()
            if "status" in state:
                self._js(f"window.setStatus('{state['status'].upper()}');")
            if "theme" in state:
                v = state["theme"]
                if v == "__next__":
                    self._js("window.nextTheme();")
                elif isinstance(v, str):
                    v = v.upper()
                    idx = THEME_NAMES.index(v) if v in THEME_NAMES else 0
                    self._js(f"window.setTheme({idx});")
                else:
                    self._js(f"window.setTheme({int(v)});")
            # Log de conversación
            if "response_text" in state and state["response_text"]:
                self.add_log("Nova", state["response_text"])
            if "user_text" in state and state["user_text"]:
                self.add_log("Tú", state["user_text"])
            # Métricas del LLM (modelo, tokens, proveedor, budget)
            if any(k in state for k in ("tokens_used", "provider", "model_info")):
                tokens   = state.get("tokens_used", 0)
                provider = state.get("provider", "")
                budget   = state.get("budget_remaining_pct", -1)
                # Extraer nombre de modelo de model_info "Tier N label | model | N tk"
                model = ""
                mi = state.get("model_info", "")
                if mi and "|" in mi:
                    parts = [p.strip() for p in mi.split("|")]
                    model = parts[1] if len(parts) > 1 else ""
                self._update_metrics(tokens=tokens, provider=provider,
                                     budget_pct=budget, model=model)


# ═══════════════════════════════════════════════════════════════════════════════
class NovaHUD:
    def __init__(self):
        self._queue         = queue.Queue()
        self._stop_event    = None
        self._text_callback = None
        self._win: "NovaWindow | None" = None

    def set_stop_event(self, ev):
        self._stop_event = ev

    def set_text_callback(self, fn):
        self._text_callback = fn
        if self._win:
            self._win.set_text_callback(fn)

    def put_state(self, **kwargs):
        self._queue.put(kwargs)

    def start(self):
        import signal
        app = QApplication(sys.argv)
        self._win = NovaWindow(self._queue, stop_event=self._stop_event)
        if self._text_callback:
            self._win.set_text_callback(self._text_callback)
        self._win.show()
        signal.signal(signal.SIGINT, lambda *_: app.quit())
        hb = QTimer(); hb.start(200); hb.timeout.connect(lambda: None)
        if self._stop_event is not None:
            ev = self._stop_event
            st = QTimer(); st.start(400)
            st.timeout.connect(lambda: app.quit() if ev.is_set() else None)
        app.exec_()
