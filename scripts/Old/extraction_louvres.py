#!/usr/bin/env python3
"""
Script d'extraction des œuvres du Louvre - VERSION TOUS CHAMPS OPTIMISÉE
"""

import time
import json
from datetime import datetime
from SPARQLWrapper import SPARQLWrapper, JSON

# ============================================
# CONFIGURATION ULTRA-OPTIMISÉE
# ============================================
USER_AGENT = "MuseumWikiBot/15.0 (https://github.com/alexandrebrief/museumwiki)"
ENDPOINT_URL = "https://query.wikidata.org/sparql"
MUSEE_ID = "Q19675"
MUSEE_NOM = "Musée du Louvre"
OUTPUT_FILE = "louvre_complet.json"

# Paramètres critiques
BATCH_SIZE = 3           # TOUT PETIT lot (3 œuvres)
TIMEOUT = 300            # Timeout client long
MAX_RETRIES = 10         # Beaucoup de tentatives
PAUSE_BETWEEN_LOTS = 10  # Pause longue pour respecter Wikidata

def get_sparql():
    sparql = SPARQLWrapper(ENDPOINT_URL)
    sparql.setReturnFormat(JSON)
    sparql.setTimeout(TIMEOUT)
    sparql.addCustomParameter("User-Agent", USER_AGENT)
    return sparql

def execute_query_with_retry(query, description="", max_retries=MAX_RETRIES):
    """Exécute une requête avec gestion intelligente des timeouts"""
    
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                print(f"  🔄 Tentative {attempt}/{max_retries}...")
            
            sparql = get_sparql()
            sparql.setQuery(query)
            results = sparql.query().convert()
            
            # Pause de courtoisie après succès
            time.sleep(2)
            return results
            
        except Exception as e:
            error_str = str(e)
            print(f"  ⚠️ Erreur: {error_str[:100]}")
            
            if "504" in error_str:
                # Timeout : pause exponentielle
                wait_time = attempt * 30  # 30s, 60s, 90s...
                print(f"  ⏳ Timeout 504, pause {wait_time}s...")
                time.sleep(wait_time)
            elif "429" in error_str:
                # Rate limit : pause longue
                wait_time = 60
                print(f"  ⏳ Rate limit, pause {wait_time}s...")
                time.sleep(wait_time)
            elif attempt < max_retries:
                # Autre erreur : pause progressive
                wait_time = attempt * 10
                print(f"  ⏳ Pause {wait_time}s...")
                time.sleep(wait_time)
    
    print(f"  ❌ Échec après {max_retries} tentatives")
    return None

def get_total_count():
    """Comptage avec hiérarchie"""
    query = f"""
    SELECT (COUNT(DISTINCT ?œuvre) AS ?count) WHERE {{
      hint:Query hint:optimizer "None".
      ?œuvre wdt:P195/wdt:P361* wd:{MUSEE_ID}.
    }}
    """
    results = execute_query_with_retry(query, "Comptage")
    if results and 'results' in results and results['results']['bindings']:
        return int(results['results']['bindings'][0]['count']['value'])
    return 0

def get_artworks_query(offset=0, limit=BATCH_SIZE):
    """
    VERSION COMPLÈTE - TOUS LES CHAMPS
    Mais avec optimisations SPARQL
    """
    return f"""
    SELECT DISTINCT 
           ?œuvre
           ?titre_fr ?titre_en
           ?image
           ?createur ?createurLabel
           ?date
           ?type ?typeLabel
           ?partie_de ?partie_deLabel
           ?collection ?collectionLabel
           ?lieu ?lieuLabel
           ?mouvement ?mouvementLabel
           ?technique
    WHERE {{
      hint:Query hint:optimizer "None".  # Désactive l'optimiseur automatique
      
      # Filtre le plus sélectif en premier
      ?œuvre wdt:P195/wdt:P361* wd:{MUSEE_ID}.
      
      # Service de labels (mais optimisé)
      SERVICE wikibase:label {{ 
        bd:serviceParam wikibase:language "fr,en". 
        ?œuvre rdfs:label ?titre.
        ?createur rdfs:label ?createurLabel.
        ?type rdfs:label ?typeLabel.
        ?partie_de rdfs:label ?partie_deLabel.
        ?collection rdfs:label ?collectionLabel.
        ?lieu rdfs:label ?lieuLabel.
        ?mouvement rdfs:label ?mouvementLabel.
      }}
      
      # Tous les OPTIONAL, mais ordonnés du plus probable au moins probable
      OPTIONAL {{ ?œuvre wdt:P31 ?type. }}
      OPTIONAL {{ ?œuvre wdt:P18 ?image. }}
      OPTIONAL {{ ?œuvre wdt:P170 ?createur. }}
      OPTIONAL {{ ?œuvre wdt:P571 ?date. }}
      OPTIONAL {{ ?œuvre wdt:P361 ?partie_de. }}
      OPTIONAL {{ ?œuvre wdt:P195 ?collection. }}
      OPTIONAL {{ ?œuvre wdt:P276 ?lieu. }}
      OPTIONAL {{ ?œuvre wdt:P135 ?mouvement. }}
      OPTIONAL {{ ?œuvre wdt:P2079 ?technique. }}
      
      # Titres spécifiques
      OPTIONAL {{
        ?œuvre rdfs:label ?titre_fr.
        FILTER(LANG(?titre_fr) = "fr")
      }}
      OPTIONAL {{
        ?œuvre rdfs:label ?titre_en.
        FILTER(LANG(?titre_en) = "en")
      }}
    }}
    ORDER BY ?titre
    LIMIT {limit}
    OFFSET {offset}
    """

def parse_artwork(binding):
    """Parse tous les champs"""
    artwork_url = binding.get('œuvre', {}).get('value', '')
    artwork_id = artwork_url.split('/')[-1] if artwork_url else ''
    
    return {
        'id': artwork_id,
        'titre_fallback': binding.get('titre', {}).get('value', 'Sans titre'),
        'titre_fr': binding.get('titre_fr', {}).get('value', ''),
        'titre_en': binding.get('titre_en', {}).get('value', ''),
        'image_url': binding.get('image', {}).get('value', ''),
        'createur_nom': binding.get('createurLabel', {}).get('value', ''),
        'createur_id': binding.get('createur', {}).get('value', '').split('/')[-1] if binding.get('createur') else '',
        'date_creation': binding.get('date', {}).get('value', ''),
        'type': binding.get('typeLabel', {}).get('value', ''),
        'type_id': binding.get('type', {}).get('value', '').split('/')[-1] if binding.get('type') else '',
        'partie_de': binding.get('partie_deLabel', {}).get('value', ''),
        'partie_de_id': binding.get('partie_de', {}).get('value', '').split('/')[-1] if binding.get('partie_de') else '',
        'collection': binding.get('collectionLabel', {}).get('value', MUSEE_NOM),
        'collection_id': binding.get('collection', {}).get('value', '').split('/')[-1] if binding.get('collection') else MUSEE_ID,
        'lieu': binding.get('lieuLabel', {}).get('value', ''),
        'lieu_id': binding.get('lieu', {}).get('value', '').split('/')[-1] if binding.get('lieu') else '',
        'mouvement': binding.get('mouvementLabel', {}).get('value', ''),
        'mouvement_id': binding.get('mouvement', {}).get('value', '').split('/')[-1] if binding.get('mouvement') else '',
        'technique': binding.get('technique', {}).get('value', ''),
        'wikidata_url': f"https://www.wikidata.org/wiki/{artwork_id}" if artwork_id else '',
        'musee': MUSEE_NOM,
        'musee_id': MUSEE_ID,
        'date_extraction': datetime.now().isoformat()
    }

def main():
    print("="*80)
    print(f"🏛️  LOUVRE - TOUS CHAMPS OPTIMISÉ")
    print("="*80)
    print(f"📊 Champs: 16 (tous ceux demandés)")
    print(f"📦 Lots de {BATCH_SIZE} œuvres (très petits)")
    print(f"⏱️  Timeout: {TIMEOUT}s")
    print("="*80)
    
    total = get_total_count()
    print(f"📊 Total: {total} œuvres")
    
    if total == 0:
        return
    
    nb_lots = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"⏱️  {nb_lots} lots, environ {nb_lots * PAUSE_BETWEEN_LOTS // 60} minutes")
    print(f"   (soit ~{nb_lots * PAUSE_BETWEEN_LOTS // 3600} heures)")
    
    toutes = []
    offset = 0
    lots_reussis = 0
    lots_echoues = 0
    
    print(f"\n📦 Début de l'extraction...")
    
    while offset < total:
        print(f"\n📦 Lot {offset//BATCH_SIZE + 1}/{nb_lots} (offset {offset})...")
        
        query = get_artworks_query(offset, BATCH_SIZE)
        results = execute_query_with_retry(query)
        
        if results and 'results' in results:
            bindings = results['results']['bindings']
            
            if bindings:
                for b in bindings:
                    toutes.append(parse_artwork(b))
                
                print(f"  ✅ +{len(bindings)} (total: {len(toutes)}/{total})")
                lots_reussis += 1
                offset += BATCH_SIZE
                lots_echoues = 0  # Reset compteur d'échecs
            else:
                print(f"  ⚠️ Lot vide, on passe au suivant")
                offset += BATCH_SIZE
        else:
            print(f"  ❌ Échec sur ce lot")
            lots_echoues += 1
            
            if lots_echoues >= 5:
                print(f"\n⚠️ 5 échecs consécutifs. Pause longue de 5 minutes...")
                time.sleep(300)
                lots_echoues = 0
            else:
                # On passe au lot suivant quand même
                offset += BATCH_SIZE
        
        # Pause systématique entre les lots
        if offset < total:
            print(f"  ⏳ Pause {PAUSE_BETWEEN_LOTS}s...")
            time.sleep(PAUSE_BETWEEN_LOTS)
        
        # Sauvegarde périodique tous les 100 lots
        if len(toutes) > 0 and len(toutes) % 300 == 0:
            print(f"\n💾 Sauvegarde intermédiaire...")
            with open(OUTPUT_FILE + ".part", 'w', encoding='utf-8') as f:
                json.dump(toutes, f, indent=2)
            print(f"   {len(toutes)} œuvres sauvegardées")
    
    # Sauvegarde finale
    print(f"\n💾 Sauvegarde finale dans {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(toutes, f, indent=2)
    
    # Statistiques
    print("\n" + "="*80)
    print("📊 RÉSULTATS FINAUX")
    print("="*80)
    print(f"✅ Récupéré: {len(toutes)}/{total}")
    
    if toutes:
        with_images = sum(1 for o in toutes if o['image_url'])
        with_dates = sum(1 for o in toutes if o['date_creation'])
        with_createur = sum(1 for o in toutes if o['createur_nom'])
        with_titre_fr = sum(1 for o in toutes if o['titre_fr'])
        
        print(f"\n📊 Qualité:")
        print(f"  🖼️  Images: {with_images}/{len(toutes)} ({with_images/len(toutes)*100:.1f}%)")
        print(f"  📅 Dates: {with_dates}/{len(toutes)} ({with_dates/len(toutes)*100:.1f}%)")
        print(f"  🎨 Créateurs: {with_createur}/{len(toutes)} ({with_createur/len(toutes)*100:.1f}%)")
        print(f"  🇫🇷 Titres FR: {with_titre_fr}/{len(toutes)} ({with_titre_fr/len(toutes)*100:.1f}%)")

if __name__ == "__main__":
    main()
