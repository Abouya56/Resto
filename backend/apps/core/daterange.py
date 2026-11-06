"""Filtre par date commun aux pages du gérant : raccourcis, ou un seul choix — un jour, un mois ou une année."""

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
# « du / au » n'est plus proposé à l'écran, mais les anciennes adresses marchent encore.
DATE_KEYS = ("periode", "period", "jour", "mois", "annee", "df_mode", "du", "au", "page")
YEARS_SHOWN = 6  # années proposées dans le choix « Une année »


@dataclass
class DateRange:
    start: date | None = None
    end: date | None = None
    key: str = ""  # « aujourdhui », « hier »… ou « jour », « mois_choisi », « annee », « perso » (choisis à la main)
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
        if self.key == "mois_choisi":
            return [("mois", self.start.strftime("%Y-%m"))]
        if self.key == "annee":
            return [("annee", str(self.start.year))]
        if self.key == "perso":
            return [("du", self.start.isoformat()), ("au", self.end.isoformat())]
        return [("periode", self.key)] if self.key else []

    @property
    def mode(self):
        """Ce que montre le choix à la main : « jour », « mois » ou « annee »."""
        return {"mois_choisi": "mois", "annee": "annee"}.get(self.key, "jour")

    @property
    def year_choices(self):
        this_year = timezone.localdate().year
        return list(range(this_year, this_year - YEARS_SHOWN, -1))

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


def parse_month(value):
    """« 2026-11 » → 1er novembre 2026 (ou None)."""
    try:
        year, month = (int(part) for part in (value or "").strip().split("-"))
        return date(year, month, 1)
    except ValueError:
        return None


def parse_year(value):
    value = (value or "").strip()
    return int(value) if value.isdigit() and 2000 <= int(value) <= 2100 else None


def month_end(first_day):
    return (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)


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
    if key == "mois_choisi":
        return date_format(start, "F Y").capitalize()
    if key == "annee":
        return f"Année {start.year}"
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
    mois = parse_month(params.get("mois"))
    annee = parse_year(params.get("annee"))
    du, au = parse_date(params.get("du")), parse_date(params.get("au"))
    preset = params.get("periode") or LEGACY.get(params.get("period", ""), "")
    if jour:
        start = end = jour
        key = "jour"
    elif mois:
        start, end = mois, max(mois, min(month_end(mois), today))  # le mois en cours s'arrête à aujourd'hui
        key = "mois_choisi"
    elif annee:
        start = date(annee, 1, 1)
        end = max(start, min(date(annee, 12, 31), today))
        key = "annee"
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
