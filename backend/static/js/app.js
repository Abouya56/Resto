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

  // Les pages posent leurs repères (RESTO_KITCHEN_WS…) dans un script placé APRÈS celui-ci :
  // on attend la fin du chargement de la page pour les lire.
  function startLive() {
  if (window.RESTO_KITCHEN_WS) {
    // Page en direct : se recharge à chaque événement, sans interrompre une saisie en cours.
    var reloadTimer = null;
    var typing = function () {
      var el = document.activeElement;
      return el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName);
    };
    var refresh = function () {
      clearTimeout(reloadTimer);
      reloadTimer = setTimeout(function () {
        if (document.hidden || typing()) {
          reloadTimer = setTimeout(refresh, 3000);
          return;
        }
        window.location.reload();
      }, 600);
    };
    var liveSocket = function () {
      var socket = connect(`/ws/kitchen/${window.RESTO_KITCHEN_WS}/`, refresh);
      socket.onclose = function () { setTimeout(liveSocket, 3000); };
    };
    liveSocket();
    // Filet de sécurité si la connexion directe est coupée (réseau mobile) : mise à jour toutes les 30 s.
    setInterval(function () { if (!document.hidden && !typing()) window.location.reload(); }, 30000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) refresh();
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
