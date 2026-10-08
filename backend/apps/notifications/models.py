from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=400)
    notif_type = models.CharField(max_length=30, default="info")
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        verbose_name = "notification"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
