/*
 * classroom3d_v2.js — النسخة الثانية: مقارنة حية «التقليدي» مقابل «ظِلال» + لوحة تحكم زمنية.
 * (النسخة الأولى classroom3d.js محفوظة دون تغيير كمرجع.)
 * كل الأرقام (لكل حالة ولكل خطوة: الحرارة، قدرة التبريد، القدرة الكهربائية، الطاقة المتراكمة، الراحة حتى الآن،
 * التوفير وفروقه) محسوبة في Python (classroom3d_compare.py)؛ هذا الملف يعرضها بالفهرس الزمني فقط.
 *
 * الأصل: القاعة الافتراضية ثلاثية الأبعاد (WebGL 1، دون أي مكتبة خارجية).
 *
 * هذه طبقة عرض فقط: كل القيم الحرارية والطاقية تأتي جاهزة من محرك Python في window.ZILAL_STATE
 * (مصفوفات لكل خطوة 15 دقيقة). لا يُعاد حساب أي فيزياء هنا؛ الشيفرة تقرأ المصفوفات بالفهرس الزمني.
 *
 * المكوّنات: رياضيات المصفوفات، شبكات (صندوق/كرة)، مظلّل بإضاءة شمس + نصف كرة + خريطة ظلال،
 * كاميرا مدارية (تدوير/تكبير/تحريك)، القاعة (جدران/نافذة/ستارة/مقاعد/طلاب/مكيّف/شاشة/إضاءة)،
 * جزيئات هواء المكيّف، طبقة حرارية مفهومية، واجهة HUD وشريط زمني بتشغيل/إيقاف/استئناف/إعادة.
 */
(function () {
  'use strict';
  var S = window.ZILAL_STATE;
  var root = document.getElementById('zl3d');
  if (!S || !root) { return; }
  var L = S.labels;

  // ---------------------------------------------------------------- math
  function m4() { var m = new Float32Array(16); m[0] = m[5] = m[10] = m[15] = 1; return m; }
  function mul(a, b) {
    var o = new Float32Array(16);
    for (var c = 0; c < 4; c++) for (var r = 0; r < 4; r++) {
      o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
    }
    return o;
  }
  function persp(fovy, asp, n, f) {
    var t = 1 / Math.tan(fovy / 2), o = new Float32Array(16);
    o[0] = t / asp; o[5] = t; o[10] = (f + n) / (n - f); o[11] = -1; o[14] = 2 * f * n / (n - f); return o;
  }
  function ortho(l, r, b, t, n, f) {
    var o = m4(); o[0] = 2 / (r - l); o[5] = 2 / (t - b); o[10] = -2 / (f - n);
    o[12] = -(r + l) / (r - l); o[13] = -(t + b) / (t - b); o[14] = -(f + n) / (f - n); return o;
  }
  function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
  function cross(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
  function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
  function norm(a) { var l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; }
  function lookAt(e, c, up) {
    var z = norm(sub(e, c)), x = norm(cross(up, z)), y = cross(z, x), o = m4();
    o[0] = x[0]; o[4] = x[1]; o[8] = x[2]; o[1] = y[0]; o[5] = y[1]; o[9] = y[2];
    o[2] = z[0]; o[6] = z[1]; o[10] = z[2]; o[12] = -dot(x, e); o[13] = -dot(y, e); o[14] = -dot(z, e); return o;
  }
  // T * Ry * S
  function trs(t, ry, s) {
    var c = Math.cos(ry || 0), sn = Math.sin(ry || 0), o = m4();
    o[0] = c * s[0]; o[2] = -sn * s[0]; o[5] = s[1]; o[8] = sn * s[2]; o[10] = c * s[2];
    o[12] = t[0]; o[13] = t[1]; o[14] = t[2]; return o;
  }
  function normalMat(ry, s) {
    // معكوس منقول (Ry·S) = Ry · S⁻¹ — يكفي لصناديق بتدوير حول y فقط
    var c = Math.cos(ry || 0), sn = Math.sin(ry || 0);
    return new Float32Array([c / s[0], 0, -sn / s[0], 0, 1 / s[1], 0, sn / s[2], 0, c / s[2]]);
  }
  function hexLin(h) {
    var v = [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
    return v.map(function (x) { return Math.pow(x / 255, 2.2); });
  }
  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }

  // ---------------------------------------------------------------- DOM
  root.innerHTML = '<div class="zl-vp">' +
    '<canvas id="zl3d-cv" aria-label="' + L.canvas + '"></canvas>' +
    '<div class="zl-cam">' +
    '  <button type="button" data-cam="default" title="' + L.camReset + '">⟲</button>' +
    '  <button type="button" data-cam="top" title="' + L.camTop + '">⊡</button>' +
    '  <button type="button" data-cam="inside" title="' + L.camInside + '">◉</button>' +
    '  <span class="zl-hint">' + L.hint + '</span>' +
    '</div>' +
    '<div class="zl-orient"><svg viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="18" fill="none" stroke="currentColor" stroke-opacity=".35"/><path id="zl3d-needle" d="M20 6 L24 20 L20 34 L16 20 Z" fill="#CC9E0A"/></svg><span id="zl3d-orient"></span></div>' +
    '<div class="zl-view" role="group" aria-label="' + L.view + '"><span>' + L.view + '</span><button type="button" data-view="zilal">' + L.zilal + '</button><button type="button" data-view="conv">' + L.conv + '</button></div>' +
    '<aside class="zl-hud" dir="rtl">' +
    '  <div class="zl-hud-head"><span class="zl-dot" id="zl3d-live"></span><b>' + L.status + '</b><span class="zl-clock" id="zl3d-clock">00:00</span></div>' +
    '  <div class="zl-temp"><span id="zl3d-tin">--</span><small>' + L.indoor + '</small></div>' +
    '  <div class="zl-chip" id="zl3d-comfort">--</div>' +
    '  <div class="zl-row"><span>' + L.outdoor + '</span><b id="zl3d-tout">--</b></div>' +
    '  <div class="zl-row"><span>' + L.students + '</span><b id="zl3d-occ">--</b></div>' +
    '  <div class="zl-row"><span>' + L.solar + '</span><b id="zl3d-sol">--</b></div>' +
    '  <div class="zl-row"><span>' + L.cooling + '</span><b id="zl3d-cool">--</b></div>' +
    '  <div class="zl-bar"><i id="zl3d-coolbar"></i></div>' +
    '  <div class="zl-row"><span>' + L.hvac + '</span><b id="zl3d-hvac">--</b></div>' +
    '  <div class="zl-row"><span>' + L.lightRow + '</span><b id="zl3d-light">--</b></div>' +
    '  <div class="zl-row"><span>' + L.energyCum + '</span><b id="zl3d-ecum">--</b></div>' +
    '  <div class="zl-ring"><svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="26" fill="none" stroke="rgba(255,255,255,.15)" stroke-width="7"/><circle id="zl3d-ringc" cx="32" cy="32" r="26" fill="none" stroke-width="7" stroke-linecap="round" transform="rotate(-90 32 32)"/></svg><div><b id="zl3d-comp">--</b><small>' + L.compliance + '</small><small id="zl3d-eday"></small></div></div>' +
    '</aside>' +
    '<div class="zl-timeline" dir="rtl">' +
    '  <div class="zl-tl-row">' +
    '    <button type="button" class="zl-play" id="zl3d-play">▶ ' + L.start + '</button>' +
    '    <button type="button" class="zl-reset" id="zl3d-reset" title="' + L.reset + '" aria-label="' + L.reset + '">↺</button>' +
    '    <div class="zl-steps" dir="ltr"><button type="button" data-step="-4" title="' + L.hourBack + '">−1h</button><button type="button" data-step="-1" title="' + L.stepBack + '">−15m</button>' +
    '      <button type="button" data-step="1" title="' + L.stepFwd + '">+15m</button><button type="button" data-step="4" title="' + L.hourFwd + '">+1h</button></div>' +
    '    <span class="zl-now" id="zl3d-now">00:00</span>' +
    '    <div class="zl-speeds" dir="ltr" role="group" aria-label="' + L.speed + '" title="' + L.speedNote + '"><button type="button" data-speed="0.5">0.5×</button><button type="button" data-speed="1">1×</button><button type="button" data-speed="2">2×</button><button type="button" data-speed="5">5×</button><button type="button" data-speed="10">10×</button></div>' +
    '  </div>' +
    '  <div class="zl-track" dir="ltr"><div class="zl-lecture" id="zl3d-lect"></div><input type="range" id="zl3d-range" min="0" max="' + S.n + '" step="1" value="0" aria-label="' + L.timeline + '"><div class="zl-ticks"><span>00</span><span>02</span><span>04</span><span>06</span><span>08</span><span>10</span><span>12</span><span>14</span><span>16</span><span>18</span><span>20</span><span>22</span><span>24</span></div></div>' +
    '</div>' +
    '<div class="zl-note">' + L.note + '</div>' +
    '<div class="zl-fallback" dir="rtl" id="zl3d-fallback" hidden>' + L.noWebgl + '</div>' +
    '</div>' +
    '<section class="zl-deck" dir="rtl" aria-live="polite">' +
    '  <div class="zl-deck-head"><b>' + L.deckTitle + ' <span id="zl-dk-time">--</span></b><span class="zl-verdict" id="zl-dk-verdict"></span></div>' +
    '  <div class="zl-deck-grid">' +
    '    <div class="zl-cmp-wrap"><table class="zl-cmp"><thead><tr><th>' + L.indicator + '</th><th class="c">' + L.conv + '</th><th class="z">' + L.zilal + '</th><th>' + L.diff + '</th></tr></thead><tbody id="zl-dk-body"></tbody></table></div>' +
    '    <div class="zl-kpis" id="zl-dk-kpis"></div>' +
    '    <div class="zl-power"><svg id="zl-dk-pw" viewBox="0 0 680 190" role="img" aria-label="' + L.powerTitle + '"></svg></div>' +
    '  </div>' +
    '</section>';

  var vpEl = root.querySelector('.zl-vp');
  var cv = document.getElementById('zl3d-cv');
  var gl = cv.getContext('webgl', { antialias: true, alpha: true, premultipliedAlpha: false }) ||
           cv.getContext('experimental-webgl', { antialias: true, alpha: true });
  if (!gl) { document.getElementById('zl3d-fallback').hidden = false; return; }

  // ---------------------------------------------------------------- shaders
  var VS = 'attribute vec3 aPos; attribute vec3 aNor; uniform mat4 uM; uniform mat4 uVP; uniform mat4 uLVP; uniform mat3 uN;' +
    'varying vec3 vW; varying vec3 vN; varying vec4 vS;' +
    'void main(){ vec4 w = uM*vec4(aPos,1.0); vW = w.xyz; vN = normalize(uN*aNor); vS = uLVP*w; gl_Position = uVP*w; }';
  var FS = 'precision mediump float; varying vec3 vW; varying vec3 vN; varying vec4 vS;' +
    'uniform vec3 uColor; uniform vec3 uEmis; uniform float uAlpha; uniform vec3 uSunDir; uniform vec3 uSun; uniform vec3 uSky; uniform vec3 uGround;' +
    'uniform vec3 uFill; uniform float uInDim; uniform vec3 uCam; uniform float uSpec; uniform sampler2D uSM; uniform float uShadowOn; uniform float uTexel;' +
    'float unpack(vec4 c){ return dot(c, vec4(1.0, 1.0/255.0, 1.0/65025.0, 1.0/16581375.0)); }' +
    'float shadow(){ vec3 p = vS.xyz/vS.w*0.5+0.5; if(p.x<0.0||p.x>1.0||p.y<0.0||p.y>1.0||p.z>1.0) return 1.0; float s=0.0;' +
    ' for(int x=-1;x<=1;x++) for(int y=-1;y<=1;y++){ float d = unpack(texture2D(uSM, p.xy+vec2(float(x),float(y))*uTexel)); s += (p.z-0.0025 > d) ? 0.0 : 1.0; } return s/9.0; }' +
    'vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }' +
    'void main(){ vec3 N = normalize(vN); if(!gl_FrontFacing) N = -N; float ndl = max(dot(N,uSunDir),0.0); float sh = uShadowOn>0.5 ? shadow() : 1.0;' +
    ' vec3 hemi = mix(uGround, uSky, N.y*0.5+0.5); vec3 fill = uFill*max(dot(N, normalize(vec3(0.25,1.0,0.35))),0.0);' +
    ' vec3 V = normalize(uCam-vW); vec3 H = normalize(V+uSunDir); float sp = pow(max(dot(N,H),0.0),48.0)*uSpec*sh;' +
    ' float ao = mix(0.72,1.0,smoothstep(0.0,0.9,vW.y));' +
    ' float inside = step(abs(vW.x),5.05)*step(abs(vW.z),3.05)*step(vW.y,3.15); hemi *= mix(1.0, uInDim, inside);' +
    ' vec3 c = uColor*(hemi*ao + fill + uSun*ndl*sh) + uSun*sp + uEmis;' +
    ' gl_FragColor = vec4(pow(aces(c), vec3(1.0/2.2)), uAlpha); }';
  var DVS = 'attribute vec3 aPos; uniform mat4 uM; uniform mat4 uLVP; void main(){ gl_Position = uLVP*uM*vec4(aPos,1.0); }';
  var DFS = 'precision mediump float; vec4 pack(float d){ vec4 e = fract(vec4(1.0,255.0,65025.0,16581375.0)*d); e -= e.yzww*vec4(1.0/255.0,1.0/255.0,1.0/255.0,0.0); return e; }' +
    'void main(){ gl_FragColor = pack(gl_FragCoord.z); }';
  var PVS = 'attribute vec3 aPos; attribute float aA; uniform mat4 uVP; uniform float uSize; varying float vA;' +
    'void main(){ vA = aA; gl_Position = uVP*vec4(aPos,1.0); gl_PointSize = uSize/gl_Position.w; }';
  var PFS = 'precision mediump float; uniform vec3 uC; uniform float uO; varying float vA;' +
    'void main(){ vec2 d = gl_PointCoord-0.5; float r = dot(d,d); if(r>0.25) discard; gl_FragColor = vec4(uC, (1.0-r*4.0)*uO*vA); }';

  function prog(vs, fs) {
    function sh(t, s) { var o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o);
      if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) { throw new Error(gl.getShaderInfoLog(o)); } return o; }
    var p = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p); if (!gl.getProgramParameter(p, gl.LINK_STATUS)) { throw new Error(gl.getProgramInfoLog(p)); }
    var u = {}, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (var i = 0; i < n; i++) { var a = gl.getActiveUniform(p, i); u[a.name] = gl.getUniformLocation(p, a.name); }
    return { p: p, u: u, aPos: gl.getAttribLocation(p, 'aPos'), aNor: gl.getAttribLocation(p, 'aNor'), aA: gl.getAttribLocation(p, 'aA') };
  }
  var P = prog(VS, FS), PD = prog(DVS, DFS), PP = prog(PVS, PFS);

  // ---------------------------------------------------------------- meshes
  function mesh(pos, nor, idx) {
    var b1 = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b1); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(pos), gl.STATIC_DRAW);
    var b2 = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b2); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(nor), gl.STATIC_DRAW);
    var b3 = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, b3); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(idx), gl.STATIC_DRAW);
    return { p: b1, n: b2, i: b3, c: idx.length };
  }
  function boxMesh() {
    var F = [[[1, 0, 0], [0, 0, -1], [0, 1, 0]], [[-1, 0, 0], [0, 0, 1], [0, 1, 0]], [[0, 1, 0], [1, 0, 0], [0, 0, -1]],
             [[0, -1, 0], [1, 0, 0], [0, 0, 1]], [[0, 0, 1], [1, 0, 0], [0, 1, 0]], [[0, 0, -1], [-1, 0, 0], [0, 1, 0]]];
    var p = [], n = [], i = [];
    F.forEach(function (f, k) {
      var N = f[0], U = f[1], V = f[2];
      [[-1, -1], [1, -1], [1, 1], [-1, 1]].forEach(function (q) {
        p.push(0.5 * (N[0] + q[0] * U[0] + q[1] * V[0]), 0.5 * (N[1] + q[0] * U[1] + q[1] * V[1]), 0.5 * (N[2] + q[0] * U[2] + q[1] * V[2]));
        n.push(N[0], N[1], N[2]);
      });
      var o = k * 4; i.push(o, o + 1, o + 2, o, o + 2, o + 3);
    });
    return mesh(p, n, i);
  }
  function sphereMesh(seg, ring) {
    var p = [], n = [], i = [];
    for (var r = 0; r <= ring; r++) for (var s = 0; s <= seg; s++) {
      var th = r / ring * Math.PI, ph = s / seg * 2 * Math.PI;
      var x = Math.sin(th) * Math.cos(ph), y = Math.cos(th), z = Math.sin(th) * Math.sin(ph);
      p.push(x * 0.5, y * 0.5, z * 0.5); n.push(x, y, z);
    }
    for (r = 0; r < ring; r++) for (s = 0; s < seg; s++) {
      var a = r * (seg + 1) + s, b = a + seg + 1; i.push(a, b, a + 1, b, b + 1, a + 1);
    }
    return mesh(p, n, i);
  }
  var BOX = boxMesh(), SPH = sphereMesh(18, 12);

  // ---------------------------------------------------------------- scene
  var objs = [];
  function add(o) {
    o.mesh = o.mesh || BOX; o.ry = o.ry || 0; o.alpha = o.alpha == null ? 1 : o.alpha;
    o.color = hexLin(o.hex || '#CCCCCC'); o.emis = o.emis || [0, 0, 0]; o.spec = o.spec || 0.05;
    o.cast = o.cast !== false; o.show = o.show !== false; o.update = function () {
      this.m = trs(this.t, this.ry, this.s); this.nm = normalMat(this.ry, this.s);
    };
    o.update(); objs.push(o); return o;
  }
  var RW = 10, RD = 6, RH = 3.2, WT = 0.2;          // أبعاد بصرية للقاعة (60 م²)
  var WIN = { z0: -2.6, z1: 2.6, y0: 0.85, y1: 2.75 }; // فتحة النافذة في الجدار الخارجي (z = -3)
  var C = {
    wall: '#ECE7DF', wall2: '#E4DED4', floor: '#C9B79C', frame: '#5B6B80', glass: '#BFE0F7', blind: '#E6E1D4',
    desk: '#B08D62', chair: '#1C3D6A', leg: '#3A4655', robe: '#F2F2EE', skin: '#B9835F', screen: '#0F2340',
    ac: '#F7F8FA', light: '#FFFFFF', ground: '#D9C8A5', bld: '#CDBFA2', gold: '#CC9E0A'
  };
  // الأرض الخارجية ومبانٍ بسيطة للسياق
  add({ t: [0, -0.06, 0], s: [70, 0.1, 70], hex: C.ground, cast: false });
  [[-34, -30, 6, 6], [32, -34, 8, 5], [-36, 28, 7, 6], [36, 26, 6, 7]].forEach(function (b) {
    add({ t: [b[0], b[3] / 2, b[1]], s: [b[2], b[3], b[2] * 0.8], hex: C.bld });
  });
  // الأرضية والجدران (كل جدار يعرف اتجاهه الخارجي ليُخفى إذا كانت الكاميرا خلفه)
  add({ t: [0, 0.02, 0], s: [RW, 0.04, RD], hex: C.floor, spec: 0.12 });
  var walls = [];
  function wall(o, side) { o.side = side; walls.push(add(o)); }
  wall({ t: [0, RH / 2, RD / 2 + WT / 2], s: [RW + 2 * WT, RH, WT], hex: C.wall }, '+z');
  wall({ t: [-RW / 2 - WT / 2, RH / 2, 0], s: [WT, RH, RD], hex: C.wall2 }, '-x');
  wall({ t: [RW / 2 + WT / 2, RH / 2, 0], s: [WT, RH, RD], hex: C.wall2 }, '+x');
  // الجدار ذو النافذة (z = -3): أربع قطع حول الفتحة
  var zW = -RD / 2 - WT / 2;
  wall({ t: [0, WIN.y0 / 2, zW], s: [RW + 2 * WT, WIN.y0, WT], hex: C.wall }, '-z');
  wall({ t: [0, (RH + WIN.y1) / 2, zW], s: [RW + 2 * WT, RH - WIN.y1, WT], hex: C.wall }, '-z');
  wall({ t: [(-RW / 2 - WT + WIN.z0) / 2, (WIN.y0 + WIN.y1) / 2, zW], s: [WIN.z0 + RW / 2 + WT, WIN.y1 - WIN.y0, WT], hex: C.wall }, '-z');
  wall({ t: [(RW / 2 + WT + WIN.z1) / 2, (WIN.y0 + WIN.y1) / 2, zW], s: [RW / 2 + WT - WIN.z1, WIN.y1 - WIN.y0, WT], hex: C.wall }, '-z');
  // السقف: يلقي الظل دائماً، ويُرسم فقط إذا كانت الكاميرا تحته
  var ceiling = add({ t: [0, RH + 0.05, 0], s: [RW + 2 * WT, 0.1, RD + 2 * WT], hex: '#F4F2EE' });
  // إطار النافذة وقواطعها والزجاج
  var wy = (WIN.y0 + WIN.y1) / 2, wh = WIN.y1 - WIN.y0;
  for (var mz = WIN.z0; mz <= WIN.z1 + 0.01; mz += (WIN.z1 - WIN.z0) / 4) {
    add({ t: [mz, wy, zW], s: [0.06, wh, 0.26], hex: C.frame, spec: 0.3 });
  }
  add({ t: [(WIN.z0 + WIN.z1) / 2, WIN.y0 - 0.03, zW + 0.05], s: [WIN.z1 - WIN.z0 + 0.1, 0.06, 0.36], hex: C.frame });
  add({ t: [(WIN.z0 + WIN.z1) / 2, WIN.y1 + 0.03, zW], s: [WIN.z1 - WIN.z0 + 0.1, 0.06, 0.26], hex: C.frame });
  var glass = add({ t: [(WIN.z0 + WIN.z1) / 2, wy, zW], s: [WIN.z1 - WIN.z0, wh, 0.02], hex: C.glass, alpha: 0.16, cast: false, spec: 0.8 });
  // الستارة الأسطوانية: تنزل من الأعلى بنسبة التظليل
  var blindBox = add({ t: [0, 0, zW + 0.16], s: [WIN.z1 - WIN.z0, 0.01, 0.03], hex: C.blind, spec: 0.02 });
  var blindRoll = add({ t: [(WIN.z0 + WIN.z1) / 2, WIN.y1 + 0.08, zW + 0.16], s: [WIN.z1 - WIN.z0 + 0.1, 0.14, 0.14], hex: '#D3CDBE' });
  // الشاشة التعليمية على الجدار الأمامي (x = +5)
  add({ t: [RW / 2 - 0.04, 1.75, 0], s: [0.06, 1.25, 2.4], hex: '#20262E', spec: 0.6 });
  var screen = add({ t: [RW / 2 - 0.08, 1.75, 0], s: [0.02, 1.13, 2.28], hex: C.screen, emis: [0.05, 0.12, 0.25], spec: 0.9 });
  add({ t: [RW / 2 - 0.9, 0.5, 0], s: [0.7, 1.0, 1.4], hex: '#8E6C47' }); // منصة المحاضر
  // المكيّف (وحدة جدارية على الجدار الخلفي x = -5) وفتحة خروج الهواء
  var acX = -RW / 2 + 0.2, acY = 2.7, acZ = 0;
  add({ t: [acX, acY, acZ], s: [0.32, 0.36, 1.3], hex: C.ac, spec: 0.4 });
  add({ t: [acX + 0.165, acY - 0.12, acZ], s: [0.01, 0.06, 1.1], hex: '#9AA7B6' });
  var acLed = add({ t: [acX + 0.17, acY + 0.08, acZ + 0.5], s: [0.01, 0.03, 0.06], hex: '#22C55E', cast: false });
  // إنارة السقف (ألواح مضيئة): تعمل عند الإشغال فقط — مثل افتراض النموذج
  var lights = [];
  [-3, 0, 3].forEach(function (x) { [-1.5, 1.5].forEach(function (z) {
    lights.push(add({ t: [x, RH - 0.02, z], s: [1.2, 0.03, 0.6], hex: '#F2F4F7', cast: false }));
  }); });
  // المقاعد: 5 صفوف × 6 = 30 مقعداً، والطلاب
  var seats = [];
  var rowsX = [-3.4, -2.1, -0.8, 0.5, 1.8], colsZ = [-2.25, -1.4, -0.55, 0.55, 1.4, 2.25];
  rowsX.forEach(function (x) { colsZ.forEach(function (z) {
    add({ t: [x + 0.34, 0.74, z], s: [0.5, 0.04, 0.72], hex: C.desk, spec: 0.25 });
    add({ t: [x + 0.34, 0.37, z - 0.33], s: [0.04, 0.72, 0.04], hex: C.leg });
    add({ t: [x + 0.34, 0.37, z + 0.33], s: [0.04, 0.72, 0.04], hex: C.leg });
    add({ t: [x - 0.12, 0.45, z], s: [0.42, 0.06, 0.44], hex: C.chair });
    add({ t: [x - 0.32, 0.72, z], s: [0.05, 0.5, 0.44], hex: C.chair });
    add({ t: [x - 0.12, 0.22, z], s: [0.05, 0.44, 0.05], hex: C.leg });
    seats.push({ x: x, z: z });
  }); });
  // ترتيب طبيعي لجلوس الطلاب (حتمي): الوسط والأمام أولاً مع تفاوت بسيط
  seats.forEach(function (s, i) { s.k = Math.abs(s.z) * 0.7 + (s.x + 4) * 0.35 + ((i * 7919) % 13) / 13 * 0.9; });
  seats.sort(function (a, b) { return a.k - b.k; });
  var students = seats.slice(0, S.capacity).map(function (s) {
    var body = add({ t: [s.x - 0.1, 0.82, s.z], s: [0.36, 0.62, 0.42], hex: C.robe });
    var head = add({ t: [s.x - 0.08, 1.27, s.z], s: [0.24, 0.27, 0.24], mesh: SPH, hex: C.skin, spec: 0.15 });
    var cap = add({ t: [s.x - 0.09, 1.34, s.z], s: [0.27, 0.12, 0.27], mesh: SPH, hex: '#F5F5F2' });
    return [body, head, cap];
  });
  // طبقة الحالة الحرارية المفهومية: حجم هواء شفاف ملوّن بحرارة القاعة المحسوبة (ليس توزيعاً مكانياً)
  var air = add({ t: [0, RH / 2, 0], s: [RW - 0.1, RH - 0.1, RD - 0.1], hex: '#9AD8C2', alpha: 0.0, cast: false });
  // قرص الشمس
  var sun = add({ t: [0, -50, 0], s: [2.4, 2.4, 2.4], mesh: SPH, hex: '#FFF1C2', emis: [3.2, 2.7, 1.6], cast: false });

  // ---------------------------------------------------------------- airflow particles
  var NP = 220, pPos = new Float32Array(NP * 3), pA = new Float32Array(NP), pSeed = [];
  for (var k = 0; k < NP; k++) { pSeed.push([Math.random(), Math.random(), Math.random()]); }
  var pBuf = gl.createBuffer(), aBuf = gl.createBuffer();

  // ---------------------------------------------------------------- shadow map
  var SM = 2048, smTex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, smTex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, SM, SM, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
  [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER].forEach(function (f) { gl.texParameteri(gl.TEXTURE_2D, f, gl.NEAREST); });
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  var smFB = gl.createFramebuffer(), smRB = gl.createRenderbuffer();
  gl.bindRenderbuffer(gl.RENDERBUFFER, smRB); gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT16, SM, SM);
  gl.bindFramebuffer(gl.FRAMEBUFFER, smFB);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, smTex, 0);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, smRB);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);

  // ---------------------------------------------------------------- camera
  var CAMS = { 'default': [0.62, 0.62, 15.5, [0, 0.9, 0]], top: [0.001, 1.45, 14, [0, 0, 0]], inside: [1.03, 0.09, 7.2, [-2.0, 1.1, -1.5]] };
  var cam = { yaw: 0, pitch: 0, dist: 0, tgt: [0, 0, 0] };
  function setCam(n) { var c = CAMS[n]; cam.yaw = c[0]; cam.pitch = c[1]; cam.dist = c[2]; cam.tgt = c[3].slice(); }
  setCam('default');
  function camPos() {
    var cp = Math.cos(cam.pitch);
    return [cam.tgt[0] + cam.dist * cp * Math.sin(cam.yaw), cam.tgt[1] + cam.dist * Math.sin(cam.pitch), cam.tgt[2] + cam.dist * cp * Math.cos(cam.yaw)];
  }
  var drag = null, pts = {};
  cv.addEventListener('pointerdown', function (e) {
    cv.setPointerCapture(e.pointerId); pts[e.pointerId] = [e.clientX, e.clientY];
    drag = { pan: e.button === 2 || e.shiftKey, x: e.clientX, y: e.clientY };
  });
  cv.addEventListener('pointermove', function (e) {
    if (!drag || !pts[e.pointerId]) { return; }
    var ids = Object.keys(pts);
    if (ids.length === 2) { // تكبير باللمس
      var o = pts[ids[0]], q = pts[ids[1]], d0 = Math.hypot(o[0] - q[0], o[1] - q[1]);
      pts[e.pointerId] = [e.clientX, e.clientY]; o = pts[ids[0]]; q = pts[ids[1]];
      var d1 = Math.hypot(o[0] - q[0], o[1] - q[1]); cam.dist = clamp(cam.dist * d0 / (d1 || 1), 2.5, 30); return;
    }
    var dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY; pts[e.pointerId] = [e.clientX, e.clientY];
    if (drag.pan) {
      var s = cam.dist * 0.0016, cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
      cam.tgt[0] += (-dx * cy) * s; cam.tgt[2] += (dx * sy) * s; cam.tgt[1] = clamp(cam.tgt[1] + dy * s, 0, 3);
    } else {
      cam.yaw -= dx * 0.006; cam.pitch = clamp(cam.pitch + dy * 0.005, 0.05, 1.5);
    }
  });
  function up(e) { delete pts[e.pointerId]; if (!Object.keys(pts).length) { drag = null; } }
  cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
  cv.addEventListener('contextmenu', function (e) { e.preventDefault(); });
  cv.addEventListener('wheel', function (e) { e.preventDefault(); cam.dist = clamp(cam.dist * (1 + e.deltaY * 0.0012), 2.5, 30); }, { passive: false });
  root.querySelectorAll('[data-cam]').forEach(function (b) { b.addEventListener('click', function () { setCam(b.getAttribute('data-cam')); }); });

  // ---------------------------------------------------------------- simulation state (from Python)
  // ---------------------------------------------------------------- playback (presentation only)
  // الموضع p ∈ [0, n]: الموضع k = الوقت k×Δt (15 دقيقة)؛ p = n يعني نهاية اليوم 24:00 (النتيجة النهائية).
  // السرعة تغيّر سرعة العرض فقط: 1× = خطوة 15 دقيقة كل 0.5 ثانية. Δt والنتائج لا تتغير.
  var STEP_SEC = 0.5;
  var st = { p: S.start_index || 0, i: S.start_index || 0, end: false, playing: false, started: false, speed: 1, acc: 0, view: 'zilal', start: S.start_index || 0 };
  var range = document.getElementById('zl3d-range'), playBtn = document.getElementById('zl3d-play');
  function Cs() { return S.cases[st.view]; }
  function setIndex(p) {
    st.p = clamp(p | 0, 0, S.n); st.end = st.p === S.n; st.i = Math.min(st.p, S.n - 1);
    range.value = st.p; hud(); deck();
  }
  range.addEventListener('input', function () { setIndex(+range.value); });
  playBtn.addEventListener('click', function () {
    if (st.playing) { st.playing = false; }
    else { if (st.p >= S.n) { setIndex(st.start); } st.playing = true; st.started = true; st.acc = 0; }
    playLabel(); hud();
  });
  document.getElementById('zl3d-reset').addEventListener('click', function () {
    st.playing = false; st.started = false; st.acc = 0; setIndex(st.start); playLabel();
  });
  root.querySelectorAll('[data-step]').forEach(function (b) {
    b.addEventListener('click', function () { setIndex(st.p + (+b.getAttribute('data-step'))); playLabel(); });
  });
  function paintSpeed() { root.querySelectorAll('[data-speed]').forEach(function (b) { b.setAttribute('aria-pressed', String(+b.getAttribute('data-speed') === st.speed)); }); }
  root.querySelectorAll('[data-speed]').forEach(function (b) {
    b.addEventListener('click', function () { st.speed = +b.getAttribute('data-speed'); paintSpeed(); });
  });
  function paintView() { root.querySelectorAll('[data-view]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-view') === st.view)); }); }
  function setView(v) { if (!S.cases[v]) { return; } st.view = v; paintView(); applyRun(); hud(); }
  root.querySelectorAll('[data-view]').forEach(function (b) { b.addEventListener('click', function () { setView(b.getAttribute('data-view')); }); });
  function playLabel() { playBtn.textContent = st.playing ? '❚❚ ' + L.pause : (st.started && !st.end ? '▶ ' + L.resume : '▶ ' + L.start); }

  // ---------------------------------------------------------------- live comparison deck (values from Python)
  function fx(x, d) { return (x === null || x === undefined) ? L.na : '<span dir="ltr" class="n">' + Number(x).toFixed(d) + '</span>'; }
  function sg(x, d) { if (x === null || x === undefined) { return L.na; } var v = Number(x).toFixed(d); return '<span dir="ltr" class="n">' + (x > 0 && +v !== 0 ? '+' : '') + v + '</span>'; }
  var STAT = ['empty', 'ok', 'hot', 'cold'];
  function deck() {
    var C = S.cases.conv, Z = S.cases.zilal, K = S.compare, p = st.p, i = st.i, end = st.end;
    var eC = end ? C.e_day : C.e_upto[p], eZ = end ? Z.e_day : Z.e_upto[p];
    var cC = end ? (C.final.applicable ? C.final.compliance : null) : C.comp_cum[i];
    var cZ = end ? (Z.final.applicable ? Z.final.compliance : null) : Z.comp_cum[i];
    var saved = end ? K.final.saved_kwh : K.saved_kwh[p], pct = end ? K.final.saved_pct : K.saved_pct[p];
    var dComp = end ? K.final.d_comp_pp : K.d_comp_pp[i];
    document.getElementById('zl-dk-time').innerHTML = end ? '<span class="n">24:00</span> · ' + L.final + ' · <span class="n">00:00–24:00</span>' : '<span class="n">' + hhmm(S.hour[i]) + '</span>';
    function st8(c) { var k = STAT[c.comfort[i]]; return '<span class="zl-st ' + k + '">' + L[k] + '</span>'; }
    function pc(x) { return x === null || x === undefined ? L.noOcc : '<span dir="ltr" class="n">' + (Math.round(x * 1000) / 10) + '%</span>'; }
    function nowRow(lbl, f, d) { return [lbl, end ? L.na : fx(f(C), d), end ? L.na : fx(f(Z), d), end ? L.na : sg(f(Z) - f(C), d)]; }
    function eRow(lbl, ea, ed_, d) { var a1 = end ? ed_(C) : ea(C)[p], a2 = end ? ed_(Z) : ea(Z)[p]; return [lbl, fx(a1, d), fx(a2, d), sg(a2 - a1, d)]; }
    var rows = [
      nowRow(L.rowCool, function (c) { return c.q_cool_kw[i]; }, 2),
      nowRow(L.rowPower, function (c) { return c.p_el_kw[i]; }, 2),
      nowRow(L.rowLight, function (c) { return c.p_light_kw[i]; }, 2),
      nowRow(L.rowTotal, function (c) { return c.p_total_kw[i]; }, 2),
      eRow(L.rowEnergyH, function (c) { return c.e_upto_hvac; }, function (c) { return c.e_day_hvac; }, 2),
      eRow(L.rowEnergyL, function (c) { return c.e_upto_light; }, function (c) { return c.e_day_light; }, 2),
      [L.rowEnergy, fx(eC, 2), fx(eZ, 2), sg(eZ - eC, 2)],
      nowRow(L.rowTemp, function (c) { return c.t_in[i]; }, 1),
      [L.rowStatus, end ? L.na : st8(C), end ? L.na : st8(Z), ''],
      [L.rowComp, pc(cC), pc(cZ), dComp === null || dComp === undefined ? L.na : sg(dComp, 1) + ' ' + L.comfortPts]
    ];
    document.getElementById('zl-dk-body').innerHTML = rows.map(function (r, k) {
      return '<tr' + (k === 6 ? ' class="hl"' : (k === 3 ? ' class="sub"' : '')) + '><th>' + r[0] + '</th><td class="c">' + r[1] + '</td><td class="z">' + r[2] + '</td><td class="d">' + r[3] + '</td></tr>';
    }).join('');
    var worse = dComp !== null && dComp !== undefined && dComp < -0.5;
    var zBad = cZ !== null && cZ !== undefined && cZ < 0.95;  // حد الراحة الموحّد
    var v, vc;
    if (saved > 0.005) { if (worse || zBad) { v = L.vCost; vc = 'bad'; } else { v = L.vGood; vc = 'ok'; } }
    else if (saved < -0.005) { v = L.vMore; vc = 'warn'; }
    else { v = L.vEqual; vc = ''; }
    var vEl = document.getElementById('zl-dk-verdict'); vEl.textContent = v; vEl.className = 'zl-verdict ' + vc;
    function tile(lbl, val, unit, cls) { return '<div class="zl-kpi ' + (cls || '') + '"><small>' + lbl + '</small><b>' + val + '</b><span>' + unit + '</span></div>'; }
    var sH = end ? K.final.saved_hvac_kwh : K.saved_hvac_kwh[p], sL = end ? K.final.saved_light_kwh : K.saved_light_kwh[p];
    document.getElementById('zl-dk-kpis').innerHTML =
      tile(L.saved, sg(saved, 2), 'kWh', saved > 0.005 ? 'pos' : (saved < -0.005 ? 'neg' : '')) +
      tile(L.savedPct, pct === null || pct === undefined ? L.na : sg(pct, 1).replace('</span>', '%</span>'), L.energyCum, pct > 0 ? 'pos' : (pct < 0 ? 'neg' : '')) +
      tile(L.savedSplit, L.partH + ' ' + sg(sH, 2) + ' · ' + L.partL + ' ' + sg(sL, 2), 'kWh', 'zl-split') +
      tile(L.dComp, dComp === null || dComp === undefined ? L.na : sg(dComp, 1), L.comfortPts, worse ? 'neg' : '');
    power(p);
  }
  // القدرة الكهربائية اللحظية (kW) للحالتين حتى اللحظة المعروضة + لحظات قرار ظِلال (محسوبة في Python)
  // رسم واحد بمسارين متطابقي المقياس: التقليدي (أعلى) وظِلال (أسفل). لكل مسار: تكييف (أزرق) + إنارة (ذهبي)
  // مكدّسان، والحد العلوي = القدرة الكلية. كل القيم من Python؛ هنا رسم فقط.
  var COL_H = '#4AA3DF', COL_L = '#E8C766';
  function power(p) {
    var C = S.cases.conv, Z = S.cases.zilal, W = 680, n = S.n, l = 40, r = 64, t0 = 30, laneH = 78, gap = 22, b = 22;
    var H = t0 + laneH * 2 + gap + b;
    var top = Math.max(Math.max.apply(null, C.p_total_kw), Math.max.apply(null, Z.p_total_kw), 0.5) * 1.1;
    function X(k) { return l + (W - l - r) * k / n; }
    function lane(c, y0, name, showEv) {
      function Y(v) { return y0 + laneH - laneH * v / top; }
      var g = '', a = -1, last = Math.min(p, n), k;
      for (k = 0; k <= n; k++) {
        var o = k < n && S.occ[k] > 0;
        if (o && a < 0) { a = k; }
        if (!o && a >= 0) { g += '<rect x="' + X(a).toFixed(1) + '" y="' + y0 + '" width="' + (X(k) - X(a)).toFixed(1) + '" height="' + laneH + '" fill="rgba(204,158,10,.13)"/>'; a = -1; }
      }
      g += '<line x1="' + l + '" x2="' + (W - r) + '" y1="' + (y0 + laneH) + '" y2="' + (y0 + laneH) + '" stroke="rgba(255,255,255,.25)"/>';
      g += '<line x1="' + l + '" x2="' + (W - r) + '" y1="' + Y(top / 1.1).toFixed(1) + '" y2="' + Y(top / 1.1).toFixed(1) + '" stroke="rgba(255,255,255,.10)"/>';
      g += '<text x="' + (l - 4) + '" y="' + (Y(top / 1.1) + 3).toFixed(1) + '" text-anchor="end">' + (top / 1.1).toFixed(1) + '</text><text x="' + (l - 4) + '" y="' + (y0 + laneH + 3) + '" text-anchor="end">0</text>';
      // مساحات مكدسة بخطوات ثابتة لكل 15 دقيقة
      var dH = '', dT = '', line = '';
      for (k = 0; k < last; k++) {
        var x1 = X(k).toFixed(1), x2 = X(k + 1).toFixed(1), yh = Y(c.p_el_kw[k]).toFixed(1), yt = Y(c.p_total_kw[k]).toFixed(1), yb = (y0 + laneH).toFixed(1);
        dH += 'M' + x1 + ' ' + yb + 'L' + x1 + ' ' + yh + 'L' + x2 + ' ' + yh + 'L' + x2 + ' ' + yb + 'Z';
        dT += 'M' + x1 + ' ' + yh + 'L' + x1 + ' ' + yt + 'L' + x2 + ' ' + yt + 'L' + x2 + ' ' + yh + 'Z';
        line += (k ? 'L' : 'M') + x1 + ' ' + yt + 'L' + x2 + ' ' + yt;
      }
      g += '<path d="' + dH + '" fill="' + COL_H + '" fill-opacity=".85"/><path d="' + dT + '" fill="' + COL_L + '" fill-opacity=".9"/>';
      g += '<path d="' + line + '" fill="none" stroke="#FFFFFF" stroke-width="1.2" stroke-opacity=".9"/>';
      g += '<text x="' + (W - r + 6) + '" y="' + (y0 + 12) + '" class="ln">' + name + '</text>';
      if (p < n || p === n) {
        var kk = Math.min(Math.max(p, 0), n - 1), val = p >= n ? null : c.p_total_kw[kk];
        g += '<text x="' + (W - r + 6) + '" y="' + (y0 + 30) + '" class="nv">' + (val === null ? '—' : val.toFixed(2) + ' kW') + '</text>';
      }
      if (showEv) {
        (c.events || []).forEach(function (e) {
          if (e.k > p || (e.kind !== 'precool' && e.kind !== 'off')) { return; }
          var x = X(e.k), left = e.kind === 'precool';
          g += '<line x1="' + x.toFixed(1) + '" x2="' + x.toFixed(1) + '" y1="' + y0 + '" y2="' + (y0 + laneH) + '" stroke="#3DD6A6" stroke-dasharray="2 3"/>';
          g += '<text x="' + (x + (left ? -4 : 4)).toFixed(1) + '" y="' + (y0 + (left ? 12 : 26)) + '" text-anchor="' + (left ? 'end' : 'start') + '" class="ev">' + (left ? L.evPrecool : L.evOff) + ' ' + hhmm(S.hour[e.k]) + '</text>';
        });
      }
      return g;
    }
    var g = '';
    g += '<text x="' + (W - r) + '" y="14" class="tt" text-anchor="end">' + L.powerTitle + '</text>';
    g += '<rect x="' + l + '" y="6" width="10" height="10" rx="2" fill="' + COL_H + '"/><text x="' + (l + 14) + '" y="15">' + L.partH + '</text>';
    g += '<rect x="' + (l + 62) + '" y="6" width="10" height="10" rx="2" fill="' + COL_L + '"/><text x="' + (l + 76) + '" y="15">' + L.partL + '</text>';
    g += '<line x1="' + (l + 122) + '" x2="' + (l + 138) + '" y1="11" y2="11" stroke="#FFF" stroke-width="1.4"/><text x="' + (l + 142) + '" y="15">' + L.partT + '</text>';
    g += '<text x="' + (l - 4) + '" y="' + (t0 - 4) + '" text-anchor="end" class="ln">kW</text>';
    g += lane(C, t0, L.conv, false);
    g += lane(Z, t0 + laneH + gap, L.zilal, true);
    for (var h = 0; h <= 24; h += 2) { g += '<text x="' + X(h * 4).toFixed(1) + '" y="' + (H - 7) + '" text-anchor="middle">' + String(h).padStart(2, '0') + '</text>'; }
    g += '<line x1="' + X(p).toFixed(1) + '" x2="' + X(p).toFixed(1) + '" y1="' + t0 + '" y2="' + (H - b) + '" stroke="#CC9E0A" stroke-dasharray="3 3"/>';
    var svg = document.getElementById('zl-dk-pw'); svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.innerHTML = g;
  }
  function hhmm(h) { var m = Math.round(h * 60); return String(Math.floor(m / 60) % 24).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'); }
  function f1(x) { return (Math.round(x * 10) / 10).toFixed(1); }
  function hud() {
    var i = st.i, c = Cs(), t = c.t_in[i], occ = S.occ[i] > 0, inBand = t >= S.band[0] - 1e-9 && t <= S.band[1] + 1e-9;
    var clock = st.end ? '24:00' : hhmm(S.hour[i]);
    document.getElementById('zl3d-clock').textContent = clock; document.getElementById('zl3d-now').textContent = clock;
    var tin = document.getElementById('zl3d-tin'); tin.textContent = f1(t) + '°';
    tin.style.color = inBand ? '#3DD6A6' : (t > S.band[1] ? '#FF8A80' : '#8DB3EA');
    var ch = document.getElementById('zl3d-comfort');
    ch.textContent = !occ ? L.empty : (inBand ? '✓ ' + L.comfortOk : '✗ ' + (t > S.band[1] ? L.tooHot : L.tooCold));
    ch.className = 'zl-chip ' + (!occ ? '' : (inBand ? 'ok' : 'bad'));
    document.getElementById('zl3d-tout').textContent = f1(S.t_out[i]) + '°';
    document.getElementById('zl3d-occ').textContent = S.occ[i] + ' / ' + S.capacity;
    document.getElementById('zl3d-sol').textContent = f1(S.q_solar[i] / 1000) + ' kW';
    document.getElementById('zl3d-cool').textContent = f1(c.q_cool_kw[i]) + ' kW';
    document.getElementById('zl3d-coolbar').style.width = clamp(c.q_cool_kw[i] * 1000 / S.q_max * 100, 0, 100) + '%';
    var on = c.q_cool_kw[i] > 0.001;
    var hv = document.getElementById('zl3d-hvac'); hv.textContent = on ? L.on : L.off; hv.style.color = on ? '#8DD3FF' : '#A9B6C8';
    var lo = !st.end && c.light_on[i], lt = document.getElementById('zl3d-light');
    lt.textContent = lo ? c.p_light_kw[i].toFixed(2) + ' kW · ' + L.lightsOn : L.lightsOff;  // الخانة LTR lt.style.color = lo ? '#F2D88A' : '#A9B6C8';
    document.getElementById('zl3d-ecum').textContent = (st.end ? c.e_day : c.e_upto[st.p]).toFixed(2) + ' kWh';
    document.getElementById('zl3d-live').className = 'zl-dot' + (st.playing ? ' on' : '');
  }
  // العناصر المرتبطة بمدخلات التشغيل كلها؛ تُعاد عند تحميل حالة جديدة (window.__zl3d.load)
  function applyRun() {
  // شريط المحاضرة على المسار الزمني (من مصفوفة الإشغال المحسوبة)
  (function () {
    var a = -1, b = -1; for (var j = 0; j < S.n; j++) { if (S.occ[j] > 0) { if (a < 0) { a = j; } b = j; } }
    var el = document.getElementById('zl3d-lect');
    el.style.display = a < 0 ? 'none' : 'block';
    if (a >= 0) { el.style.left = (a / S.n * 100) + '%'; el.style.width = ((b - a + 1) / S.n * 100) + '%'; }
  })();
  document.getElementById('zl3d-orient').textContent = L.windowFaces + ' ' + S.orientation_label;
  document.getElementById('zl3d-needle').setAttribute('transform', 'rotate(' + ({ East: 90, South: 180, West: 270 }[S.orientation] || 0) + ' 20 20)');

  (function ring() {
    var c = Cs().final.compliance, el = document.getElementById('zl3d-ringc');
    el.setAttribute('stroke', c >= 0.95 ? '#3DD6A6' : (c >= 0.8 ? '#E8C766' : '#FF8A80'));
    el.setAttribute('stroke-dasharray', (2 * Math.PI * 26 * c).toFixed(1) + ' 999');
    document.getElementById('zl3d-comp').textContent = Math.round(c * 100) + '%';
    document.getElementById('zl3d-eday').textContent = Cs().label + ' · ' + L.energyDay + ' ' + Cs().final.energy_kwh.toFixed(2) + ' kWh';
  })();
  shade = clamp(S.shading, 0, 1); placeBlind();
  }

  // ---------------------------------------------------------------- per-frame scene update from state
  var BEAR = { East: 90, South: 180, West: 270 };
  function sunState(i) {
    var h = S.hour[i], p = (h - 6) / 12.75;
    if (p <= 0 || p >= 1) { return { dir: [0, -1, 0], up: false, k: 0 }; }
    var elev = 75 * Math.sin(Math.PI * p) * Math.PI / 180;
    var a = ((90 + 180 * p) - (BEAR[S.orientation] || 270)) * Math.PI / 180; // زاوية الشمس نسبةً لاتجاه النافذة
    var dir = norm([Math.cos(elev) * Math.sin(a), Math.sin(elev), -Math.cos(elev) * Math.cos(a)]);
    // الشدة البصرية تتبع إشعاع الواجهة المحسوب في Python (g_facade) — لا حساب مستقل هنا
    return { dir: dir, up: true, k: clamp(S.g_facade[i] / 750, 0, 1.25), elev: elev };
  }
  function tempColor(t) {
    var stops = [[22, [0.36, 0.55, 0.93]], [24, [0.24, 0.78, 0.62]], [25.5, [0.40, 0.80, 0.55]], [27, [0.98, 0.72, 0.30]], [29.5, [0.97, 0.50, 0.25]], [32, [0.93, 0.30, 0.22]]];
    if (t <= stops[0][0]) { return stops[0][1]; }
    for (var j = 1; j < stops.length; j++) {
      if (t <= stops[j][0]) { var f = (t - stops[j - 1][0]) / (stops[j][0] - stops[j - 1][0]), a = stops[j - 1][1], b = stops[j][1];
        return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]; }
    }
    return stops[stops.length - 1][1];
  }
  var shade = clamp(S.shading, 0, 1);
  function placeBlind() {
    var hgt = Math.max(0.01, shade * wh);
    blindBox.t = [(WIN.z0 + WIN.z1) / 2, WIN.y1 - hgt / 2, zW + 0.16]; blindBox.s = [WIN.z1 - WIN.z0, hgt, 0.03]; blindBox.update();
    blindBox.show = shade > 0.005;
  }

  // ---------------------------------------------------------------- render
  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2), w = vpEl.clientWidth, h = vpEl.clientHeight;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
  }
  function bindMesh(pr, m, withNormals) {
    gl.bindBuffer(gl.ARRAY_BUFFER, m.p); gl.enableVertexAttribArray(pr.aPos); gl.vertexAttribPointer(pr.aPos, 3, gl.FLOAT, false, 0, 0);
    if (withNormals) { gl.bindBuffer(gl.ARRAY_BUFFER, m.n); gl.enableVertexAttribArray(pr.aNor); gl.vertexAttribPointer(pr.aNor, 3, gl.FLOAT, false, 0, 0); }
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, m.i);
  }
  var last = performance.now();
  function frame(now) {
    var dt = Math.min(0.1, (now - last) / 1000); last = now;
    if (st.playing) {
      st.acc += dt * st.speed;
      while (st.acc >= STEP_SEC) { st.acc -= STEP_SEC; if (st.p < S.n) { setIndex(st.p + 1); } if (st.p >= S.n) { st.playing = false; st.acc = 0; playLabel(); hud(); break; } }
    }
    resize();
    var i = st.i, sunS = sunState(i), cp = camPos();
    var cc = Cs(), occ = S.occ[i], occN = Math.min(occ, students.length), qc = cc.q_cool_kw[i] * 1000 / S.q_max, tin = cc.t_in[i];
    // ظهور الكائنات حسب الكاميرا والحالة المحسوبة
    walls.forEach(function (w) {
      var hide = (w.side === '+z' && cp[2] > RD / 2) || (w.side === '-z' && cp[2] < -RD / 2) ||
                 (w.side === '+x' && cp[0] > RW / 2) || (w.side === '-x' && cp[0] < -RW / 2);
      w.show = !hide;
    });
    ceiling.show = cp[1] < RH;
    students.forEach(function (g, j) { g.forEach(function (o) { o.show = j < occN; }); });
    // الإنارة تتبع حالة الإنارة المحسوبة للحالة المعروضة (جدول ثابت للتقليدي، حسب الإشغال لظِلال)
    var lightsOn = !st.end && cc.light_on[i];
    lights.forEach(function (o) { o.emis = lightsOn ? [1.6, 1.6, 1.5] : [0, 0, 0]; o.show = ceiling.show; });
    screen.emis = occ > 0 ? [0.08, 0.22, 0.5] : [0.01, 0.03, 0.06];
    acLed.color = hexLin(qc > 0.002 ? '#22C55E' : '#64748B'); acLed.emis = qc > 0.002 ? [0.1, 0.8, 0.3] : [0, 0, 0];
    var tc = tempColor(tin); air.color = tc.map(function (x) { return Math.pow(x, 2.2); }); air.alpha = 0.05 + 0.10 * clamp(Math.abs(tin - 24.75) / 5, 0, 1);
    var day = sunS.up;
    sun.show = day; if (day) { sun.t = [sunS.dir[0] * 34, sunS.dir[1] * 34, sunS.dir[2] * 34]; sun.update(); }
    // خلفية السماء حسب الوقت (CSS)
    vpEl.style.setProperty('--sky1', day ? '#9CC3E8' : '#0B1626'); vpEl.style.setProperty('--sky2', day ? '#E7F0F8' : '#1C3D6A');

    var sunCol = day ? [3.1 * sunS.k, 2.85 * sunS.k, 2.45 * sunS.k] : [0, 0, 0];
    var sky = day ? [0.30, 0.36, 0.44] : [0.03, 0.05, 0.10], ground = day ? [0.20, 0.17, 0.13] : [0.02, 0.02, 0.03];
    var fill = lightsOn ? [0.55, 0.55, 0.52] : (day ? [0.10, 0.10, 0.10] : [0.0, 0.0, 0.0]);
    var center = [0, 1.2, 0], useShadow = day && sunS.k > 0.01;
    var upv = Math.abs(sunS.dir[1]) > 0.98 ? [0, 0, 1] : [0, 1, 0];
    var lvp = mul(ortho(-11, 11, -11, 11, 1, 60), lookAt([center[0] + sunS.dir[0] * 25, center[1] + sunS.dir[1] * 25, center[2] + sunS.dir[2] * 25], center, upv));

    gl.enable(gl.DEPTH_TEST); gl.enable(gl.CULL_FACE);
    if (useShadow) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, smFB); gl.viewport(0, 0, SM, SM); gl.clearColor(1, 1, 1, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.useProgram(PD.p); gl.uniformMatrix4fv(PD.u.uLVP, false, lvp); gl.disable(gl.CULL_FACE);
      objs.forEach(function (o) {
        if (!o.cast || o.alpha < 0.99) { return; }
        if (o.mesh !== BOX && o.mesh !== SPH) { return; }
        var visibleCaster = o.show || walls.indexOf(o) >= 0 || o === ceiling;
        if (!visibleCaster) { return; }
        gl.uniformMatrix4fv(PD.u.uM, false, o.m); bindMesh(PD, o.mesh, false); gl.drawElements(gl.TRIANGLES, o.mesh.c, gl.UNSIGNED_SHORT, 0);
      });
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    }
    gl.viewport(0, 0, cv.width, cv.height); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    var vp = mul(persp(0.78, cv.width / Math.max(1, cv.height), 0.1, 200), lookAt(cp, cam.tgt, [0, 1, 0]));
    gl.useProgram(P.p);
    gl.uniformMatrix4fv(P.u.uVP, false, vp); gl.uniformMatrix4fv(P.u.uLVP, false, lvp);
    gl.uniform3fv(P.u.uSunDir, sunS.dir); gl.uniform3fv(P.u.uSun, sunCol); gl.uniform3fv(P.u.uSky, sky); gl.uniform3fv(P.u.uGround, ground);
    gl.uniform3fv(P.u.uFill, fill); gl.uniform1f(P.u.uInDim, lightsOn ? 0.85 : 0.5); gl.uniform3fv(P.u.uCam, cp); gl.uniform1f(P.u.uShadowOn, useShadow ? 1 : 0); gl.uniform1f(P.u.uTexel, 1 / SM);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, smTex); gl.uniform1i(P.u.uSM, 0);
    function draw(o) {
      gl.uniformMatrix4fv(P.u.uM, false, o.m); gl.uniformMatrix3fv(P.u.uN, false, o.nm);
      gl.uniform3fv(P.u.uColor, o.color); gl.uniform3fv(P.u.uEmis, o.emis); gl.uniform1f(P.u.uAlpha, o.alpha); gl.uniform1f(P.u.uSpec, o.spec);
      bindMesh(P, o.mesh, true); gl.drawElements(gl.TRIANGLES, o.mesh.c, gl.UNSIGNED_SHORT, 0);
    }
    gl.disable(gl.BLEND); gl.enable(gl.CULL_FACE);
    objs.forEach(function (o) { if (o.show && o.alpha >= 0.99) { draw(o); } });
    // الشفافة: الزجاج ثم حجم الهواء المفهومي
    gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.depthMask(false); gl.disable(gl.CULL_FACE);
    objs.forEach(function (o) { if (o.show && o.alpha < 0.99 && o.alpha > 0.001) { draw(o); } });

    // جزيئات هواء المكيّف: الكثافة والسرعة تتبع قدرة التبريد المحسوبة / القدرة القصوى
    if (qc > 0.002) {
      var tsec = now / 1000, speed = 0.35 + 0.9 * qc;
      for (var j = 0; j < NP; j++) {
        var sd = pSeed[j], life = (sd[0] + tsec * speed * 0.45) % 1;
        pPos[j * 3] = acX + 0.25 + life * 3.2 + Math.sin(sd[1] * 40 + tsec) * 0.05;
        pPos[j * 3 + 1] = acY - 0.2 - life * life * 1.7;
        pPos[j * 3 + 2] = acZ + (sd[2] - 0.5) * 1.2 * (1 + life * 2.2);
        pA[j] = (1 - life) * (j < NP * Math.max(0.15, qc) ? 1 : 0);
      }
      gl.useProgram(PP.p); gl.uniformMatrix4fv(PP.u.uVP, false, vp);
      gl.uniform1f(PP.u.uSize, 26 * Math.min(window.devicePixelRatio || 1, 2)); gl.uniform3fv(PP.u.uC, [0.55, 0.83, 1.0]); gl.uniform1f(PP.u.uO, 0.55);
      gl.bindBuffer(gl.ARRAY_BUFFER, pBuf); gl.bufferData(gl.ARRAY_BUFFER, pPos, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(PP.aPos); gl.vertexAttribPointer(PP.aPos, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, aBuf); gl.bufferData(gl.ARRAY_BUFFER, pA, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(PP.aA); gl.vertexAttribPointer(PP.aA, 1, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.POINTS, 0, NP);
      gl.disableVertexAttribArray(PP.aA);
    }
    gl.depthMask(true); gl.disable(gl.BLEND);
    window.__zl3dFrames = (window.__zl3dFrames || 0) + 1;
    requestAnimationFrame(frame);
  }
  paintSpeed(); paintView(); applyRun(); setIndex(st.p); playLabel();
  function load(ns, keepTime) {
    if (!ns || ns.n !== S.n) { return; }
    S = ns; st.start = ns.start_index || 0; applyRun(); setIndex(keepTime ? st.p : st.start);
  }
  window.__zl3d = { setIndex: setIndex, state: st, cam: cam, setCam: setCam, load: load, setView: setView };
  requestAnimationFrame(frame);
})();
