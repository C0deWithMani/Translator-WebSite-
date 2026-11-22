(function () {
  "use strict";

  var UI = window.UI;
  var el = UI.el;
  var $ = function (id) {
    return document.getElementById(id);
  };
  function titleCase(s) {
    return s.replace(/\b\w/g, function (c) {
      return c.toUpperCase();
    });
  }
  function fmtSize(b) {
    return b < 1048576
      ? Math.max(1, Math.round(b / 1024)) + " KB"
      : (b / 1048576).toFixed(2) + " MB";
  }

  function showTopError(msg) {
    var box = $("top-error");
    box.textContent = "";
    box.appendChild(UI.icon("alert"));
    box.appendChild(el("span", { text: msg }));
    box.hidden = false;
    UI.replay(box, "shake");
  }
  function clearTopError() {
    $("top-error").hidden = true;
  }

  // ---------- state ----------
  var mode = "pdf";
  var runMode = null;
  var pdf = { file: null, pages: 0, token: 0 };
  var img = { file: null, url: null };
  var pollTimer = null,
    notesShown = 0,
    stepNodes = [],
    launchState = "idle";
  var cfg = { locales: {}, ocr_languages: ["eng"] };
  var STEP_ICONS = ["scan", "filter", "translate", "speaker", "package"];

  // ---------- init ----------
  async function init() {
    try {
      var res = await fetch("/api/config");
      cfg = await res.json();
      cfg.languages.forEach(function (name) {
        $("language").appendChild(
          el("option", { value: name, text: titleCase(name) }),
        );
      });
      var ocr = $("ocr-lang");
      ocr.textContent = "";
      cfg.ocr_languages.forEach(function (c) {
        ocr.appendChild(el("option", { value: c, text: c }));
      });
      var src = $("live-src");
      Object.keys(cfg.locales)
        .sort(function (a, b) {
          return a === "english"
            ? -1
            : b === "english"
              ? 1
              : a.localeCompare(b);
        })
        .forEach(function (n) {
          src.appendChild(
            el("option", {
              value: cfg.locales[n],
              text: titleCase(n) + " (" + cfg.locales[n] + ")",
            }),
          );
        });
      if (!cfg.tesseract_ok) $("tess-warning").hidden = false;
    } catch (e) {
      showTopError("Could not reach the server: " + e.message);
    }
    setMode("pdf");
    setLaunch("idle");
    document.querySelectorAll(".range").forEach(paintRange);
    window.addEventListener("resize", function () {
      UI.slidePill(
        $("mode-tabs"),
        $("mode-pill"),
        document.querySelector(".mode-tab.active"),
      );
      updateOutTabs();
      if (redrawOverlay) redrawOverlay();
    });
    if (document.fonts && document.fonts.ready)
      document.fonts.ready.then(function () {
        UI.slidePill(
          $("mode-tabs"),
          $("mode-pill"),
          document.querySelector(".mode-tab.active"),
        );
      });
  }

  // ---------- modes ----------
  var IDLE = {
    pdf: [
      "Turn any PDF into speech",
      "Upload a PDF → choose pages → pick a language → launch",
    ],
    image: [
      "Translate the text inside any picture",
      "Upload an image → choose its text language → pick a target language → translate",
    ],
    live: [
      "Speak or type — translated live",
      "Choose a target language, then type or press the mic",
    ],
  };

  function setMode(m) {
    if (mode === "live" && m !== "live") {
      stopMic();
      stopAudio();
      live.queue.length = 0;
    }
    var changed = m !== mode;
    mode = m;
    clearTopError();
    document.querySelectorAll(".mode-tab").forEach(function (t) {
      t.classList.toggle("active", t.dataset.mode === m);
    });
    UI.slidePill(
      $("mode-tabs"),
      $("mode-pill"),
      document.querySelector(".mode-tab.active"),
    );
    document.querySelectorAll("[data-modes]").forEach(function (n) {
      var show = n.dataset.modes.split(" ").indexOf(m) !== -1;
      if (show && n.hidden) {
        n.hidden = false;
        UI.replay(n, "enter");
      } else if (!show) n.hidden = true;
    });
    $("panel-doc").hidden = m === "live";
    $("panel-live").hidden = m !== "live";
    var shown = m === "live" ? $("panel-live") : $("panel-doc");
    if (changed) UI.replay(shown, "enter");
    $("idle-title").textContent = IDLE[m][0];
    $("idle-sub").textContent = IDLE[m][1];
    if (m !== "live") {
      var showRun = runMode === m;
      $("run").hidden = !showRun;
      $("idle").hidden = showRun;
      if (launchState === "idle") setLaunch("idle");
      updateOutTabs();
    } else {
      refreshLiveHint();
      updateLiveLabel();
    }
    updateFlow();
  }
  document.querySelectorAll(".mode-tab").forEach(function (t) {
    t.addEventListener("click", function () {
      setMode(t.dataset.mode);
    });
  });

  // ---------- flow: Upload -> Configure -> Launch ----------
  function updateFlow() {
    var hasFile = mode === "image" ? !!img.file : !!pdf.file;
    var step = launchState === "idle" ? (hasFile ? 2 : 1) : 3;
    var all = launchState === "done";
    document.querySelectorAll("#flow .flow-node").forEach(function (n, i) {
      n.classList.toggle("done", all || i + 1 < step);
      n.classList.toggle("active", !all && i + 1 === step);
    });
    $("flow-fill").style.width = (all ? 100 : (step - 1) * 50) + "%";
  }

  // ---------- uploads ----------
  function wireDrop(zoneId, inputId, handler) {
    var zone = $(zoneId),
      input = $(inputId);
    input.addEventListener("change", function () {
      if (input.files[0]) handler(input.files[0]);
    });
    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) {
        e.preventDefault();
        zone.classList.add("drag");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) {
        e.preventDefault();
        zone.classList.remove("drag");
      });
    });
    zone.addEventListener("drop", function (e) {
      if (e.dataTransfer.files && e.dataTransfer.files.length)
        handler(e.dataTransfer.files[0]);
    });
  }

  function openChip(kind, file) {
    $(kind + "-name").textContent = file.name;
    $(kind + "-meta").textContent = fmtSize(file.size);
    $(kind + "-collapse").classList.add("closed");
    var chip = $(kind + "-chip");
    chip.hidden = false;
    chip.style.animation = "none";
    void chip.offsetWidth;
    chip.style.animation = ""; // replay the pop-in
    updateFlow();
  }

  function closeChip(kind) {
    $(kind + "-chip").hidden = true;
    $(kind + "-collapse").classList.remove("closed");
    $(kind === "pdf" ? "file" : "imgfile").value = "";
    $(kind + "-preview").hidden = true;
    updateFlow();
  }

  async function setPdfFile(file) {
    clearTopError();
    if (!/\.pdf$/i.test(file.name)) {
      UI.toast("Please choose a PDF file.", "error");
      return;
    }
    pdf.file = file;
    pdf.pages = 0;
    var token = ++pdf.token;
    openChip("pdf", file);
    $("pdf-chip").classList.add("analyzing");
    $("pdf-meta").textContent = fmtSize(file.size) + " · analysing…";
    try {
      var fd = new FormData();
      fd.append("file", file);
      var res = await fetch("/api/pdfinfo", { method: "POST", body: fd });
      var d = null;
      try {
        d = await res.json();
      } catch (e) {
        d = null;
      }
      if (token !== pdf.token) return;
      if (!d) {
        // server without /api/pdfinfo: keep the file, just no preview
        $("pdf-meta").textContent = fmtSize(file.size);
        UI.toast("PDF added.", "success", 2400);
        return;
      }
      if (!d.ok) throw new Error(d.error || "Could not read this PDF");
      pdf.pages = d.pages;
      $("pdf-meta").textContent =
        fmtSize(file.size) +
        " · " +
        d.pages +
        (d.pages === 1 ? " page" : " pages");
      $("pdf-pages").textContent =
        d.pages + (d.pages === 1 ? " page" : " pages");
      if (d.thumb) {
        $("pdf-thumb").src = d.thumb;
        $("pdf-preview").hidden = false;
      }
      $("pages-hint").textContent =
        "This PDF has " +
        d.pages +
        (d.pages === 1 ? " page" : " pages") +
        " · blank = all";
      $("pages").placeholder = "e.g. 3  or  1-" + d.pages;
      validatePages();
      UI.toast(
        "PDF ready — " +
          d.pages +
          (d.pages === 1 ? " page" : " pages") +
          " found.",
        "success",
      );
    } catch (e) {
      if (token !== pdf.token) return;
      removePdf();
      UI.toast(e.message, "error");
    } finally {
      if (token === pdf.token) $("pdf-chip").classList.remove("analyzing");
    }
  }

  function removePdf() {
    pdf.file = null;
    pdf.pages = 0;
    pdf.token++;
    closeChip("pdf");
    $("pages-hint").textContent = "Leave blank to convert all pages";
    $("pages").placeholder = "e.g. 3  or  1-5  or blank = ALL";
    $("pages").classList.remove("invalid");
  }

  function setImgFile(file) {
    clearTopError();
    if (
      !/^image\//.test(file.type) &&
      !/\.(png|jpe?g|bmp|tiff?|webp)$/i.test(file.name)
    ) {
      UI.toast(
        "Please choose an image (PNG, JPG, WEBP, BMP or TIFF).",
        "error",
      );
      return;
    }
    img.file = file;
    if (img.url) URL.revokeObjectURL(img.url);
    img.url = URL.createObjectURL(file);
    openChip("img", file);
    var t = $("img-thumb");
    t.onload = function () {
      $("img-meta").textContent =
        fmtSize(file.size) + " · " + t.naturalWidth + "×" + t.naturalHeight;
    };
    t.src = img.url;
    $("img-preview").hidden = false;
    UI.toast("Image loaded.", "success", 2400);
  }

  function removeImg() {
    img.file = null;
    if (img.url) {
      URL.revokeObjectURL(img.url);
      img.url = null;
    }
    closeChip("img");
  }

  wireDrop("pdf-drop", "file", setPdfFile);
  wireDrop("img-drop", "imgfile", setImgFile);
  $("pdf-remove").addEventListener("click", removePdf);
  $("img-remove").addEventListener("click", removeImg);

  document.addEventListener("paste", function (e) {
    // Ctrl+V a screenshot
    if (mode !== "image" || !e.clipboardData) return;
    var files = e.clipboardData.files;
    if (files && files.length && /^image\//.test(files[0].type)) {
      var f = files[0];
      setImgFile(
        f.name && f.name !== "image.png"
          ? f
          : new File([f], "pasted-image.png", { type: f.type }),
      );
    }
  });

  // page range check with live feedback
  function validatePages() {
    var box = $("pages"),
      v = box.value.trim(),
      ok = true;
    if (v) {
      var m = v.match(/^(\d+)(?:\s*-\s*(\d+))?$/);
      if (!m) ok = false;
      else {
        var a = +m[1],
          b = m[2] ? +m[2] : a;
        ok = a >= 1 && a <= b && (!pdf.pages || b <= pdf.pages);
      }
    }
    box.classList.toggle("invalid", !ok);
    return ok;
  }
  $("pages").addEventListener("input", validatePages);

  // ---------- voice card ----------
  function currentEngine() {
    return document.querySelector('input[name="engine"]:checked').value;
  }
  document.querySelectorAll('input[name="engine"]').forEach(function (r) {
    r.addEventListener("change", function () {
      document.querySelectorAll("#engine-tiles .tile").forEach(function (t) {
        t.classList.toggle("on", t.querySelector("input").checked);
      });
      $("voice-collapse").classList.toggle(
        "closed",
        currentEngine() === "edge",
      );
    });
  });
  document.querySelectorAll('input[name="voice"]').forEach(function (r) {
    r.addEventListener("change", function () {
      document.querySelectorAll("#voice-seg label").forEach(function (l) {
        l.classList.toggle("on", l.querySelector("input").checked);
      });
    });
  });
  function paintRange(r) {
    var pct = ((r.value - r.min) / (r.max - r.min)) * 100;
    r.style.setProperty("--pct", pct + "%");
  }
  document.querySelectorAll(".range").forEach(function (r) {
    r.addEventListener("input", function () {
      paintRange(r);
    });
  });
  $("speed").addEventListener("input", function (e) {
    $("speed-out").textContent = e.target.value;
  });
  $("volume").addEventListener("input", function (e) {
    $("volume-out").textContent = Number(e.target.value).toFixed(1);
  });

  // ---------- launch button states ----------
  function setLaunch(state, pct) {
    launchState = state;
    var b = $("launch"),
      p = pct || 0;
    b.dataset.state = state;
    b.disabled = state === "uploading" || state === "working";
    var text = {
      idle: mode === "image" ? "Translate image" : "Launch conversion",
      uploading: "Uploading… " + Math.round(p * 100) + "%",
      working: "Processing…",
      done: "Done",
    }[state];
    $("launch-text").textContent = text;
    UI.setIcon(
      $("launch-ic"),
      { idle: "bolt", uploading: "upload", working: "sparkle", done: "check" }[
        state
      ],
    );
    $("launch-fill").style.width =
      state === "uploading"
        ? p * 100 + "%"
        : state === "working"
          ? "100%"
          : "0%";
    updateFlow();
  }

  function sendForm(url, fd, onProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", url);
      xhr.upload.onprogress = function (e) {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
      xhr.onload = function () {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch (err) {
          reject(new Error("The server sent an unreadable reply."));
        }
      };
      xhr.onerror = function () {
        reject(new Error("Network error while uploading."));
      };
      xhr.send(fd);
    });
  }

  // ---------- run view: timeline ----------
  function resetRunUI() {
    clearTopError();
    $("idle").hidden = true;
    $("run").hidden = false;
    UI.replay($("run"), "enter");
    $("output").hidden = true;
    $("complete").hidden = true;
    $("tabbtn-image").hidden = true;
    $("mission").textContent = "";
    $("notes").textContent = "";
    $("steps").textContent = "";
    $("overall-fill").style.width = "0%";
    $("overall-pct").textContent = "0%";
    $("overall-label").textContent = "Starting…";
    notesShown = 0;
    var player = $("player");
    player.pause();
    player.removeAttribute("src");
    player.load();
    player.hidden = false;
    $("audio-card").classList.remove("playing");

    stepNodes = [];
    for (var i = 0; i < 5; i++) {
      var badge = el("div", { class: "t-badge" }, [UI.icon(STEP_ICONS[i])]);
      var title = el("div", { class: "t-title" });
      var msg = el("div", { class: "t-msg" });
      var bar = el("span");
      var track = el("div", { class: "t-bar" }, [bar]);
      var card = el("div", { class: "t-card" }, [title, msg, track]);
      var item = el("div", { class: "t-item pending" }, [badge, card]);
      item.hidden = true;
      $("steps").appendChild(item);
      stepNodes.push({
        item: item,
        badge: badge,
        title: title,
        msg: msg,
        track: track,
        bar: bar,
        state: "pending",
      });
    }
  }

  function renderMission(info) {
    var m = $("mission");
    m.textContent = "";
    function cell(key, valueNode) {
      return el("div", null, [
        el("div", { class: "m-key", text: key }),
        valueNode,
      ]);
    }
    var lang =
      info.language !== "None" ? info.language.toUpperCase() : "ENGLISH (NONE)";
    var engine = info.engine === "edge" ? "EDGE-TTS NEURAL" : "PYTTSX3 OFFLINE";
    m.appendChild(
      cell("DOCUMENT", el("div", { class: "m-val", text: info.filename })),
    );
    if (info.kind === "image") {
      m.appendChild(
        cell(
          "IMAGE TEXT",
          el("div", { class: "m-val v-cyan", text: info.ocr_lang }),
        ),
      );
    } else {
      m.appendChild(
        cell(
          "PAGES",
          el("div", { class: "m-val v-cyan" }, [
            info.start_page + " → " + info.end_page + " ",
            el("span", { class: "v-dim", text: "/ " + info.total_pages }),
          ]),
        ),
      );
    }
    m.appendChild(
      cell("TARGET LANG", el("div", { class: "m-val v-purple", text: lang })),
    );
    m.appendChild(
      cell("ENGINE", el("div", { class: "m-val v-green", text: engine })),
    );
  }

  function badgeIcon(n, state, i) {
    var name = {
      running: STEP_ICONS[i],
      pending: STEP_ICONS[i],
      done: "check",
      error: "alert",
      skipped: "skip",
    }[state];
    n.badge.textContent = "";
    n.badge.appendChild(UI.icon(name, state === "done" ? "ic-draw" : ""));
  }

  function renderSteps(steps) {
    var finished = 0,
      running = null;
    steps.forEach(function (s, i) {
      var n = stepNodes[i];
      if (!n) return;
      n.item.hidden = s.state === "pending";
      n.title.textContent = s.title;
      n.msg.textContent = s.message;
      if (n.state !== s.state) {
        n.state = s.state;
        n.item.className = "t-item " + s.state;
        badgeIcon(n, s.state, i);
      }
      var showBar =
        s.state === "running" &&
        s.progress !== null &&
        s.progress !== undefined;
      n.track.hidden = !showBar;
      if (showBar) n.bar.style.width = s.progress + "%";
      if (s.state === "done" || s.state === "skipped" || s.state === "error")
        finished++;
      if (s.state === "running")
        running = { i: i, p: showBar ? s.progress / 100 : 0.4, title: s.title };
    });
    var pct = Math.min(
      100,
      Math.round(((finished + (running ? running.p : 0)) / steps.length) * 100),
    );
    $("overall-fill").style.width = pct + "%";
    $("overall-pct").textContent = pct + "%";
    $("overall-label").textContent = running
      ? "Step " +
        (running.i + 1) +
        " of " +
        steps.length +
        " · " +
        titleCase(running.title.toLowerCase())
      : finished === steps.length
        ? "All steps finished"
        : "Working…";
  }

  function renderNotes(notes) {
    for (var i = notesShown; i < notes.length; i++) {
      $("notes").appendChild(
        el("div", { class: "note " + notes[i].level }, [
          UI.icon(notes[i].level === "warning" ? "alert" : "info"),
          el("span", { text: notes[i].text }),
        ]),
      );
    }
    notesShown = notes.length;
  }

  // ---------- image overlay ----------
  var redrawOverlay = null,
    overlayLayer = null;

  function renderImageTab(info, r) {
    var stage = $("img-stage");
    stage.textContent = "";
    var pic = el("img", { src: r.image_url, alt: "Uploaded image" });
    var layer = el("div", { class: "ov-layer" });
    stage.appendChild(pic);
    stage.appendChild(layer);
    overlayLayer = layer;
    layer.hidden = !$("ov-toggle").checked;
    var W = r.image_size.w,
      H = r.image_size.h;
    redrawOverlay = function () {
      layer.textContent = "";
      var ratio = pic.clientWidth / W;
      if (!ratio) return;
      r.lines.forEach(function (l, idx) {
        var text = l.translated;
        if (!text) return;
        var box = el("div", {
          class: "ov-box",
          text: text,
          title: l.text + "  →  " + text,
        });
        box.style.left = (l.x / W) * 100 + "%";
        box.style.top = (l.y / H) * 100 + "%";
        box.style.width = (l.w / W) * 100 + "%";
        box.style.height = (l.h / H) * 100 + "%";
        box.style.animationDelay = idx * 60 + "ms";
        var wide = /[^\u0000-\u024F]/.test(text);
        var byWidth =
          (l.w * ratio) / Math.max(1, text.length * (wide ? 0.95 : 0.55));
        box.style.fontSize =
          Math.max(8, Math.min(l.h * ratio * 0.85, byWidth)) + "px";
        layer.appendChild(box);
      });
    };
    pic.addEventListener("load", redrawOverlay);
    $("img-caption").textContent =
      info.language === "None"
        ? "Choose a target language above to see the translation on the image."
        : !r.lines.length
          ? "No text boxes could be placed on the picture. Read the result in the Translation tab."
          : r.lines.length +
            " text box(es) translated. Hover a box to see the original text.";
  }
  $("ov-toggle").addEventListener("change", function (e) {
    if (overlayLayer) overlayLayer.hidden = !e.target.checked;
  });

  // ---------- result ----------
  function renderResult(info, r) {
    var isImage = r.kind === "image";
    var c = $("complete");
    c.textContent = "";
    var big = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    big.setAttribute("class", "big-check");
    big.setAttribute("viewBox", "0 0 52 52");
    big.innerHTML =
      '<circle cx="26" cy="26" r="24"/><path d="M14 27l8 8 16-17"/>';
    c.appendChild(big);
    c.appendChild(
      el("div", null, [
        el("div", { class: "c-title", text: "MISSION COMPLETE" }),
        el("div", { class: "c-sub" }, [
          "Processed in ",
          el("strong", { text: r.elapsed + "s" }),
          " · " +
            (isImage
              ? "1 image"
              : r.page_count + (r.page_count === 1 ? " page" : " pages")) +
            " · " +
            r.final_words.toLocaleString() +
            " words · " +
            r.language_label,
        ]),
      ]),
    );
    c.hidden = false;

    $("raw-text").value = r.raw_text;
    $("clean-text").value = r.clean_text;
    if (r.translated_text) {
      $("trans-label").textContent = titleCase(info.language) + " translation";
      $("trans-text").value = r.translated_text;
      $("trans-box").hidden = false;
      $("trans-none").hidden = true;
    } else {
      $("trans-box").hidden = true;
      $("trans-none").hidden = false;
    }

    if (r.audio_url) {
      $("player").hidden = false;
      $("player").src = r.audio_url;
      $("voice-caption").textContent = "Voice: " + r.voice_label;
    } else {
      $("player").hidden = true;
      $("voice-caption").textContent =
        "Audio could not be created. The exact error is in the yellow warning cards above. Text, translation and the ZIP are still available.";
    }
    var dl = $("download");
    dl.href = r.zip_url;
    dl.setAttribute("download", r.zip_name);

    $("m-pages-label").textContent = isImage ? "Images" : "Pages";
    $("metrics-caption").textContent =
      "WER & CER compare original vs translated text. 0 = no translation selected (identical)." +
      (r.metrics.sampled
        ? " (Long text: measured on the first 1500 words / 2000 characters.)"
        : "");

    $("output").hidden = false;
    UI.replay($("output"), "enter");
    $("tabbtn-image").hidden = !isImage;
    if (isImage) {
      renderImageTab(info, r);
      selectTab("image");
    } else selectTab("text");

    UI.countUp($("m-wer"), r.metrics.wer, { decimals: 4 });
    UI.countUp($("m-cer"), r.metrics.cer, { decimals: 4 });
    UI.countUp($("m-acc"), r.metrics.word_accuracy, {
      decimals: 2,
      suffix: "%",
    });
    UI.countUp($("m-pages"), isImage ? 1 : r.page_count, { decimals: 0 });
    UI.countUp($("m-time"), r.elapsed, { decimals: 1, suffix: "s" });

    UI.toast(
      r.audio_url
        ? "All done — your audio is ready."
        : "Finished, but the audio could not be created.",
      r.audio_url ? "success" : "warn",
    );
    c.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // ---------- output tabs ----------
  function updateOutTabs() {
    UI.slidePill(
      $("out-tabs"),
      $("out-ind"),
      $("out-tabs").querySelector(".tab.active"),
    );
  }
  function selectTab(name) {
    document.querySelectorAll("#out-tabs .tab").forEach(function (t) {
      t.classList.toggle("active", t.dataset.tab === name);
    });
    ["image", "text", "trans", "audio"].forEach(function (n) {
      $("tab-" + n).hidden = n !== name;
    });
    updateOutTabs();
    if (name === "image" && redrawOverlay) redrawOverlay();
  }
  document.querySelectorAll("#out-tabs .tab").forEach(function (t) {
    t.addEventListener("click", function () {
      selectTab(t.dataset.tab);
    });
  });
  $("player").addEventListener("play", function () {
    $("audio-card").classList.add("playing");
  });
  ["pause", "ended"].forEach(function (ev) {
    $("player").addEventListener(ev, function () {
      $("audio-card").classList.remove("playing");
    });
  });

  // ---------- launch + polling ----------
  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function launch() {
    var isImg = mode === "image";
    var file = isImg ? img.file : pdf.file;
    if (!file) {
      showTopError(
        isImg
          ? "No image detected. Add a picture in the upload box first."
          : "No document detected. Add a PDF in the upload box first.",
      );
      return;
    }
    if (!isImg && !validatePages()) {
      UI.toast(
        "Check the page range: use a number like 3 or a range like 1-5" +
          (pdf.pages ? " (this PDF has " + pdf.pages + " pages)." : "."),
        "error",
      );
      return;
    }
    var fd = new FormData();
    fd.append("file", file);
    fd.append("engine", currentEngine());
    fd.append(
      "voice",
      document.querySelector('input[name="voice"]:checked').value,
    );
    fd.append("speed", $("speed").value);
    fd.append("volume", $("volume").value);
    fd.append("language", $("language").value);
    if (isImg) fd.append("ocr_lang", $("ocr-lang").value);
    else fd.append("pages", $("pages").value);

    clearTopError();
    setLaunch("uploading", 0);
    var data;
    try {
      data = await sendForm(
        isImg ? "/api/image" : "/api/convert",
        fd,
        function (p) {
          setLaunch("uploading", p);
        },
      );
    } catch (e) {
      setLaunch("idle");
      showTopError(e.message);
      return;
    }
    if (!data.ok) {
      setLaunch("idle");
      showTopError(data.error || "Something went wrong.");
      return;
    }

    runMode = mode;
    setLaunch("working");
    resetRunUI();
    var failures = 0,
      jobId = data.job_id;

    async function poll() {
      try {
        var res = await fetch("/api/status/" + jobId);
        var s = await res.json();
        failures = 0;
        if (!s.ok) {
          stopPolling();
          setLaunch("idle");
          showTopError(s.error || "Job lost.");
          return;
        }
        if ($("mission").childNodes.length === 0) renderMission(s.info);
        renderSteps(s.steps);
        renderNotes(s.notes);
        if (s.state === "done") {
          stopPolling();
          setLaunch("done");
          renderResult(s.info, s.result);
          setTimeout(function () {
            if (launchState === "done") setLaunch("idle");
          }, 2600);
        } else if (s.state === "error") {
          stopPolling();
          setLaunch("idle");
          showTopError(s.error);
        }
      } catch (e) {
        failures += 1;
        if (failures >= 5) {
          stopPolling();
          setLaunch("idle");
          showTopError("Lost connection to the server: " + e.message);
        }
      }
    }
    poll();
    pollTimer = setInterval(poll, 800);
  }
  $("launch").addEventListener("click", launch);

  // ---------- MOS (stars) / CMOS ----------
  var MOS = {
    1: "1 — Bad",
    2: "2 — Poor",
    3: "3 — Fair",
    4: "4 — Good",
    5: "5 — Excellent",
  };
  var CMOS = {
    "-3": "Much Worse",
    "-2": "Worse",
    "-1": "Slightly Worse",
    0: "Equal",
    1: "Slightly Better",
    2: "Better",
    3: "Much Better",
  };
  var mosValue = 3,
    stars = [];
  for (var s = 1; s <= 5; s++) {
    (function (v) {
      var b = el(
        "button",
        {
          class: "star",
          type: "button",
          role: "radio",
          "aria-label": v + " star",
        },
        [UI.icon("star")],
      );
      b.addEventListener("mouseenter", function () {
        paintStars(v);
      });
      b.addEventListener("mouseleave", function () {
        paintStars(mosValue);
      });
      b.addEventListener("click", function () {
        mosValue = v;
        paintStars(v);
        UI.replay(b, "pop");
        $("mos-text").textContent = MOS[v];
      });
      $("mos-stars").appendChild(b);
      stars.push(b);
    })(s);
  }
  function paintStars(n) {
    stars.forEach(function (b, i) {
      b.classList.toggle("on", i < n);
    });
  }
  paintStars(3);

  $("cmos").addEventListener("input", function (e) {
    $("cmos-text").textContent = e.target.value + " — " + CMOS[e.target.value];
  });
  $("mos-submit").addEventListener("click", function () {
    UI.toast("MOS recorded: " + MOS[mosValue], "success");
  });
  $("cmos-submit").addEventListener("click", function () {
    var v = $("cmos").value;
    UI.toast("CMOS recorded: " + v + " (" + CMOS[v] + ")", "success");
  });

  /* =====================================================================
     LIVE TRANSLATION
     ===================================================================== */
  var live = {
    timer: null,
    seq: 0,
    chain: Promise.resolve(),
    recog: null,
    listening: false,
    micPaused: false,
    queue: [],
    playing: false,
    audio: null,
    lastWarning: "",
  };

  function targetLang() {
    return $("language").value;
  }
  function setStatus(t) {
    $("live-status").textContent = t;
  }
  function refreshLiveHint() {
    $("live-hint").hidden = targetLang() !== "None";
  }
  function updateLiveLabel() {
    var t = targetLang();
    $("live-out-label").textContent =
      t === "None" ? "Translation" : "Translation → " + titleCase(t);
  }
  function voiceOptions() {
    return {
      engine: currentEngine(),
      voice: document.querySelector('input[name="voice"]:checked').value,
      speed: $("speed").value,
      volume: $("volume").value,
      language: targetLang(),
    };
  }
  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  async function liveTranslate(text) {
    var res = await postJSON("/api/live/translate", {
      text: text,
      language: targetLang(),
    });
    var data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok || !data.ok)
      throw new Error(data.error || "Translation failed");
    return data.translation;
  }

  async function runLiveTranslate() {
    var text = $("live-in").value.trim();
    refreshLiveHint();
    if (!text) {
      $("live-out").value = "";
      setStatus("");
      return;
    }
    if (targetLang() === "None") return;
    var my = ++live.seq;
    setStatus("Translating…");
    try {
      var t = await liveTranslate(text);
      if (my !== live.seq) return;
      $("live-out").value = t;
      setStatus("Live ✓");
    } catch (e) {
      if (my === live.seq) setStatus(e.message);
    }
  }
  $("live-in").addEventListener("input", function () {
    clearTimeout(live.timer);
    live.timer = setTimeout(runLiveTranslate, 600);
  });
  $("live-in").addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || e.shiftKey || !$("auto-speak").checked) return;
    var ta = e.target;
    var line = ta.value.slice(0, ta.selectionStart).split("\n").pop().trim();
    if (!line || targetLang() === "None") return;
    liveTranslate(line)
      .then(function (t) {
        enqueueSpeak(t);
      })
      .catch(function (err) {
        setStatus(err.message);
      });
  });
  $("language").addEventListener("change", function () {
    refreshLiveHint();
    updateLiveLabel();
    if (mode === "live") runLiveTranslate();
  });

  // --- speaking
  async function fetchSpeech(text) {
    var res = await postJSON(
      "/api/live/speak",
      Object.assign({ text: text }, voiceOptions()),
    );
    if (!res.ok) {
      var d = await res.json().catch(function () {
        return {};
      });
      var err = new Error(d.error || "Speech failed (HTTP " + res.status + ")");
      err.details = d.details || [];
      err.hint = d.hint || "";
      throw err;
    }
    live.lastWarning = res.headers.get("X-TTS-Warning") || "";
    return res.blob();
  }

  function showSpeechError(e) {
    var box = $("live-error");
    var lines = [e.message];
    (e.details || []).forEach(function (d) {
      lines.push("• " + d);
    });
    if (e.hint) lines.push("", "Tip: " + e.hint);
    box.className = "alert alert-error live-error";
    box.textContent = "";
    box.appendChild(UI.icon("alert"));
    box.appendChild(el("span", { text: lines.join("\n") }));
    box.hidden = false;
  }
  function showSpeechWarning(w) {
    var box = $("live-error");
    if (!w) {
      box.hidden = true;
      return;
    }
    box.className = "alert alert-warn live-error";
    box.textContent = "";
    box.appendChild(UI.icon("alert"));
    box.appendChild(
      el("span", { text: "A backup voice was used. Reason:\n" + w }),
    );
    box.hidden = false;
  }

  function loadVoices() {
    return new Promise(function (resolve) {
      var synth = window.speechSynthesis;
      if (!synth) {
        resolve([]);
        return;
      }
      var have = synth.getVoices();
      if (have.length) {
        resolve(have);
        return;
      }
      var done = function () {
        resolve(synth.getVoices());
      };
      synth.addEventListener("voiceschanged", done, { once: true });
      setTimeout(done, 1500);
    });
  }

  async function browserSpeak(text) {
    var synth = window.speechSynthesis;
    if (!synth)
      throw new Error(
        "This browser has no speech output. Use Microsoft Edge or Google Chrome.",
      );
    var locale = (cfg.locales && cfg.locales[targetLang()]) || "en-US";
    var lc = locale.toLowerCase();
    var voices = await loadVoices();
    var voice =
      voices.find(function (v) {
        return v.lang.toLowerCase().replace("_", "-") === lc;
      }) ||
      voices.find(function (v) {
        return v.lang.toLowerCase().indexOf(lc.slice(0, 2)) === 0;
      });
    if (!voice)
      setStatus(
        "No browser voice for " +
          locale +
          ". Add it in Windows Settings → Time & language → Speech.",
      );
    var u = new SpeechSynthesisUtterance(text);
    u.lang = voice ? voice.lang : locale;
    if (voice) u.voice = voice;
    u.rate = Math.max(0.5, Math.min(2, Number($("speed").value) / 150));
    u.volume = Number($("volume").value);
    await new Promise(function (resolve) {
      var guard = setTimeout(
        function () {
          synth.cancel();
          resolve();
        },
        Math.min(120000, 4000 + text.length * 140),
      );
      var end = function () {
        clearTimeout(guard);
        resolve();
      };
      u.onend = end;
      u.onerror = end;
      synth.speak(u);
    });
  }

  async function playServer(text) {
    var blob = await fetchSpeech(text);
    var url = URL.createObjectURL(blob);
    var audio = new Audio(url);
    live.audio = audio;
    await new Promise(function (resolve) {
      audio.onended = resolve;
      audio.onerror = resolve;
      audio.play().catch(resolve);
    });
    URL.revokeObjectURL(url);
    live.audio = null;
  }

  async function speakOne(text) {
    if ($("live-voice").value === "server") {
      try {
        await playServer(text);
        showSpeechWarning(live.lastWarning);
        return;
      } catch (e) {
        showSpeechError(e);
        setStatus("Server voice failed — using the browser voice");
      }
    }
    await browserSpeak(text);
  }

  function stopAudio() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (live.audio) {
      var a = live.audio;
      live.audio = null;
      a.pause();
      a.dispatchEvent(new Event("ended"));
    }
  }
  function enqueueSpeak(text) {
    if (text) {
      live.queue.push(text);
      pump();
    }
  }

  async function pump() {
    if (live.playing) return;
    var text = live.queue.shift();
    if (text === undefined) {
      resumeMic();
      return;
    }
    live.playing = true;
    $("live-out-card").classList.add("speaking");
    pauseMic();
    try {
      setStatus("Speaking…");
      await speakOne(text);
      if (!/failed|No browser voice/.test($("live-status").textContent))
        setStatus("Live ✓");
    } catch (e) {
      setStatus(e.message);
    }
    live.audio = null;
    live.playing = false;
    if (!live.queue.length) $("live-out-card").classList.remove("speaking");
    pump();
  }

  $("live-speak").addEventListener("click", function () {
    var text = $("live-out").value.trim();
    if (!text) {
      UI.toast("Nothing to speak yet.", "info", 2400);
      return;
    }
    live.queue.length = 0;
    stopAudio();
    enqueueSpeak(text);
  });
  $("live-copy").addEventListener("click", async function () {
    var out = $("live-out");
    if (!out.value) {
      UI.toast("Nothing to copy yet.", "info", 2400);
      return;
    }
    try {
      await navigator.clipboard.writeText(out.value);
    } catch (e) {
      out.select();
      document.execCommand("copy");
    }
    UI.toast("Translation copied.", "success", 2200);
  });
  $("live-clear").addEventListener("click", function () {
    live.queue.length = 0;
    stopAudio();
    $("live-in").value = "";
    $("live-out").value = "";
    $("live-interim").textContent = "";
    $("live-error").hidden = true;
    setStatus("");
  });

  // --- microphone
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;

  function updateMicBtn() {
    $("mic-btn").classList.toggle("on", live.listening);
    $("mic-lbl").textContent = live.listening ? "Stop mic" : "Start mic";
    UI.setIcon($("mic-ic"), live.listening ? "stop" : "mic");
    $("live-eq").hidden = !live.listening;
  }

  function onFinalSegment(text) {
    if (!text) return;
    var input = $("live-in");
    input.value +=
      (input.value && !input.value.endsWith("\n") ? "\n" : "") + text + "\n";
    input.scrollTop = input.scrollHeight;
    refreshLiveHint();
    if (targetLang() === "None") return;
    live.chain = live.chain.then(async function () {
      try {
        setStatus("Translating…");
        var t = await liveTranslate(text);
        var out = $("live-out");
        out.value +=
          (out.value && !out.value.endsWith("\n") ? "\n" : "") + t + "\n";
        out.scrollTop = out.scrollHeight;
        setStatus("Live ✓");
        if ($("auto-speak").checked) enqueueSpeak(t);
      } catch (e) {
        setStatus(e.message);
      }
    });
  }

  function startMic() {
    if (!SR) return;
    stopMic();
    var rec = new SR();
    rec.lang = $("live-src").value || "en-US";
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = function (ev) {
      var interim = "";
      for (var i = ev.resultIndex; i < ev.results.length; i++) {
        var r = ev.results[i];
        if (r.isFinal) onFinalSegment(r[0].transcript.trim());
        else interim += r[0].transcript;
      }
      $("live-interim").textContent = interim || "Listening…";
    };
    rec.onerror = function (e) {
      var msg = {
        "not-allowed":
          "Microphone permission is blocked. Allow it in the address bar, then try again.",
        "service-not-allowed":
          "Microphone permission is blocked. Allow it in the address bar, then try again.",
        "audio-capture": "No microphone was found on this PC.",
        network: "Speech recognition needs an internet connection.",
      }[e.error];
      if (msg) {
        $("mic-note").textContent = msg;
        UI.toast(msg, "error");
        stopMic();
      }
    };
    rec.onend = function () {
      if (live.listening && !live.micPaused && live.recog === rec) {
        try {
          rec.start();
        } catch (err) {
          /* running */
        }
      }
    };
    live.recog = rec;
    live.listening = true;
    live.micPaused = false;
    $("mic-note").textContent = "";
    $("live-interim").textContent = "Listening…";
    try {
      rec.start();
    } catch (err) {
      /* ignore */
    }
    updateMicBtn();
  }

  function stopMic() {
    var rec = live.recog;
    live.listening = false;
    live.micPaused = false;
    live.recog = null;
    if (rec) {
      try {
        rec.stop();
      } catch (e) {
        /* ignore */
      }
    }
    $("live-interim").textContent = "";
    updateMicBtn();
  }

  function pauseMic() {
    if (live.listening && live.recog && !live.micPaused) {
      live.micPaused = true;
      try {
        live.recog.stop();
      } catch (e) {
        /* ignore */
      }
    }
  }
  function resumeMic() {
    if (!(live.listening && live.micPaused)) return;
    live.micPaused = false;
    var rec = live.recog;
    var tryStart = function (left) {
      if (!live.listening || live.recog !== rec) return;
      try {
        rec.start();
      } catch (e) {
        if (left > 0)
          setTimeout(function () {
            tryStart(left - 1);
          }, 400);
      }
    };
    setTimeout(function () {
      tryStart(3);
    }, 350);
  }

  $("mic-btn").addEventListener("click", function () {
    if (live.listening) stopMic();
    else startMic();
  });
  $("live-src").addEventListener("change", function () {
    if (live.listening) startMic();
  });
  if (!SR) {
    $("mic-btn").disabled = true;
    $("mic-note").textContent =
      "The microphone needs Google Chrome or Microsoft Edge. Typing works in every browser.";
  }

  init();
})();
