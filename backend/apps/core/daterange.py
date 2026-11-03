"""Filtre par date commun aux pages du gérant : raccourcis, un jour précis, ou une période « du … au … »."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone
from django.utils.formats import date_format

PRESETS = (
    ("aujourdhui", "Aujourd'hui"),
    ("hier", "Hier"),
    ("7j", "7 derniers jours"),
    ("mois", "Ce mois-ci"),
    ("mois-dernier", "Mois dernier"),
)
PRESET_LABELS = dict(PRESETS)
# Anciennes adresses du tableau de bord (?period=today|week|month) : elles continuent de marcher.
LEGACY = {"today": "aujourdhui", "week": "7j", "month": "mois"}
DATE_KEYS = ("periode", "period", "jour", "du", "au", "page")


@dataclass
class DateRange:
    start: date | None = None
    end: date | None = None
    key: str = ""  # « aujourdhui », « hier »… ou « jour » / « perso » pour une date choisie à la main
    label: str = "Toutes les dates"
    keep: list = field(default_factory=list)  # autres réglages de la page à conserver quand on change de date

    @property
    def active(self):
        return self.start is not None or self.end is not None

    @property
    def is_single_day(self):
        return self.start is not None and self.start == self.end

    @property
    def params(self):
        """Les dates actuelles sous forme de champs cachés, pour les autres formulaires de la page."""
        if self.key == "jour":
            return [("jour", self.start.isoformat())]
        if self.key == "perso":
            return [("du", self.start.isoformat()), ("au", self.end.isoformat())]
        return [("periode", self.key)] if self.key else []

    def contains_filter(self, field_name):
        """Filtre Django sur un champ date : {'created_at__date__gte': …, '…__lte': …}."""
        lookup = {}
        if self.start:
            lookup[f"{field_name}__gte"] = self.start
        if self.end:
            lookup[f"{field_name}__lte"] = self.end
        return lookup


def parse_date(value):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def preset_bounds(key, today=None):
    today = today or timezone.localdate()
    if key == "aujourdhui":
        return today, today
    if key == "hier":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if key == "7j":
        return today - timedelta(days=6), today
    if key == "mois":
        return today.replace(day=1), today
    if key == "mois-dernier":
        last_day = today.replace(day=1) - timedelta(days=1)
        return last_day.replace(day=1), last_day
    return None, None


def _short(day, today):
    return date_format(day, "j F" if day.year == today.year else "j F Y")


def describe(start, end, key, today):
    if key in PRESET_LABELS:
        return PRESET_LABELS[key]
    if start and end and start == end:
        return "Le " + date_format(start, "l ") + _short(start, today)
    if start and end:
        if start.year == end.year == today.year and start.month == end.month:
            return f"Du {start.day} au {_short(end, today)}"
        return f"Du {_short(start, today)} au {_short(end, today)}"
    return "Toutes les dates"


def get_date_range(request, default=None):
    """Lit ?jour=, ?du=&au= ou ?periode= dans l'adresse. `default` : raccourci appliqué si rien n'est demandé."""
    params = request.GET
    today = timezone.localdate()
    keep = [(name, value) for name in params for value in params.getlist(name) if name not in DATE_KEYS and value]

    jour = parse_date(params.get("jour"))
    du, au = parse_date(params.get("du")), parse_date(params.get("au"))
    preset = params.get("periode") or LEGACY.get(params.get("period", ""), "")
    if jour:
        start = end = jour
        key = "jour"
    elif du or au:
        start = du or au  # seulement « au » : on prend ce jour-là
        end = au or today  # seulement « du » : jusqu'à aujourd'hui
        if start > end:
            start, end = end, start
        key = "perso"
    elif preset in PRESET_LABELS:
        start, end = preset_bounds(preset, today)
        key = preset
    elif default:
        start, end = preset_bounds(default, today)
        key = default
    else:
        return DateRange(keep=keep)
    return DateRange(start=start, end=end, key=key, label=describe(start, end, key, today), keep=keep)
