#!/usr/bin/env python3
"""
Application Flask pour MuseumWiki
Version PostgreSQL (locale et VPS) avec filtres dynamiques
"""

# ============================================
# 1. IMPORTS
# ============================================
from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import os
import plotly.express as px
import plotly.utils
import json
from datetime import datetime

# ============================================
# 2. CONFIGURATION DE LA BASE DE DONNÉES
# ============================================
app = Flask(__name__)

# MÊMES IDENTIFIANTS PARTOUT (local comme VPS)
DB_USER = 'superadmin'
DB_PASSWORD = 'Lahess!2'
DB_HOST = 'localhost'
DB_NAME = 'museumwiki'

app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialisation SQLAlchemy
db = SQLAlchemy(app)

# ============================================
# 3. MODÈLE POUR LES ŒUVRES
# ============================================
class Artwork(db.Model):
    __tablename__ = 'artworks'
    
    id = db.Column(db.String, primary_key=True)
    titre = db.Column(db.String(500))
    createur = db.Column(db.String(200))
    createur_id = db.Column(db.String(50))
    date = db.Column(db.String(50))
    image_url = db.Column(db.String(500))
    lieu = db.Column(db.String(200))
    genre = db.Column(db.String(200))
    mouvement = db.Column(db.String(200))
    wikidata_url = db.Column(db.String(500))
    
    def to_dict(self):
        return {
            'id': self.id,
            'titre': self.titre,
            'createur': self.createur,
            'date': self.date,
            'image_url': self.image_url,
            'lieu': self.lieu,
            'genre': self.genre,
            'mouvement': self.mouvement,
            'wikidata_url': self.wikidata_url
        }

# ============================================
# 4. FONCTIONS UTILITAIRES
# ============================================

def get_filtered_query(query, artists, museums, movements):
    """
    Construit une requête SQLAlchemy filtrée
    """
    q = Artwork.query
    
    if query:
        search = f"%{query}%"
        q = q.filter(
            (Artwork.titre.ilike(search)) |
            (Artwork.createur.ilike(search)) |
            (Artwork.lieu.ilike(search)) |
            (Artwork.genre.ilike(search))
        )
    
    if artists:
        artist_filters = []
        for artist in artists:
            artist_filters.append(Artwork.createur.ilike(f"%{artist}%"))
        q = q.filter(db.or_(*artist_filters))
    
    if museums:
        museum_filters = []
        for museum in museums:
            museum_filters.append(Artwork.lieu.ilike(f"%{museum}%"))
        q = q.filter(db.or_(*museum_filters))
    
    if movements:
        movement_filters = []
        for movement in movements:
            movement_filters.append(Artwork.mouvement.ilike(f"%{movement}%"))
        q = q.filter(db.or_(*movement_filters))
    
    return q

# ============================================
# 5. ROUTE PRINCIPALE
# ============================================

@app.route('/')
def index():
    """Page d'accueil avec recherche, filtres et tris"""
    # Récupération des paramètres
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    artists = request.args.getlist('artist')
    museums = request.args.getlist('museum')
    movements = request.args.getlist('movement')
    sort = request.args.get('sort', 'relevance')
    
    # Construction de la requête de base
    base_query = get_filtered_query(query, artists, museums, movements)
    
    # Application du tri
    if sort == 'date_asc':
        base_query = base_query.order_by(Artwork.date)
    elif sort == 'date_desc':
        base_query = base_query.order_by(Artwork.date.desc())
    elif sort == 'title_asc':
        base_query = base_query.order_by(Artwork.titre)
    elif sort == 'title_desc':
        base_query = base_query.order_by(Artwork.titre.desc())
    elif sort == 'artist_asc':
        base_query = base_query.order_by(Artwork.createur)
    elif sort == 'artist_desc':
        base_query = base_query.order_by(Artwork.createur.desc())
    # relevance = pas de tri
    
    # Pagination
    pagination = base_query.paginate(page=page, per_page=per_page, error_out=False)
    results_page = pagination.items
    total = pagination.total
    total_pages = pagination.pages
    
    return render_template('index.html', 
                         query=query,
                         results=[a.to_dict() for a in results_page],
                         count=total,
                         page=page,
                         total_pages=total_pages,
                         artists=artists,
                         museums=museums,
                         movements=movements,
                         sort=sort)

# ============================================
# 6. API POUR LES FILTRES DYNAMIQUES
# ============================================

@app.route('/api/artists')
def api_artists():
    """Retourne la liste des artistes avec leur nombre d'œuvres,
       filtrée par la recherche ET les filtres déjà appliqués"""
    query = request.args.get('q', '')
    
    # Récupérer les filtres déjà sélectionnés dans l'URL
    current_artists = request.args.getlist('artist')
    current_museums = request.args.getlist('museum')
    current_movements = request.args.getlist('movement')
    
    # Appliquer tous les filtres
    base_query = get_filtered_query(query, current_artists, current_museums, current_movements)
    
    # Agrégation par artiste
    results = db.session.query(
        Artwork.createur.label('name'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.createur != 'Inconnu'
    ).group_by(
        Artwork.createur
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    return jsonify([{'name': r.name, 'count': r.count} for r in results])

@app.route('/api/museums')
def api_museums():
    """Retourne la liste des musées avec leur nombre d'œuvres,
       filtrée par la recherche ET les filtres déjà appliqués"""
    query = request.args.get('q', '')
    
    current_artists = request.args.getlist('artist')
    current_museums = request.args.getlist('museum')
    current_movements = request.args.getlist('movement')
    
    base_query = get_filtered_query(query, current_artists, current_museums, current_movements)
    
    results = db.session.query(
        Artwork.lieu.label('name'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.lieu != 'Inconnu'
    ).group_by(
        Artwork.lieu
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    return jsonify([{'name': r.name, 'count': r.count} for r in results])

@app.route('/api/movements')
def api_movements():
    """Retourne la liste des mouvements avec leur nombre d'œuvres,
       filtrée par la recherche ET les filtres déjà appliqués"""
    query = request.args.get('q', '')
    
    current_artists = request.args.getlist('artist')
    current_museums = request.args.getlist('museum')
    current_movements = request.args.getlist('movement')
    
    base_query = get_filtered_query(query, current_artists, current_museums, current_movements)
    
    results = db.session.query(
        Artwork.mouvement.label('name'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.mouvement != 'Inconnu',
        Artwork.mouvement != 'nan'
    ).group_by(
        Artwork.mouvement
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    return jsonify([{'name': r.name, 'count': r.count} for r in results])

# ============================================
# 7. ROUTES PAGES STATIQUES
# ============================================

@app.route('/stats')
def statistics():
    """Page de statistiques"""
    # Top 10 artistes
    top_artists_data = db.session.query(
        Artwork.createur, func.count(Artwork.id)
    ).filter(
        Artwork.createur != 'Inconnu'
    ).group_by(
        Artwork.createur
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(10).all()
    top_artists = {a: c for a, c in top_artists_data}
    
    # Top 10 genres
    top_genres_data = db.session.query(
        Artwork.genre, func.count(Artwork.id)
    ).filter(
        Artwork.genre != 'Inconnu'
    ).group_by(
        Artwork.genre
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(10).all()
    genres = {g: c for g, c in top_genres_data}
    
    return render_template('stats.html',
                         top_artists=top_artists,
                         genres=genres)

@app.route('/about')
def about():
    """Page à propos"""
    return render_template('about.html')

@app.route('/oeuvre/<string:oeuvre_id>')
def oeuvre_detail(oeuvre_id):
    """Page détaillée d'une œuvre"""
    artwork = Artwork.query.get(oeuvre_id)
    
    if artwork:
        return render_template('detail.html', oeuvre=artwork.to_dict())
    else:
        return "Œuvre non trouvée", 404

@app.route('/api/suggestions')
def suggestions():
    """API pour l'autocomplete"""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    search = f"%{query}%"
    
    # Artistes
    artists = db.session.query(Artwork.createur).filter(
        Artwork.createur.ilike(search),
        Artwork.createur != 'Inconnu'
    ).distinct().limit(3).all()
    
    # Titres
    titles = db.session.query(Artwork.titre).filter(
        Artwork.titre.ilike(search),
        Artwork.titre != 'Inconnu'
    ).distinct().limit(3).all()
    
    # Musées
    museums = db.session.query(Artwork.lieu).filter(
        Artwork.lieu.ilike(search),
        Artwork.lieu != 'Inconnu'
    ).distinct().limit(3).all()
    
    suggestions_list = []
    for a in artists:
        suggestions_list.append({'texte': a[0], 'categorie': 'artiste'})
    for t in titles:
        suggestions_list.append({'texte': t[0], 'categorie': 'œuvre'})
    for m in museums:
        suggestions_list.append({'texte': m[0], 'categorie': 'musée'})
    
    return jsonify(suggestions_list[:9])

# ============================================
# 8. LANCEMENT
# ============================================
if __name__ == '__main__':
    # Création des tables au démarrage (si elles n'existent pas)
    with app.app_context():
        db.create_all()
        print("✅ Tables PostgreSQL vérifiées/créées")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
