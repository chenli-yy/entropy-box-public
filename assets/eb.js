/* ===========================================================
   Entropy Box — page behaviour
   1. Scroll reveal for [data-rv]
   2. Count-up for [data-count]
   3. Draw-on for chart polylines
   4. Nav section highlighting
   No background animation: the page is deliberately still.
   =========================================================== */
(function () {
  'use strict';
  var reduce = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var hasIO = 'IntersectionObserver' in window;

  /* ---------- 1. reveal ---------- */
  (function () {
    var items = document.querySelectorAll('[data-rv]');
    if (!items.length) return;
    function show(el) { el.classList.add('in'); }
    if (reduce || !hasIO) {
      for (var k = 0; k < items.length; k++) show(items[k]);
      return;
    }
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        var d = parseInt(e.target.getAttribute('data-rv'), 10) || 0;
        setTimeout(function () { show(e.target); }, d);
        io.unobserve(e.target);
      });
    }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });
    for (var i = 0; i < items.length; i++) io.observe(items[i]);
    setTimeout(function () {
      var left = document.querySelectorAll('[data-rv]:not(.in)');
      for (var n = 0; n < left.length; n++) show(left[n]);
    }, 4000);
  })();

  /* ---------- 2. count-up ---------- */
  (function () {
    var cells = document.querySelectorAll('[data-count]');
    if (!cells.length || reduce || !hasIO) return;

    function animate(el) {
      var raw = el.textContent.trim();
      var m = raw.match(/^([\d,]+)(\.\d+)?(%)?$/);
      if (!m) return;
      var suffix = m[3] || '';
      var target = parseFloat(raw.replace(/[,%]/g, ''));
      if (!isFinite(target)) return;
      var dec = ((raw.split('.')[1] || '').replace(/%/g, '')).length;
      var t0 = null, dur = 1000;
      function fmt(v) {
        var s = v.toFixed(dec), parts = s.split('.');
        return parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',') +
          (parts[1] ? '.' + parts[1] : '') + suffix;
      }
      function step(ts) {
        if (!t0) t0 = ts;
        var p = Math.min((ts - t0) / dur, 1);
        el.textContent = fmt(target * (1 - Math.pow(1 - p, 3)));
        if (p < 1) requestAnimationFrame(step); else el.textContent = raw;
      }
      requestAnimationFrame(step);
    }

    var seen = [];
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting || seen.indexOf(e.target) > -1) return;
        seen.push(e.target);
        animate(e.target);
        io.unobserve(e.target);
      });
    }, { threshold: 0.5 });
    for (var i = 0; i < cells.length; i++) io.observe(cells[i]);
  })();

  /* ---------- 3. chart draw-on ---------- */
  (function () {
    var lines = document.querySelectorAll('.chartbox svg polyline[data-draw]');
    if (!lines.length) return;
    function prime(el) {
      var len;
      try { len = el.getTotalLength(); } catch (e) { return false; }
      if (!len || !isFinite(len)) return false;
      el.style.strokeDasharray = len;
      el.style.strokeDashoffset = len;
      return true;
    }
    function run(el) { el.style.strokeDashoffset = '0'; }
    if (reduce || !hasIO) return;
    var primed = [];
    for (var i = 0; i < lines.length; i++) if (prime(lines[i])) primed.push(lines[i]);
    if (!primed.length) return;
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target, d = parseInt(el.getAttribute('data-draw'), 10) || 0;
        setTimeout(function () { run(el); }, d);
        io.unobserve(el);
      });
    }, { threshold: 0.3 });
    for (var n = 0; n < primed.length; n++) io.observe(primed[n]);
    setTimeout(function () { for (var q = 0; q < primed.length; q++) run(primed[q]); }, 6000);
  })();

  /* ---------- 4. nav highlighting ---------- */
  (function () {
    var links = document.querySelectorAll('.navlinks a[href^="#"]');
    if (!links.length || !hasIO) return;
    var map = {};
    for (var i = 0; i < links.length; i++) {
      var id = links[i].getAttribute('href').slice(1);
      var sec = id && document.getElementById(id);
      if (sec) map[id] = links[i];
    }
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        var a = map[e.target.id];
        if (!a) return;
        if (e.isIntersecting) {
          for (var id in map) map[id].classList.remove('on');
          a.classList.add('on');
        }
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    for (var id2 in map) io.observe(document.getElementById(id2));
  })();
})();
