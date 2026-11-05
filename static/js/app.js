/* Etic'Monts — app shell behaviour (navigation drawer, nav groups, theme, chart theming). */
(function () {
    'use strict';

    var root = document.documentElement;
    var body = document.body;

    /* ---- Mobile navigation drawer ---------------------------------------- */
    var toggle = document.querySelector('.nav-toggle');
    function setNav(open) {
        body.classList.toggle('nav-open', open);
        if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    if (toggle) toggle.addEventListener('click', function () { setNav(!body.classList.contains('nav-open')); });
    document.querySelectorAll('[data-nav-close]').forEach(function (el) {
        el.addEventListener('click', function () { setNav(false); });
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setNav(false); });

    /* ---- Collapsible sidebar groups (state remembered per browser) ------- */
    var KEY = 'emb-sidebar-collapsed';
    var state = {};
    try { state = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { state = {}; }
    document.querySelectorAll('.nav-group').forEach(function (group) {
        var id = group.dataset.section;
        var header = group.querySelector('.nav-section');
        // Never hide the group holding the current page.
        if (state[id] && !group.querySelector('a.active')) group.classList.add('collapsed');
        if (header) header.setAttribute('aria-expanded', group.classList.contains('collapsed') ? 'false' : 'true');
        if (!header) return;
        header.addEventListener('click', function () {
            group.classList.toggle('collapsed');
            var collapsed = group.classList.contains('collapsed');
            header.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
            state[id] = collapsed;
            try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
        });
    });

    /* ---- Farm picker (WhatsApp senders): filter + Enter picks the first match ---- */
    function fold(s) { return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
    document.querySelectorAll('.farm-pick').forEach(function (pick) {
        var input = pick.querySelector('.farm-pick-filter');
        var chips = Array.prototype.slice.call(pick.querySelectorAll('.farm-chip[data-label]'));
        var empty = pick.querySelector('.farm-pick-empty');
        pick.addEventListener('toggle', function () {
            if (!pick.open) return;
            // one picker open at a time
            document.querySelectorAll('.farm-pick[open]').forEach(function (o) { if (o !== pick) o.open = false; });
            if (input) input.focus();
        });
        if (!input) return;
        input.addEventListener('input', function () {
            var q = fold(input.value.trim());
            var shown = 0;
            chips.forEach(function (c) {
                c.hidden = !!q && fold(c.dataset.label).indexOf(q) === -1;
                if (!c.hidden) shown++;
            });
            if (empty) empty.hidden = shown > 0;
        });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {            // never submit without a farm
                e.preventDefault();
                var first = chips.filter(function (c) { return !c.hidden; })[0];
                if (first) first.click();
            } else if (e.key === 'Escape') {
                pick.open = false;
            }
        });
    });

    /* ---- Theme: auto (system) / light / dark ----------------------------- */
    var themeSelect = document.getElementById('theme-select');
    function currentTheme() {
        try { return localStorage.getItem('emb-theme') || 'auto'; } catch (e) { return 'auto'; }
    }
    function applyTheme(t) {
        if (t === 'light' || t === 'dark') root.setAttribute('data-theme', t);
        else root.removeAttribute('data-theme');
        try { localStorage.setItem('emb-theme', t); } catch (e) {}
        window.EMBChart && window.EMBChart.refresh();
    }
    if (themeSelect) {
        themeSelect.value = currentTheme();
        themeSelect.addEventListener('change', function () { applyTheme(themeSelect.value); });
    }

    /* ---- Chart.js theming ------------------------------------------------- */
    function css(name) { return getComputedStyle(root).getPropertyValue(name).trim(); }
    var EMBChart = {
        css: css,
        palette: function () {
            return [1, 2, 3, 4, 5, 6, 7, 8].map(function (i) { return css('--chart-' + i); });
        },
        color: function (i) { var p = EMBChart.palette(); return p[i % p.length]; },
        alpha: function (color, a) {
            // hex (#rrggbb) → rgba
            var m = /^#([0-9a-f]{6})$/i.exec(color);
            if (!m) return color;
            var n = parseInt(m[1], 16);
            return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')';
        },
        applyDefaults: function () {
            if (!window.Chart) return;
            Chart.defaults.font.family = css('--font-sans') || 'system-ui';
            Chart.defaults.font.size = 12;
            Chart.defaults.color = css('--chart-text');
            Chart.defaults.borderColor = css('--chart-grid');
            Chart.defaults.plugins.legend.labels.boxWidth = 10;
            Chart.defaults.plugins.legend.labels.boxHeight = 10;
            Chart.defaults.plugins.legend.labels.useBorderRadius = true;
            Chart.defaults.plugins.legend.labels.borderRadius = 3;
            Chart.defaults.plugins.tooltip.backgroundColor = css('--text');
            Chart.defaults.plugins.tooltip.titleColor = css('--bg-card');
            Chart.defaults.plugins.tooltip.bodyColor = css('--bg-card');
            Chart.defaults.plugins.tooltip.padding = 10;
            Chart.defaults.plugins.tooltip.cornerRadius = 8;
            Chart.defaults.elements.bar.borderRadius = 4;
            Chart.defaults.elements.line.tension = 0.3;
            Chart.defaults.locale = 'fr-FR';
        },
        refresh: function () {
            EMBChart.applyDefaults();
            if (!window.Chart) return;
            Object.values(Chart.instances || {}).forEach(function (c) {
                if (typeof c.$embRecolor === 'function') c.$embRecolor(c);
                c.update();
            });
        }
    };
    window.EMBChart = EMBChart;
    EMBChart.applyDefaults();

    if (window.matchMedia) {
        var mq = window.matchMedia('(prefers-color-scheme: dark)');
        var onChange = function () { if (currentTheme() === 'auto') EMBChart.refresh(); };
        if (mq.addEventListener) mq.addEventListener('change', onChange);
    }
})();
