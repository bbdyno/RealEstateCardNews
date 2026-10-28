/* 집값레이더 랭킹 카운트다운 릴스(9:16).
 * 데이터: data.js 의 window.DATA — build.py 가 DB 에서 만든다. 단지명·가격·상승률은 DATA 의 문자열을 그대로 쓴다.
 *   올라가는 중간 숫자만 여기서 계산하고, 멈춘 프레임은 언제나 원문(label)이다. 숫자를 지어내는 곳이 없다.
 * 시각: timeline.js 의 큐(intro·r5…r1·outro·end). 배경음도 같은 큐로 합성해 박자가 맞는다.
 * 엔진(engine.js·fx.js)은 third_party/showreel 의 것을 그대로 쓴다. 우리 것은 이 파일과 brand.css 뿐이다. */
const { ease, prog, kf, spring, clamp, lerp, rand, noise, split, stagger, inout, css, h, cue } = REEL;
const D = window.DATA;
const W = 1080, H = 1920, AC = D.accent, N = D.rows.length;
const END = cue('end', 19.2);
REEL.config({ duration: END, fps: 30, width: W, height: H, audio: null, push: 0.012 });

// 사이트와 같은 금액 표기(245000 → '24억 5,000만'). 올라가는 중간값에만 쓴다.
function won(v) {
  v = Math.round(v / 100) * 100;
  const eok = Math.floor(v / 10000), man = v % 10000;
  if (eok && man) return `${eok}억 ${man.toLocaleString('en-US')}만`;
  if (eok) return `${eok}억`;
  return `${man.toLocaleString('en-US')}만`;
}
const at = k => cue(`r${k}`, 2.4 * (N - k + 1));            // k위 장면이 시작하는 시각
const until = k => (k === 1 ? cue('outro', 16.8) : at(k - 1)); // k위 장면이 끝나는 시각

/* ── 배경: 연한 바탕 위로 점 격자가 천천히 흐른다(멈춘 화면처럼 보이지 않게) ── */
let bgc, bgx;
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
  bgc = h('canvas', 'full', el); bgc.width = W; bgc.height = H; bgx = bgc.getContext('2d');
} });

/* ── 머리: 로고 · 기준일 · 진행 막대(위 250px 은 인스타 UI 자리라 그 아래에 둔다) ── */
let hd = {};
REEL.overlay(t => {
  const p = prog(t, 0.05, 0.5, ease.snap) * (D.site ? 1 - prog(t, cue('outro', 16.8) - 0.1, 0.3, ease.exit) : 1);
  css(hd.wrap, { opacity: p, transform: `translateY(${(1 - p) * -30}px)` });
  hd.bars.forEach((b, i) => {                                   // i=0 이 5위
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

// 박마다 화면을 살짝 밀어 넣기만 한다(정지 방지). 흔들림·화면을 덮는 전환 막대는 뺐다 — 편(색·글자 양)에 따라
// 1위 진입에서 섬광 기준(1초 3회)을 넘어 게시가 막혔다(2026-10-28 18:10 세종 하락 순위, 11.9초).
const BEATS = ((REEL.TL.music || {}).beats || []).filter(b => b > 0.5 && b < END - 0.5);
FX.camera({ drift: 0.5, beat: { hits: BEATS, amount: 0.012 } });

/* ── 아래 빈 자리(인스타 글 영역 뒤)를 흐르는 큰 외곽선 글자 띠 — 장식이자 움직임 ── */
let mq;
REEL.overlay(t => {
  css(mq.a, { transform: `translateX(${-((t * 140) % mq.w)}px)` });
  css(mq.b, { transform: `translateX(${-mq.w + ((t * 110) % mq.w)}px)` });
}, { layer: 'back', setup(el) {
  const word = `${D.sido} ${D.head} · `.repeat(8);
  mq = { w: 1900 };
  mq.a = h('div', 'a display', el, word);
  css(mq.a, { left: '0', top: '1530px', fontSize: '150px', whiteSpace: 'nowrap', color: 'transparent', WebkitTextStroke: '3px rgba(21,23,26,.16)' });
  mq.b = h('div', 'a display', el, word);
  css(mq.b, { left: '0', top: '1700px', fontSize: '150px', whiteSpace: 'nowrap', color: 'transparent', WebkitTextStroke: '3px ' + AC + '55' });
} });

/* ── 오프닝: 시도 칩 → 제목 글자가 솟고 → 'TOP 5' 가 박자에 떨어진다 ── */
REEL.scene({
  id: 'intro', start: 0, end: at(N) + 0.3,
  setup(el) {
    this.g = h('div', 'full', el);
    this.sido = h('div', 'a chip', this.g, D.sido);
    css(this.sido, { left: '60px', top: '520px', fontSize: '64px', padding: '14px 40px', background: 'var(--lime)' });
    this.t1 = h('div', 'a display', this.g, D.head);
    css(this.t1, { left: '56px', top: '650px', fontSize: '150px' });
    this.c1 = split(this.t1, 'char', { mask: true });
    this.top = h('div', 'a num', this.g, `TOP ${N}`);
    css(this.top, { left: '60px', top: '830px', fontSize: '300px', color: AC });
    this.sub = h('div', 'a', this.g, D.sub);
    css(this.sub, { left: '64px', right: '60px', top: '1180px', fontSize: '42px', fontWeight: 700, color: 'var(--ink2)', lineHeight: '1.4' });
  },
  render(lt) {
    const out = at(N) - 0.05;
    inout(this.g, lt, 0, out, { inDur: 0.01, rise: 0, from: 1, lift: 220 });
    const sp = spring(lt, 0.05, 2.6, 0.45);
    css(this.sido, { transform: `scale(${lerp(0.3, 1, sp)}) rotate(${(1 - sp) * -8}deg)`, opacity: clamp(sp * 3) });
    this.c1.forEach((c, i) => { const p = stagger(lt, 0.2, 0.06, 0.5, i); css(c, { transform: `translateY(${(1 - p) * 120}%)`, opacity: p > 0 ? 1 : 0 }); });
    const sl = prog(lt, 0.45, 0.28, ease.snap);                                  // 0.6초(첫 박)에 착지
    const tb = REEL.pulse(lt, [1.2, 1.8], 0.25);
    css(this.top, { opacity: sl, transform: `scale(${lerp(2.2, 1, sl) * (1 + 0.05 * tb)})`, filter: `blur(${(1 - sl) * 20}px)`, transformOrigin: '0 50%' });
    const sb = prog(lt, 0.9, 0.5, ease.snap);
    css(this.sub, { opacity: sb, transform: `translateY(${(1 - sb) * 40}px)` });
  },
});

/* ── 순위 장면: 큰 순위 숫자 · 지역 칩 · 단지명 · 가격 카드(이전 최고 → 새 가격 카운트업 → 상승률) ── */
function rankScene(row) {
  const k = row.rank, one = k === 1;
  const s0 = at(k), s1 = until(k), dur = s1 - s0;
  const land = one ? 2.4 : 1.35;                               // 카운트업이 끝나는 장면 안 시각
  REEL.scene({
    id: `r${k}`, start: s0 - 0.05, end: s1 + 0.25,
    setup(el) {
      this.g = h('div', 'full', el);
      if (one) {                                               // 1위: 숫자 뒤로 천천히 도는 빛줄기
        this.rays = h('canvas', 'a', this.g); this.rays.width = 560; this.rays.height = 560;
        css(this.rays, { left: '-80px', top: '310px' }); this.rx = this.rays.getContext('2d');
      }
      this.num = h('div', 'a num', this.g, String(k));
      css(this.num, { left: '52px', top: '380px', fontSize: one ? '440px' : '400px', color: AC, transformOrigin: '30% 70%' });
      this.wi = h('div', 'a display', this.g, '위');
      css(this.wi, { left: one ? '250px' : '238px', top: one ? '700px' : '660px', fontSize: '96px' });
      this.loc = h('div', 'a chip', this.g, row.loc);
      css(this.loc, { left: '400px', top: '440px' });
      this.py = h('div', 'a chip', this.g, `${row.py}평`);
      css(this.py, { left: '400px', top: '540px', background: 'var(--yellow)' });
      const n = [...row.name].length, fs = n <= 8 ? 112 : Math.min(100, Math.floor(1880 / (n * 0.98)));
      this.name = h('div', 'a display', this.g, row.name);
      css(this.name, { left: '58px', width: '960px', top: one ? '850px' : '810px', fontSize: `${fs}px`, wordBreak: 'break-all', lineHeight: '1.05' });
      this.nc = split(this.name, 'char', { mask: true });
      this.meta = h('div', 'a', this.g, row.meta);
      css(this.meta, { left: '62px', top: one ? '1066px' : '1026px', fontSize: '38px', fontWeight: 700, color: 'var(--ink2)' });

      this.card = h('div', 'card', this.g); css(this.card, { top: one ? '1120px' : '1090px', height: '370px' });
      this.pl = h('div', 'a k', this.card, row.prev_name); css(this.pl, { left: '50px', top: '40px', fontSize: '34px', color: 'var(--muted)' });
      this.pv = h('div', 'a', this.card, row.prev_label); css(this.pv, { left: '50px', top: '84px', fontSize: '56px', fontWeight: 800, color: 'var(--ink2)' });
      this.st = h('div', 'a', this.card); css(this.st, { left: '44px', top: '120px', height: '6px', width: `${row.prev_label.length * 44 + 20}px`, background: AC, transformOrigin: '0 50%' });
      this.nl = h('div', 'a k', this.card, row.now_name); css(this.nl, { left: '50px', top: '172px', fontSize: '34px', color: AC });
      this.nv = h('div', 'a', this.card, row.prev_label); css(this.nv, { left: '46px', top: '210px', fontSize: one ? '104px' : '96px', fontWeight: 900, color: 'var(--ink)', letterSpacing: '-0.05em' });
      this.bd = h('div', 'a', this.card, row.up_label);
      css(this.bd, { right: '40px', top: '36px', fontSize: '50px', fontWeight: 900, color: '#fff', background: AC, padding: '10px 26px', borderRadius: '999px', transformOrigin: '100% 50%' });
      this.track = h('div', 'a', this.card); css(this.track, { left: '50px', right: '50px', top: '330px', height: '18px', borderRadius: '10px', background: 'var(--line)', overflow: 'hidden' });
      this.base = h('div', 'a', this.track); css(this.base, { left: '0', top: '0', bottom: '0', background: 'var(--ink2)', transformOrigin: '0 50%' });
      this.delta = h('div', 'a', this.track); css(this.delta, { top: '0', bottom: '0', background: AC, transformOrigin: '0 50%' });
      const lo = Math.min(row.prev, row.price), hi = Math.max(row.prev, row.price);
      this.fb = lo / hi;
      css(this.base, { width: `${this.fb * 100}%` }); css(this.delta, { left: `${this.fb * 100}%`, width: `${(1 - this.fb) * 100}%` });

      if (one && D.fmt === 'highs') {                          // 1위 착지 순간의 색종이 — 신고가에서만(하락·해제에 축하는 맞지 않다)
        this.cf = h('canvas', 'full', this.g); this.cf.width = W; this.cf.height = H; this.cx = this.cf.getContext('2d');
      }
    },
    render(lt) {
      inout(this.g, lt, 0.05, dur + 0.05, { inDur: 0.01, rise: 0, from: 1, lift: 260, outDur: 0.32 });
      const sp = spring(lt, 0.05, one ? 2.0 : 2.6, 0.4);
      const fl = noise(lt * 0.8, k) * 6;
      css(this.num, { transform: `scale(${lerp(0.25, 1, sp)}) rotate(${(1 - sp) * -14 + fl * 0.3}deg) translateY(${fl}px)`, opacity: clamp(sp * 4) });
      const wp = prog(lt, 0.25, 0.35, ease.snap);
      css(this.wi, { opacity: wp, transform: `translateX(${(1 - wp) * -30}px)` });
      [this.loc, this.py].forEach((c, i) => { const q = spring(lt, 0.18 + i * 0.12, 2.8, 0.45); css(c, { transform: `scale(${lerp(0.5, 1, q)})`, opacity: clamp(q * 3), transformOrigin: '0 50%' }); });
      this.nc.forEach((c, i) => { const p = stagger(lt, 0.22, 0.035, 0.45, i); css(c, { transform: `translateY(${(1 - p) * 120}%)`, opacity: p > 0 ? 1 : 0 }); });
      const mp = prog(lt, 0.55, 0.4, ease.snap);
      css(this.meta, { opacity: mp, transform: `translateY(${(1 - mp) * 20}px)` });

      const cp = prog(lt, 0.4, 0.45, ease.snap);               // 카드가 아래에서 올라온다
      css(this.card, { opacity: cp, transform: `translateY(${(1 - cp) * 140}px) rotate(${(1 - cp) * 3}deg)` });
      const c0 = one ? 0.9 : 0.62, cv = prog(lt, c0, land - c0, ease.outQuart);
      this.nv.textContent = cv >= 1 ? row.price_label : won(lerp(row.prev, row.price, cv));   // 끝은 언제나 원문
      css(this.nv, { color: cv >= 1 ? AC : 'var(--ink)', transform: `scale(${1 + (cv >= 1 ? 0.08 * (1 - prog(lt, land, 0.35, ease.outQuart)) : 0)})`, transformOrigin: '0 60%' });
      if (!this.stw) { this.stw = this.pv.offsetWidth; if (this.stw) css(this.st, { width: `${this.stw + 14}px` }); }
      css(this.st, { transform: `scaleX(${prog(lt, land - 0.15, 0.25, ease.swift)})` });
      const bp = spring(lt, land, 2.6, 0.38), beat = REEL.pulse(s0 + lt, BEATS.filter(b => b > s0 + land), 0.25);
      css(this.bd, { transform: `scale(${lerp(0, 1, bp) * (1 + 0.07 * beat)}) rotate(${(1 - clamp(bp)) * 10}deg)`, opacity: clamp(bp * 3) });
      css(this.delta, { transform: `scaleX(${prog(lt, c0, land - c0, ease.outQuart)})` });

      if (one) {
        const g = this.rx, R = 280; g.clearRect(0, 0, 560, 560);
        const a = prog(lt, 0.1, 0.6, ease.snap) * (1 - prog(lt, dur - 0.4, 0.3));
        if (a > 0) {
          g.save(); g.translate(R, R); g.rotate(lt * 0.35);
          for (let i = 0; i < 18; i++) { g.rotate(Math.PI * 2 / 18); g.fillStyle = i % 2 ? 'rgba(255,228,94,.45)' : 'rgba(240,68,82,.12)'; g.globalAlpha = a; g.beginPath(); g.moveTo(0, 0); g.lineTo(R, -28); g.lineTo(R, 28); g.fill(); }
          g.restore();
        }
        const x = this.cx; if (x) x.clearRect(0, 0, W, H);
        const ct = lt - land;                                   // 착지 뒤 경과
        if (x && ct > 0 && ct < 2.2) {
          for (let i = 0; i < 60; i++) {
            const ang = -Math.PI * (0.18 + rand(i, 1) * 0.5), v = 700 + rand(i, 2) * 800;
            const px = 880 + Math.cos(ang) * v * ct, py = 1160 + Math.sin(ang) * v * ct + 1400 * ct * ct;
            const sz = 10 + rand(i, 3) * 14, rot = ct * (4 + rand(i, 4) * 8);
            x.save(); x.translate(px, py); x.rotate(rot); x.globalAlpha = 1 - prog(ct, 1.4, 0.8);
            x.fillStyle = [AC, '#FFE45E', '#D4FA4B', '#15171A', '#AECBFF'][i % 5]; x.fillRect(-sz / 2, -sz / 4, sz, sz / 2); x.restore();
          }
        }
      }
    },
  });
}
D.rows.slice().reverse().forEach(rankScene);                  // 5위 → 1위

/* ── 마무리 A: 1위 단지의 실제 집값레이더 페이지가 휴대폰 속에서 스크롤된다(사이트로 보내기) ── */
const SITE_IMG = D.site ? REEL.img(D.site.img) : null;   // 렌더러가 다 불러올 때까지 기다린다
if (D.site) REEL.scene({
  id: 'site', start: cue('outro', 16.8) - 0.05, end: END,
  setup(el) {
    this.l1 = h('div', 'a display', el, D.site.lead + ',');
    css(this.l1, { left: '60px', top: '262px', fontSize: '70px' });
    this.c1 = split(this.l1, 'char', { mask: true });
    this.l2 = h('div', 'a display', el, `<span style="color:${AC}">여기서 전부</span> 볼 수 있어요`);
    css(this.l2, { left: '60px', top: '350px', fontSize: '70px' });
    this.cta = h('div', 'a chip', el, '프로필 링크 → jipgapradar.kr');
    css(this.cta, { left: '60px', top: '460px', fontSize: '40px', background: 'var(--lime)', transformOrigin: '0 50%' });
    this.ph = h('div', 'a', el);
    // 휴대폰은 카드와 같은 흰 바탕 + 검은 선 — 검은 휴대폰이 밝은 바탕을 가로지르면 섬광 기준을 넘는다(실측)
    css(this.ph, { left: '280px', top: '580px', width: '520px', height: '900px', borderRadius: '70px', background: '#fff',
      border: '6px solid var(--ink)', padding: '14px', boxSizing: 'border-box', boxShadow: '0 16px 0 var(--ink)', transformOrigin: '50% 100%' });
    this.sc = h('div', 'full', this.ph);
    css(this.sc, { inset: '14px', borderRadius: '54px', overflow: 'hidden', background: '#fff', outline: '2px solid var(--line)' });
    this.img = SITE_IMG; this.img.className = 'a'; this.sc.appendChild(this.img);
    css(this.img, { left: '0', top: '44px', width: '484px' });
    const notch = h('div', 'a', this.ph); css(notch, { left: '50%', top: '30px', width: '130px', height: '32px', marginLeft: '-65px', borderRadius: '20px', background: 'var(--ink)' });
    this.tag = h('div', 'a chip', el, '실제 화면');
    css(this.tag, { left: '730px', top: '610px', fontSize: '32px', background: 'var(--yellow)', transformOrigin: '50% 50%' });
    this.url = h('div', 'a', el, D.site.url);
    css(this.url, { left: '0', right: '0', top: '1494px', textAlign: 'center', fontSize: '28px', fontWeight: 700, color: 'var(--ink2)' });
  },
  render(lt) {
    this.c1.forEach((c, i) => { const p = stagger(lt, 0.05, 0.03, 0.4, i); css(c, { transform: `translateY(${(1 - p) * 120}%)`, opacity: p > 0 ? 1 : 0 }); });
    const a2 = prog(lt, 0.25, 0.4, ease.snap); css(this.l2, { opacity: a2, transform: `translateY(${(1 - a2) * 40}px)` });
    const cs = spring(lt, 0.5, 2.6, 0.42), cb = REEL.pulse(lt, [1.8, 2.4, 3.0, 3.6, 4.2], 0.3);
    css(this.cta, { opacity: clamp(cs * 3), transform: `scale(${lerp(0.5, 1, cs) * (1 + 0.04 * cb)})` });
    const pin = prog(lt, 0.3, 1.0, ease.snap);                    // 1위가 다 빠진 뒤에, 천천히
    css(this.ph, { transform: `translateY(${(1 - pin) * 520}px) rotate(${lerp(-8, -2, pin) + noise(lt * 0.4, 7) * 0.6}deg)` });
    const ih = this.img.naturalHeight ? this.img.naturalHeight * 484 / this.img.naturalWidth : 1900;
    const scroll = kf(lt, [[1.4, 0], [4.2, Math.max(0, ih - 820), ease.inOutSine]]);
    css(this.img, { transform: `translateY(${-scroll}px)` });
    const tg = spring(lt, 0.9, 2.6, 0.4);
    css(this.tag, { opacity: clamp(tg * 3), transform: `scale(${lerp(0.4, 1, tg)}) rotate(${6 - (1 - clamp(tg)) * 12}deg)` });
    css(this.url, { opacity: prog(lt, 1.2, 0.5) });
  },
});

/* ── 마무리 B(사이트 화면을 못 찍었을 때): 사이트 주소 + 저장 유도 ── */
if (!D.site) REEL.scene({
  id: 'outro', start: cue('outro', 16.8) - 0.05, end: END,
  setup(el) {
    this.a = h('div', 'a', el, D.outro_lead); css(this.a, { left: '60px', top: '600px', fontSize: '58px', fontWeight: 800, color: 'var(--ink2)' });
    this.u = h('div', 'a display', el, 'jipgapradar.kr'); css(this.u, { left: '56px', top: '690px', fontSize: '118px', color: AC, letterSpacing: '-0.04em' });
    this.uc = split(this.u, 'char', { mask: true });
    this.ul = h('div', 'a', el); css(this.ul, { left: '60px', top: '840px', width: '880px', height: '14px', background: 'var(--ink)', transformOrigin: '0 50%' });
    this.b = h('div', 'a', el, '저장해 두면 다음 순위와<br>비교할 수 있어요'); css(this.b, { left: '60px', top: '930px', fontSize: '56px', fontWeight: 800, lineHeight: '1.35' });
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
