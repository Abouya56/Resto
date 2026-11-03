import unicodedata
from difflib import SequenceMatcher

SIMILARITY = 0.6  # en dessous, deux noms ne se ressemblent pas assez pour être proposés


def normalize(text):
    """Minuscules, sans accents ni ponctuation : « Café  DU Coin » et « cafe du coin » sont identiques."""
    text = unicodedata.normalize("NFKD", (text or "").casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def _similarity(query, name):
    """Meilleure ressemblance entre la recherche et le nom entier ou l'un de ses mots."""
    candidates = [name, *name.split()]
    return max(SequenceMatcher(None, query, candidate).ratio() for candidate in candidates)


def _same_place(city, restaurant):
    """« Bobo Dioulasso » trouve un restaurant de « Bobo », et « Bobo » un restaurant de « Bobo Dioulasso »."""
    place = normalize(restaurant.city)
    return bool(place) and (city in place or place in city)


def search_restaurants(restaurants, query="", city=""):
    """Renvoie (résultats, propositions). Les résultats contiennent tous les mots cherchés,
    sans tenir compte de la casse ni des accents ; les propositions sont les noms qui y ressemblent."""
    restaurants = list(restaurants)
    query, city = normalize(query), normalize(city)
    if city:
        restaurants = [r for r in restaurants if _same_place(city, r)]
    if not query:
        return restaurants, []
    words = query.split()
    results, others = [], []
    for restaurant in restaurants:
        name = normalize(restaurant.name)
        if all(word in name for word in words):
            results.append(restaurant)
        else:
            others.append((_similarity(query, name), restaurant))
    suggestions = [r for score, r in sorted(others, key=lambda pair: -pair[0]) if score >= SIMILARITY][:4]
    return results, suggestions
