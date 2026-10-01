/* GA4: <head> 의 gtag.js 주소에서 측정 ID 를 읽어 시작한다(페이지마다 설정 스크립트를 넣지 않으려고) */
(function(){
  var t = document.querySelector('script[src*="googletagmanager.com/gtag/js?id="]'); if (!t) return;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function(){ window.dataLayer.push(arguments); };
  window.gtag('js', new Date());
  window.gtag('config', t.src.split('id=')[1]);
})();

/* 모든 페이지 공통: 수집일 표시, 단지·지역 검색, 알약 탭 전환 */
(function(){
  fetch('/meta.json').then(function(r){return r.json()}).then(function(m){ if(!m.collected) return;
    document.querySelectorAll('[data-collected]').forEach(function(e){ e.textContent=' · '+m.collected+' 수집' }); }).catch(function(){});
  var btn=document.getElementById('search-toggle'),panel=document.getElementById('search-panel'),
      inp=document.getElementById('search-input'),box=document.getElementById('search-results'),idx=null,sel=-1;
  function load(){ if(idx) return Promise.resolve(idx);
    return fetch('/search.json').then(function(r){return r.json()}).then(function(d){idx=d;return d}); }
  function norm(s){return s.replace(/\s+/g,'').toLowerCase()}
  function show(q){ q=norm(q); if(!q){box.classList.remove('open');return}
    load().then(function(d){ var out=[],i; for(i=0;i<d.length&&out.length<12;i++){ if(norm(d[i][0]).indexOf(q)>=0) out.push(d[i]) }
      box.innerHTML=out.length?out.map(function(r){return '<a href="'+r[2]+'"><span>'+r[0].replace(/</g,'&lt;')+'</span><span class="s">'+r[1]+'</span></a>'}).join(''):'<div class="empty">찾는 결과가 없어요</div>';
      box.classList.add('open'); sel=-1; }); }
  btn.addEventListener('click',function(){ panel.classList.toggle('open'); if(panel.classList.contains('open')){inp.focus();load()} });
  inp.addEventListener('input',function(){show(inp.value)});
  inp.addEventListener('keydown',function(e){ var a=box.querySelectorAll('a'); if(!a.length) return;
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){ e.preventDefault(); sel=(sel+(e.key==='ArrowDown'?1:-1)+a.length)%a.length;
      a.forEach(function(x,i){x.classList.toggle('sel',i===sel)}) }
    if(e.key==='Enter'){ location.href=(a[sel]||a[0]).href } });
  document.querySelectorAll('[data-pills]').forEach(function(g){
    g.querySelectorAll('button').forEach(function(b){ b.addEventListener('click',function(){
      g.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b)});
      document.querySelectorAll('[data-pane="'+g.dataset.pills+'"]').forEach(function(p){ p.hidden=p.dataset.key!==b.dataset.key }); }) }) });
})();

/* 단지 페이지 그래프: 페이지에 들어 있는 숫자(#cxd)로 그 자리 폭에 맞춰 SVG 를 그린다.
   데이터 모양: {m0:'YYYY-MM', t:[{k, med[36], cnt[36], pts:[[월번호, 일, 가격, 종류, 층]], gap:[[분기, 매매, 신규전세]]}]}
   종류: 0 저층 · 1 중층 · 2 고층 · 3 해제 · 4 직거래 · 5 확인 필요. 금액은 만원. */
(function(){
  var el = document.getElementById('cxd'); if (!el) return;
  var D = JSON.parse(el.textContent), byK = {};
  D.t.forEach(function(t){ byK[t.k] = t; });
  var NS = 'http://www.w3.org/2000/svg';
  function eok(v){ if (v === 0) return '0'; if (!v) return '–'; if (v >= 10000){ var s = (v/10000).toFixed(2).replace(/0+$/,'').replace(/\.$/,''); return s+'억'; } return Math.round(v).toLocaleString()+'만'; }
  function mlabel(i){ var y = +D.m0.slice(0,4), m = +D.m0.slice(5,7) - 1 + i; y += Math.floor(m/12); m = m%12 + 1;
    return m === 1 ? '’'+String(y).slice(2)+'.1월' : m+'월'; }
  function svg(w, h){ var s = document.createElementNS(NS,'svg'); s.setAttribute('viewBox','0 0 '+w+' '+h); s.setAttribute('class','chart'); return s; }
  function add(p, tag, a, text){ var e = document.createElementNS(NS, tag); for (var k in a) e.setAttribute(k, a[k]); if (text != null) e.textContent = text; p.appendChild(e); return e; }
  function tip(e, t){ add(e, 'title', {}, t); }
  // 점과 점을 곧게 잇는다(곡선 보간은 없는 오르내림을 그려 넣을 수 있다)
  function poly(P){ return P.map(function(p, i){ return (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(''); }
  function smooth(P){ if (P.length < 2) return ''; var d = 'M'+P[0][0].toFixed(1)+','+P[0][1].toFixed(1);
    for (var i = 0; i < P.length-1; i++){ var p0 = P[i-1]||P[i], p1 = P[i], p2 = P[i+1], p3 = P[i+2]||p2;
      d += 'C'+(p1[0]+(p2[0]-p0[0])/6).toFixed(1)+','+(p1[1]+(p2[1]-p0[1])/6).toFixed(1)+' '+(p2[0]-(p3[0]-p1[0])/6).toFixed(1)+','+(p2[1]-(p3[1]-p1[1])/6).toFixed(1)+' '+p2[0].toFixed(1)+','+p2[1].toFixed(1); }
    return d; }

  // 흐름: 값이 찍힌 꺾은선 + 아래 거래량 막대. 좁은 화면은 최근 12개월, 넓으면 24개월
  function line(box, t){
    var W = box.clientWidth, H = W < 480 ? 230 : 250, n = W < 480 ? 12 : 24, s0 = t.med.length - n;
    var med = t.med.slice(s0), cnt = t.cnt.slice(s0), known = [];
    med.forEach(function(v,i){ if (v) known.push([i,v]); });
    if (known.length < 2) return empty(box, '그릴 만큼 거래가 없어요');
    var top = 30, bottom = 28, volH = 34, ph = H - top - bottom - volH, L = 22, R = W - 22;
    var lo = Math.min.apply(null, known.map(function(p){return p[1]})), hi = Math.max.apply(null, known.map(function(p){return p[1]}));
    var pad = (hi-lo)*0.12 || hi*0.05; lo -= pad; hi += pad;
    var sx = function(i){ return L + (R-L)*i/(n-1); }, sy = function(v){ return top + ph*(1-(v-lo)/(hi-lo)); };
    var s = svg(W, H), cmax = Math.max.apply(null, cnt) || 1, bw = Math.max(3, (R-L)/n*0.5), base = H - bottom;
    cnt.forEach(function(c,i){ if (!c) return; var h = volH*0.9*c/cmax;
      tip(add(s,'rect',{x:(sx(i)-bw/2).toFixed(1), y:(base-h).toFixed(1), width:bw.toFixed(1), height:h.toFixed(1), rx:1.5, 'class':'vol'}), mlabel(s0+i)+' '+c+'건'); });
    add(s,'path',{d:poly(known.map(function(p){return [sx(p[0]), sy(p[1])]})), 'class':'line'});
    var iMax = known.reduce(function(a,p){return p[1]>a[1]?p:a})[0], iMin = known.reduce(function(a,p){return p[1]<a[1]?p:a})[0], iLast = known[known.length-1][0];
    var every = n <= 12 ? 2 : 3, em = [iMax, iMin, iLast];
    known.forEach(function(p, k){ var i = p[0], v = p[1], x = sx(i), y = sy(v), isEm = em.indexOf(i) >= 0;
      var near = em.some(function(j){ return Math.abs(i-j) <= 1; });
      tip(add(s,'circle',{cx:x.toFixed(1), cy:y.toFixed(1), r:isEm?5:3.2, 'class':'dot'+(i===iMax?' hi':i===iMin?' lo':i===iLast?' last':'')}), mlabel(s0+i)+' '+eok(v)+' · '+cnt[i]+'건');
      if (isEm || (k % every === 0 && !near))
        add(s,'text',{x:x.toFixed(1), y:(i===iMin ? y+18 : y-10).toFixed(1), 'text-anchor':'middle', 'class':'val'+(isEm?' em':'')}, eok(v).replace('억',''));
    });
    for (var i = 0; i < n; i++) if (i % (n <= 12 ? 2 : 3) === 0 || i === n-1)
      add(s,'text',{x:sx(i).toFixed(1), y:H-8, 'text-anchor':'middle', 'class':'axis'}, mlabel(s0+i));
    box.replaceChildren(s);
  }

  // 모든 거래: 계약 한 건 = 점 하나(층 높을수록 진하게), 선은 월 중위
  function dots(box, t){
    var W = box.clientWidth, H = W < 480 ? 240 : 260, n = W < 480 ? 12 : 36, s0 = 36 - n;
    var pts = t.pts.filter(function(p){ return p[0] >= s0; });
    if (!pts.length) return empty(box, '이 기간에는 거래가 없어요');
    var top = 14, bottom = 26, L = 46, R = W - 8, ph = H - top - bottom;
    var vals = pts.map(function(p){return p[2]}), lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi-lo)*0.1 || hi*0.05;
    lo -= pad; hi += pad;
    var colw = (R-L)/n, sx = function(m, d){ return L + colw*(m - s0 + (Math.min(d,30)-0.5)/30); }, sy = function(v){ return top + ph*(1-(v-lo)/(hi-lo)); };
    var s = svg(W, H);
    for (var g = 0; g < 4; g++){ var y = top + ph*g/3; add(s,'line',{x1:L, x2:R, y1:y.toFixed(1), y2:y.toFixed(1), 'class':'grid'});
      add(s,'text',{x:L-6, y:(y+4).toFixed(1), 'text-anchor':'end', 'class':'axis'}, eok(hi-(hi-lo)*g/3)); }
    var mp = []; t.med.slice(s0).forEach(function(v,i){ if (v) mp.push([L + colw*(i+0.5), sy(v)]); });
    if (mp.length >= 2) add(s,'path',{d:poly(mp), 'class':'med'});
    var cls = ['lo','mid','hi','x','dir','out'], order = [3,3,3,0,1,2], tag = ['','','',' · 해제',' · 직거래',' · 확인 필요'];
    pts.slice().sort(function(a,b){ return order[a[3]] - order[b[3]]; }).forEach(function(p){
      var x = sx(p[0], p[1]), y = sy(p[2]), e, lab = mlabel(p[0]).replace('월','')+'월 '+p[1]+'일 · '+p[4]+'층 · '+eok(p[2])+tag[p[3]];
      if (p[3] === 3) e = add(s,'path',{d:'M'+(x-3.5).toFixed(1)+','+(y-3.5).toFixed(1)+'l7,7m0,-7l-7,7', 'class':'pt x'});
      else e = add(s,'circle',{cx:x.toFixed(1), cy:y.toFixed(1), r:3.6, 'class':'pt '+cls[p[3]]});
      tip(e, lab); });
    for (var i = 0; i < n; i++) if (i % (n <= 12 ? 2 : 6) === 0 || i === n-1)
      add(s,'text',{x:(L + colw*(i+0.5)).toFixed(1), y:H-6, 'text-anchor':'middle', 'class':'axis'}, mlabel(s0+i));
    box.replaceChildren(s);
  }

  // 전세·갭: 분기 매매 중위(막대 전체)와 신규 전세 중위(아래 칠한 부분)
  function gap(box, t){
    var rows = t.gap.slice(box.clientWidth < 480 ? -6 : -8);
    if (rows.length < 2) return empty(box, '분기 자료가 모자라요');
    var W = box.clientWidth, H = 200, top = 14, bottom = 26, L = 44, ph = H - top - bottom;
    var vmax = Math.max.apply(null, rows.map(function(r){return r[1]})) * 1.05, slot = (W-L)/rows.length, bw = Math.min(28, slot*0.6);
    var s = svg(W, H);
    for (var g = 0; g < 4; g++){ var y = top + ph*g/3; add(s,'line',{x1:L, x2:W, y1:y.toFixed(1), y2:y.toFixed(1), 'class':'grid'});
      add(s,'text',{x:L-6, y:(y+4).toFixed(1), 'text-anchor':'end', 'class':'axis'}, eok(vmax*(1-g/3))); }
    rows.forEach(function(r, i){ var x = L + slot*i + (slot-bw)/2, hs = ph*r[1]/vmax;
      tip(add(s,'rect',{x:x.toFixed(1), y:(top+ph-hs).toFixed(1), width:bw.toFixed(1), height:hs.toFixed(1), rx:4, 'class':'g-sale'}), r[0]+' 매매 '+eok(r[1]));
      if (r[2]){ var hj = ph*r[2]/vmax;
        tip(add(s,'rect',{x:x.toFixed(1), y:(top+ph-hj).toFixed(1), width:bw.toFixed(1), height:hj.toFixed(1), rx:4, 'class':'g-jeonse'}), r[0]+' 신규 전세 '+eok(r[2])+' · 갭 '+eok(r[1]-r[2])); }
      add(s,'text',{x:(x+bw/2).toFixed(1), y:H-6, 'text-anchor':'middle', 'class':'axis'}, r[0].replace('년 ','.').replace('분기','Q')); });
    box.replaceChildren(s);
  }
  function empty(box, msg){ box.innerHTML = '<div class="empty">'+msg+'</div>'; }
  var cur = D.t.length ? D.t[0].k : null;       // 지금 고른 평형(면적 타입)
  function draw(box){ var t = byK[cur]; if (!t || !box.offsetParent) return;
    ({line: line, dots: dots, gap: gap})[box.dataset.v](box, t); }
  function drawAll(){ document.querySelectorAll('.cx-chart').forEach(draw); }

  var tabs = document.querySelector('[data-types]');
  if (tabs) tabs.addEventListener('click', function(e){ var b = e.target.closest('button'); if (!b) return;
    tabs.querySelectorAll('button').forEach(function(x){ x.classList.toggle('on', x === b); });
    cur = +b.dataset.k;
    document.querySelectorAll('.tk').forEach(function(p){ p.hidden = p.dataset.k !== b.dataset.k; });
    drawAll(); });
  document.querySelectorAll('[data-seg]').forEach(function(seg){ seg.addEventListener('click', function(e){
    var b = e.target.closest('button'); if (!b) return; var card = seg.closest('.card'), box = card.querySelector('.cx-chart');
    seg.querySelectorAll('button').forEach(function(x){ x.classList.toggle('on', x === b); });
    box.dataset.v = b.dataset.v;
    card.querySelectorAll('[data-legend]').forEach(function(l){ l.hidden = l.dataset.legend !== b.dataset.v; });
    draw(box); }); });
  var rt; window.addEventListener('resize', function(){ clearTimeout(rt); rt = setTimeout(drawAll, 150); });
  drawAll();
})();

/* 광고 자리: 한 자리에 광고 하나를 순서대로(docs/MONETIZATION.md 3절). 페이지에는 <div class="ad-slot" data-g data-f> 만 있다.
   애드센스(data-g) 태그를 만들어 요청하고, 안 채워지면(data-ad-status="unfilled") 애드핏(data-f)으로 바꾸고, 그것도 없으면 자리를 접는다. */
(function(){
  var slots = document.querySelectorAll('.ad-slot'); if (!slots.length) return;
  var meta = document.querySelector('meta[name="ad-client"]'), client = meta && meta.content, kakao = false;
  function fold(el){ var s = el.closest('.ad-slot'); if (s) s.hidden = true; }
  window.adFail = fold;                                   // 애드핏 NO-AD 콜백(data-ad-onfail)
  function loadKakao(){ if (kakao) return; kakao = true;
    var sc = document.createElement('script'); sc.async = true; sc.src = 'https://t1.daumcdn.net/kas/static/ba.min.js'; document.body.appendChild(sc); }
  function kakaoIns(spec){ var f = (spec || '').match(/^(.+):(\d+)x(\d+)$/); if (!f) return null;
    var k = document.createElement('ins'); k.className = 'kakao_ad_area'; k.style.display = 'none';
    k.setAttribute('data-ad-unit', f[1]); k.setAttribute('data-ad-width', f[2]); k.setAttribute('data-ad-height', f[3]); k.setAttribute('data-ad-onfail', 'adFail');
    return k; }
  slots.forEach(function(s){
    var gs = s.dataset.g, fs = s.dataset.f;
    if (!gs || !client) { var k = kakaoIns(fs); if (k) { s.appendChild(k); loadKakao(); } else fold(s); return; }
    var g = document.createElement('ins'); g.className = 'adsbygoogle'; g.style.display = 'block';
    g.setAttribute('data-ad-client', client); g.setAttribute('data-ad-slot', gs);
    if (s.classList.contains('ad-related')) g.setAttribute('data-ad-format', 'autorelaxed');
    else { g.setAttribute('data-ad-format', 'auto'); g.setAttribute('data-full-width-responsive', 'true'); }
    s.appendChild(g);
    new MutationObserver(function(){ if (g.dataset.adStatus === 'unfilled') { var k = kakaoIns(fs); if (k) { g.replaceWith(k); loadKakao(); } else fold(g); } })
      .observe(g, {attributes: true, attributeFilter: ['data-ad-status']});
    try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) { fold(g); }
  });
})();

/* 쿠팡 파트너스 배너: 맥락(data-cp)에 맞는 배너 코드를 /coupang.json 에서 넣는다. */
(function(){
  var boxes = document.querySelectorAll('.coupang[data-cp]'); if (!boxes.length) return;
  fetch('/coupang.json').then(function(r){ return r.json(); }).then(function(b){
    boxes.forEach(function(x){ var h = b[x.dataset.cp] || b.book; if (h) x.querySelector('.coupang-body').innerHTML = h; else x.hidden = true; });
  }).catch(function(){ boxes.forEach(function(x){ x.hidden = true; }); });
})();

/* 방문 통계(GA4). config analytics.ga4 가 있을 때만 gtag 가 있다 — 페이지뷰·방문자·유입 경로는 GA4 가 자동으로 모으고,
   여기서는 무엇을 누르는지(평형 탭·그래프 전환·비슷한 단지·검색·광고/제휴 클릭)를 이벤트로 남긴다. */
(function(){
  function track(name, p){ if (window.gtag) { try { window.gtag('event', name, p || {}); } catch (e) {} } }
  document.addEventListener('click', function(e){
    var a = e.target.closest('a,button'); if (!a) return;
    if (a.closest('[data-types]')) track('select_area_type', {area: a.dataset.k});
    else if (a.closest('[data-seg]')) track('chart_view', {view: a.dataset.v});
    else if (a.classList.contains('sim')) track('similar_click', {to: a.getAttribute('href')});
    else if (a.classList.contains('sponsor')) track('sponsor_click', {url: a.href});
    else if (a.closest('.coupang')) track('coupang_click');
    else if (a.closest('.search-results')) track('search_select', {to: a.getAttribute('href')});
    else if (a.closest('.cx-hero .acts')) track('compare_add');
    else if (a.closest('.quick')) track('quick_menu', {to: a.getAttribute('href')});
  }, true);
})();
