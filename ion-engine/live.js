const IE = __DATA__;
__MODEL__
const ieP = IE.P;
const ieStage = document.querySelector(".ie-stage");
const ieSvg = ieStage.querySelector("svg");
const ieSled = ieSvg.querySelector('[data-part="sled"]');
const ieRod = ieSvg.querySelector('[data-part="rod"]');
const ieNeedle = ieSvg.querySelector('[data-part="needle"]');
const iePointer = ieSvg.querySelector('[data-part="pointer"]');
const ieReadout = document.querySelector("[data-readout]");
const ieStill = matchMedia("(prefers-reduced-motion: reduce)");
const IE_LIGHT = document.body.dataset.theme === "light" || document.querySelector("[data-theme]")?.getAttribute("data-theme") === "light" ? 1 : 0;
const ieClamp = (value, low, high) => Math.min(high, Math.max(low, value));
const IE_FULL = MODEL.at(1).thrust;
const IE_OFF = 0.06;
const IE_STEPS = [0, ...Array.from({ length: 16 }, (_, index) => IE_OFF + ((1 - IE_OFF) * index) / 15)];

const IE_FRAGMENT = `
uniform float uBeam;
uniform float uVolt;
uniform float uShift;
uniform float uLight;
const float XG=${IE.xg.toFixed(2)};
const float ZA=${IE.za.toFixed(2)};
const float R0=${IE.r0.toFixed(2)};
const float LEN=${IE.plume.toFixed(2)};
const vec3 NEUT=vec3(${IE.neutraliser.map((n) => n.toFixed(2)).join(",")});
const vec3 TINT=vec3(.86,.93,1.);
const vec3 BODY=vec3(.33,.55,.97);
const vec3 RIM=vec3(.3,.7,1.);
const vec3 ICE=vec3(.92,.98,1.);
float plume(vec3 p){
  float x=p.x-XG-uShift;
  float xs=max(x,0.);
  float rb=R0*.8+xs*.13;
  vec2 q=vec2(p.y,p.z-ZA);
  float rho2=dot(q,q);
  float body=exp(-pow(rho2/(rb*rb*.78),1.5));
  float along=smoothstep(-.5,1.5,x)*(1.-smoothstep(.5,1.,x/LEN));
  float thin=pow(R0*.8/rb,1.6);
  float streak=1.+.7*(noise2(q*.7)-.5)*exp(-xs/70.);
  float flow=1.+.22*(noise3(vec3(x*.07-uTime*(1.4+1.6*uVolt),q*.09))-.5);
  return body*along*thin*streak*flow*smoothstep(0.,6.,p.z);
}
vec3 paperOf(float e){
  vec3 c=mix(vec3(1.),TINT,smoothstep(0.,.1,e));
  c=mix(c,BODY,smoothstep(.08,.62,e));
  return mix(c,RIM,smoothstep(.7,.97,e));
}
vec4 inkFor(vec3 seen,float cover){
  vec3 absorbed=1.-seen;
  float a=max(max(absorbed.r,max(absorbed.g,absorbed.b)),cover);
  return vec4(vec3(a)-absorbed,a);
}
void main(){
  vec2 vb=viewOf(gl_FragCoord.xy);
  vec3 p0=rayOf(vb);
  vec3 V=towardViewer();
  float w2=V.y*V.y+V.z*V.z;
  float tc=-(p0.y*V.y+(p0.z-ZA)*V.z)/w2;
  const float T=84.;
  const int N=20;
  float ta=max(tc-T,(XG+uShift-p0.x)/V.x);
  float dt=max(tc+T-ta,0.)/float(N);
  float j=hash12(gl_FragCoord.xy+fract(uTime)*37.);
  float E=0.;
  for(int i=0;i<N;i++){
    float t=ta+(float(i)+j)*dt;
    E+=plume(p0+t*V);
  }
  E*=dt*sqrt(w2)/(R0*1.772)*uBeam*(.85+.3*uVolt);
  vec2 n=project(NEUT+vec3(uShift,0.,0.));
  float dn=length(vb-n)/uK;
  float glow=(exp(-dn*dn/2.2)+.2*exp(-dn*dn/20.))*smoothstep(0.,.25,uBeam)*.5;
  float nz=(hash12(gl_FragCoord.xy+fract(uTime*.61)*91.)+hash12(gl_FragCoord.yx*1.37+fract(uTime*.37)*57.)-1.)/255.;
  vec3 col=tonemap(vec3(.2,.46,1.)*E*1.7+vec3(.7,.88,1.)*E*E*.6+vec3(.62,.8,1.)*glow,1.25);
  float m=max(col.r,max(col.g,col.b));
  col=max(col+nz*smoothstep(0.,1.5/255.,m),0.);
  vec4 dark=vec4(col,max(col.r,max(col.g,col.b)));
  float e=1.-exp(-1.5*(E+glow*.8));
  vec4 ink=inkFor(paperOf(e),.3*smoothstep(.7,.97,e));
  ink=max(ink+nz*smoothstep(0.,1.5/255.,ink.a),0.);
  ink.rgb=min(ink.rgb,vec3(ink.a));
  gl_FragColor=mix(dark,ink,uLight);
}`;

const ieLayer = glLayer({ canvas: ieStage.querySelector(".ie-gl"), fragment: IE_FRAGMENT, view: [IE.W, IE.H], camera: IE.camera, uniforms: ["uBeam", "uVolt", "uShift"], fixed: { uLight: IE_LIGHT } });
if (ieLayer) ieStage.setAttribute("data-gl", "");

const ieNeedleAt = (share) => {
  const angle = ((-IE.sweep / 2 + IE.sweep * share) * Math.PI) / 180;
  const [x, y] = IE.gauge.at;
  const r = IE.gauge.r;
  return lineOnTop([x - Math.sin(angle) * 2.4, y + Math.cos(angle) * 2.4], [x + Math.sin(angle) * (r - 3.2), y - Math.cos(angle) * (r - 3.2)], IE.gauge.top + 0.2, ieP);
};

const iePointerAt = (share) => {
  const angle = ((-IE.knob.sweep / 2 + IE.knob.sweep * share) * Math.PI) / 180;
  const [x, y] = IE.knob.at;
  return lineOnTop([x, y], [x + Math.sin(angle) * IE.knob.r, y - Math.cos(angle) * IE.knob.r], IE.knob.top, ieP);
};
const ieKnob = { x: 0, v: 0 };
let ieThrottle = 0;
let ieTouring = !ieStill.matches;
let ieClock = 0, ieTime = 0, ieLast = 0, ieFrame = 0, ieVisible = false, ieIdle = 0, ieDrawn = "";
const ieBeam = { x: 0, v: 0 }, ieHot = { x: 0, v: 0 }, ieThrust = { x: 0, v: 0 }, iePush = { x: 0, v: 0 };
const IE_TOUR = [0, 0.4, 1, 0.7];
if (ieStill.matches) ieThrottle = 1;

const ieTarget = () => {
  const on = ieThrottle >= IE_OFF;
  const m = MODEL.at((ieThrottle - IE_OFF) / (1 - IE_OFF));
  return { on, m };
};

function ieDraw() {
  const { on, m } = ieTarget();
  const origin = iso([0, 0, 0], ieP);
  const moved = iso([-iePush.x, 0, 0], ieP);
  const offset = [moved[0] - origin[0], moved[1] - origin[1]];
  const move = "translate(" + offset[0].toFixed(2) + " " + offset[1].toFixed(2) + ")";
  ieSled.setAttribute("transform", move);
  ieRod.setAttribute("transform", move);
  holdStill(ieRod, offset);
  iePointer.setAttribute("d", iePointerAt(ieKnob.x));
  ieNeedle.setAttribute("d", ieNeedleAt(ieClamp(ieThrust.x / IE.fullScale, 0, 1)));
  ieStage.style.setProperty("--ie-beam", ieBeam.x.toFixed(3));
  const shown = Math.abs(ieThrust.x) < 0.05 ? 0 : ieThrust.x;
  const text = on ? m.volts + " V · " + m.amps.toFixed(2) + " A · " + shown.toFixed(0) + " mN · ions at " + m.speed.toFixed(0) + " km/s" : "beam off · " + shown.toFixed(0) + " mN";
  if (ieReadout.textContent !== text) ieReadout.textContent = text;
  ieStage.setAttribute("aria-valuenow", String(Math.round(shown)));
  ieStage.setAttribute("aria-valuetext", text);
  if (!ieLayer) return;
  if (ieBeam.x > 1e-3) {
    const values = { uBeam: ieBeam.x, uVolt: ieHot.x, uShift: -iePush.x };
    const time = ieStill.matches ? 0.8 : ieTime;
    const key = JSON.stringify(values) + time;
    if (key !== ieDrawn) { ieLayer.draw(values, time); ieDrawn = key; }
  } else { ieLayer.clear(); ieDrawn = ""; }
}

function ieTick(now) {
  const dt = ieLast ? Math.min((now - ieLast) / 1000, 1 / 30) : 1 / 60;
  ieLast = now;
  const calm = ieStill.matches;
  if (ieTouring) { ieClock += dt; ieThrottle = IE_TOUR[Math.floor(ieClock / 3.4) % IE_TOUR.length]; }
  ieTime += dt;
  const { on, m } = ieTarget();
  let moving = false;
  moving = settle(ieKnob, ieThrottle, dt, 0.12, calm) || moving;
  moving = settle(ieBeam, on ? m.share : 0, dt, 0.32, calm) || moving;
  moving = settle(ieHot, on ? m.hot : 0, dt, 0.4, calm) || moving;
  moving = settle(ieThrust, on ? m.thrust : 0, dt, 0.3, calm) || moving;
  moving = settle(iePush, (ieThrust.x / IE_FULL) * IE.travel, dt, 0.16, calm) || moving;
  ieDraw();
  const alive = moving || ieTouring || (ieBeam.x > 1e-3 && !calm && ieLayer);
  ieFrame = ieVisible && alive ? requestAnimationFrame(ieTick) : 0;
}
const ieRun = () => { if (!ieFrame && ieVisible) { ieLast = 0; ieFrame = requestAnimationFrame(ieTick); } };
const ieSteer = (next) => {
  ieTouring = false;
  ieThrottle = ieClamp(next, 0, 1);
  clearTimeout(ieIdle);
  ieIdle = setTimeout(() => { ieTouring = !ieStill.matches; ieClock = 0; ieRun(); }, 5000);
  ieRun();
};
new IntersectionObserver((entries) => { ieVisible = entries[entries.length - 1].isIntersecting; if (ieVisible) ieRun(); }, { rootMargin: "120px 0px" }).observe(ieStage);
ieStage.addEventListener("pointermove", (event) => {
  const box = ieSvg.getBoundingClientRect();
  ieSteer(ieClamp(((event.clientX - box.left) / box.width - 0.15) / 0.7, 0, 1));
});
ieStage.addEventListener("pointerleave", () => ieSteer(ieThrottle));
ieStage.addEventListener("keydown", (event) => {
  const here = IE_STEPS.reduce((best, step, index) => (Math.abs(step - ieThrottle) < Math.abs(IE_STEPS[best] - ieThrottle) ? index : best), 0);
  let to = null;
  if (event.key === "ArrowRight" || event.key === "ArrowUp") to = Math.min(IE_STEPS.length - 1, here + 1);
  if (event.key === "ArrowLeft" || event.key === "ArrowDown") to = Math.max(0, here - 1);
  if (event.key === "Home" || event.key === "Escape") to = 0;
  if (event.key === "End") to = IE_STEPS.length - 1;
  if (to === null) return;
  event.preventDefault();
  ieSteer(IE_STEPS[to]);
});
addEventListener("resize", () => { ieDrawn = ""; ieRun(); });
ieDraw();
