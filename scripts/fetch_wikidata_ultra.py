#!/usr/bin/env python3
"""
Script de récupération ULTRA MASSIVE des œuvres d'art depuis Wikidata
Version "Big Data Totale" - Vise 1M+ avec couverture maximale
Stratégies multiples : artistes, mouvements, musées, genres, pays, siècles
"""

from SPARQLWrapper import SPARQLWrapper, JSON
import pandas as pd
import json
from datetime import datetime
import os
import time
import sys
import random
from collections import Counter

# Configuration
ENDPOINT_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "MuseumWikiBot/3.0 (https://github.com/alexandrebrief/museumwiki) - Ultra Massive"
CACHE_FILE = "data/fetch_cache.json"

# ============================================
# LISTES ÉLARGIES POUR COUVERTURE MAXIMALE
# ============================================

# 50+ MOUVEMENTS ARTISTIQUES
MOUVEMENTS_MAJEURS = {
    # Renaissance et Pré-renaissance
    "Gothique": "Q41183",
    "Renaissance": "Q4692",
    "Renaissance italienne": "Q134781",
    "Renaissance flamande": "Q1349336",
    "Maniérisme": "Q131682",
    
    # Baroque et Classique
    "Baroque": "Q37853",
    "Baroque flamand": "Q2365280",
    "Baroque hollandais": "Q2365282",
    "Classicisme": "Q131492",
    "Rococo": "Q147193",
    "Néoclassicisme": "Q131087",
    
    # Romantisme et Réalisme
    "Romantisme": "Q37068",
    "Romantisme allemand": "Q749031",
    "Romantisme français": "Q3441585",
    "Préraphaélisme": "Q213880",
    "Réalisme": "Q181991",
    "Naturalisme": "Q1092855",
    "Académisme": "Q218589",
    
    # Impressionnisme et Post
    "Impressionnisme": "Q40415",
    "Post-impressionnisme": "Q203934",
    "Pointillisme": "Q241615",
    "Nabi": "Q927072",
    "Les Nabis": "Q845535",
    "Synthétisme": "Q1633805",
    "Cloisonnisme": "Q1101838",
    
    # Art Nouveau et Symbolisme
    "Art nouveau": "Q147843",
    "Jugendstil": "Q319142",
    "Sécession viennoise": "Q265502",
    "Symbolisme": "Q131833",
    "Arts & Crafts": "Q191989",
    
    # Modernes
    "Fauvisme": "Q165445",
    "Expressionnisme": "Q80113",
    "Expressionnisme abstrait": "Q178046",
    "Die Brücke": "Q157831",
    "Der Blaue Reiter": "Q156874",
    "Cubisme": "Q42934",
    "Cubisme analytique": "Q3007023",
    "Cubisme synthétique": "Q3007024",
    "Orphisme": "Q910657",
    "Futurisme": "Q131669",
    "Dadaïsme": "Q130895",
    "Surréalisme": "Q39423",
    "Constructivisme": "Q173661",
    "Suprématisme": "Q193678",
    "Bauhaus": "Q124354",
    "De Stijl": "Q190088",
    "Art déco": "Q173226",
    
    # Contemporains
    "Art abstrait": "Q128115",
    "Art informel": "Q705909",
    "Tachisme": "Q1126140",
    "Cobra": "Q662704",
    "Pop art": "Q134157",
    "Nouveau réalisme": "Q748407",
    "Fluxus": "Q203353",
    "Art conceptuel": "Q193267",
    "Minimalisme": "Q184686",
    "Arte Povera": "Q708196",
    "Land art": "Q214408",
    "Body art": "Q464373",
    "Performance art": "Q175748",
    "Installation artistique": "Q209912",
    "Art vidéo": "Q460450",
    "Art numérique": "Q231365",
    "Street art": "Q17515",
    "Graffiti": "Q17515",
    "Hyperréalisme": "Q208130",
    "Photoréalisme": "Q1389422"
}

# 100+ MUSÉES MAJEURS
MUSEES_MAJEURS = {
    "Louvre": "Q19675",
    "Musée d'Orsay": "Q23402",
    "Centre Pompidou": "Q178065",
    "Metropolitan Museum of Art": "Q160236",
    "MoMA": "Q188740",
    "Guggenheim": "Q182301",
    "National Gallery London": "Q180788",
    "Tate Modern": "Q193375",
    "British Museum": "Q6373",
    "Victoria and Albert Museum": "Q213322",
    "Hermitage": "Q132783",
    "Pouchkine": "Q487831",
    "Rijksmuseum": "Q190804",
    "Van Gogh Museum": "Q224124",
    "Mauritshuis": "Q1472219",
    "Prado": "Q160112",
    "Reina Sofia": "Q460889",
    "Thyssen": "Q1763889",
    "Uffizi": "Q51252",
    "Académie Florence": "Q1054865",
    "Vatican Museums": "Q182955",
    "Borghese": "Q840481",
    "Brera": "Q652568",
    "Albertina": "Q371595",
    "Kunsthistorisches": "Q95569",
    "Belvédère": "Q478717",
    "Alte Pinakothek": "Q154568",
    "Neue Pinakothek": "Q254322",
    "Pinakothek der Moderne": "Q45563",
    "Gemäldegalerie Berlin": "Q165631",
    "Hamburger Bahnhof": "Q565744",
    "Kunsthaus Zurich": "Q685833",
    "Kunstmuseum Basel": "Q194626",
    "Fondation Beyeler": "Q688574",
    "Art Institute Chicago": "Q239303",
    "MFA Boston": "Q49133",
    "Philadelphia Museum": "Q510324",
    "SFMOMA": "Q658277",
    "LACMA": "Q1641836",
    "National Gallery of Art DC": "Q214867",
    "Hirshhorn": "Q1371428",
    "Phillips Collection": "Q678618",
    "Getty Center": "Q29247",
    "Norton Simon": "Q648155",
    "National Portrait Gallery London": "Q238587",
    "National Portrait Gallery DC": "Q1968685",
    "Smithsonian American Art": "Q1192305",
    "Whitney": "Q639791",
    "Morgan Library": "Q1473422",
    "Frick Collection": "Q922109",
    "Courtauld Gallery": "Q1137682",
    "Wallace Collection": "Q1325889",
    "Dulwich Picture Gallery": "Q1241163",
    "Royal Academy": "Q270920",
    "Scottish National Gallery": "Q936478",
    "National Gallery of Ireland": "Q2018379",
    "National Museum of Wales": "Q691802",
    "Museu Nacional d'Art de Catalunya": "Q861252",
    "Thyssen-Bornemisza": "Q1763889",
    "Galleria Nazionale d'Arte Moderna": "Q764842",
    "Museo di Capodimonte": "Q1638549",
    "Museo Correr": "Q1476574",
    "Ca' Rezzonico": "Q2262260",
    "Accademia Carrara": "Q732119",
    "Museo Poldi Pezzoli": "Q1519019",
    "Museo Bagatti Valsecchi": "Q3867803",
    "Museo Nazionale Romano": "Q977385",
    "Musei Capitolini": "Q333031",
    "Museo Archeologico Napoli": "Q637248",
    "Museo Egizio": "Q630610",
    "Bode Museum": "Q157415",
    "Pergamonmuseum": "Q157298",
    "Neues Museum": "Q157109",
    "Altes Museum": "Q156722",
    "Staatliche Museen zu Berlin": "Q700216",
    "Grünes Gewölbe": "Q264320",
    "Gemäldegalerie Alte Meister": "Q478625",
    "Kunstsammlung Nordrhein-Westfalen": "Q701647",
    "Museum Ludwig": "Q704751",
    "Wallraf-Richartz-Museum": "Q700641",
    "Städel Museum": "Q163804",
    "Schirn Kunsthalle": "Q881418",
    "Kunsthalle Hamburg": "Q153801",
    "Kunsthalle Bremen": "Q564912",
    "Museum Folkwang": "Q152188",
    "Stuttgart State Gallery": "Q315947",
    "Lenbachhaus": "Q265639",
    "Brandhorst Museum": "Q826551",
    "Museum Brandhorst": "Q826551"
}

# GENRES ARTISTIQUES
GENRES_ARTISTIQUES = {
    "Portrait": "Q134307",
    "Autoportrait": "Q192110",
    "Paysage": "Q191163",
    "Marine": "Q192485",
    "Nature morte": "Q170571",
    "Scène de genre": "Q1047779",
    "Peinture d'histoire": "Q1564655",
    "Peinture religieuse": "Q1749758",
    "Peinture mythologique": "Q2168332",
    "Nu": "Q2099160",
    "Allégorie": "Q185932",
    "Scène de bataille": "Q745920",
    "Scène de chasse": "Q1757808",
    "Scène de rue": "Q19835157",
    "Intérieur": "Q1976748",
    "Veduta": "Q1065293",
    "Capriccio": "Q1035171",
    "Trompe-l'œil": "Q216830",
    "Vanité": "Q6497547",
    "Animalier": "Q2346578",
    "Floral": "Q10861797",
    "Abstrait": "Q128115",
    "Figuratif": "Q1130696",
    "Cubiste": "Q42934",
    "Surréaliste": "Q39423"
}

# PAYS (pour couverture géographique)
PAYS_MAJEURS = {
    "France": "Q142",
    "Italie": "Q38",
    "Espagne": "Q29",
    "Allemagne": "Q183",
    "Pays-Bas": "Q55",
    "Belgique": "Q31",
    "Royaume-Uni": "Q145",
    "États-Unis": "Q30",
    "Mexique": "Q96",
    "Canada": "Q16",
    "Brésil": "Q155",
    "Argentine": "Q414",
    "Chili": "Q298",
    "Pérou": "Q419",
    "Japon": "Q17",
    "Chine": "Q148",
    "Corée": "Q884",
    "Inde": "Q668",
    "Russie": "Q159",
    "Pologne": "Q36",
    "République tchèque": "Q213",
    "Hongrie": "Q28",
    "Autriche": "Q40",
    "Suisse": "Q39",
    "Suède": "Q34",
    "Norvège": "Q20",
    "Danemark": "Q35",
    "Finlande": "Q33",
    "Grèce": "Q41",
    "Portugal": "Q45"
}

# ============================================
# REQUÊTES SPÉCIALISÉES
# ============================================

def get_artists_by_country(country_id, limit=500):
    """Récupère les artistes d'un pays"""
    return f"""
    SELECT DISTINCT ?artiste ?artisteLabel (COUNT(?œuvre) AS ?count)
    WHERE {{
      ?artiste wdt:P31 wd:Q5.
      ?artiste wdt:P27 wd:{country_id}.
      ?œuvre wdt:P170 ?artiste.
      ?œuvre wdt:P31/wdt:P279* wd:Q3305213.
    }}
    GROUP BY ?artiste ?artisteLabel
    ORDER BY DESC(?count)
    LIMIT {limit}
    """

def get_artworks_by_museum(museum_id, limit=5000):
    """Récupère les œuvres d'un musée"""
    return f"""
    SELECT DISTINCT ?œuvre ?œuvreLabel ?createur ?createurLabel ?date ?image ?mouvement ?mouvementLabel
    WHERE {{
      ?œuvre wdt:P31/wdt:P279* wd:Q3305213.
      ?œuvre wdt:P276 wd:{museum_id}.
      OPTIONAL {{ ?œuvre wdt:P170 ?createur. }}
      OPTIONAL {{ ?œuvre wdt:P571 ?date. }}
      OPTIONAL {{ ?œuvre wdt:P18 ?image. }}
      OPTIONAL {{ ?œuvre wdt:P135 ?mouvement. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
    }}
    LIMIT {limit}
    """

def get_artworks_by_genre(genre_id, limit=2000):
    """Récupère les œuvres d'un genre"""
    return f"""
    SELECT DISTINCT ?œuvre ?œuvreLabel ?createur ?createurLabel ?date ?image ?lieu ?lieuLabel
    WHERE {{
      ?œuvre wdt:P31/wdt:P279* wd:Q3305213.
      ?œuvre wdt:P136 wd:{genre_id}.
      OPTIONAL {{ ?œuvre wdt:P170 ?createur. }}
      OPTIONAL {{ ?œuvre wdt:P571 ?date. }}
      OPTIONAL {{ ?œuvre wdt:P18 ?image. }}
      OPTIONAL {{ ?œuvre wdt:P276 ?lieu. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
    }}
    LIMIT {limit}
    """

def get_artworks_by_century(century, limit=10000):
    """Récupère les œuvres d'un siècle (ex: 19)"""
    start_year = (century - 1) * 100
    end_year = century * 100
    return f"""
    SELECT DISTINCT ?œuvre ?œuvreLabel ?createur ?createurLabel ?date ?image ?lieu ?lieuLabel
    WHERE {{
      ?œuvre wdt:P31/wdt:P279* wd:Q3305213.
      ?œuvre wdt:P571 ?date.
      FILTER(YEAR(?date) >= {start_year} && YEAR(?date) < {end_year})
      OPTIONAL {{ ?œuvre wdt:P170 ?createur. }}
      OPTIONAL {{ ?œuvre wdt:P18 ?image. }}
      OPTIONAL {{ ?œuvre wdt:P276 ?lieu. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
    }}
    LIMIT {limit}
    """

def get_top_artists_global(offset=0, limit=1000):
    """Récupère les TOP artistes mondiaux"""
    return f"""
    SELECT ?artiste ?artisteLabel (COUNT(?œuvre) AS ?count)
    WHERE {{
      ?œuvre wdt:P31/wdt:P279* wd:Q3305213.
      ?œuvre wdt:P170 ?artiste.
    }}
    GROUP BY ?artiste ?artisteLabel
    ORDER BY DESC(?count)
    LIMIT {limit} OFFSET {offset}
    """

# ============================================
# CLASSE PRINCIPALE DE RÉCUPÉRATION
# ============================================

class WikidataMassiveFetcher:
    def __init__(self, target=1_500_000):
        self.target = target
        self.all_artworks = []
        self.seen_ids = set()
        self.stats = Counter()
        self.sparql = SPARQLWrapper(ENDPOINT_URL)
        self.sparql.setReturnFormat(JSON)
        self.sparql.addCustomParameter("User-Agent", USER_AGENT)
        
        # Charger cache si existe
        self.load_cache()
        
    def load_cache(self):
        """Charge les IDs déjà récupérés"""
        os.makedirs("data", exist_ok=True)
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r') as f:
                    cache = json.load(f)
                    self.seen_ids = set(cache.get('ids', []))
                    print(f"📦 Cache chargé: {len(self.seen_ids)} IDs existants")
            except:
                print("⚠️ Cache corrompu, nouveau départ")
                
    def save_cache(self):
        """Sauvegarde les IDs récupérés"""
        cache = {'ids': list(self.seen_ids)[-100000:]}  # Garder les 100k derniers
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    
    def fetch_with_retry(self, query, retries=3):
        """Exécute une requête avec retry"""
        for attempt in range(retries):
            try:
                self.sparql.setQuery(query)
                results = self.sparql.query().convert()
                time.sleep(random.uniform(0.3, 0.8))
                return results
            except Exception as e:
                print(f"   ⚠️ Tentative {attempt+1}/{retries} échouée: {e}")
                time.sleep(5 * (attempt + 1))
        return None
    
    def add_artworks(self, artworks_data, source=""):
        """Ajoute des œuvres en évitant les doublons"""
        new_count = 0
        for result in artworks_data:
            oeuvre_id = result.get("œuvre", {}).get("value", "").split("/")[-1]
            
            if oeuvre_id and oeuvre_id not in self.seen_ids:
                self.seen_ids.add(oeuvre_id)
                
                createur = result.get("createurLabel", {}).get("value", "Inconnu")
                createur_id = result.get("createur", {}).get("value", "").split("/")[-1] if result.get("createur") else ""
                
                oeuvre = {
                    "id": oeuvre_id,
                    "titre": result.get("œuvreLabel", {}).get("value", "Titre inconnu"),
                    "createur": createur,
                    "createur_id": createur_id,
                    "date": result.get("date", {}).get("value", "")[:10],
                    "image_url": result.get("image", {}).get("value", ""),
                    "lieu": result.get("lieuLabel", {}).get("value", "Inconnu"),
                    "genre": result.get("genreLabel", {}).get("value", ""),
                    "mouvement": result.get("mouvementLabel", {}).get("value", ""),
                    "wikidata_url": result.get("œuvre", {}).get("value", "")
                }
                self.all_artworks.append(oeuvre)
                new_count += 1
                
        self.stats[source] += new_count
        return new_count
    
    def phase_1_top_artists(self):
        """Phase 1: TOP 5000 artistes mondiaux"""
        print("\n" + "="*80)
        print("📊 PHASE 1: TOP 5000 ARTISTES MONDIAUX")
        print("="*80)
        
        total_new = 0
        for offset in range(0, 5000, 100):
            if len(self.all_artworks) >= self.target:
                break
                
            print(f"\n🔍 Lot artistes {offset+1}-{offset+100}...")
            query = get_top_artists_global(offset=offset, limit=100)
            results = self.fetch_with_retry(query)
            
            if not results or 'results' not in results:
                continue
                
            artists = []
            for result in results['results']['bindings']:
                artist_id = result.get('artiste', {}).get('value', '').split('/')[-1]
                artist_name = result.get('artisteLabel', {}).get('value', 'Inconnu')
                count = int(result.get('count', {}).get('value', 0))
                artists.append((artist_id, artist_name, min(count, 300)))
            
            for artist_id, artist_name, limit in artists:
                if len(self.all_artworks) >= self.target:
                    break
                    
                print(f"   🎨 {artist_name} (max {limit})...")
                query = f"""
                SELECT DISTINCT ?œuvre ?œuvreLabel ?date ?image ?lieu ?lieuLabel ?genre ?genreLabel ?mouvement ?mouvementLabel
                WHERE {{
                  ?œuvre wdt:P31/wdt:P279* wd:Q3305213.
                  ?œuvre wdt:P170 wd:{artist_id}.
                  OPTIONAL {{ ?œuvre wdt:P571 ?date. }}
                  OPTIONAL {{ ?œuvre wdt:P18 ?image. }}
                  OPTIONAL {{ ?œuvre wdt:P276 ?lieu. }}
                  OPTIONAL {{ ?œuvre wdt:P136 ?genre. }}
                  OPTIONAL {{ ?œuvre wdt:P135 ?mouvement. }}
                  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
                }}
                LIMIT {limit}
                """
                
                artworks_data = self.fetch_with_retry(query)
                if artworks_data and 'results' in artworks_data:
                    new = self.add_artworks(artworks_data['results']['bindings'], f"artist_{artist_id}")
                    total_new += new
                    print(f"      ✅ +{new} (total: {len(self.all_artworks):,})")
                    
    def phase_2_museums(self):
        """Phase 2: Musées"""
        print("\n" + "="*80)
        print("📊 PHASE 2: MUSÉES ({:,})".format(len(MUSEES_MAJEURS)))
        print("="*80)
        
        for museum_name, museum_id in MUSEES_MAJEURS.items():
            if len(self.all_artworks) >= self.target:
                break
                
            print(f"\n🏛️  Musée: {museum_name}...")
            query = get_artworks_by_museum(museum_id, limit=3000)
            results = self.fetch_with_retry(query)
            
            if results and 'results' in results:
                new = self.add_artworks(results['results']['bindings'], f"museum_{museum_id}")
                print(f"   ✅ +{new} œuvres")
    
    def phase_3_movements(self):
        """Phase 3: Mouvements"""
        print("\n" + "="*80)
        print("📊 PHASE 3: MOUVEMENTS ({:,})".format(len(MOUVEMENTS_MAJEURS)))
        print("="*80)
        
        for movement_name, movement_id in MOUVEMENTS_MAJEURS.items():
            if len(self.all_artworks) >= self.target:
                break
                
            print(f"\n🎭 Mouvement: {movement_name}...")
            query = f"""
            SELECT DISTINCT ?œuvre ?œuvreLabel ?createur ?createurLabel ?date ?image ?lieu ?lieuLabel
            WHERE {{
              ?œuvre wdt:P31/wdt:P279* wd:Q3305213.
              ?œuvre wdt:P135 wd:{movement_id}.
              OPTIONAL {{ ?œuvre wdt:P170 ?createur. }}
              OPTIONAL {{ ?œuvre wdt:P571 ?date. }}
              OPTIONAL {{ ?œuvre wdt:P18 ?image. }}
              OPTIONAL {{ ?œuvre wdt:P276 ?lieu. }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
            }}
            LIMIT 3000
            """
            
            results = self.fetch_with_retry(query)
            if results and 'results' in results:
                new = self.add_artworks(results['results']['bindings'], f"movement_{movement_id}")
                print(f"   ✅ +{new} œuvres")
    
    def phase_4_genres(self):
        """Phase 4: Genres artistiques"""
        print("\n" + "="*80)
        print("📊 PHASE 4: GENRES ({:,})".format(len(GENRES_ARTISTIQUES)))
        print("="*80)
        
        for genre_name, genre_id in GENRES_ARTISTIQUES.items():
            if len(self.all_artworks) >= self.target:
                break
                
            print(f"\n🎨 Genre: {genre_name}...")
            query = get_artworks_by_genre(genre_id, limit=2000)
            results = self.fetch_with_retry(query)
            
            if results and 'results' in results:
                new = self.add_artworks(results['results']['bindings'], f"genre_{genre_id}")
                print(f"   ✅ +{new} œuvres")
    
    def phase_5_countries(self):
        """Phase 5: Pays"""
        print("\n" + "="*80)
        print("📊 PHASE 5: PAYS ({:,})".format(len(PAYS_MAJEURS)))
        print("="*80)
        
        for country_name, country_id in PAYS_MAJEURS.items():
            if len(self.all_artworks) >= self.target:
                break
                
            print(f"\n🌍 Pays: {country_name}...")
            
            # D'abord récupérer les artistes du pays
            query = get_artists_by_country(country_id, limit=200)
            results = self.fetch_with_retry(query)
            
            if results and 'results' in results:
                for result in results['results']['bindings'][:50]:  # Top 50 artistes
                    artist_id = result.get('artiste', {}).get('value', '').split('/')[-1]
                    artist_name = result.get('artisteLabel', {}).get('value', 'Inconnu')
                    
                    if len(self.all_artworks) >= self.target:
                        break
                        
                    print(f"   🎨 {artist_name}...")
                    query_art = f"""
                    SELECT DISTINCT ?œuvre ?œuvreLabel ?date ?image ?lieu ?lieuLabel ?mouvement ?mouvementLabel
                    WHERE {{
                      ?œuvre wdt:P31/wdt:P279* wd:Q3305213.
                      ?œuvre wdt:P170 wd:{artist_id}.
                      OPTIONAL {{ ?œuvre wdt:P571 ?date. }}
                      OPTIONAL {{ ?œuvre wdt:P18 ?image. }}
                      OPTIONAL {{ ?œuvre wdt:P276 ?lieu. }}
                      OPTIONAL {{ ?œuvre wdt:P135 ?mouvement. }}
                      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
                    }}
                    LIMIT 200
                    """
                    
                    art_results = self.fetch_with_retry(query_art)
                    if art_results and 'results' in art_results:
                        new = self.add_artworks(art_results['results']['bindings'], f"country_{country_id}")
                        if new > 0:
                            print(f"      ✅ +{new}")
    
    def phase_6_centuries(self):
        """Phase 6: Siècles (du 14e au 21e)"""
        print("\n" + "="*80)
        print("📊 PHASE 6: SIÈCLES (14e - 21e)")
        print("="*80)
        
        for century in range(14, 22):
            if len(self.all_artworks) >= self.target:
                break
                
            print(f"\n📅 Siècle: {century}e...")
            query = get_artworks_by_century(century, limit=15000)
            results = self.fetch_with_retry(query)
            
            if results and 'results' in results:
                new = self.add_artworks(results['results']['bindings'], f"century_{century}")
                print(f"   ✅ +{new} œuvres")
    
    def run(self):
        """Exécute toutes les phases"""
        print("="*80)
        print("🚀 LANCEMENT RÉCUPÉRATION ULTRA MASSIVE")
        print(f"🎯 Objectif: {self.target:,} œuvres")
        print("="*80)
        
        start_time = time.time()
        
        phases = [
            self.phase_1_top_artists,
            self.phase_2_museums,
            self.phase_3_movements,
            self.phase_4_genres,
            self.phase_5_countries,
            self.phase_6_centuries
        ]
        
        for phase in phases:
            if len(self.all_artworks) >= self.target:
                break
            phase()
            self.save_cache()
            
            # Stats intermédiaires
            elapsed = time.time() - start_time
            print(f"\n📊 Stats après {len(self.all_artworks):,} œuvres")
            print(f"⏱️  Temps écoulé: {elapsed/3600:.1f} heures")
            print(f"📈 Vitesse: {len(self.all_artworks)/elapsed:.1f} œuvres/sec")
        
        return self.all_artworks

# ============================================
# SAUVEGARDE FINALE
# ============================================

def save_final_data(artworks, fetcher):
    """Sauvegarde finale avec stats détaillées"""
    
    os.makedirs("data", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print("\n" + "="*80)
    print("💾 SAUVEGARDE FINALE")
    print("="*80)
    
    # Créer DataFrame
    df = pd.DataFrame(artworks)
    
    # Stats globales
    print(f"\n📊 STATISTIQUES GLOBALES:")
    print(f"   Total œuvres: {len(df):,}")
    print(f"   Artistes uniques: {df['createur'].nunique():,}")
    print(f"   Musées uniques: {df['lieu'].nunique():,}")
    print(f"   Mouvements: {df['mouvement'].nunique():,}")
    print(f"   Genres: {df['genre'].nunique():,}")
    
    # Stats images
    avec_image = len(df[df['image_url'] != ''])
    print(f"   Avec image: {avec_image:,} ({avec_image/len(df)*100:.1f}%)")
    
    # Top artistes
    print("\n🏆 TOP 50 ARTISTES:")
    top_artists = df['createur'].value_counts().head(50)
    for artist, count in top_artists.items():
        print(f"   {artist}: {count:,} œuvres")
    
    # Top musées
    print("\n🏛️  TOP 30 MUSÉES:")
    top_museums = df['lieu'].value_counts().head(30)
    for museum, count in top_museums.items():
        print(f"   {museum}: {count:,} œuvres")
    
    # Sauvegarde CSV
    print("\n💾 Sauvegarde des fichiers...")
    csv_file = f"data/artworks_ultra_{timestamp}.csv"
    df.to_csv(csv_file, index=False, encoding='utf-8')
    print(f"   ✅ CSV: {csv_file}")
    
    # Sauvegarde JSON (échantillon)
    sample = df.head(100000).to_dict('records')
    json_file = f"data/artworks_sample_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    print(f"   ✅ JSON (échantillon): {json_file}")
    
    # Copie principale
    latest_file = "../data/artworks_latest.csv"
    df.to_csv(latest_file, index=False, encoding='utf-8')
    print(f"   ✅ Fichier principal: {latest_file}")
    
    # Rapport
    report = {
        'timestamp': timestamp,
        'total': len(df),
        'artists': int(df['createur'].nunique()),
        'museums': int(df['lieu'].nunique()),
        'movements': int(df['mouvement'].nunique()),
        'with_images': int(avec_image),
        'sources': dict(fetcher.stats)
    }
    
    report_file = f"data/report_{timestamp}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f"   ✅ Rapport: {report_file}")
    
    return csv_file

# ============================================
# MAIN
# ============================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Récupération ULTRA massive d\'œuvres')
    parser.add_argument('--target', type=int, default=1_500_000, 
                       help='Nombre d\'œuvres cible (défaut: 1.5M)')
    parser.add_argument('--resume', action='store_true',
                       help='Reprendre depuis le cache')
    args = parser.parse_args()
    
    # Créer le fetcher
    fetcher = WikidataMassiveFetcher(target=args.target)
    
    # Lancer la récupération
    artworks = fetcher.run()
    
    # Sauvegarder
    if artworks:
        save_final_data(artworks, fetcher)
        print("\n" + "="*80)
        print("✨ MISSION ACCOMPLIE !")
        print(f"📊 Total final: {len(artworks):,} œuvres")
        print("="*80)
    else:
        print("\n❌ Aucune donnée récupérée")

if __name__ == "__main__":
    main()
