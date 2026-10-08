from apps.tables.models import DiningTable, QRCode


def ensure_qrcode(table: DiningTable) -> QRCode:
    qrcode, created = QRCode.objects.get_or_create(table=table)
    if created or not qrcode.image:
        qrcode.generate_image()
        qrcode.save()
    return qrcode


def regenerate_qrcode(table: DiningTable) -> QRCode:
    qrcode, _ = QRCode.objects.get_or_create(table=table)
    qrcode.regenerate()
    return qrcode
