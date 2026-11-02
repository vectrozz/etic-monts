/* Coût de revient — live calculation.
   Mirrors eticmonts/production_cost.py::compute(); keep both in sync. */
(function () {
    'use strict';

    var form = document.getElementById('cr-form');
    if (!form) return;
    var cfg = JSON.parse(document.getElementById('cr-config').textContent);

    var NNBSP = ' ';
    function fmt(v, decimals) {
        if (v === null || v === undefined || !isFinite(v)) return '—';
        return v.toLocaleString('fr-FR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    }
    function money(v, decimals) {
        var s = fmt(v, decimals === undefined ? 2 : decimals);
        return s === '—' ? s : s + NNBSP + '€';
    }

    function val(name) {
        var el = form.elements[name];
        if (!el || el.value === '') return null;
        var f = parseFloat(String(el.value).replace(',', '.'));
        return isFinite(f) ? f : null;
    }
    function pos(name) { var f = val(name); return f !== null && f > 0 ? f : null; }
    function div(a, b) { return (a === null || b === null || b === 0) ? null : a / b; }
    function sum(prefix, keys) {
        return keys.reduce(function (acc, k) { var f = val(prefix + k); return acc + (f === null ? 0 : f); }, 0);
    }

    function compute() {
        var plants = pos('nb_units'), surface = pos('surface_m2'), yieldKg = pos('yield_kg');
        var price = pos('sale_price'), rate = pos('hourly_cost');
        var hours = sum('task_', cfg.tasks);
        var harvestH = pos('task_' + cfg.harvestTask);
        var inputs = sum('charge_', cfg.inputs);
        var structure = sum('charge_', cfg.structure);

        var labour = rate !== null ? hours * rate : null;
        var total = (labour || 0) + inputs + structure;
        var revenue = (yieldKg !== null && price !== null) ? yieldKg * price : null;
        var costPerKg = total > 0 ? div(total, yieldKg) : null;
        function share(part) { return (part !== null && total > 0) ? part / total * 100 : null; }

        var missing = [];
        [[plants, 'nombre de plants'], [surface, 'surface'], [yieldKg, 'récolte commercialisée'],
         [price, 'prix de vente'], [rate, 'coût horaire']].forEach(function (p) { if (p[0] === null) missing.push(p[1]); });
        if (hours === 0) missing.push('temps de travail');

        return {
            hours_total: hours,
            hours_per_1000m2: hours ? div(hours * 1000, surface) : null,
            harvest_kg_per_hour: div(yieldKg, harvestH),
            labour_cost: labour,
            labour_included: rate !== null,
            inputs_total: inputs,
            structure_total: structure,
            total_cost: total,
            cost_per_kg: costPerKg,
            cost_per_plant: total > 0 ? div(total, plants) : null,
            yield_per_plant_g: yieldKg ? div(yieldKg * 1000, plants) : null,
            yield_per_m2: div(yieldKg, surface),
            margin_per_kg: (price !== null && costPerKg !== null) ? price - costPerKg : null,
            hourly_return: (revenue !== null && hours) ? div(revenue - inputs - structure, hours) : null,
            share_labour: share(labour),
            share_inputs: share(inputs),
            share_structure: share(structure),
            missing: missing
        };
    }

    var FORMATS = {
        hours_total: function (v) { return fmt(v, 1); },
        hours_per_1000m2: function (v) { return fmt(v, 0); },
        harvest_kg_per_hour: function (v) { return fmt(v, 1); },
        labour_cost: function (v) { return money(v, 0); },
        inputs_total: function (v) { return money(v, 0); },
        structure_total: function (v) { return money(v, 0); },
        total_cost: function (v) { return money(v, 0); },
        cost_per_kg: function (v) { return fmt(v, 2); },
        cost_per_plant: function (v) { return money(v, 2); },
        yield_per_plant_g: function (v) { return fmt(v, 0); },
        yield_per_m2: function (v) { return fmt(v, 2); },
        hourly_return: function (v) { return money(v, 2); },
        share_labour: function (v) { return v === null ? '—' : fmt(v, 0) + ' %'; },
        share_inputs: function (v) { return v === null ? '—' : fmt(v, 0) + ' %'; },
        share_structure: function (v) { return v === null ? '—' : fmt(v, 0) + ' %'; },
        missing: function (v) { return v.join(', '); }
    };

    function render() {
        var r = compute();
        document.querySelectorAll('[data-out]').forEach(function (el) {
            var key = el.getAttribute('data-out');
            if (key === 'margin_label') {
                el.textContent = r.margin_per_kg === null
                    ? (r.cost_per_kg === null ? 'Marge : renseignez récolte et charges' : 'Marge : indiquez le prix de vente')
                    : 'Marge ' + money(r.margin_per_kg) + '/kg';
                return;
            }
            if (key in FORMATS) el.textContent = FORMATS[key](r[key]);
        });
        document.querySelectorAll('[data-bar]').forEach(function (el) {
            el.style.width = (r[el.getAttribute('data-bar')] || 0) + '%';
        });
        document.querySelectorAll('[data-out-class="margin_per_kg"]').forEach(function (el) {
            el.classList.toggle('pos', r.margin_per_kg !== null && r.margin_per_kg >= 0);
            el.classList.toggle('neg', r.margin_per_kg !== null && r.margin_per_kg < 0);
        });
        document.querySelectorAll('[data-show="no_labour"]').forEach(function (el) { el.hidden = r.labour_included; });
        document.querySelectorAll('[data-show="missing"]').forEach(function (el) { el.hidden = r.missing.length === 0; });
    }

    form.addEventListener('input', render);
    form.addEventListener('change', render);
    render();

    /* ---- "Reprendre l'année précédente" ---------------------------------- */
    var prevNode = document.getElementById('cr-previous');
    var prev = prevNode ? JSON.parse(prevNode.textContent) : null;
    var copyBtn = document.querySelector('[data-copy-previous]');
    if (copyBtn && prev) {
        copyBtn.addEventListener('click', function () {
            function set(name, v) {
                var el = form.elements[name];
                if (el && v !== null && v !== undefined && el.value === '') el.value = v;
            }
            ['nb_units', 'surface_m2', 'variety', 'system', 'sale_price', 'hourly_cost'].forEach(function (k) { set(k, prev[k]); });
            Object.keys(prev.tasks || {}).forEach(function (k) { set('task_' + k, prev.tasks[k]); });
            Object.keys(prev.charges || {}).forEach(function (k) { set('charge_' + k, prev.charges[k]); });
            copyBtn.disabled = true;
            copyBtn.textContent = 'Valeurs reprises — ajustez-les';
            render();
        });
    }

    /* ---- Warn before leaving with unsaved changes ------------------------ */
    var dirty = false;
    form.addEventListener('input', function () { dirty = true; });
    document.querySelectorAll('button[type="submit"]').forEach(function (b) {
        b.addEventListener('click', function () { dirty = false; });
    });
    window.addEventListener('beforeunload', function (e) {
        if (dirty) { e.preventDefault(); e.returnValue = ''; }
    });

    /* ---- History chart: €/kg split per campaign --------------------------- */
    var canvas = document.getElementById('history-chart');
    var histNode = document.getElementById('cr-history-data');
    if (canvas && histNode && window.Chart && window.EMBChart) {
        var h = JSON.parse(histNode.textContent);
        var labels = h.map(function (d) { return String(d.year); });
        function colorize(datasets) {
            var p = EMBChart.palette();
            var colors = [p[0], p[2], p[3]];
            datasets.forEach(function (ds, i) {
                var c = i < 3 ? colors[i] : p[1];
                ds.backgroundColor = c;
                ds.borderColor = c;
                ds.pointBackgroundColor = c;
                ds.pointBorderColor = c;
            });
            return datasets;
        }
        var chart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: colorize([
                    { label: "Main-d'œuvre", data: h.map(function (d) { return d.labour; }), stack: 'c', maxBarThickness: 64 },
                    { label: 'Intrants', data: h.map(function (d) { return d.inputs; }), stack: 'c', maxBarThickness: 64 },
                    { label: 'Structure', data: h.map(function (d) { return d.structure; }), stack: 'c', maxBarThickness: 64 },
                    { label: 'Prix de vente', type: 'line', data: h.map(function (d) { return d.price; }),
                      pointRadius: 4, borderWidth: 2, spanGaps: true }
                ])
            },
            options: {
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { stacked: true, grid: { display: false } },
                    y: { stacked: true, beginAtZero: true, title: { display: true, text: '€ / kg' } }
                },
                plugins: {
                    legend: { position: 'bottom' },
                    tooltip: { callbacks: { label: function (c) { return c.dataset.label + ' : ' + money(c.parsed.y); } } }
                }
            }
        });
        // Re-applied by EMBChart.refresh() when the theme changes.
        chart.$embRecolor = function (c) { colorize(c.data.datasets); };
    }
})();
