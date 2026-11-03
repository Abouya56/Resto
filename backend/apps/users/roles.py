class Role:
    PLATFORM_ADMIN = "platform_admin"
    MANAGER = "manager"
    RECEPTION = "reception"
    CUSTOMER = "customer"

    CHOICES = (
        (PLATFORM_ADMIN, "Administrateur plateforme"),
        (MANAGER, "Gérant"),
        (RECEPTION, "Réception"),
        (CUSTOMER, "Client"),
    )

    STAFF = (MANAGER, RECEPTION)
    # Anciens rôles (cuisine, service, livraison) : fusionnés dans « Réception ».
    LEGACY_STAFF = ("cook", "waiter", "driver")
    LABELS = dict(CHOICES)
