from datetime import date, timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.core.daterange import get_date_range, preset_bounds


def drange(query, default=None):
    return get_date_range(RequestFactory().get("/", query), default=default)


class DateRangeParsingTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()

    def test_presets(self):
        self.assertEqual(
            (drange({"periode": "aujourdhui"}).start, drange({"periode": "aujourdhui"}).end), (self.today,) * 2
        )
        yesterday = self.today - timedelta(days=1)
        self.assertEqual(drange({"periode": "hier"}).start, yesterday)
        week = drange({"periode": "7j"})
        self.assertEqual((week.start, week.end), (self.today - timedelta(days=6), self.today))
        month = drange({"periode": "mois"})
        self.assertEqual((month.start, month.end), (self.today.replace(day=1), self.today))
        last = drange({"periode": "mois-dernier"})
        self.assertEqual(last.end, self.today.replace(day=1) - timedelta(days=1))
        self.assertEqual(last.start.day, 1)
        self.assertEqual(drange({"periode": "hier"}).label, "Hier")

    def test_one_day_and_custom_range(self):
        one = drange({"jour": "2026-10-09"})
        self.assertEqual((one.start, one.end, one.key), (date(2026, 10, 9), date(2026, 10, 9), "jour"))
        self.assertTrue(one.is_single_day)
        self.assertIn("9 octobre", one.label)
        both = drange({"du": "2026-10-03", "au": "2026-10-09"})
        self.assertEqual((both.start, both.end, both.key), (date(2026, 10, 3), date(2026, 10, 9), "perso"))
        self.assertEqual(both.label, "Du 3 au 9 octobre")
        swapped = drange({"du": "2026-10-09", "au": "2026-10-03"})
        self.assertEqual(
            (swapped.start, swapped.end), (date(2026, 10, 3), date(2026, 10, 9))
        )  # dates à l'envers : corrigées
        self.assertEqual(drange({"du": "2026-10-03"}).end, self.today)  # « depuis le … »
        only_end = drange({"au": "2026-10-03"})
        self.assertEqual((only_end.start, only_end.end), (date(2026, 10, 3),) * 2)

    def test_defaults_legacy_and_garbage(self):
        self.assertFalse(drange({}).active)
        self.assertEqual(drange({}, default="aujourdhui").start, self.today)
        self.assertEqual(drange({"period": "week"}).key, "7j")  # ancienne adresse du tableau de bord
        self.assertFalse(drange({"jour": "n-importe-quoi", "du": "x", "au": "2026-13-45"}).active)
        self.assertFalse(drange({"periode": "inconnu"}).active)

    def test_other_page_settings_are_kept(self):
        dr = drange({"vue": "toutes", "q": "awa", "jour": "2026-10-09", "page": "3"})
        self.assertEqual(sorted(dr.keep), [("q", "awa"), ("vue", "toutes")])  # ni dates ni page
        self.assertEqual(dr.params, [("jour", "2026-10-09")])
        self.assertEqual(
            drange({"du": "2026-10-03", "au": "2026-10-09"}).params, [("du", "2026-10-03"), ("au", "2026-10-09")]
        )
        self.assertEqual(drange({"periode": "hier"}).params, [("periode", "hier")])

    def test_preset_bounds_handles_january(self):
        self.assertEqual(preset_bounds("mois-dernier", date(2027, 1, 15)), (date(2026, 12, 1), date(2026, 12, 31)))
