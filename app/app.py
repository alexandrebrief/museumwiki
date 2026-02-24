#!/usr/bin/env python3
"""
Application Flask pour MuseumWiki
Affiche les œuvres d'art récupérées de Wikidata
"""

# ============================================
# 1. IMPORTS
# ============================================
from flask import Flask, render_template, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import pandas as pd
import os
import plotly.express as px
import plotly.utils
import json
from datetime import datetime
from flask import redirect, url_for

# ============================================
# 2. CONFIGURATION GLOBALE
# ============================================
app = Flask(__name__)

# Cache global pour le DataFrame (évite de relire le fichier à chaque requête)
_df_cache = None

# Configuration du rate limiting (limitation du nombre de requêtes)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,  # Identifie l'utilisateur par son IP
    default_limits=["200 per day", "50 per hour"]  # Limites par défaut
)

# ============================================
# 3. DÉTERMINATION DU CHEMIN DES DONNÉES
# ============================================
# On adapte le chemin selon qu'on est dans Docker ou en local
if os.path.exists('/app/data/artworks_latest.csv'):
    DATA_PATH = '/app/data/artworks_latest.csv'   # Dans Docker
else:
    DATA_PATH = '../data/artworks_latest.csv'     # En local

# ============================================
# 4. FONCTIONS UTILITAIRES
# ============================================

def load_artworks():
    """
    Charge les œuvres depuis le CSV avec mise en cache.
    Le DataFrame est stocké en mémoire pour éviter de relire le fichier
    à chaque appel (amélioration des performances).
    """
    global _df_cache
    if _df_cache is None:
        try:
            _df_cache = pd.read_csv(DATA_PATH)
            _df_cache = _df_cache.fillna('Inconnu')
            print("✅ CSV chargé en cache")
        except Exception as e:
            print(f"❌ Erreur de chargement: {e}")
            return pd.DataFrame()
    return _df_cache

# ============================================
# 5. ROUTES PRINCIPALES
# ============================================

@app.route('/')
def index():
    """Page d'accueil avec recherche"""
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    df = load_artworks()
    
    if query:
        # Recherche dans titre, createur, lieu, genre
        mask = (
            df['titre'].str.contains(query, case=False, na=False) |
            df['createur'].str.contains(query, case=False, na=False) |
            df['lieu'].str.contains(query, case=False, na=False) |
            df['genre'].str.contains(query, case=False, na=False)
        )
        all_results = df[mask]
        total = len(all_results)
        
        # Pagination
        start = (page - 1) * per_page
        end = start + per_page
        results_page = all_results.iloc[start:end]
        total_pages = (total + per_page - 1) // per_page
    else:
        results_page = pd.DataFrame()
        total = 0
        total_pages = 1
    
    return render_template('index.html', 
                         query=query,
                         results=results_page.to_dict('records'),
                         count=total,
                         page=page,
                         total_pages=total_pages)



@app.route('/oeuvre/<string:oeuvre_id>')
def oeuvre_detail(oeuvre_id):
    """
    Page détaillée d'une œuvre spécifique.
    L'URL est de la forme /oeuvre/Q123456
    """
    df = load_artworks()
    oeuvre_data = df[df['id'] == oeuvre_id].to_dict('records')
    
    if oeuvre_data:
        return render_template('detail.html', oeuvre=oeuvre_data[0])
    else:
        return "Œuvre non trouvée", 404


@app.route('/stats')
def statistics():
    """
    Page de statistiques avec graphiques.
    Affiche les top artistes et les genres les plus représentés.
    """
    df = load_artworks()
    
    # Top 10 artistes
    top_artists = df['createur'].value_counts().head(10).to_dict()
    
    # Répartition par genre
    genres = df['genre'].value_counts().head(10).to_dict()
    
    # Création du graphique avec Plotly
    fig = px.bar(
        x=list(top_artists.keys()), 
        y=list(top_artists.values()),
        title="Top 10 des artistes",
        labels={'x': 'Artiste', 'y': "Nombre d'œuvres"}
    )
    graph_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    
    return render_template(
        'stats.html',
        top_artists=top_artists,
        genres=genres,
        graph_json=graph_json
    )


@app.route('/about')
def about():
    """Page à propos du projet."""
    return render_template('about.html')


@app.route('/artist/<artist_name>')
def artist_works(artist_name):
    """
    Filtre les œuvres par artiste.
    Affiche toutes les œuvres d'un artiste donné.
    """
    df = load_artworks()
    artist_works = df[df['createur'].str.contains(artist_name, case=False, na=False)]
    return render_template(
        'artist.html', 
        artist=artist_name,
        artworks=artist_works.to_dict('records')
    )

# ============================================
# 6. API (pour les appels AJAX / autocomplete)
# ============================================

@app.route('/api/artworks')
@limiter.limit("100 per minute")  # Limite plus élevée pour l'API
def api_artworks():
    """
    API JSON retournant les œuvres.
    Utile pour les appels JavaScript (ex: chargement dynamique).
    """
    df = load_artworks()
    limit = request.args.get('limit', 100, type=int)
    return jsonify(df.head(limit).to_dict('records'))


@app.route('/api/suggestions')
@limiter.limit("60 per minute")
def suggestions():
    """
    API pour l'autocomplete de la barre de recherche.
    Retourne des suggestions regroupées par catégorie :
    - artistes
    - œuvres
    - musées
    """
    query = request.args.get('q', '').strip()
    if len(query) < 2:  # Pas de suggestion avant 2 caractères
        return jsonify([])
    
    df = load_artworks()
    
    # Masques de recherche par catégorie
    mask_artistes = df['createur'].str.contains(query, case=False, na=False)
    mask_oeuvres = df['titre'].str.contains(query, case=False, na=False)
    mask_musees = df['lieu'].str.contains(query, case=False, na=False)
    
    suggestions_list = []
    
    # Artistes (max 3)
    artistes = df[mask_artistes]['createur'].drop_duplicates().head(3).tolist()
    for artiste in artistes:
        suggestions_list.append({
            'texte': artiste,
            'categorie': 'artiste'
        })
    
    # Œuvres (max 3)
    oeuvres = df[mask_oeuvres]['titre'].drop_duplicates().head(3).tolist()
    for oeuvre in oeuvres:
        suggestions_list.append({
            'texte': oeuvre,
            'categorie': 'œuvre'
        })
    
    # Musées (max 3)
    musees = df[mask_musees]['lieu'].drop_duplicates().head(3).tolist()
    for musee in musees:
        suggestions_list.append({
            'texte': musee,
            'categorie': 'musée'
        })
    
    return jsonify(suggestions_list[:9])  # Max 9 suggestions

# ============================================
# 7. LANCEMENT DE L'APPLICATION
# ============================================
if __name__ == '__main__':
    # debug=False car on est en production ou en test
    # jamais debug=True en production (risques de sécurité)
    app.run(host='0.0.0.0', port=5000, debug=True)
