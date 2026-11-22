(function () {
  "use strict";

  var reduced = !!(
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  var NS = "http://www.w3.org/2000/svg";

  // ---------- icon sprite (24x24, stroke icons) ----------
  var ICONS = {
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/>',
    upload:
      '<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M5 16v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3"/>',
    image:
      '<rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="9" cy="10" r="1.6"/><path d="M3.5 17l5-5 4 4 3-3 5 5"/>',
    globe:
      '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.7 3.8 5.7 3.8 9S14.5 18.3 12 21c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z"/>',
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2.5"/>',
    speaker:
      '<path d="M4 10v4h4l5 4V6L8 10z"/><path d="M16 9a4 4 0 0 1 0 6"/><path d="M18.5 6.5a8 8 0 0 1 0 11"/>',
    sliders:
      '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
    translate:
      '<path d="M4 6h9M8.5 4v2M6 6c.5 3 2.5 5.5 5.5 7"/><path d="M12 6c-.7 3-3 6-7 8"/><path d="M12 20l4-9 4 9M13.4 17h5.2"/>',
    bolt: '<path d="M13 3L5 13.5h6L10 21l9-11.5h-6z"/>',
    package:
      '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5"/><path d="M12 12v9"/>',
    download:
      '<path d="M12 4v11"/><path d="M7 11l5 5 5-5"/><path d="M5 20h14"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    trash:
      '<path d="M5 7h14"/><path d="M10 7V5h4v2"/><path d="M7 7l1 12h8l1-12"/>',
    check: '<path pathLength="1" d="M5 12.5l4.5 4.5L19 7.5"/>',
    alert:
      '<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5"/><path d="M12 17.5v.5"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8v.5"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    scan: '<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M8 9h8M8 12h8M8 15h5"/>',
    filter: '<path d="M4 5h16l-6 7.5V19l-4 2v-8.5z"/>',
    cloud:
      '<path d="M6.5 18.5A4.5 4.5 0 0 1 6 9.6 6 6 0 0 1 17.6 8.4a4.7 4.7 0 0 1-.1 10.1z"/>',
    chip: '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/>',
    wave: '<path d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4"/>',
    play: '<path d="M8 5l11 7-11 7z"/>',
    sparkle:
      '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 17l.7 1.8 1.8.7-1.8.7L19 22l-.7-1.8-1.8-.7 1.8-.7z"/>',
    folder:
      '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    clock:
      '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2"/><path d="M9 3h6"/>',
    skip: '<path d="M5 5l9 7-9 7z"/><path d="M18 5v14"/>',
    text: '<path d="M5 6h14M12 6v13M9 19h6"/>',
    star: '<path d="M12 3.5l2.6 5.5 6 .8-4.4 4.2 1.1 6-5.3-2.9-5.3 2.9 1.1-6L3.4 9.8l6-.8z"/>',
    scale:
      '<path d="M12 4v16M7 20h10"/><path d="M5 7h14"/><path d="M5 7l-2.5 6a3 3 0 0 0 5 0zM19 7l-2.5 6a3 3 0 0 0 5 0z"/>',
    layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/>',
    pages:
      '<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M9.5 8h5M9.5 12h5M9.5 16h3"/>',
    moon: '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4"/>',
  };

  function buildSprite() {
    if (document.getElementById("vm-sprite")) return;
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("id", "vm-sprite");
    svg.setAttribute("aria-hidden", "true");
    svg.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
    var html = "";
    Object.keys(ICONS).forEach(function (k) {
      html +=
        '<symbol id="i-' +
        k +
        '" viewBox="0 0 24 24">' +
        ICONS[k] +
        "</symbol>";
    });
    svg.innerHTML = html;
    document.body.insertBefore(svg, document.body.firstChild);
  }

  function icon(name, cls) {
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "ic" + (cls ? " " + cls : ""));
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS(NS, "use");
    use.setAttribute("href", "#i-" + name);
    svg.appendChild(use);
    return svg;
  }

  function setIcon(svg, name) {
    var use = svg.querySelector("use");
    if (use) use.setAttribute("href", "#i-" + name);
  }

  // <i data-ic="file" class="extra"></i>  ->  <svg class="ic extra">
  function hydrate(root) {
    Array.prototype.slice
      .call((root || document).querySelectorAll("i[data-ic]"))
      .forEach(function (n) {
        var svg = icon(n.getAttribute("data-ic"), n.className);
        if (n.id) svg.id = n.id;
        n.parentNode.replaceChild(svg, n);
      });
  }

  // ---------- small DOM helpers ----------
  function el(tag, props, children) {
    var node = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        if (k === "class") node.className = props[k];
        else if (k === "text") node.textContent = props[k];
        else node.setAttribute(k, props[k]);
      });
    }
    (children || []).forEach(function (c) {
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function replay(node, cls) {
    // restart a CSS animation
    node.classList.remove(cls);
    void node.offsetWidth;
    node.classList.add(cls);
  }

  // ---------- in-place notices (no floating pop-ups) ----------
  var TOAST_ICON = {
    success: "check",
    error: "alert",
    info: "info",
    warn: "alert",
  };
  var noticeSeq = 0,
    noticeTimer = null;
  function toast(message, type, ms) {
    type = type || "info";
    var box = document.getElementById("notice");
    if (!box) return;
    var my = ++noticeSeq;
    function hide() {
      if (my !== noticeSeq) return;
      box.classList.add("notice-out");
      setTimeout(function () {
        if (my === noticeSeq) {
          box.hidden = true;
          box.classList.remove("notice-out");
        }
      }, 280);
    }
    box.className = "notice " + type;
    box.textContent = "";
    box.appendChild(
      el("span", { class: "notice-ic" }, [icon(TOAST_ICON[type] || "info")]),
    );
    box.appendChild(el("span", { class: "notice-msg", text: message }));
    var x = el(
      "button",
      { class: "notice-x", type: "button", "aria-label": "Dismiss" },
      [icon("x")],
    );
    x.addEventListener("click", hide);
    box.appendChild(x);
    box.hidden = false;
    replay(box, "notice-in");
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(hide, ms || 5200);
  }

  // ---------- pointer effects ----------
  var SPOT = ".card, .feature-card, .metric, .eval-card, .t-card";
  document.addEventListener(
    "pointermove",
    function (e) {
      var t = e.target.closest ? e.target.closest(SPOT) : null;
      if (t) {
        var r = t.getBoundingClientRect();
        t.style.setProperty("--mx", e.clientX - r.left + "px");
        t.style.setProperty("--my", e.clientY - r.top + "px");
      }
      if (reduced) return;
      var tl = e.target.closest ? e.target.closest(".tilt") : null;
      if (tl) {
        var b = tl.getBoundingClientRect();
        var px = (e.clientX - b.left) / b.width - 0.5;
        var py = (e.clientY - b.top) / b.height - 0.5;
        tl.style.transform =
          "perspective(800px) rotateX(" +
          (-py * 9).toFixed(2) +
          "deg) rotateY(" +
          (px * 11).toFixed(2) +
          "deg) translateY(-5px)";
      }
    },
    { passive: true },
  );
  document.addEventListener("pointerout", function (e) {
    var tl = e.target.closest ? e.target.closest(".tilt") : null;
    if (tl && (!e.relatedTarget || !tl.contains(e.relatedTarget)))
      tl.style.transform = "";
  });

  document.addEventListener("pointerdown", function (e) {
    // ripple on buttons
    if (reduced) return;
    var b = e.target.closest ? e.target.closest(".btn") : null;
    if (!b || b.disabled) return;
    var r = b.getBoundingClientRect();
    var size = Math.max(r.width, r.height) * 1.6;
    var s = el("span", { class: "ripple" });
    s.style.width = s.style.height = size + "px";
    s.style.left = e.clientX - r.left - size / 2 + "px";
    s.style.top = e.clientY - r.top - size / 2 + "px";
    b.appendChild(s);
    setTimeout(function () {
      if (s.parentNode) s.parentNode.removeChild(s);
    }, 700);
  });

  // ---------- count-up ----------
  function countUp(node, to, opts) {
    opts = opts || {};
    var d = opts.decimals || 0,
      suf = opts.suffix || "";
    if (reduced || !isFinite(to)) {
      node.textContent = Number(to).toFixed(d) + suf;
      return;
    }
    var t0 = performance.now(),
      dur = opts.duration || 1000;
    (function tick() {
      var p = Math.min(1, (performance.now() - t0) / dur);
      var e = 1 - Math.pow(1 - p, 3);
      node.textContent = (to * e).toFixed(d) + suf;
      if (p < 1) requestAnimationFrame(tick);
    })();
  }

  // ---------- sliding highlight (tabs) ----------
  function slidePill(container, pill, active) {
    if (!container || !pill || !active || !active.offsetWidth) return;
    pill.style.width = active.offsetWidth + "px";
    pill.style.transform = "translateX(" + active.offsetLeft + "px)";
  }

  buildSprite();
  window.UI = {
    reduced: reduced,
    icon: icon,
    setIcon: setIcon,
    hydrate: hydrate,
    el: el,
    replay: replay,
    toast: toast,
    countUp: countUp,
    slidePill: slidePill,
  };
  hydrate(document);
})();
