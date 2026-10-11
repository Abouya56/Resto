from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateFileSystemStorage(FileSystemStorage):
    """Stockage hors de MEDIA_ROOT : aucun fichier n'a d'URL publique, il faut passer par une vue protégée."""

    def url(self, name):
        raise ValueError("Ce fichier est privé : il n'a pas d'URL publique.")


def private_storage():
    return PrivateFileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)
