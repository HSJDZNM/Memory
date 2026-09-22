(function () {
  'use strict';
  var D = window.CONSOLE_DATA || {};
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var PAGE = document.body.getAttribute('data-page') || '';
  // 仓库公开的演示令牌（api/README.md 与 tests/fixtures/api/README.md 已登记），不是真实凭据
  var DEMO_TOKEN = 'local-dev-token';

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text !== undefined && text !== null) { n.textContent = String(text); }
    return n;
  }
  function td(text, cls) { var c = el('td', cls || null, text); return c; }
  function chip(kind, text, tip) {
    var c = el('span', 'chip ' + kind, text);
    if (tip) { c.setAttribute('data-tip', tip); }
    return c;
  }
  function q(tip) { var s = el('span', 'q', '?'); s.setAttribute('data-tip', tip); return s; }
  function frac(node, text) { node.textContent = text; }

  /* ---------- tooltip ---------- */
  function initTips() {
    var box = el('div'); box.id = 'tip'; document.body.appendChild(box);
    function show(target) {
      var text = target.getAttribute('data-tip');
      if (!text) { return; }
      box.textContent = text;
      box.style.display = 'block';
      var r = target.getBoundingClientRect();
      var w = box.offsetWidth, h = box.offsetHeight;
      var left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
      var top = r.top - h - 8;
      if (top < 8) { top = r.bottom + 8; }
      box.style.left = left + 'px';
      box.style.top = top + 'px';
    }
    document.addEventListener('mouseover', function (e) {
      var t = e.target.closest ? e.target.closest('[data-tip]') : null;
      if (t) { show(t); }
    });
    document.addEventListener('mouseout', function (e) {
      var t = e.target.closest ? e.target.closest('[data-tip]') : null;
      if (t) { box.style.display = 'none'; }
    });
    document.addEventListener('focusin', function (e) {
      var t = e.target.closest ? e.target.closest('[data-tip]') : null;
      if (t) { show(t); }
    });
    document.addEventListener('focusout', function () { box.style.display = 'none'; });
    window.addEventListener('scroll', function () { box.style.display = 'none'; }, true);
  }

  /* ---------- store ---------- */
  var Store = {
    read: function () {
      try {
        var raw = window.localStorage.getItem('console.state');
        var parsed = raw ? JSON.parse(raw) : null;
        if (parsed && typeof parsed === 'object') {
          parsed.picks = parsed.picks || []; parsed.candidates = parsed.candidates || [];
          return parsed;
        }
      } catch (e) { /* file:// 下可能不可用 */ }
      return { picks: [], candidates: [] };
    },
    write: function (state) {
      try { window.localStorage.setItem('console.state', JSON.stringify(state)); } catch (e) { /* ignore */ }
      return state;
    }
  };

  /* ---------- tabs ---------- */
  function initTabs() {
    var buttons = $$('.tabs button');
    if (!buttons.length) { return; }
    function select(name) {
      buttons.forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-tab') === name); });
      $$('[data-panel]').forEach(function (p) { p.classList.toggle('hide', p.getAttribute('data-panel') !== name); });
      $$('.tabs a').forEach(function (a) { a.classList.remove('active'); });
    }
    buttons.forEach(function (b) {
      b.addEventListener('click', function () { select(b.getAttribute('data-tab')); history.replaceState(null, '', '#' + b.getAttribute('data-tab')); });
    });
    var wanted = (location.hash || '').replace('#', '');
    select(buttons.some(function (b) { return b.getAttribute('data-tab') === wanted; }) ? wanted : buttons[0].getAttribute('data-tab'));
  }

  /* ---------- 数据层：chunk 列表 + 勾选 ---------- */
  function initData() {
    var body = $('#chunk-body');
    if (!body) { return; }
    var state = Store.read();
    var filter = $('#chunk-filter');
    function render() {
      var needle = (filter && filter.value || '').trim().toLowerCase();
      body.textContent = '';
      D.chunks.forEach(function (c) {
        var hay = [c.chunk_id, c.document, c.dataset, c.heading, c.text].join(' ').toLowerCase();
        if (needle && hay.indexOf(needle) < 0) { return; }
        var tr = el('tr');
        var cell = el('td'); var cb = el('input'); cb.type = 'checkbox';
        cb.checked = state.picks.indexOf(c.chunk_id) >= 0;
        cb.addEventListener('change', function () {
          var i = state.picks.indexOf(c.chunk_id);
          if (cb.checked && i < 0) { state.picks.push(c.chunk_id); }
          if (!cb.checked && i >= 0) { state.picks.splice(i, 1); }
          Store.write(state); count(); tr.classList.toggle('sel', cb.checked);
        });
        cell.appendChild(cb); tr.appendChild(cell);
        tr.appendChild(td(c.chunk_id, 'mono'));
        tr.appendChild(td(c.dataset, 'mono'));
        tr.appendChild(td(c.heading));
        tr.appendChild(td((c.text || '').slice(0, 70) + '…'));
        tr.appendChild(td((c.hash || '').slice(0, 10) + '…', 'mono'));
        if (cb.checked) { tr.classList.add('sel'); }
        body.appendChild(tr);
      });
    }
    function count() { frac($('#sel-count'), state.picks.length); }
    if (filter) { filter.addEventListener('input', render); }
    var add = $('#add-picks');
    if (add) {
      add.addEventListener('click', function () {
        if (!state.picks.length) { return; }
        Store.write(state);
        location.href = 'authoring.html';
      });
    }
    render(); count();
  }

  /* ---------- 提炼与审查 ---------- */
  var CHECKER_FIELDS = D.checker_fields || {};

  function fieldsFor(checker) { return CHECKER_FIELDS[checker] || []; }
  function bodyOf(ids) {
    var body = {};
    ids.forEach(function (id) {
      var input = $('#' + id);
      var name = input.getAttribute('data-field');
      var kind = input.getAttribute('data-kind');
      var raw = input.value.trim();
      if (!raw) { return; }
      if (kind === 'bool') { body[name] = (raw === 'true'); return; }
      var parts = raw.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
      body[name] = parts.length > 1 ? parts : parts[0];
    });
    return body;
  }

  function renderFields() {
    var host = $('#body-fields');
    if (!host) { return; }
    host.textContent = '';
    fieldsFor($('#checker').value).forEach(function (spec) {
      var lab = el('label', 'f', spec.label + (spec.required ? ' *' : ''));
      if (spec.hint) { lab.appendChild(q(spec.hint)); }
      host.appendChild(lab);
      var input = el('input'); input.type = 'text'; input.id = 'f-' + spec.name;
      input.setAttribute('data-field', spec.name); input.setAttribute('data-kind', spec.kind);
      input.placeholder = spec.kind === 'bool' ? 'true / false' : (spec.placeholder || (spec.values ? spec.values.join(', ') : ''));
      host.appendChild(input);
    });
  }

  function validate(payload) {
    var out = [];
    function add(code, level, text) { out.push({ code: code, level: level, text: text }); }
    var spec = (D.checkers || []).filter(function (c) { return c.id === payload.checker; })[0];
    if (!spec) { add('unknown_checker', 'no', 'checker 未实现'); }
    else {
      add('checker_known', 'ok', 'checker 已实现');
      if (!spec.validators.length) { add('checker_uncovered', 'no', '无验证器供证（C25）'); }
      else { add('checker_covered', 'ok', spec.validators.length + ' 个验证器供证'); }
      var specs = fieldsFor(payload.checker);
      specs.filter(function (f) { return f.required; }).forEach(function (f) {
        if (payload.body[f.name] === undefined) { add('rule_body_incomplete', 'no', '缺少 ' + f.name + '（C19）'); }
      });
      var names = specs.map(function (f) { return f.name; });
      Object.keys(payload.body).forEach(function (k) {
        if (names.indexOf(k) < 0) { add('rule_body_unknown_field', 'no', '未知字段 ' + k + '（C21）'); }
      });
      if (payload.checker === 'style_lint' || payload.checker === 'type_check') {
        var codes = payload.body.codes;
        if (codes) {
          (Array.isArray(codes) ? codes : [codes]).forEach(function (c) {
            if (c !== c.toUpperCase()) { add('codes_not_uppercase', 'no', 'codes 必须大写（C19）'); }
          });
        }
      }
    }
    if (!payload.message) { add('message_empty', 'no', 'message 必填'); }
    if ((D.severities || []).indexOf(payload.severity) < 0) { add('severity_unknown', 'no', '未知 severity（C15）'); }
    else { add('severity_ok', 'ok', 'severity=' + payload.severity + '（枚举有效；最终 Decision 只由 Policy API 返回）'); }
    return out;
  }

  function yamlOf(payload) {
    var lines = ['id: NEW-00' + (Store.read().candidates.length + 1), 'version: 1', 'name: draft-from-console',
      'description: 控制台草案', 'scope:', '  language: python', 'severity: ' + payload.severity,
      'enforcement:', '  type: deterministic', '  checker: ' + payload.checker, 'rule:', '  ' + payload.checker + ':'];
    Object.keys(payload.body).forEach(function (k) {
      var v = payload.body[k];
      lines.push('    ' + k + ': ' + (Array.isArray(v) ? '[' + v.join(', ') + ']' : v));
    });
    lines.push('message: ' + payload.message);
    lines.push('source:', '  kind: standard', '  path: ' + payload.source);
    return lines.join('\n');
  }

  function initAuthoring() {
    var queue = $('#queue-body');
    if (!queue) { return; }
    var state = Store.read();
    var current = null;
    var filter = $('#queue-filter');

    function renderQueue() {
      var needle = (filter && filter.value || '').trim().toLowerCase();
      queue.textContent = '';
      D.chunks.forEach(function (c) {
        var hay = [c.chunk_id, c.document, c.dataset, c.heading, c.text].join(' ').toLowerCase();
        if (needle && hay.indexOf(needle) < 0) { return; }
        var picked = state.picks.indexOf(c.chunk_id) >= 0;
        var tr = el('tr');
        var cell = el('td'); var cb = el('input'); cb.type = 'checkbox'; cb.checked = picked;
        cb.addEventListener('change', function () {
          var i = state.picks.indexOf(c.chunk_id);
          if (cb.checked && i < 0) { state.picks.push(c.chunk_id); }
          if (!cb.checked && i >= 0) { state.picks.splice(i, 1); }
          Store.write(state); count(); tr.classList.toggle('sel', cb.checked);
        });
        cell.appendChild(cb); tr.appendChild(cell);
        tr.appendChild(td(c.chunk_id, 'mono'));
        tr.appendChild(td(c.heading));
        tr.appendChild(td(picked ? '已选' : '—'));
        tr.style.cursor = 'pointer';
        tr.addEventListener('click', function (e) {
          if (e.target.tagName === 'INPUT') { return; }
          load(c);
        });
        if (picked) { tr.classList.add('sel'); }
        queue.appendChild(tr);
      });
      var none = el('tr'); var c = td('（无匹配）'); c.colSpan = 5; none.appendChild(c);
      if (!queue.children.length) { queue.appendChild(none); }
    }
    function count() { frac($('#picked-count'), state.picks.length); }

    function load(c) {
      current = c;
      $('#source-path').value = c.document || '';
      var ref = $('#chunk-ref');
      ref.textContent = c.chunk_id + ' · ' + (c.heading || '');
      ref.setAttribute('data-tip', '来源：' + (c.document || '') + '｜text_hash ' + (c.hash || '') + '｜许可 ' + (c.license || '—'));
      renderFields();
      frac($('#result'), '');
    }

    function dryRun() {
      var payload = { checker: $('#checker').value, severity: $('#severity').value, message: $('#message').value.trim(),
        body: bodyOf($$('#body-fields input').map(function (i) { return i.id; })), source: $('#source-path').value };
      var lines = validate(payload);
      var host = $('#result'); host.textContent = '';
      var blocked = lines.filter(function (l) { return l.level === 'no'; }).length;
      var head = el('div', 'toolbar');
      head.appendChild(chip(blocked ? 'no' : 'ok', blocked ? '预演失败 ' + blocked + ' 项' : '预演通过'));
      head.appendChild(el('span', 'small', blocked ? '整批不加载，现网规则集未替换（C23）' : '通过 ≠ 生效'));
      host.appendChild(head);
      lines.forEach(function (l) {
        var row = el('div', 'result');
        row.appendChild(el('span', 'code', l.code));
        row.appendChild(el('span', l.level, l.level === 'no' ? '阻断' : '通过'));
        row.appendChild(el('span', null, l.text));
        host.appendChild(row);
      });
      var pre = el('pre'); var code = el('code'); code.textContent = yamlOf(payload); pre.appendChild(code);
      var prev = $('#yaml-preview'); prev.textContent = ''; prev.appendChild(pre);
      window.__draft = { payload: payload, lines: lines, chunk: current };
      $('#add-candidate').disabled = blocked > 0;
    }

    function addCandidate() {
      if (!window.__draft) { return; }
      var d = window.__draft;
      state.candidates.push({
        id: 'CAND-' + String(state.candidates.length + 1).padStart(3, '0'),
        checker: d.payload.checker, severity: d.payload.severity, message: d.payload.message,
        source: d.payload.source, chunk: d.chunk ? d.chunk.chunk_id : '', state: 'D2 可加载'
      });
      Store.write(state);
      renderCandidates();
      var b = $('#add-candidate'); b.textContent = '已加入候选（' + state.candidates.length + '）'; b.disabled = true;
    }

    function renderCandidates() {
      var body = $('#cand-body');
      if (!body) { return; }
      body.textContent = '';
      if (!state.candidates.length) { var tr = el('tr'); var c = td('（空）'); c.colSpan = 6; tr.appendChild(c); body.appendChild(tr); return; }
      state.candidates.forEach(function (k) {
        var tr = el('tr');
        tr.appendChild(td(k.id, 'mono'));
        tr.appendChild(td(k.checker, 'mono'));
        tr.appendChild(td(k.severity));
        tr.appendChild(td(k.chunk || '—', 'mono'));
        tr.appendChild(td(k.state));
        var a = el('td'); var link = el('a', null, '去门禁'); link.href = 'gates.html'; a.appendChild(link); tr.appendChild(a);
        body.appendChild(tr);
      });
    }

    var checker = $('#checker');
    if (checker) { checker.addEventListener('change', renderFields); }
    var run = $('#dry-run');
    if (run) { run.addEventListener('click', dryRun); }
    var addBtn = $('#add-candidate');
    if (addBtn) { addBtn.addEventListener('click', addCandidate); }
    if (filter) { filter.addEventListener('input', renderQueue); }
    var clear = $('#clear-picks');
    if (clear) { clear.addEventListener('click', function () { state.picks = []; Store.write(state); renderQueue(); count(); }); }
    renderFields(); renderQueue(); count(); renderCandidates();
    if (state.picks.length) {
      var first = D.chunks.filter(function (c) { return c.chunk_id === state.picks[0]; })[0];
      if (first) { load(first); }
    }
  }

  /* ---------- 门禁 ---------- */
  function initGates() {
    var summary = $('#gate-summary');
    if (summary) {
      function refresh() {
        var broken = $$('#gate-table input[type=checkbox]').filter(function (c) { return c.checked; });
        summary.textContent = '';
        if (!broken.length) { summary.appendChild(chip('ok', '加载成功：' + $('#gate-table tbody').children.length + ' 条规则通过')); }
        else {
          summary.appendChild(chip('no', '整批不加载（退出码 2）'));
          summary.appendChild(el('span', 'small', '坏规则 ' + broken.map(function (c) { return c.getAttribute('data-rule'); }).join('、') + ' → 现网规则集未替换'));
        }
      }
      $$('#gate-table input[type=checkbox]').forEach(function (c) { c.addEventListener('change', refresh); });
      refresh();
    }
    var cand = $('#cand-gate-body');
    if (cand) {
      var state = Store.read();
      cand.textContent = '';
      if (!state.candidates.length) { var tr = el('tr'); var c = td('（无候选：先在第 2 页起草）'); c.colSpan = 5; tr.appendChild(c); cand.appendChild(tr); }
      state.candidates.forEach(function (k) {
        var tr = el('tr');
        tr.appendChild(td(k.id, 'mono'));
        tr.appendChild(td(k.checker, 'mono'));
        tr.appendChild(td(k.severity));
        tr.appendChild(td('待预演'));
        var act = el('td');
        var btn = el('button', 'btn ghost', '预演');
        btn.addEventListener('click', function () {
          var spec = (D.checkers || []).filter(function (x) { return x.id === k.checker; })[0];
          var covered = spec && spec.validators.length;
          tr.children[3].textContent = covered ? '预演通过' : '无验证器供证（C25）';
          tr.children[3].className = covered ? 'ok' : 'no';
          btn.disabled = true;
        });
        act.appendChild(btn); tr.appendChild(act);
        cand.appendChild(tr);
      });
    }
  }

  /* ---------- 审批 · 生效 ---------- */
  function initActivation() {
    var body = $('#submit-body');
    if (!body) { return; }
    var state = Store.read();
    var last = state.candidates[state.candidates.length - 1];
    function render() {
      body.textContent = '';
      if (!last) { var tr = el('tr'); var c = td('（无候选：先在第 2 页起草）'); c.colSpan = 2; tr.appendChild(c); body.appendChild(tr); return; }
      [['candidate', last.id], ['tool', 'orc.policy.write'], ['file_path', 'policies/<domain>/' + last.id + '.yaml'],
       ['checker', last.checker], ['severity', last.severity], ['source_chunk', last.chunk || '—'],
       ['action_hash', '（由平台计算）'], ['rollback', 'file_snapshot'],
       ['post_checks', 'content_matches, file_changed, file_syntax, diff_recorded']].forEach(function (pair) {
        var tr = el('tr'); tr.appendChild(td(pair[0], 'mono')); tr.appendChild(td(pair[1], 'mono')); body.appendChild(tr);
      });
    }
    render();
  }

  /* ---------- 连接自检 ---------- */
  function initProbe() {
    var btn = $('#probe-btn');
    if (!btn) { return; }
    var out = $('#probe-out');
    btn.addEventListener('click', function () {
      out.textContent = '';
      out.appendChild(el('div', 'small', 'GET http://127.0.0.1:8088/v1/health/live …'));
      fetch('http://127.0.0.1:8088/v1/health/live', {
        headers: { Authorization: 'Bearer ' + DEMO_TOKEN },
      })
        .then(function (r) {
          out.textContent = '';
          var acao = r.headers.get('access-control-allow-origin');
          out.appendChild(chip(r.ok ? 'ok' : 'gap', 'HTTP ' + r.status));
          out.appendChild(el('span', 'small', 'Access-Control-Allow-Origin: ' + (acao === null ? '（缺失）' : acao)));
          return r.text();
        })
        .then(function (text) { var pre = el('pre'); var c = el('code'); c.textContent = text; pre.appendChild(c); out.appendChild(pre); })
        .catch(function (e) {
          out.textContent = '';
          out.appendChild(chip('no', '浏览器拒绝：' + e.name));
          out.appendChild(el('span', 'small', '服务端未注册 CORS 中间件；独立源读不到响应'));
        });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initTips(); initTabs();
    if (PAGE === 'data') { initData(); }
    if (PAGE === 'authoring') { initAuthoring(); }
    if (PAGE === 'gates') { initGates(); }
    if (PAGE === 'activation') { initActivation(); }
    if (PAGE === 'system') { initProbe(); }
  });
})();
