/* 집값레이더 업무지구 출퇴근 릴스(9:16).
 * 데이터: data.js 의 window.DATA — build.py 가 cards/commute.py 로 DB 에서 만든다. 단지명·금액·노선·시간은 DATA 의 문자열을 그대로 쓴다.
 *   올라가는 중간 금액만 여기서 계산하고, 멈춘 프레임은 언제나 원문(label)이다. 숫자를 지어내는 곳이 없다.
 * 레이더: 가운데가 업무지구, 가운데에서 멀수록 출퇴근이 오래 걸린다(반지름 = 대략 시간의 가운데 값). 방향은 장식이라 지도가 아니다.
 * 시각: timeline.js 의 큐(intro·r5…r1·sum·outro·end). 배경음도 같은 큐로 합성해 박자가 맞는다.
 * 엔진(engine.js·fx.js)은 third_party/showreel 의 것을 그대로 쓴다. 우리 것은 이 파일과 brand.css 뿐이다. */
const { ease, prog, kf, spring, clamp, lerp, rand, noise, split, stagger, inout, css, h, cue } = REEL;
const D = window.DATA;
const W = 1080, H = 1920, AC = D.accent, N = D.rows.length;
const END = cue('end', 26.4);
const MAXMIN = 50;                                         // 레이더 바깥 고리 = 50분
REEL.config({ duration: END, fps: 30, width: W, height: H, audio: null, push: 0.012 });

function won(v) {
  v = Math.round(v / 100) * 100;
  const eok = Math.floor(v / 10000), man = v % 10000;
  if (eok && man) return `${eok}억 ${man.toLocaleString('en-US')}만`;
  if (eok) return `${eok}억`;
  return `${man.toLocaleString('en-US')}만`;
}
const at = k => cue(`r${k}`, 2.4 * (N - k + 2));
const until = k => (k === 1 ? cue('sum', 19.2) : at(k - 1));
const mid = m => (m[0] + m[1]) / 2;
// 단지마다 정해진 방향(장식) — 같은 데이터면 늘 같은 자리
const angleOf = i => -Math.PI / 2 + i * 2.39996 + rand(i, 11) * 0.5;

/* 노선 칩: 동그라미 안에 호선 숫자나 노선 첫 글자 */
function lineChips(parent, lines, size = 54) {
  const wrap = h('div', 'a', parent); css(wrap, { display: 'flex', gap: '8px' });
  lines.forEach(l => {
    const c = h('div', '', wrap, l.t);
    css(c, { width: `${size}px`, height: `${size}px`, borderRadius: '50%', background: l.c, color: '#fff', fontWeight: 900,
      fontSize: `${l.t.length > 1 ? size * 0.36 : size * 0.56}px`, display: 'flex', alignItems: 'center', justifyContent: 'center',
      border: '3px solid var(--ink)', letterSpacing: '-0.06em' });
  });
  return wrap;
}

/* ── 배경: 연한 바탕 위로 점 격자가 천천히 흐른다 ── */
let bgx;
REEL.overlay(t => {
  bgx.clearRect(0, 0, W, H);
  const step = 54, off = (t * 26) % step;
  for (let y = -step; y < H + step; y += step)
    for (let x = -step; x < W + step; x += step) {
      const r = 2.2 + 1.4 * noise(t * 0.3 + x * 0.01 + y * 0.013, 3);
      bgx.fillStyle = 'rgba(21,23,26,.10)';
      bgx.beginPath(); bgx.arc(x + off * 0.4, y + off, Math.max(0.8, r), 0, 7); bgx.fill();
    }
}, { layer: 'back', setup(el) {
  const c = h('canvas', 'full', el); c.width = W; c.height = H; bgx = c.getContext('2d');
} });

/* ── 머리: 로고 · 기준일 · 진행 막대 ── */
let hd = {};
REEL.overlay(t => {
  const p = prog(t, 0.05, 0.5, ease.snap) * (D.site ? 1 - prog(t, cue('outro', 21.6) - 0.1, 0.3, ease.exit) : 1);
  css(hd.wrap, { opacity: p, transform: `translateY(${(1 - p) * -30}px)` });
  hd.bars.forEach((b, i) => {
    const k = N - i, s = at(k), f = prog(t, s, until(k) - s, ease.linear);
    css(b.firstChild, { transform: `scaleX(${f})` });
  });
}, { layer: 'top', setup(el) {
  hd.wrap = h('div', 'a', el); css(hd.wrap, { left: '60px', right: '60px', top: '262px', height: '120px' });
  const logo = h('div', 'a', hd.wrap, '<b style="color:var(--ink)">집값</b><b style="color:' + AC + '">레이더</b>');
  css(logo, { left: '0', top: '0', fontSize: '44px', fontWeight: 900, letterSpacing: '-0.04em' });
  const day = h('div', 'a chip', hd.wrap, D.asof);
  css(day, { right: '0', top: '-6px', fontSize: '30px', padding: '8px 22px', borderWidth: '3px' });
  hd.bars = [];
  for (let i = 0; i < N; i++) {
    const b = h('div', 'a', hd.wrap); const gap = 12, bw = (960 - gap * (N - 1)) / N;
    css(b, { left: `${i * (bw + gap)}px`, top: '84px', width: `${bw}px`, height: '10px', borderRadius: '6px', background: 'rgba(21,23,26,.12)', overflow: 'hidden' });
    const f = h('div', 'full', b); css(f, { background: AC, transformOrigin: '0 50%', transform: 'scaleX(0)' });
    hd.bars.push(b);
  }
} });

const BEATS = ((REEL.TL.music || {}).beats || []).filter(b => b > 0.5 && b < END - 0.5);
// 흔들림·전환 막대 없이 박자 밀기만 — 화면을 덮는 전환 막대는 편(색·글자 양)에 따라 섬광 기준(1초 3회)을 넘었다(실측: 구디·가산 4억대 59형).
// 장면 넘김은 각 장면의 들어오기·나가기 움직임으로만 한다.
FX.camera({ drift: 0.5, beat: { hits: BEATS, amount: 0.012 } });

/* ── 아래 빈 자리(인스타 글 영역 뒤)를 흐르는 외곽선 글자 띠 ── */
let mq;
REEL.overlay(t => {
  css(mq.a, { transform: `translateX(${-((t * 140) % mq.w)}px)` });
  css(mq.b, { transform: `translateX(${-mq.w + ((t * 110) % mq.w)}px)` });
}, { layer: 'back', setup(el) {
  const word = `${D.marquee} · `.repeat(8);
  mq = { w: 1900 };
  mq.a = h('div', 'a display', el, word);
  css(mq.a, { left: '0', top: '1530px', fontSize: '150px', whiteSpace: 'nowrap', color: 'transparent', WebkitTextStroke: '3px rgba(21,23,26,.16)' });
  mq.b = h('div', 'a display', el, word);
  css(mq.b, { left: '0', top: '1700px', fontSize: '150px', whiteSpace: 'nowrap', color: 'transparent', WebkitTextStroke: '3px ' + AC + '55' });
} });

/* 레이더 그리기: 고리 3개(10·30·50분 근처) · 도는 빛줄기 · 점(후보) · 큰 점(TOP 5) */
function drawRadar(g, R, t, o) {
  const cx = R + 20, cy = R + 20;
  g.clearRect(0, 0, (R + 20) * 2, (R + 20) * 2);
  g.save(); g.translate(cx, cy);
  g.fillStyle = '#fff'; g.strokeStyle = '#15171A'; g.lineWidth = 5;
  g.beginPath(); g.arc(0, 0, R, 0, 7); g.fill(); g.stroke();
  g.lineWidth = 2; g.strokeStyle = 'rgba(21,23,26,.18)';
  [1 / 3, 2 / 3].forEach(f => { g.beginPath(); g.arc(0, 0, R * f, 0, 7); g.stroke(); });
  g.beginPath(); g.moveTo(-R, 0); g.lineTo(R, 0); g.moveTo(0, -R); g.lineTo(0, R); g.stroke();
  const sw = o.sweep;                                       // 빛줄기 각도
  if (o.showSweep) {
    const grd = g.createConicGradient ? g.createConicGradient(sw - 0.9, 0, 0) : null;
    if (grd) { grd.addColorStop(0, 'rgba(212,250,75,0)'); grd.addColorStop(0.143, 'rgba(212,250,75,.75)'); grd.addColorStop(0.1431, 'rgba(212,250,75,0)'); g.fillStyle = grd; }
    else g.fillStyle = 'rgba(212,250,75,.4)';
    g.beginPath(); g.moveTo(0, 0); g.arc(0, 0, R - 3, sw - 0.9, sw); g.closePath(); g.fill();
  }
  (o.dots || []).forEach((d, i) => {
    if (d.a <= 0) return;
    const r = R * Math.min(1, mid(d.min) / MAXMIN) * 0.94, ang = angleOf(d.i ?? i);
    const x = Math.cos(ang) * r, y = Math.sin(ang) * r;
    g.globalAlpha = d.a;
    if (d.big) {
      g.fillStyle = d.on ? AC : '#15171A';
      g.beginPath(); g.arc(x, y, d.on ? 22 : 15, 0, 7); g.fill();
      g.lineWidth = 4; g.strokeStyle = '#fff'; g.stroke();
      if (d.on) { g.globalAlpha = d.a * 0.35 * (1 - (t * 1.2) % 1); g.strokeStyle = AC; g.lineWidth = 5; g.beginPath(); g.arc(x, y, 22 + 30 * ((t * 1.2) % 1), 0, 7); g.stroke(); }
    } else {
      g.fillStyle = 'rgba(21,23,26,.35)'; g.beginPath(); g.arc(x, y, 8, 0, 7); g.fill();
    }
    g.globalAlpha = 1;
  });
  g.fillStyle = AC; g.beginPath(); g.arc(0, 0, 16, 0, 7); g.fill();
  g.restore();
}

/* ── 오프닝(두 마디): 업무지구 칩 → 예산·평형 → '가장 많이 산 아파트 TOP 5' → 레이더가 돌며 후보가 찍힌다 ── */
REEL.scene({
  id: 'intro', start: 0, end: at(N) + 0.3,
  setup(el) {
    this.g = h('div', 'full', el);
    this.hub = h('div', 'a chip', this.g, D.chip);
    css(this.hub, { left: '60px', top: '430px', fontSize: '60px', padding: '14px 40px', background: 'var(--lime)' });
    this.t1 = h('div', 'a display', this.g, D.title);
    css(this.t1, { left: '56px', top: '540px', fontSize: D.title.length > 9 ? '128px' : '150px', whiteSpace: 'nowrap' });
    this.c1 = split(this.t1, 'char', { mask: true });
    this.hook = h('div', 'a display', this.g, D.hook);
    css(this.hook, { left: '60px', top: '722px', fontSize: '64px', whiteSpace: 'nowrap' });
    this.top = h('div', 'a num', this.g, `TOP ${N}`);
    css(this.top, { left: '60px', top: '808px', fontSize: '150px', color: AC, transformOrigin: '0 50%' });
    this.rc = h('canvas', 'a', this.g); this.R = 230; this.rc.width = this.rc.height = (this.R + 20) * 2;
    css(this.rc, { left: `${540 - this.R - 20}px`, top: '960px' }); this.rx = this.rc.getContext('2d');
    this.hubl = h('div', 'a chip', this.g, D.to);
    css(this.hubl, { left: '540px', top: `${960 + this.R + 20 + 28}px`, fontSize: '30px', padding: '6px 18px', background: 'var(--yellow)', transform: 'translateX(-50%)' });
    this.pool = h('div', 'a', this.g, D.pool_label);
    css(this.pool, { right: '60px', top: '820px', fontSize: '40px', fontWeight: 800, color: 'var(--ink2)', textAlign: 'right' });
    this.leg = h('div', 'a', this.g, '가운데에서 멀수록 오래 걸려요');
    css(this.leg, { right: '60px', top: '878px', fontSize: '30px', fontWeight: 700, color: 'var(--muted)', textAlign: 'right' });
    this.cond = h('div', 'a', this.g, D.cond);
    css(this.cond, { left: '60px', right: '60px', top: '1462px', fontSize: '30px', fontWeight: 700, color: 'var(--ink2)', textAlign: 'center' });
  },
  render(lt) {
    inout(this.g, lt, 0, at(N) - 0.05, { inDur: 0.01, rise: 0, from: 1, lift: 220 });
    const sp = spring(lt, 0.05, 2.6, 0.45);
    css(this.hub, { transform: `scale(${lerp(0.3, 1, sp)}) rotate(${(1 - sp) * -8}deg)`, opacity: clamp(sp * 3), transformOrigin: '0 50%' });
    this.c1.forEach((c, i) => { const p = stagger(lt, 0.2, 0.05, 0.5, i); css(c, { transform: `translateY(${(1 - p) * 120}%)`, opacity: p > 0 ? 1 : 0 }); });
    const hk = prog(lt, 0.55, 0.4, ease.snap);
    css(this.hook, { opacity: hk, transform: `translateY(${(1 - hk) * 40}px)` });
    const sl = prog(lt, 0.85, 0.3, ease.snap), tb = REEL.pulse(lt, [1.8, 2.4, 3.0, 3.6], 0.25);
    css(this.top, { opacity: sl, transform: `scale(${lerp(2.0, 1, sl) * (1 + 0.05 * tb)})`, filter: `blur(${(1 - sl) * 16}px)` });
    const ra = spring(lt, 1.0, 2.2, 0.5);
    css(this.rc, { opacity: clamp(ra * 2), transform: `scale(${lerp(0.4, 1, ra)}) rotate(${(1 - clamp(ra)) * -30}deg)` });
    css(this.hubl, { opacity: prog(lt, 1.4, 0.3) });
    const sweep = (lt - 1.0) * 3.2 - Math.PI / 2;
    // 빛줄기가 지나간 점부터 켠다(작은 점 = 다른 후보, 큰 점 = TOP 5)
    const passed = ang => { const a = ((ang + Math.PI / 2) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2); return (lt - 1.0) * 3.2 >= a; };
    const dots = D.pool.map((m, i) => ({ min: m, i: i + 10, a: passed(angleOf(i + 10)) ? 1 : 0 }))
      .concat(D.rows.map((r, i) => ({ min: r.min, i, big: true, on: false, a: passed(angleOf(i)) ? 1 : 0 })));
    drawRadar(this.rx, this.R, lt, { sweep, showSweep: lt > 1.0, dots });
    const pp = prog(lt, 1.6, 0.4, ease.snap);
    css(this.pool, { opacity: pp, transform: `translateX(${(1 - pp) * 40}px)` });
    css(this.leg, { opacity: prog(lt, 1.9, 0.4) });
    css(this.cond, { opacity: prog(lt, 2.2, 0.5) });
  },
});

/* ── 순위 장면: 큰 순위 숫자 · 동·준공·면적 칩 · 단지명 · 금액 카드(6개월 중앙값 카운트업 · 범위 막대 · 노선과 시간) · 작은 레이더 ── */
function rankScene(row, idx) {
  const k = row.rank, one = k === 1, dual = !!row.commute2;
  const s0 = at(k), s1 = until(k), dur = s1 - s0;
  const land = one ? 2.2 : 1.3;
  REEL.scene({
    id: `r${k}`, start: s0 - 0.05, end: s1 + 0.25,
    setup(el) {
      this.g = h('div', 'full', el);
      if (one) {
        this.rays = h('canvas', 'a', this.g); this.rays.width = 560; this.rays.height = 560;
        css(this.rays, { left: '-80px', top: '310px' }); this.rx = this.rays.getContext('2d');
      }
      this.num = h('div', 'a num', this.g, String(k));
      css(this.num, { left: '52px', top: '380px', fontSize: one ? '420px' : '380px', color: AC, transformOrigin: '30% 70%' });
      this.wi = h('div', 'a display', this.g, '위');
      css(this.wi, { left: one ? '240px' : '228px', top: one ? '680px' : '640px', fontSize: '92px' });
      this.rw = h('div', 'a', this.g, D.rank_word);
      css(this.rw, { left: '60px', top: one ? '800px' : '760px', fontSize: '30px', fontWeight: 800, color: 'var(--muted)' });
      this.loc = h('div', 'a chip', this.g, row.loc);
      css(this.loc, { left: '380px', top: '420px', fontSize: row.loc.length > 9 ? '32px' : '38px' });
      this.meta1 = h('div', 'a chip', this.g, row.spec);
      css(this.meta1, { left: '380px', top: '510px', background: 'var(--yellow)', fontSize: '34px' });
      this.mr = h('canvas', 'a', this.g); this.R = 104; this.mr.width = this.mr.height = (this.R + 20) * 2;
      css(this.mr, { left: `${1020 - (this.R + 20) * 2}px`, top: '590px' }); this.mx = this.mr.getContext('2d');
      const n = [...row.name].length, fs = n <= 8 ? 108 : Math.min(96, Math.floor(1880 / (n * 0.98)));
      this.name = h('div', 'a display', this.g, row.name);
      css(this.name, { left: '58px', width: '960px', top: one ? '850px' : '820px', fontSize: `${fs}px`, wordBreak: 'keep-all', lineHeight: '1.05' });
      this.nc = split(this.name, 'char', { mask: true });
      this.meta = h('div', 'a', this.g, row.deals);
      css(this.meta, { left: '62px', top: one ? '1040px' : '1010px', fontSize: '36px', fontWeight: 700, color: 'var(--ink2)' });

      const ch = dual ? 420 : 380;
      this.card = h('div', 'card', this.g); css(this.card, { top: one ? '1092px' : '1066px', height: `${ch}px` });
      this.pl = h('div', 'a k', this.card, '6개월 중앙값'); css(this.pl, { left: '50px', top: '34px', fontSize: '34px', color: AC });
      this.nv = h('div', 'a', this.card, row.lo_label); css(this.nv, { left: '46px', top: '74px', fontSize: one ? '100px' : '92px', fontWeight: 900, color: 'var(--ink)', letterSpacing: '-0.05em' });
      this.bd = h('div', 'a', this.card, row.min_label);
      css(this.bd, { right: '40px', top: '40px', fontSize: '44px', fontWeight: 900, color: '#fff', background: AC, padding: '10px 26px', borderRadius: '999px', transformOrigin: '100% 50%' });
      this.track = h('div', 'a', this.card); css(this.track, { left: '50px', right: '50px', top: '200px', height: '16px', borderRadius: '10px', background: 'var(--line)' });
      this.fill = h('div', 'a', this.track); css(this.fill, { left: '0', top: '0', bottom: '0', width: '100%', borderRadius: '10px', background: 'var(--ink2)', transformOrigin: '0 50%' });
      this.mk = h('div', 'a', this.track); css(this.mk, { top: '-10px', width: '14px', height: '36px', marginLeft: '-7px', borderRadius: '7px', background: AC, border: '3px solid var(--ink)', left: `${row.med_pos * 100}%` });
      this.lo = h('div', 'a', this.card, row.lo_short); css(this.lo, { left: '50px', top: '228px', fontSize: '28px', fontWeight: 700, color: 'var(--muted)' });
      this.hi = h('div', 'a', this.card, row.hi_short); css(this.hi, { right: '50px', top: '228px', fontSize: '28px', fontWeight: 700, color: 'var(--muted)', textAlign: 'right' });
      const strip = (y, lines, text) => {
        const s = h('div', 'a', this.card); css(s, { left: '44px', right: '40px', top: `${y}px`, height: '64px', display: 'flex', alignItems: 'center', gap: '16px' });
        const c = lineChips(s, lines, 54); css(c, { position: 'relative' });
        const tx = h('div', '', s, text); css(tx, { fontSize: '36px', fontWeight: 800, color: 'var(--ink)', whiteSpace: 'nowrap' });
        return s;
      };
      this.s1 = strip(282, row.lines, row.commute);
      if (dual) this.s2 = strip(350, row.lines2, row.commute2);
      if (one) { this.cf = h('canvas', 'full', this.g); this.cf.width = W; this.cf.height = H; this.cx = this.cf.getContext('2d'); }
    },
    render(lt) {
      inout(this.g, lt, 0.05, dur + 0.05, { inDur: 0.01, rise: 0, from: 1, lift: 260, outDur: 0.32 });
      const sp = spring(lt, 0.05, one ? 2.0 : 2.6, 0.4), fl = noise(lt * 0.8, k) * 6;
      css(this.num, { transform: `scale(${lerp(0.25, 1, sp)}) rotate(${(1 - sp) * -14 + fl * 0.3}deg) translateY(${fl}px)`, opacity: clamp(sp * 4) });
      const wp = prog(lt, 0.25, 0.35, ease.snap);
      css(this.wi, { opacity: wp, transform: `translateX(${(1 - wp) * -30}px)` });
      css(this.rw, { opacity: prog(lt, 0.4, 0.3) });
      [this.loc, this.meta1].forEach((c, i) => { const q = spring(lt, 0.15 + i * 0.1, 2.8, 0.45); css(c, { transform: `scale(${lerp(0.5, 1, q)})`, opacity: clamp(q * 3), transformOrigin: '0 50%' }); });
      const mq_ = spring(lt, 0.3, 2.4, 0.5);
      css(this.mr, { opacity: clamp(mq_ * 2), transform: `scale(${lerp(0.5, 1, mq_)})` });
      drawRadar(this.mx, this.R, s0 + lt, { sweep: 0, showSweep: false,
        dots: D.rows.map((r, i) => ({ min: r.min, i, big: true, on: r.rank === k, a: r.rank === k ? 1 : 0.45 })) });
      this.nc.forEach((c, i) => { const p = stagger(lt, 0.2, 0.03, 0.42, i); css(c, { transform: `translateY(${(1 - p) * 120}%)`, opacity: p > 0 ? 1 : 0 }); });
      const mp = prog(lt, 0.5, 0.4, ease.snap);
      css(this.meta, { opacity: mp, transform: `translateY(${(1 - mp) * 20}px)` });
      const cp = prog(lt, 0.35, 0.45, ease.snap);
      css(this.card, { opacity: cp, transform: `translateY(${(1 - cp) * 140}px) rotate(${(1 - cp) * 3}deg)` });
      const c0 = one ? 0.85 : 0.6, cv = prog(lt, c0, land - c0, ease.outQuart);
      this.nv.textContent = cv >= 1 ? row.median_label : won(lerp(row.lo, row.median, cv));
      css(this.nv, { color: cv >= 1 ? AC : 'var(--ink)', transform: `scale(${1 + (cv >= 1 ? 0.08 * (1 - prog(lt, land, 0.35, ease.outQuart)) : 0)})`, transformOrigin: '0 60%' });
      css(this.fill, { transform: `scaleX(${prog(lt, c0, 0.5, ease.swift)})` });
      const mk = spring(lt, land - 0.1, 2.6, 0.4);
      css(this.mk, { opacity: clamp(mk * 3), transform: `scaleY(${lerp(0.2, 1, mk)})` });
      css(this.lo, { opacity: prog(lt, c0 + 0.2, 0.3) }); css(this.hi, { opacity: prog(lt, c0 + 0.2, 0.3) });
      const bp = spring(lt, 0.55, 2.6, 0.38), beat = REEL.pulse(s0 + lt, BEATS.filter(b => b > s0 + land), 0.25);
      css(this.bd, { transform: `scale(${lerp(0, 1, bp) * (1 + 0.06 * beat)}) rotate(${(1 - clamp(bp)) * 10}deg)`, opacity: clamp(bp * 3) });
      [this.s1, this.s2].filter(Boolean).forEach((s, i) => { const q = prog(lt, 0.75 + i * 0.12, 0.35, ease.snap); css(s, { opacity: q, transform: `translateX(${(1 - q) * -40}px)` }); });

      if (one) {
        const g = this.rx, R = 280; g.clearRect(0, 0, 560, 560);
        const a = prog(lt, 0.1, 0.6, ease.snap) * (1 - prog(lt, dur - 0.4, 0.3));
        if (a > 0) {
          g.save(); g.translate(R, R); g.rotate(lt * 0.35);
          for (let i = 0; i < 18; i++) { g.rotate(Math.PI * 2 / 18); g.fillStyle = i % 2 ? 'rgba(255,228,94,.45)' : 'rgba(240,68,82,.12)'; g.globalAlpha = a; g.beginPath(); g.moveTo(0, 0); g.lineTo(R, -28); g.lineTo(R, 28); g.fill(); }
          g.restore();
        }
        const x = this.cx; x.clearRect(0, 0, W, H);
        const ct = lt - land;
        if (ct > 0 && ct < 2.2) {
          for (let i = 0; i < 60; i++) {
            const ang = -Math.PI * (0.18 + rand(i, 1) * 0.5), v = 700 + rand(i, 2) * 800;
            const px = 880 + Math.cos(ang) * v * ct, py = 1140 + Math.sin(ang) * v * ct + 1400 * ct * ct;
            const sz = 10 + rand(i, 3) * 14, rot = ct * (4 + rand(i, 4) * 8);
            x.save(); x.translate(px, py); x.rotate(rot); x.globalAlpha = 1 - prog(ct, 1.4, 0.8);
            x.fillStyle = [AC, '#FFE45E', '#D4FA4B', '#15171A', '#AECBFF'][i % 5]; x.fillRect(-sz / 2, -sz / 4, sz, sz / 2); x.restore();
          }
        }
      }
    },
  });
}
D.rows.slice().reverse().forEach(rankScene);

/* ── 한 줄 정리(한 마디): 가장 가까운 곳 · 가장 새 아파트 · 중앙값이 가장 낮은 곳 — 순위가 아니라 기준별 정리 ── */
REEL.scene({
  id: 'sum', start: cue('sum', 19.2) - 0.05, end: cue('outro', 21.6) + 0.3,
  setup(el) {
    this.g = h('div', 'full', el);
    this.t = h('div', 'a display', this.g, '기준별로 보면');
    css(this.t, { left: '60px', top: '430px', fontSize: '96px' });
    this.tc = split(this.t, 'char', { mask: true });
    this.items = D.summary.map((s, i) => {
      const c = h('div', 'card', this.g); css(c, { top: `${600 + i * 270}px`, height: '220px' });
      const k = h('div', 'a chip', c, s.k); css(k, { left: '40px', top: '-30px', fontSize: '34px', background: ['var(--lime)', 'var(--yellow)', '#fff'][i] });
      const v = h('div', 'a display', c, s.v); css(v, { left: '44px', top: '56px', right: '40px', fontSize: [...s.v].length > 12 ? '58px' : '72px', whiteSpace: 'nowrap', overflow: 'hidden' });
      const d = h('div', 'a', c, s.s); css(d, { left: '46px', top: '146px', fontSize: '36px', fontWeight: 700, color: 'var(--ink2)' });
      return c;
    });
  },
  render(lt) {
    const dur = cue('outro', 21.6) - cue('sum', 19.2);
    // 퇴장은 천천히·조금만 — 검은 테두리 카드 세 장이 0.15초에 흐려지며 빠지면 섬광 기준을 넘었다(실측 21.5초)
    inout(this.g, lt, 0.05, dur + 0.2, { inDur: 0.01, rise: 0, from: 1, lift: 90, outDur: 0.65, blur: 3 });
    this.tc.forEach((c, i) => { const p = stagger(lt, 0.05, 0.04, 0.4, i); css(c, { transform: `translateY(${(1 - p) * 120}%)`, opacity: p > 0 ? 1 : 0 }); });
    this.items.forEach((c, i) => { const q = spring(lt, 0.2 + i * 0.22, 2.6, 0.45); css(c, { opacity: clamp(q * 3), transform: `translateX(${(1 - clamp(q)) * 120}px) rotate(${(1 - clamp(q)) * 2}deg)` }); });
  },
});

/* ── 마무리 A: 1위 단지의 실제 집값레이더 페이지가 휴대폰 속에서 스크롤된다 ── */
const SITE_IMG = D.site ? REEL.img(D.site.img) : null;
if (D.site) REEL.scene({
  id: 'site', start: cue('outro', 21.6) - 0.05, end: END,
  setup(el) {
    this.l1 = h('div', 'a display', el, D.site.lead + ',');
    css(this.l1, { left: '60px', top: '262px', fontSize: '70px' });
    this.c1 = split(this.l1, 'char', { mask: true });
    this.l2 = h('div', 'a display', el, `<span style="color:${AC}">여기서 전부</span> 볼 수 있어요`);
    css(this.l2, { left: '60px', top: '350px', fontSize: '70px' });
    this.cta = h('div', 'a chip', el, '프로필 링크 → jipgapradar.kr');
    css(this.cta, { left: '60px', top: '460px', fontSize: '40px', background: 'var(--lime)', transformOrigin: '0 50%' });
    this.ph = h('div', 'a', el);
    css(this.ph, { left: '280px', top: '580px', width: '520px', height: '900px', borderRadius: '70px', background: '#fff',
      border: '6px solid var(--ink)', padding: '14px', boxSizing: 'border-box', boxShadow: '0 16px 0 var(--ink)', transformOrigin: '50% 100%' });
    this.sc = h('div', 'full', this.ph);
    css(this.sc, { inset: '14px', borderRadius: '54px', overflow: 'hidden', background: '#fff', outline: '2px solid var(--line)' });
    this.img = SITE_IMG; this.img.className = 'a'; this.sc.appendChild(this.img);
    css(this.img, { left: '0', top: '44px', width: '484px' });
    const notch = h('div', 'a', this.ph); css(notch, { left: '50%', top: '30px', width: '130px', height: '32px', marginLeft: '-65px', borderRadius: '20px', background: 'var(--ink)' });
    this.tag = h('div', 'a chip', el, '실제 화면');
    css(this.tag, { left: '730px', top: '610px', fontSize: '32px', background: 'var(--yellow)', transformOrigin: '50% 50%' });
    this.url = h('div', 'a', el, D.source);
    css(this.url, { left: '0', right: '0', top: '1494px', textAlign: 'center', fontSize: '28px', fontWeight: 700, color: 'var(--ink2)' });
  },
  render(lt) {
    this.c1.forEach((c, i) => { const p = stagger(lt, 0.05, 0.03, 0.4, i); css(c, { transform: `translateY(${(1 - p) * 120}%)`, opacity: p > 0 ? 1 : 0 }); });
    const a2 = prog(lt, 0.25, 0.4, ease.snap); css(this.l2, { opacity: a2, transform: `translateY(${(1 - a2) * 40}px)` });
    const cs = spring(lt, 0.5, 2.6, 0.42), cb = REEL.pulse(lt, [1.8, 2.4, 3.0, 3.6, 4.2], 0.3);
    css(this.cta, { opacity: clamp(cs * 3), transform: `scale(${lerp(0.5, 1, cs) * (1 + 0.04 * cb)})` });
    // 휴대폰은 화면 밖에서 서서히 — 첫 프레임에 바로 보이면 어두운 사이트 머리가 한꺼번에 나타나 섬광 기준을 넘었다(실측 21.5초)
    const pin = prog(lt, 0.35, 1.1, ease.snap);
    css(this.ph, { opacity: prog(lt, 0.35, 0.6), transform: `translateY(${(1 - pin) * 1400}px) rotate(${lerp(-8, -2, pin) + noise(lt * 0.4, 7) * 0.6}deg)` });
    const ih = this.img.naturalHeight ? this.img.naturalHeight * 484 / this.img.naturalWidth : 1900;
    const scroll = kf(lt, [[1.4, 0], [4.2, Math.max(0, ih - 820), ease.inOutSine]]);
    css(this.img, { transform: `translateY(${-scroll}px)` });
    const tg = spring(lt, 0.9, 2.6, 0.4);
    css(this.tag, { opacity: clamp(tg * 3), transform: `scale(${lerp(0.4, 1, tg)}) rotate(${6 - (1 - clamp(tg)) * 12}deg)` });
    css(this.url, { opacity: prog(lt, 1.2, 0.5) });
  },
});

/* ── 마무리 B(사이트 화면을 못 찍었을 때): 사이트 주소 + 댓글 유도 ── */
if (!D.site) REEL.scene({
  id: 'outro', start: cue('outro', 21.6) - 0.05, end: END,
  setup(el) {
    this.a = h('div', 'a', el, '단지별 층별 가격·모든 거래는'); css(this.a, { left: '60px', top: '600px', fontSize: '58px', fontWeight: 800, color: 'var(--ink2)' });
    this.u = h('div', 'a display', el, 'jipgapradar.kr'); css(this.u, { left: '56px', top: '690px', fontSize: '118px', color: AC, letterSpacing: '-0.04em' });
    this.uc = split(this.u, 'char', { mask: true });
    this.ul = h('div', 'a', el); css(this.ul, { left: '60px', top: '840px', width: '880px', height: '14px', background: 'var(--ink)', transformOrigin: '0 50%' });
    this.b = h('div', 'a', el, '다른 업무지구·예산은<br>댓글로 남겨 주세요'); css(this.b, { left: '60px', top: '930px', fontSize: '56px', fontWeight: 800, lineHeight: '1.35' });
    this.src = h('div', 'a', el, D.source); css(this.src, { left: '62px', top: '1130px', fontSize: '32px', fontWeight: 600, color: 'var(--muted)' });
  },
  render(lt) {
    const a = prog(lt, 0.05, 0.4, ease.snap); css(this.a, { opacity: a, transform: `translateY(${(1 - a) * 30}px)` });
    this.uc.forEach((c, i) => { const p = stagger(lt, 0.15, 0.03, 0.45, i); css(c, { transform: `translateY(${(1 - p) * 120}%)`, opacity: p > 0 ? 1 : 0 }); });
    css(this.ul, { transform: `scaleX(${prog(lt, 0.55, 0.5, ease.swift)})` });
    const b = prog(lt, 0.7, 0.45, ease.snap); css(this.b, { opacity: b, transform: `translateY(${(1 - b) * 30}px)` });
    css(this.src, { opacity: prog(lt, 1.0, 0.4) });
  },
});
