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

  if (window.RESTO_KITCHEN_WS) {
    connect(`/ws/kitchen/${window.RESTO_KITCHEN_WS}/`, function () {
      window.location.reload();
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
