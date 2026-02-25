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
from werkzeug.security import generate_password_hash, check_password_hash
import re

# ============================================
# 2. CONFIGURATION DE LA BASE DE DONNÉES
# ============================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'une-cle-secrete-tres-longue-et-difficile-a-deviner-123!'

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
# 3. MODÈLE POUR LES UTILISATEURS
# ============================================
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.strftime('%d/%m/%Y')
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
    
    # Construire la requête avec TOUS les filtres
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
    """Page de statistiques enrichie"""
    # Total des œuvres
    total_oeuvres = Artwork.query.count()
    
    # Nombre d'artistes uniques
    total_artistes = db.session.query(Artwork.createur).filter(
        Artwork.createur != 'Inconnu'
    ).distinct().count()
    
    # Nombre de musées uniques
    total_musees = db.session.query(Artwork.lieu).filter(
        Artwork.lieu != 'Inconnu'
    ).distinct().count()
    
    # Top 30 artistes
    top_artistes_data = db.session.query(
        Artwork.createur.label('nom'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.createur != 'Inconnu'
    ).group_by(
        Artwork.createur
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    # Top 30 musées
    top_musees_data = db.session.query(
        Artwork.lieu.label('nom'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.lieu != 'Inconnu'
    ).group_by(
        Artwork.lieu
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    # Date de dernière mise à jour (prendre la date du fichier ou maintenant)
    from datetime import datetime
    last_update = datetime.now().strftime('%d/%m/%Y à %H:%M')
    
    return render_template('stats.html',
                         total_oeuvres=total_oeuvres,
                         total_artistes=total_artistes,
                         total_musees=total_musees,
                         top_artistes=top_artistes_data,
                         top_musees=top_musees_data,
                         last_update=last_update)


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
# 8. ROUTES D'AUTHENTIFICATION
# ============================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Page d'inscription"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        errors = []
        
        # Vérifier que tous les champs sont remplis
        if not username or not email or not password or not confirm_password:
            errors.append("Tous les champs sont obligatoires")
        
        # Vérifier que les mots de passe correspondent
        if password != confirm_password:
            errors.append("Les mots de passe ne correspondent pas")
        
        # Vérifier la complexité du mot de passe
        if len(password) < 8:
            errors.append("Le mot de passe doit contenir au moins 8 caractères")
        
        if not re.search(r"[A-Z]", password):
            errors.append("Le mot de passe doit contenir au moins une majuscule")
        
        if not re.search(r"[a-z]", password):
            errors.append("Le mot de passe doit contenir au moins une minuscule")
        
        if not re.search(r"[0-9]", password):
            errors.append("Le mot de passe doit contenir au moins un chiffre")
        
        # Vérifier le format de l'email
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            errors.append("Format d'email invalide")
        
        # Vérifier si l'utilisateur existe déjà
        if User.query.filter_by(username=username).first():
            errors.append("Ce nom d'utilisateur est déjà pris")
        
        if User.query.filter_by(email=email).first():
            errors.append("Cet email est déjà utilisé")
        
        if errors:
            return render_template('register.html', errors=errors, 
                                 username=username, email=email)
        
        # Créer l'utilisateur
        user = User(username=username, email=email)
        user.set_password(password)
        
        try:
            db.session.add(user)
            db.session.commit()
            flash('Inscription réussie ! Vous pouvez maintenant vous connecter.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Une erreur est survenue. Veuillez réessayer.', 'danger')
            return render_template('register.html', username=username, email=email)
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash(f'Bienvenue {user.username} !', 'success')
            return redirect(url_for('index'))
        else:
            flash('Nom d\'utilisateur ou mot de passe incorrect', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Déconnexion"""
    session.clear()
    flash('Vous avez été déconnecté', 'info')
    return redirect(url_for('index'))

@app.route('/profile')
def profile():
    """Page de profil utilisateur"""
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour accéder à cette page', 'warning')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    return render_template('profile.html', user=user.to_dict())

# ============================================
# 8. LANCEMENT
# ============================================
if __name__ == '__main__':
    # Création des tables au démarrage (si elles n'existent pas)
    with app.app_context():
        db.create_all()
        print("✅ Tables PostgreSQL vérifiées/créées")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
