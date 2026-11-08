"""En-têtes de sécurité envoyés avec chaque page."""

CSP = "; ".join(
    [
        "frame-ancestors 'none'",  # personne ne peut afficher le site dans un autre site (clickjacking)
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",  # un formulaire ne peut envoyer ses données que vers le site lui-même
    ]
)
PERMISSIONS = "camera=(), microphone=(), payment=(), usb=(), geolocation=(self)"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", CSP)
        response.setdefault("Permissions-Policy", PERMISSIONS)
        return response


def client_ip(request):
    """Adresse du visiteur. Derrière le proxy, la dernière adresse de la liste est celle qu'il a vue (la première peut être truquée)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")
