from urllib.parse import urlparse

from django.conf import settings

from apps.tables.models import DiningTable, QRCode

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1", "0.0.0.0", "[::1]")


def site_is_local(base=None):
    """L'adresse est 127.0.0.1 / localhost : un téléphone scannant le QR ne pourrait pas l'ouvrir."""
    host = urlparse(base or settings.SITE_URL).hostname or ""
    return host in LOOPBACK_HOSTS


def lan_ip():
    """L'adresse du PC sur le Wi-Fi (ex. 192.168.1.20), ou None."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))  # rien n'est envoyé : on lit juste la bonne interface
            ip = probe.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") else ip


def site_base_url(request=None):
    """L'adresse à écrire dans les QR codes.

    En production, c'est SITE_URL. En test sur un PC (SITE_URL en 127.0.0.1), on prend l'adresse par laquelle
    la page est ouverte si elle est joignable depuis un téléphone, sinon l'adresse du PC sur le Wi-Fi.
    """
    if not site_is_local() or request is None:
        return settings.SITE_URL
    host = request.get_host()
    if (host.rsplit(":", 1)[0] if not host.startswith("[") else host) not in LOOPBACK_HOSTS:
        return f"{request.scheme}://{host}"
    if settings.DEBUG:
        ip = lan_ip()
        if ip:
            return f"{request.scheme}://{ip}:{request.get_port()}"
    return settings.SITE_URL


def ensure_qrcode(table: DiningTable, base=None) -> QRCode:
    qrcode, created = QRCode.objects.get_or_create(table=table)
    if created or not qrcode.image:
        qrcode.generate_image(base)
        qrcode.save()
    elif qrcode.public_url != qrcode.build_url(base):
        qrcode.refresh_address(base)  # l'adresse du site a changé : même jeton, nouvelle adresse
    return qrcode


def regenerate_qrcode(table: DiningTable, base=None) -> QRCode:
    qrcode, _ = QRCode.objects.get_or_create(table=table)
    qrcode.regenerate(base)
    return qrcode
