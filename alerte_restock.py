"""
Alerte restock Pokémon
----------------------
Surveille des pages produits et t'envoie une notif Telegram quand un produit
repasse en stock (et sous ton prix max). Le script n'achète RIEN : il te
prévient, et c'est toi qui achètes.

Deux façons de le lancer :
- Sur GitHub Actions (iPhone OK) : python alerte_restock.py --une-fois
  -> fait un seul tour, GitHub le relance automatiquement.
- Sur un PC                     : python alerte_restock.py  (tourne en boucle)
Test sans notif                 : python alerte_restock.py --test
"""
import json
import os
import random
import sys
import time

import requests
from bs4 import BeautifulSoup

# Sur GitHub, le token et le chat_id viennent des "Secrets" (ne les écris pas ici).
# Sur PC, tu peux les coller à la place des textes entre guillemets.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "COLLE_TON_TOKEN_ICI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "COLLE_TON_CHAT_ID_ICI")

INTERVALLE_MIN = 5  # mode PC uniquement : minutes entre deux tours
FICHIER_ETAT = "etat.json"

# ---------- TES PRODUITS ----------
PRODUITS = [
    {
        "nom": "ETB Héros Transcendants - Cultura",
        "url": "https://www.cultura.com/p-coffret-dresseur-d-elite-pokemon-mega-evolution-heros-transcendants-12768528.html",
        "prix_max": 65.0,
    },
    # {"nom": "...", "url": "https://...", "prix_max": 65.0},
]
# ----------------------------------

MOTS_RUPTURE = [
    "rupture de stock", "indisponible", "épuisé", "bientôt disponible",
    "produit non disponible", "out of stock", "sold out", "currently unavailable",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def lire_offres(soup):
    """Récupère les offres (stock + prix) déclarées dans la page (JSON-LD)."""
    offres = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        pile = [data]
        while pile:
            obj = pile.pop()
            if isinstance(obj, list):
                pile.extend(obj)
                continue
            if not isinstance(obj, dict):
                continue
            if "@graph" in obj:
                pile.append(obj["@graph"])
            if "offers" in obj:
                pile.append(obj["offers"])
            if "availability" in obj or obj.get("@type") in ("Offer", "AggregateOffer"):
                offres.append(obj)
    return offres


def verifier(produit):
    """Retourne (disponible, prix, info) ; disponible = None en cas d'erreur."""
    try:
        r = requests.get(produit["url"], headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        return None, None, f"erreur réseau : {e}"
    if r.status_code != 200:
        return None, None, f"HTTP {r.status_code} (site qui bloque ? utilise Visualping pour lui)"

    soup = BeautifulSoup(r.text, "html.parser")
    dispo, prix = None, None
    for o in lire_offres(soup):
        a = str(o.get("availability", "")).lower()
        if any(x in a for x in ("instock", "limitedavailability", "preorder")):
            dispo = True
        elif a and dispo is None:
            dispo = False
        p = o.get("price", o.get("lowPrice"))
        try:
            p = float(str(p).replace(",", "."))
            prix = p if prix is None else min(prix, p)
        except (TypeError, ValueError):
            pass

    if dispo is not None:
        return dispo, prix, "données structurées"
    texte = soup.get_text(" ").lower()
    return not any(m in texte for m in MOTS_RUPTURE), prix, "texte de la page"


def notifier(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=15)
    except requests.RequestException as e:
        print(f"  Notif Telegram ratée : {e}")


def charger_etat():
    try:
        with open(FICHIER_ETAT, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def sauver_etat(etat):
    with open(FICHIER_ETAT, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False)


def un_tour(etat, mode_test=False):
    for produit in PRODUITS:
        dispo, prix, info = verifier(produit)
        prix_txt = f"{prix:.2f} €" if prix is not None else "prix ?"
        statut = "DISPO" if dispo else "rupture" if dispo is False else "??"
        print(f"[{time.strftime('%H:%M')}] {produit['nom']} -> {statut} | {prix_txt} | {info}")

        if not mode_test and dispo is not None:
            prix_ok = prix is None or prix <= produit["prix_max"]
            if dispo and prix_ok and not etat.get(produit["nom"]):
                notifier(f"🚨 DISPO : {produit['nom']}\nPrix : {prix_txt}\n{produit['url']}")
            etat[produit["nom"]] = bool(dispo and prix_ok)

        time.sleep(random.uniform(3, 8))  # espace les requêtes


def main():
    etat = charger_etat()
    if "--test" in sys.argv:
        un_tour(etat, mode_test=True)
    elif "--une-fois" in sys.argv:
        un_tour(etat)
        sauver_etat(etat)
    else:
        notifier(f"✅ Alerte restock lancée, je surveille {len(PRODUITS)} produit(s).")
        while True:
            un_tour(etat)
            sauver_etat(etat)
            time.sleep(INTERVALLE_MIN * 60 + random.uniform(0, 60))


if __name__ == "__main__":
    main()
