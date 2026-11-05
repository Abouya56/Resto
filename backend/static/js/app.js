(function () {
  function connect(path, onMessage) {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}${path}`);
    socket.onmessage = function (event) {
      const data = JSON.parse(event.data);
      onMessage(data);
    };
    return socket;
  }

  // ---- Alerte « nouvelle commande » (réception et gérant) : son, vibration, écran allumé ----
  // Les navigateurs ne jouent un son qu'après un premier appui sur la page : d'où le bouton « Activer le son ».
  var audioCtx = null;
  function getAudio() {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!audioCtx) audioCtx = new AC();
    return audioCtx;
  }

  function chime() {
    var ctx = getAudio();
    if (!ctx) return;
    if (ctx.state === "suspended") ctx.resume().catch(function () {});
    var start = ctx.currentTime + 0.05;
    // « Ding-dong » répété trois fois.
    for (var i = 0; i < 3; i += 1) {
      [[988, 0], [740, 0.32]].forEach(function (note) {
        var t = start + i * 1.1 + note[1];
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = note[0];
        gain.gain.setValueAtTime(0.0001, t);
        gain.gain.exponentialRampToValueAtTime(0.6, t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
        osc.connect(gain).connect(ctx.destination);
        osc.start(t);
        osc.stop(t + 0.65);
      });
    }
  }

  // Gérant : un message discret, sans bruit (c'est la réception qui traite les commandes).
  function orderToast() {
    var old = document.querySelector(".order-toast");
    if (old) old.remove();
    var toast = document.createElement("div");
    toast.className = "order-toast";
    toast.setAttribute("role", "status");
    toast.innerHTML = '<i class="bi bi-bell"></i> Nouvelle commande reçue · la réception s\'en occupe';
    document.body.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 8000);
  }

  function alertNewOrder(mode) {
    if (mode !== "sound") {
      orderToast();
    } else {
      chime();
      try { if (navigator.vibrate) navigator.vibrate([400, 200, 400, 200, 400]); } catch (e) { /* pas de vibreur */ }
    }
    if (document.hidden && !/^\(\d+\)/.test(document.title)) {
      // Onglet en arrière-plan sur ordinateur : le titre de l'onglet le signale.
      document.title = "(1) Nouvelle commande · " + document.title;
    }
  }

  function pendingMark(root) {
    var el = root.querySelector("[data-pending-latest]");
    if (!el) return null;
    return { latest: parseInt(el.dataset.pendingLatest, 10) || 0, restaurant: el.dataset.restaurant, alert: el.dataset.alert };
  }

  // Sonne si une commande à accepter est plus récente que la dernière déjà signalée sur cet appareil.
  function checkNewOrders(root) {
    var mark = pendingMark(root);
    if (!mark) return;
    var key = "resto-alert-" + mark.restaurant;
    var seen = null;
    try { seen = window.localStorage.getItem(key); } catch (e) { /* stockage bloqué */ }
    var last = seen === null ? null : parseInt(seen, 10) || 0;
    if (last !== null && mark.latest > last) alertNewOrder(mark.alert);
    try { window.localStorage.setItem(key, String(Math.max(mark.latest, last || 0))); } catch (e) { /* idem */ }
  }

  function soundButton() {
    var ctx = getAudio();
    if (!ctx) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "sound-toggle";
    var render = function () {
      var on = ctx.state === "running";
      button.classList.toggle("is-on", on);
      button.innerHTML = on
        ? '<i class="bi bi-bell-fill"></i><span class="visually-hidden">Son activé : appuyer pour tester</span>'
        : '<i class="bi bi-volume-mute-fill"></i> Activer le son';
      button.title = on ? "Son activé : appuyer pour tester" : "Activer le son des nouvelles commandes";
    };
    button.addEventListener("click", function () {
      ctx.resume().then(function () { render(); chime(); }).catch(function () {});
    });
    // N'importe quel appui sur la page débloque aussi le son.
    document.addEventListener("pointerdown", function () {
      if (ctx.state === "suspended") ctx.resume().then(render).catch(function () {});
    });
    ctx.onstatechange = render;
    render();
    document.body.appendChild(button);
  }

  // L'écran reste allumé pendant le service (tant que la page est affichée).
  function keepAwake() {
    if (!("wakeLock" in navigator) || document.hidden) return;
    navigator.wakeLock.request("screen").catch(function () {});
  }

  // Met à jour le contenu de la page sans la recharger (le son reste ainsi activé).
  function swapPart(doc, selector) {
    var current = document.querySelector(selector);
    var fresh = doc.querySelector(selector);
    if (!current && !fresh) return true;
    if (!current || !fresh) return false;
    current.replaceWith(document.importNode(fresh, true));
    return true;
  }

  function update(swapContent) {
    return fetch(window.location.href, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok || response.redirected) throw new Error("page changée");
        return response.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        if (swapContent) {
          if (!swapPart(doc, "[data-live-region]") || !swapPart(doc, ".staff-nav")) throw new Error("page changée");
          document.title = doc.title;
        }
        checkNewOrders(doc);
      })
      .catch(function () {
        if (swapContent) window.location.reload();
      });
  }

  // Les pages posent leurs repères (RESTO_KITCHEN_WS…) dans un script placé APRÈS celui-ci :
  // on attend la fin du chargement de la page pour les lire.
  function startLive() {
  var mark = pendingMark(document);
  var restaurantId = window.RESTO_KITCHEN_WS || (mark && mark.restaurant);
  if (restaurantId) {
    // Pages en direct (RESTO_KITCHEN_WS) : le contenu se met à jour seul, sans interrompre une saisie.
    // Autres pages de la réception et du gérant : on vérifie seulement s'il faut sonner.
    var livePage = Boolean(window.RESTO_KITCHEN_WS);
    var stale = false;
    var timer = null;
    var busy = function () {
      var el = document.activeElement;
      if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return true;
      return Boolean(document.querySelector("[data-live-region] details[open]"));
    };
    var refresh = function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        var canSwap = livePage && !document.hidden && !busy();
        stale = livePage && !canSwap;
        update(canSwap);
      }, 600);
    };
    var liveSocket = function () {
      var socket = connect(`/ws/kitchen/${restaurantId}/`, refresh);
      socket.onclose = function () { setTimeout(liveSocket, 3000); };
    };
    var withSound = Boolean(mark && mark.alert === "sound");
    if (mark) checkNewOrders(document);
    if (withSound) {
      soundButton();
      keepAwake();
    }
    liveSocket();
    // Contenu en retard (saisie en cours, onglet caché) : mis à jour dès que possible.
    setInterval(function () {
      if (stale && !document.hidden && !busy()) { stale = false; update(true); }
    }, 3000);
    // Filet de sécurité si la connexion directe est coupée (réseau mobile) : vérification toutes les 30 s.
    setInterval(refresh, 30000);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) return;
      document.title = document.title.replace(/^\(1\) Nouvelle commande · /, "");
      if (withSound) keepAwake();
      refresh();
    });
  }

  if (window.RESTO_ORDER_WS) {
    connect(`/ws/orders/${window.RESTO_ORDER_WS}/`, function (data) {
      if (data.status) {
        var url = new URL(window.location.href);
        url.searchParams.delete("nouvelle");
        window.location.replace(url.toString());
      }
    });
  }

  if (document.body.dataset.authenticated === "1") {
    connect("/ws/notifications/", function (data) {
      if (data.title) {
        console.debug("Notification", data.title);
      }
    });
  }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startLive);
  } else {
    startLive();
  }

  // Panier sur téléphone : la barre du bas ouvre la fiche « Ma commande » ; elle se rouvre après un + ou un −.
  (function () {
    var body = document.body;
    if (!document.getElementById("cart-col")) return;
    function setOpen(open) { body.classList.toggle("cart-open", open); }
    document.querySelectorAll("[data-cart-open]").forEach(function (el) {
      el.addEventListener("click", function () { setOpen(true); });
    });
    document.querySelectorAll("[data-cart-close]").forEach(function (el) {
      el.addEventListener("click", function () { setOpen(false); });
    });
    document.addEventListener("keydown", function (event) { if (event.key === "Escape") setOpen(false); });
    if (window.location.hash === "#panier" && window.matchMedia("(max-width: 991px)").matches) setOpen(true);
  })();

  // App installable : le service worker rend le site installable ; le bouton propose l'installation.
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
    });
  }

  var installEvent = null;
  var installButtons = document.querySelectorAll("[data-install]");
  var installHint = document.querySelector("[data-install-hint]");
  var alreadyInstalled = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  var onIos = /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;

  function setInstallVisible(visible) {
    installButtons.forEach(function (button) {
      button.hidden = !visible;
    });
  }

  if (!alreadyInstalled) {
    window.addEventListener("beforeinstallprompt", function (event) {
      event.preventDefault();
      installEvent = event;
      setInstallVisible(true);
    });
    if (onIos) setInstallVisible(true); // iPhone : pas d'invite automatique, on explique le geste
  }
  window.addEventListener("appinstalled", function () {
    installEvent = null;
    setInstallVisible(false);
    if (installHint) installHint.hidden = true;
  });
  installButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      if (installEvent) {
        installEvent.prompt();
        installEvent.userChoice.finally(function () {
          installEvent = null;
          setInstallVisible(false);
        });
      } else if (installHint) {
        installHint.hidden = !installHint.hidden;
      }
    });
  });

  // Champs fichier : on montre tout de suite l'image choisie et son nom, avant d'enregistrer.
  document.querySelectorAll("[data-preview-input]").forEach(function (input) {
    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      var name = document.querySelector('[data-file-name="' + input.id + '"]');
      var img = document.querySelector('[data-preview-img="' + input.id + '"]');
      var empty = document.querySelector('[data-preview-empty="' + input.id + '"]');
      if (name) name.textContent = file ? file.name + " (pas encore enregistrée)" : "Aucun fichier choisi";
      if (img && file && file.type.indexOf("image/") === 0) {
        img.src = URL.createObjectURL(file);
        img.hidden = false;
        if (empty) empty.hidden = true;
      }
    });
  });

  // Menu du personnel sur téléphone : le bouton ☰ du haut ouvre le menu en tiroir, à gauche.
  // Un seul lien (réception) = pas de menu.
  var staffMenu = document.getElementById("staff-menu");
  if (staffMenu) {
    if (staffMenu.querySelectorAll("nav a").length <= 1) {
      document.body.classList.add("staff-solo");
    } else {
      var toggler = document.querySelector(".navbar-toggler");
      if (toggler) {
        toggler.removeAttribute("data-bs-toggle");
        toggler.removeAttribute("data-bs-target");
        toggler.setAttribute("aria-controls", "staff-menu");
        toggler.setAttribute("aria-expanded", "false");
        var backdrop = document.createElement("div");
        backdrop.className = "staff-backdrop";
        document.body.appendChild(backdrop);
        var setDrawer = function (open) {
          document.body.classList.toggle("staff-sheet-open", open);
          toggler.setAttribute("aria-expanded", open ? "true" : "false");
        };
        toggler.addEventListener("click", function () {
          setDrawer(!document.body.classList.contains("staff-sheet-open"));
        });
        backdrop.addEventListener("click", function () { setDrawer(false); });
        document.addEventListener("keydown", function (e) { if (e.key === "Escape") setDrawer(false); });
        // Pied du tiroir : notifications et déconnexion (cachées du haut de page sur téléphone).
        var foot = document.createElement("div");
        foot.className = "staff-drawer-foot";
        var bell = document.querySelector('#mainNav a[href*="notifications"]');
        if (bell) {
          var bellLink = document.createElement("a");
          bellLink.href = bell.getAttribute("href");
          bellLink.innerHTML = '<i class="bi bi-bell"></i> Notifications';
          foot.appendChild(bellLink);
        }
        var logout = document.querySelector('#mainNav form[action*="deconnexion"]');
        if (logout) {
          var logoutCopy = logout.cloneNode(true);
          var logoutButton = logoutCopy.querySelector("button");
          if (logoutButton) logoutButton.className = "";
          if (logoutButton) logoutButton.innerHTML = '<i class="bi bi-box-arrow-right"></i> Déconnexion';
          foot.appendChild(logoutCopy);
        }
        staffMenu.appendChild(foot);
      }
    }
  }

  // Messages du personnel : ils disparaissent seuls au bout de quelques secondes.
  document.querySelectorAll(".staff-toasts .alert").forEach(function (alert) {
    setTimeout(function () {
      try {
        window.bootstrap.Alert.getOrCreateInstance(alert).close();
      } catch (e) {
        alert.remove();
      }
    }, 7000);
  });

  var checkoutForm = document.getElementById("checkout-form");
  var locateButton = document.getElementById("use-location");
  if (checkoutForm && locateButton) {
    var locationStatus = document.getElementById("location-status");
    locateButton.addEventListener("click", function () {
      if (!navigator.geolocation) {
        if (locationStatus) locationStatus.textContent = "Votre appareil ne donne pas sa position. Remplissez l'adresse.";
        return;
      }
      locateButton.disabled = true;
      locateButton.textContent = "Recherche…";
      navigator.geolocation.getCurrentPosition(
        function (position) {
          checkoutForm.querySelector("#id_latitude").value = position.coords.latitude.toFixed(6);
          checkoutForm.querySelector("#id_longitude").value = position.coords.longitude.toFixed(6);
          locateButton.disabled = false;
          locateButton.textContent = "Position ajoutée ✓";
          if (locationStatus) {
            locationStatus.textContent = "Position envoyée au livreur. Indiquez quand même le quartier et un repère.";
          }
        },
        function () {
          locateButton.disabled = false;
          locateButton.textContent = "Utiliser ma position";
          if (locationStatus) locationStatus.textContent = "Position refusée. Remplissez l'adresse ci-dessous.";
        }
      );
    });
  }

  document.querySelectorAll("[data-demo-email]").forEach(function (button) {
    button.addEventListener("click", function () {
      var email = document.querySelector("#id_username");
      var password = document.querySelector("#id_password");
      if (email) email.value = button.dataset.demoEmail;
      if (password) password.value = button.dataset.demoPassword;
    });
  });
})();
