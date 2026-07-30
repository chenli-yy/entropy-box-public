/* ===========================================================
   Entropy Box — shared atmosphere behaviour
   1. Live node network painted into <canvas id="bgnet">
   2. Scroll reveal for [data-rv]
   3. Draw-on animation for chart polylines
   Respects prefers-reduced-motion; pauses when the tab is hidden.
   =========================================================== */
(function () {
  'use strict';

  var reduce = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------------- 1. node network ---------------- */
  (function network() {
    var c = document.getElementById('bgnet');
    if (!c || !c.getContext) return;
    var ctx = c.getContext('2d');
    var w = 0, h = 0, nodes = [], raf = null, running = false;
    var LINK = 156;           // px within which two nodes are wired
    var LINK2 = LINK * LINK;

    // two-tone palette: teal backbone, magenta accents
    var TEAL = [126, 242, 228];
    var PINK = [250, 158, 208];
    var PINK_SHARE = 0.38;

    function build() {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = c.clientWidth || window.innerWidth;
      h = c.clientHeight || window.innerHeight;
      c.width = Math.round(w * dpr);
      c.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      var target = Math.round(Math.min(84, Math.max(26, (w * h) / 21000)));
      nodes = [];
      for (var i = 0; i < target; i++) {
        var col = Math.random() < PINK_SHARE ? PINK : TEAL;
        nodes.push({
          x: Math.random() * w,
          y: Math.random() * h,
          vx: (Math.random() - 0.5) * 0.20,
          vy: (Math.random() - 0.5) * 0.20,
          r: Math.random() * 1.5 + 0.9,
          p: Math.random() * Math.PI * 2,
          c: col
        });
      }
    }

    function paint(t) {
      ctx.clearRect(0, 0, w, h);
      var i, j, a, b, dx, dy, d2, alpha;

      for (i = 0; i < nodes.length; i++) {
        a = nodes[i];
        a.x += a.vx; a.y += a.vy;
        if (a.x < -50) a.x = w + 50; else if (a.x > w + 50) a.x = -50;
        if (a.y < -50) a.y = h + 50; else if (a.y > h + 50) a.y = -50;
      }

      ctx.lineWidth = 1;
      for (i = 0; i < nodes.length; i++) {
        a = nodes[i];
        for (j = i + 1; j < nodes.length; j++) {
          b = nodes[j];
          dx = a.x - b.x; dy = a.y - b.y; d2 = dx * dx + dy * dy;
          if (d2 < LINK2) {
            alpha = (1 - Math.sqrt(d2) / LINK) * 0.18;
            // an edge takes the average of the two endpoint hues,
            // so teal–magenta pairs are wired in a soft violet
            ctx.strokeStyle = 'rgba('
              + ((a.c[0] + b.c[0]) >> 1) + ','
              + ((a.c[1] + b.c[1]) >> 1) + ','
              + ((a.c[2] + b.c[2]) >> 1) + ','
              + alpha.toFixed(3) + ')';
            ctx.beginPath();
            ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      for (i = 0; i < nodes.length; i++) {
        a = nodes[i];
        var pulse = 0.55 + 0.45 * Math.sin(t / 1500 + a.p);
        ctx.beginPath();
        ctx.arc(a.x, a.y, a.r, 0, 6.2832);
        ctx.fillStyle = 'rgba(' + a.c[0] + ',' + a.c[1] + ',' + a.c[2] + ','
          + (0.34 * pulse).toFixed(3) + ')';
        ctx.fill();
      }
    }

    function loop(t) { paint(t); raf = requestAnimationFrame(loop); }

    function start() {
      if (running || reduce) return;
      running = true; raf = requestAnimationFrame(loop);
    }
    function stop() {
      running = false;
      if (raf) { cancelAnimationFrame(raf); raf = null; }
    }

    build();
    if (reduce) { paint(0); } else { start(); }

    var rt = null;
    window.addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(function () { build(); if (reduce) paint(0); }, 180);
    });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) stop(); else start();
    });
  })();

  /* ---------------- 2. scroll reveal ---------------- */
  (function reveal() {
    var items = document.querySelectorAll('[data-rv]');
    if (!items.length) return;
    function show(el) { el.classList.add('rv-in'); }
    if (reduce || !('IntersectionObserver' in window)) {
      for (var k = 0; k < items.length; k++) show(items[k]);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var d = parseInt(e.target.getAttribute('data-rv'), 10) || 0;
        setTimeout(function () { show(e.target); }, d);
        io.unobserve(e.target);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -60px 0px' });
    for (var i = 0; i < items.length; i++) io.observe(items[i]);
    // Safety net: never leave content invisible.
    setTimeout(function () {
      var left = document.querySelectorAll('[data-rv]:not(.rv-in)');
      for (var n = 0; n < left.length; n++) show(left[n]);
    }, 4000);
  })();

  /* ---------------- 3. chart draw-on ---------------- */
  (function drawCharts() {
    var lines = document.querySelectorAll('.chartbox svg polyline[data-draw]');
    if (!lines.length) return;

    function prime(el) {
      var len;
      try { len = el.getTotalLength(); } catch (e) { return null; }
      if (!len || !isFinite(len)) return null;
      el.style.strokeDasharray = len;
      el.style.strokeDashoffset = len;
      return len;
    }
    function run(el) { el.style.strokeDashoffset = '0'; }

    var primed = [];
    for (var i = 0; i < lines.length; i++) {
      if (reduce) continue;
      if (prime(lines[i]) !== null) primed.push(lines[i]);
    }
    if (reduce || !primed.length || !('IntersectionObserver' in window)) {
      for (var k = 0; k < primed.length; k++) run(primed[k]);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        var d = parseInt(el.getAttribute('data-draw'), 10) || 0;
        setTimeout(function () { run(el); }, d);
        io.unobserve(el);
      });
    }, { threshold: 0.35 });
    for (var n = 0; n < primed.length; n++) io.observe(primed[n]);
  })();
})();
