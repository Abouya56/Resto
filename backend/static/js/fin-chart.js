/* Graphique « 14 derniers jours » de la caisse : colonnes encaissé / dépensé par jour, un seul axe en FCFA. */
(function () {
  var box = document.getElementById("fin-chart");
  var dataEl = document.getElementById("fin-chart-data");
  if (!box || !dataEl) return;
  var days = JSON.parse(dataEl.textContent);
  var tip = document.getElementById("fin-tip");
  var NS = "http://www.w3.org/2000/svg";
  var W = 720, H = 230, L = 56, R = 8, T = 12, B = 40;
  var plotW = W - L - R, plotH = H - T - B;
  var money = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });

  function fcfa(v) {
    return money.format(v) + " FCFA";
  }
  function short(v) {
    return v >= 1000 ? money.format(v / 1000) + " k" : money.format(v);
  }

  var max = 0;
  days.forEach(function (d) {
    max = Math.max(max, d.cashed, d.spent);
  });
  // Graduations « rondes » (1, 2, 2,5 ou 5 × 10^n) pour que chaque ligne se lise d'un coup d'œil.
  function niceStep(v) {
    var raw = v / 4;
    var p = Math.pow(10, Math.floor(Math.log10(raw)));
    var n = raw / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
  }
  var step = max ? niceStep(max) : 5000;
  var top = Math.max(step, Math.ceil(max / step) * step);
  function y(v) {
    return T + plotH - (v / top) * plotH;
  }

  var svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  svg.setAttribute("class", "fin-svg");
  svg.setAttribute("aria-hidden", "true");
  function el(name, attrs, parent) {
    var node = document.createElementNS(NS, name);
    Object.keys(attrs).forEach(function (k) {
      node.setAttribute(k, attrs[k]);
    });
    (parent || svg).appendChild(node);
    return node;
  }

  for (var g = 0; g <= top + 1e-9; g += step) {
    el("line", { x1: L, x2: W - R, y1: y(g), y2: y(g), class: g === 0 ? "fin-axis" : "fin-grid" });
    el("text", { x: L - 8, y: y(g) + 4, "text-anchor": "end", class: "fin-tick" }).textContent = short(g);
  }

  var band = plotW / days.length;
  var barW = Math.min(16, (band - 10) / 2);

  // Colonne arrondie en haut (4 px), carrée sur la ligne de base.
  function column(x, value, cls) {
    if (!value) return;
    var h = Math.max(2, y(0) - y(value));
    var r = Math.min(4, h / 2, barW / 2);
    var t0 = y(0) - h;
    el("path", {
      d:
        "M" + x + "," + y(0) + "V" + (t0 + r) +
        "Q" + x + "," + t0 + " " + (x + r) + "," + t0 +
        "H" + (x + barW - r) +
        "Q" + (x + barW) + "," + t0 + " " + (x + barW) + "," + (t0 + r) +
        "V" + y(0) + "Z",
      class: cls,
    });
  }

  function line(label, cls, value) {
    var span = document.createElement("span");
    if (cls) {
      var sw = document.createElement("i");
      sw.className = "fin-swatch " + cls;
      span.appendChild(sw);
    }
    span.appendChild(document.createTextNode(label));
    var b = document.createElement("b");
    b.textContent = value;
    span.appendChild(b);
    return span;
  }

  var tipBox = box.querySelector(".fin-tip");
  days.forEach(function (d, i) {
    var x0 = L + band * i;
    var cx = x0 + band / 2;
    if (d.selected) el("rect", { x: x0 + 2, y: T, width: band - 4, height: plotH, rx: 6, class: "fin-sel" });
    column(cx - barW - 1, d.cashed, "fin-bar-in"); // 2 px d'air entre les deux colonnes
    column(cx + 1, d.spent, "fin-bar-out");
    el("text", { x: cx, y: H - B + 16, "text-anchor": "middle", class: d.selected ? "fin-day is-sel" : "fin-day" }).textContent = d.short;
    el("text", { x: cx, y: H - B + 30, "text-anchor": "middle", class: "fin-wd" }).textContent = d.weekday;

    // Zone de survol et de clic plus large que les colonnes.
    // Le clavier et les lecteurs d'écran passent par le tableau en dessous (mêmes chiffres, mêmes liens).
    var hit = el("rect", { x: x0, y: 0, width: band, height: H, class: "fin-hit" });
    function show() {
      var rest = d.cashed - d.spent;
      tip.textContent = "";
      var title = document.createElement("strong");
      title.textContent = d.label;
      tip.appendChild(title);
      tip.appendChild(line("Encaissé", "fin-swatch-in", fcfa(d.cashed)));
      tip.appendChild(line("Dépensé", "fin-swatch-out", fcfa(d.spent)));
      var restLine = line("Reste", "", (rest > 0 ? "+" : "") + fcfa(rest));
      restLine.className = "fin-tip-rest" + (rest < 0 ? " is-negative" : "");
      tip.appendChild(restLine);
      tip.hidden = false;
      var boxW = box.getBoundingClientRect().width;
      var px = (cx / W) * boxW;
      tip.style.left = Math.min(Math.max(px - tip.offsetWidth / 2, 0), boxW - tip.offsetWidth) + "px";
    }
    function hide() {
      tip.hidden = true;
    }
    function go() {
      window.location.search = "?jour=" + d.day;
    }
    hit.addEventListener("mouseenter", show);
    hit.addEventListener("mouseleave", hide);
    hit.addEventListener("click", go);
  });
  box.insertBefore(svg, tipBox);
})();
