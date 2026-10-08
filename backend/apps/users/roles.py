class Role:
    PLATFORM_ADMIN = "platform_admin"
    MANAGER = "manager"
    COOK = "cook"
    WAITER = "waiter"
    DRIVER = "driver"
    CUSTOMER = "customer"

    CHOICES = (
        (PLATFORM_ADMIN, "Administrateur plateforme"),
        (MANAGER, "Gérant"),
        (COOK, "Cuisinier"),
        (WAITER, "Serveur"),
        (DRIVER, "Livreur"),
        (CUSTOMER, "Client"),
    )

    STAFF = (MANAGER, COOK, WAITER, DRIVER)
    LABELS = dict(CHOICES)
