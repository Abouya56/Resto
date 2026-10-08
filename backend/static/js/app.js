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
        const el = document.querySelector(".order-status");
        if (el) el.textContent = data.status;
        else window.location.reload();
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

  document.querySelectorAll("[data-demo-email]").forEach(function (button) {
    button.addEventListener("click", function () {
      var email = document.querySelector("#id_username");
      var password = document.querySelector("#id_password");
      if (email) email.value = button.dataset.demoEmail;
      if (password) password.value = button.dataset.demoPassword;
    });
  });
})();
