(function () {
  "use strict";

  var THEMES = ["ocean", "lavender", "mint", "sunset"];
  var NAMES = {
    ocean: "Ocean",
    lavender: "Lavender",
    mint: "Mint",
    sunset: "Sunset",
  };
  var root = document.documentElement;
  var bar = document.getElementById("theme-bar");
  var seg = document.getElementById("theme-seg");
  var pill = document.getElementById("theme-pill");
  var btnGold = document.getElementById("btn-gold");
  var btnLight = document.getElementById("btn-light");
  var nameEl = document.getElementById("theme-name");
  var dots = Array.prototype.slice.call(document.querySelectorAll(".dot"));

  var light = false,
    pinned = false,
    current = 0,
    timer = null;
  var reduced = !!(
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );

  function store(k, v) {
    try {
      localStorage.setItem(k, v);
    } catch (e) {
      /* private mode */
    }
  }
  function load(k) {
    try {
      return localStorage.getItem(k);
    } catch (e) {
      return null;
    }
  }
  function interval() {
    return Number(bar.dataset.interval) || 12000;
  }

  function movePill() {
    if (window.UI) UI.slidePill(seg, pill, light ? btnLight : btnGold);
  }

  function restartBar() {
    // thin progress line under the Light button
    btnLight.classList.remove("auto");
    void btnLight.offsetWidth;
    if (light && !pinned && !reduced) {
      btnLight.style.setProperty("--iv", interval() + "ms");
      btnLight.classList.add("auto");
    }
  }

  function paint() {
    if (light) {
      root.setAttribute("data-mode", "multi");
      root.setAttribute("data-theme", THEMES[current]);
    } else {
      root.setAttribute("data-mode", "gold");
      root.removeAttribute("data-theme");
      nameEl.textContent = "";
    }
    btnGold.classList.toggle("active", !light);
    btnLight.classList.toggle("active", light);
    btnGold.setAttribute("aria-pressed", String(!light));
    btnLight.setAttribute("aria-pressed", String(light));
    dots.forEach(function (d) {
      var on = light && d.dataset.pick === THEMES[current];
      d.classList.toggle("active", on);
      d.setAttribute("aria-pressed", String(on));
    });
    movePill();
  }

  function stopTimer() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }
  function startTimer() {
    stopTimer();
    if (light && !pinned && !reduced) timer = setInterval(next, interval());
    restartBar();
  }

  function next() {
    current = (current + 1) % THEMES.length;
    paint();
    restartBar();
  }

  function setLight(on) {
    light = !!on;
    pinned = light && reduced; // reduced-motion PCs keep the colour still
    store("vm-multi", light ? "1" : "0");
    store("vm-pinned", pinned ? "1" : "0");
    paint();
    startTimer();
  }

  btnGold.addEventListener("click", function () {
    if (light) setLight(false);
  });
  btnLight.addEventListener("click", function () {
    if (!light) setLight(true);
    else if (pinned) {
      // resume the automatic colour change
      pinned = false;
      store("vm-pinned", "0");
      paint();
      startTimer();
    }
  });
  dots.forEach(function (d) {
    d.addEventListener("click", function () {
      current = Math.max(0, THEMES.indexOf(d.dataset.pick));
      pinned = true; // choosing a colour keeps it
      store("vm-theme", THEMES[current]);
      store("vm-pinned", "1");
      paint();
      startTimer();
    });
  });

  // start-up: remembered choice, default = Black & Gold
  var savedTheme = load("vm-theme");
  current = Math.max(0, THEMES.indexOf(savedTheme));
  light = load("vm-multi") === "1";
  pinned = load("vm-pinned") === "1" || (light && reduced);
  paint();
  startTimer();

  window.addEventListener("resize", movePill);
  if (document.fonts && document.fonts.ready)
    document.fonts.ready.then(movePill);
  setTimeout(movePill, 150);

  window.VFTheme = {
    next: next,
    setLight: setLight,
    pick: function (n) {
      current = Math.max(0, THEMES.indexOf(n));
      pinned = true;
      paint();
      startTimer();
    },
  };
})();
