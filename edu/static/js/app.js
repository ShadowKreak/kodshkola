/* KodShkola — клиентская логика: меню, подтверждения, подсветка кода, редактор Markdown. */
(function () {
  "use strict";

  /* ---------- боковое меню на мобильных ---------- */
  var burger = document.querySelector("[data-nav-toggle]");
  var scrim = document.querySelector(".scrim");
  if (burger) burger.addEventListener("click", function () { document.body.classList.toggle("nav-open"); });
  if (scrim) scrim.addEventListener("click", function () { document.body.classList.remove("nav-open"); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") document.body.classList.remove("nav-open"); });

  /* ---------- регистрация: поле кода только для администратора ---------- */
  var codeField = document.getElementById("admin-code-field");
  if (codeField) {
    var radios = document.querySelectorAll('input[name="role"]');
    var sync = function () {
      var admin = document.querySelector('input[name="role"][value="admin"]');
      codeField.style.display = admin && admin.checked ? "" : "none";
    };
    radios.forEach(function (r) { r.addEventListener("change", sync); });
    sync();
  }

  /* ---------- подтверждение опасных действий ---------- */
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  /* ---------- закрытие уведомлений ---------- */
  document.querySelectorAll(".flash button").forEach(function (b) {
    b.addEventListener("click", function () { b.parentNode.remove(); });
  });

  /* ---------- показать / скрыть форму переименования ---------- */
  document.querySelectorAll("[data-toggle]").forEach(function (b) {
    b.addEventListener("click", function () {
      var t = document.getElementById(b.getAttribute("data-toggle"));
      if (t) { t.classList.toggle("open"); var i = t.querySelector("input"); if (i) i.focus(); }
    });
  });

  /* ---------- подсветка синтаксиса ---------- */
  var KW = {
    python: "False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield self print",
    javascript: "async await break case catch class const continue debugger default delete do else export extends finally for from function if import in instanceof let new of return super switch this throw try typeof var void while with yield null undefined true false",
    csharp: "abstract as async await base bool break byte case catch char class const continue decimal default delegate do double else enum event explicit extern false finally float for foreach if in int interface internal is lock long namespace new null object operator out override params private protected public readonly ref return sealed short static string struct switch this throw true try typeof uint ulong using var virtual void while get set",
    java: "abstract boolean break byte case catch char class const continue default do double else enum extends final finally float for if implements import instanceof int interface long new null package private protected public return short static super switch this throw throws true false try void volatile while",
    cpp: "auto bool break case catch char class const continue default delete do double else enum explicit extern false float for friend goto if inline int long namespace new nullptr operator private protected public return short signed sizeof static struct switch template this throw true try typedef typename union unsigned using virtual void volatile while include std",
    sql: "select from where and or not insert into values update set delete create table alter drop join inner left right outer on group by order having limit as distinct null is in like between primary key foreign references default count sum avg min max union all case when then else end asc desc",
    bash: "if then else elif fi for while do done case esac function in echo cd ls cat grep export return exit",
    html: "", css: "", text: ""
  };
  var LINE_COMMENT = { python: "#", bash: "#", sql: "--", javascript: "//", csharp: "//", java: "//", cpp: "//" };
  var kwSets = {};
  Object.keys(KW).forEach(function (l) {
    var s = {}; KW[l].split(" ").forEach(function (w) { if (w) s[l === "sql" ? w.toLowerCase() : w] = 1; });
    kwSets[l] = s;
  });

  function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  function highlight(code, lang) {
    if (lang === "text" || !(lang in KW)) return esc(code);
    var out = "", i = 0, n = code.length, lc = LINE_COMMENT[lang];
    var kws = kwSets[lang];
    function peek(str) { return code.substr(i, str.length) === str; }
    while (i < n) {
      var ch = code[i];
      if (lang === "html") {
        var m = /^<\/?[A-Za-z][^>]*>|^<!--[\s\S]*?-->/.exec(code.slice(i));
        if (m) { out += '<span class="' + (m[0].indexOf("<!--") === 0 ? "tok-c" : "tok-k") + '">' + esc(m[0]) + "</span>"; i += m[0].length; continue; }
        out += esc(ch); i++; continue;
      }
      if (lang === "css") {
        var mc = /^\/\*[\s\S]*?\*\//.exec(code.slice(i));
        if (mc) { out += '<span class="tok-c">' + esc(mc[0]) + "</span>"; i += mc[0].length; continue; }
        var mp = /^[a-z-]+(?=\s*:)/.exec(code.slice(i));
        if (mp) { out += '<span class="tok-k">' + mp[0] + "</span>"; i += mp[0].length; continue; }
        var ms = /^[#.][\w-]+/.exec(code.slice(i));
        if (ms) { out += '<span class="tok-f">' + esc(ms[0]) + "</span>"; i += ms[0].length; continue; }
        var mn = /^-?\d[\w.%]*/.exec(code.slice(i));
        if (mn) { out += '<span class="tok-n">' + mn[0] + "</span>"; i += mn[0].length; continue; }
        out += esc(ch); i++; continue;
      }
      /* комментарии */
      if (lc && peek(lc)) {
        var e1 = code.indexOf("\n", i); if (e1 < 0) e1 = n;
        out += '<span class="tok-c">' + esc(code.slice(i, e1)) + "</span>"; i = e1; continue;
      }
      if ((lang === "javascript" || lang === "csharp" || lang === "java" || lang === "cpp" || lang === "sql") && peek("/*")) {
        var e2 = code.indexOf("*/", i + 2); e2 = e2 < 0 ? n : e2 + 2;
        out += '<span class="tok-c">' + esc(code.slice(i, e2)) + "</span>"; i = e2; continue;
      }
      /* строки */
      if (lang === "python" && (peek('"""') || peek("'''"))) {
        var q3 = code.substr(i, 3), e3 = code.indexOf(q3, i + 3); e3 = e3 < 0 ? n : e3 + 3;
        out += '<span class="tok-s">' + esc(code.slice(i, e3)) + "</span>"; i = e3; continue;
      }
      if (ch === '"' || ch === "'" || (ch === "`" && lang === "javascript")) {
        var j = i + 1;
        while (j < n && code[j] !== ch && code[j] !== "\n" || (ch === "`" && j < n && code[j] !== ch)) {
          if (code[j] === "\\") j++;
          j++;
        }
        j = Math.min(j + 1, n);
        out += '<span class="tok-s">' + esc(code.slice(i, j)) + "</span>"; i = j; continue;
      }
      /* числа */
      if (/[0-9]/.test(ch) && !/[\w]/.test(code[i - 1] || " ")) {
        var mnum = /^\d+(\.\d+)?/.exec(code.slice(i));
        out += '<span class="tok-n">' + mnum[0] + "</span>"; i += mnum[0].length; continue;
      }
      /* слова */
      if (/[A-Za-z_]/.test(ch)) {
        var mw = /^[A-Za-z_]\w*/.exec(code.slice(i))[0];
        var key = lang === "sql" ? mw.toLowerCase() : mw;
        var after = code[i + mw.length];
        if (kws[key]) out += '<span class="tok-k">' + mw + "</span>";
        else if (after === "(") out += '<span class="tok-f">' + mw + "</span>";
        else if (/^[A-Z]/.test(mw) && lang !== "sql" && lang !== "bash") out += '<span class="tok-t">' + mw + "</span>";
        else out += mw;
        i += mw.length; continue;
      }
      out += esc(ch); i++;
    }
    return out;
  }

  var LANG_NAMES = { python: "Python", javascript: "JavaScript", csharp: "C#", java: "Java", cpp: "C++", sql: "SQL", html: "HTML", css: "CSS", bash: "Bash", text: "Текст" };
  var ALIASES = { js: "javascript", "c#": "csharp", cs: "csharp", "c++": "cpp", py: "python", sh: "bash", shell: "bash", txt: "text", plaintext: "text" };

  function enhance(pre, forcedLang, title) {
    if (pre.parentNode.classList.contains("code-block")) return;
    var codeEl = pre.querySelector("code") || pre;
    var lang = forcedLang || "";
    if (!lang) {
      var m = /language-([\w+#-]+)/.exec(codeEl.className || "");
      lang = m ? m[1].toLowerCase() : "text";
    }
    lang = ALIASES[lang] || lang;
    var raw = codeEl.textContent.replace(/\n$/, "");
    var lines = raw.split("\n").length;

    var wrap = document.createElement("div"); wrap.className = "code-block";
    var head = document.createElement("div"); head.className = "code-head";
    head.innerHTML = '<span class="code-title"></span>';
    head.querySelector(".code-title").textContent = lang === "text" ? (title || "Код") : (title ? title + " — " : "") + (LANG_NAMES[lang] || lang);
    var btn = document.createElement("button"); btn.type = "button"; btn.className = "code-copy"; btn.textContent = "Копировать";
    btn.addEventListener("click", function () {
      function done() { btn.textContent = "Скопировано"; btn.classList.add("done"); setTimeout(function () { btn.textContent = "Копировать"; btn.classList.remove("done"); }, 1600); }
      if (navigator.clipboard && window.isSecureContext !== false) navigator.clipboard.writeText(raw).then(done, fallback); else fallback();
      function fallback() {
        var t = document.createElement("textarea"); t.value = raw; document.body.appendChild(t); t.select();
        try { document.execCommand("copy"); done(); } catch (err) { /* ignore */ } t.remove();
      }
    });
    head.appendChild(btn);

    var newPre = document.createElement("pre");
    var ln = document.createElement("span"); ln.className = "ln"; ln.setAttribute("aria-hidden", "true");
    var nums = []; for (var k = 1; k <= lines; k++) nums.push(k); ln.textContent = nums.join("\n");
    var code = document.createElement("code"); code.innerHTML = highlight(raw, lang);
    newPre.appendChild(ln); newPre.appendChild(code);
    wrap.appendChild(head); wrap.appendChild(newPre);
    pre.parentNode.replaceChild(wrap, pre);
  }

  document.querySelectorAll(".prose pre:not([data-lang])").forEach(function (p) { enhance(p); });
  document.querySelectorAll("pre[data-lang]").forEach(function (p) {
    enhance(p, p.getAttribute("data-lang"), p.getAttribute("data-title"));
  });
  window.KodShkola = { enhance: enhance };

  /* ---------- редактор Markdown ---------- */
  var editor = document.querySelector("[data-editor]");
  if (editor) {
    var ta = editor.querySelector("textarea");
    var preview = editor.querySelector(".editor-preview");
    var token = document.querySelector('meta[name="csrf-token"]').content;
    var timer = null, seq = 0;

    function renderPreview() {
      var my = ++seq;
      fetch("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        credentials: "same-origin",
        body: JSON.stringify({ text: ta.value })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (my !== seq) return;
        preview.innerHTML = d.html || '<p class="muted">Здесь появится предпросмотр урока.</p>';
        preview.querySelectorAll("pre").forEach(function (p) { enhance(p); });
      }).catch(function () { /* офлайн — предпросмотр не обновляется */ });
    }
    function schedule() { clearTimeout(timer); timer = setTimeout(renderPreview, 350); }
    ta.addEventListener("input", schedule);
    renderPreview();

    function wrapSel(before, after, placeholder) {
      var s = ta.selectionStart, e = ta.selectionEnd, v = ta.value;
      var sel = v.slice(s, e) || placeholder;
      ta.value = v.slice(0, s) + before + sel + after + v.slice(e);
      ta.focus(); ta.selectionStart = s + before.length; ta.selectionEnd = s + before.length + sel.length;
      schedule();
    }
    function linePrefix(prefix, placeholder) {
      var s = ta.selectionStart, v = ta.value;
      var start = v.lastIndexOf("\n", s - 1) + 1;
      var endIdx = v.indexOf("\n", ta.selectionEnd); if (endIdx < 0) endIdx = v.length;
      var block = v.slice(start, endIdx) || placeholder;
      var out = block.split("\n").map(function (l, i) { return (prefix === "1. " ? (i + 1) + ". " : prefix) + l; }).join("\n");
      ta.value = v.slice(0, start) + out + v.slice(endIdx);
      ta.focus(); ta.selectionStart = start; ta.selectionEnd = start + out.length; schedule();
    }
    var actions = {
      bold: function () { wrapSel("**", "**", "жирный текст"); },
      italic: function () { wrapSel("*", "*", "курсив"); },
      h2: function () { linePrefix("## ", "Заголовок раздела"); },
      h3: function () { linePrefix("### ", "Подзаголовок"); },
      ul: function () { linePrefix("- ", "пункт списка"); },
      ol: function () { linePrefix("1. ", "шаг"); },
      quote: function () { linePrefix("> ", "Важная заметка"); },
      icode: function () { wrapSel("`", "`", "код"); },
      code: function () {
        var lang = editor.querySelector("[data-code-lang]").value;
        wrapSel("\n```" + lang + "\n", "\n```\n", "# ваш код здесь");
      },
      link: function () { wrapSel("[", "](https://)", "текст ссылки"); },
      table: function () {
        var t = "\n| Колонка 1 | Колонка 2 |\n|-----------|-----------|\n| значение  | значение  |\n";
        var s = ta.selectionStart; ta.value = ta.value.slice(0, s) + t + ta.value.slice(s); ta.focus(); schedule();
      }
    };
    editor.querySelectorAll("[data-act]").forEach(function (b) {
      b.addEventListener("click", function () { actions[b.getAttribute("data-act")](); });
    });
    editor.querySelectorAll("[data-mode]").forEach(function (b) {
      b.addEventListener("click", function () {
        editor.classList.remove("mode-write", "mode-preview");
        var m = b.getAttribute("data-mode"); if (m !== "split") editor.classList.add("mode-" + m);
        if (m !== "write") renderPreview();
      });
    });
    ta.addEventListener("keydown", function (e) {
      if (e.key === "Tab") { e.preventDefault(); wrapSel("    ", "", ""); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") { e.preventDefault(); actions.bold(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "i") { e.preventDefault(); actions.italic(); }
    });
  }

  /* Tab в полях с кодом */
  document.querySelectorAll("textarea.code").forEach(function (t) {
    t.addEventListener("keydown", function (e) {
      if (e.key === "Tab") {
        e.preventDefault();
        var s = t.selectionStart; t.value = t.value.slice(0, s) + "    " + t.value.slice(t.selectionEnd);
        t.selectionStart = t.selectionEnd = s + 4;
      }
    });
  });
})();
