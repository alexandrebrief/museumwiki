#!/usr/bin/env python3
"""
Application Flask pour MuseumWiki
Version PostgreSQL avec authentification, favoris et notations
"""

# ============================================
# 1. IMPORTS
# ============================================
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
import plotly.express as px
import plotly.utils
import json
import re
import secrets
import logging
from sqlalchemy import inspect
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
# ============================================
# 2. CONFIGURATION DE L'APPLICATION
# ============================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'une-cle-secrete-tres-longue-et-difficile-a-deviner-123!'

# Configuration de la base de données
DB_USER = 'superadmin'
DB_PASSWORD = 'Lahess!2'
DB_HOST = 'localhost'
DB_NAME = 'museumwiki'

app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuration SendGrid
try:
    from config import SENDGRID_API_KEY, FROM_EMAIL, BASE_URL
except ImportError:
    # Fallback pour le développement
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')
    FROM_EMAIL = 'alexandre.brief2.0@gmail.com'
    BASE_URL = 'http://localhost:5000'

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialisation SQLAlchemy
db = SQLAlchemy(app)


# ============================================
# 2.1 SÉCURITÉ - HEADERS HTTP (Flask-Talisman)
# ============================================

Talisman(app,
    content_security_policy={
        'default-src': ["'self'"],
        'script-src': ["'self'", "https://cdn.jsdelivr.net", "https://code.jquery.com", "https://cdnjs.cloudflare.com"],
        'style-src': ["'self'", "https://cdn.jsdelivr.net", "https://fonts.googleapis.com", "https://cdnjs.cloudflare.com", "'unsafe-inline'"],
        'font-src': ["'self'", "https://fonts.gstatic.com", "https://cdnjs.cloudflare.com"],
        'img-src': ["'self'", "data:", "https:", "http:", "*"],
    },
    force_https=False,
    strict_transport_security=True,
    session_cookie_secure=False,
    session_cookie_http_only=True,
    referrer_policy='strict-origin-when-cross-origin'
)

# ============================================
# 2.2 SÉCURITÉ - RATE LIMITING (Flask-Limiter)
# ============================================


limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ============================================
# 2.3 SÉCURITÉ - CSRF PROTECTION (Flask-WTF)
# ============================================


csrf = CSRFProtect(app)


# ============================================
# 2.5 LOGGING DE SÉCURITÉ
# ============================================
from logging.handlers import RotatingFileHandler

# Logger de sécurité
security_logger = logging.getLogger('security')
security_logger.setLevel(logging.WARNING)

handler = RotatingFileHandler('security.log', maxBytes=10000, backupCount=3)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
security_logger.addHandler(handler)

# ============================================
# 3. MODÈLES DE BASE DE DONNÉES
# ============================================

class Artwork(db.Model):
    """Modèle pour les œuvres d'art"""
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


class User(db.Model):
    """Modèle pour les utilisateurs"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(100), unique=True)
    verification_token = db.Column(db.String(100), unique=True)
    last_login = db.Column(db.DateTime)
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
            'email_verified': self.email_verified,
            'created_at': self.created_at.strftime('%d/%m/%Y')
        }


class EmailVerification(db.Model):
    """Modèle pour les vérifications d'email"""
    __tablename__ = 'email_verifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User', backref='verifications')
    
    @staticmethod
    def generate_code():
        return ''.join(secrets.choice('0123456789') for _ in range(6))
    
    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(32)
    
    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at


class Favorite(db.Model):
    """Modèle pour les favoris"""
    __tablename__ = 'favorites'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    artwork_id = db.Column(db.String, db.ForeignKey('artworks.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='favorites')
    artwork = db.relationship('Artwork', backref='favorited_by')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'artwork_id', name='unique_user_artwork_favorite'),)


class Rating(db.Model):
    """Modèle pour les notes"""
    __tablename__ = 'ratings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    artwork_id = db.Column(db.String, db.ForeignKey('artworks.id'), nullable=False)
    
    note_globale = db.Column(db.Float, nullable=False)
    note_technique = db.Column(db.Float, nullable=False)
    note_originalite = db.Column(db.Float, nullable=False)
    note_emotion = db.Column(db.Float, nullable=False)
    
    commentaire = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref='ratings')
    artwork = db.relationship('Artwork', backref='ratings')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'artwork_id', name='unique_user_artwork_rating'),)
    
    def to_dict(self):
        return {
            'id': self.id,
            'note_globale': self.note_globale,
            'note_technique': self.note_technique,
            'note_originalite': self.note_originalite,
            'note_emotion': self.note_emotion,
            'commentaire': self.commentaire,
            'created_at': self.created_at.strftime('%d/%m/%Y'),
            'updated_at': self.updated_at.strftime('%d/%m/%Y') if self.updated_at else None
        }

# ============================================
# 4. FONCTIONS UTILITAIRES
# ============================================

def send_verification_email(user_email, username, code, token):
    """Envoie un email de vérification avec code et lien"""
    
    verification_link = f"{BASE_URL}/verify-email?token={token}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: 'Inter', sans-serif;
                background-color: #f5f0e8;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: white;
                border-radius: 16px;
                padding: 30px;
                box-shadow: 0 4px 12px rgba(44,62,80,0.05);
            }}
            h1 {{
                font-family: 'Playfair Display', serif;
                color: #2c3e50;
                font-size: 24px;
                margin-bottom: 20px;
            }}
            .code {{
                font-size: 32px;
                font-weight: bold;
                color: #2c3e50;
                background: #f5f0e8;
                padding: 15px;
                border-radius: 8px;
                text-align: center;
                letter-spacing: 5px;
                margin: 20px 0;
            }}
            .button {{
                background: #2c3e50;
                color: #e6d8c3;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 8px;
                display: inline-block;
                margin: 20px 0;
            }}
            .footer {{
                margin-top: 30px;
                color: #5d6d7e;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Bienvenue sur MuseumWiki, {username} !</h1>
            <p>Merci de vous être inscrit. Pour activer votre compte, veuillez utiliser le code de vérification ci-dessous :</p>
            
            <div class="code">{code}</div>
            
            <p>Ou cliquez sur le lien suivant :</p>
            <a href="{verification_link}" class="button">Vérifier mon email</a>
            
            <p>Ce code et ce lien expireront dans 24 heures.</p>
            
            <div class="footer">
                <p>Si vous n'avez pas créé de compte sur MuseumWiki, ignorez cet email.</p>
                <p>© 2025 MuseumWiki · Collection d'œuvres d'art · Données Wikidata</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=user_email,
        subject='MuseumWiki - Vérification de votre email',
        html_content=html_content
    )
    
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        logger.info(f"Email envoyé à {user_email}, statut: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Erreur d'envoi d'email: {e}")
        return False


def get_filtered_query(query, artists, museums, movements):
    """Construit une requête SQLAlchemy filtrée pour les œuvres"""
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


def handle_unverified_user(user, email):
    """Gère le cas d'un utilisateur avec email non vérifié"""
    old_verifications = EmailVerification.query.filter_by(
        user_id=user.id, used=False
    ).all()
    for v in old_verifications:
        v.used = True
    
    code = EmailVerification.generate_code()
    token = EmailVerification.generate_token()
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    verification = EmailVerification(
        user_id=user.id,
        token=token,
        code=code,
        expires_at=expires_at
    )
    db.session.add(verification)
    db.session.commit()
    
    if send_verification_email(email, user.username, code, token):
        flash('Un email de vérification a été renvoyé. Vérifiez votre boîte de réception.', 'info')
    else:
        flash('Erreur lors de l\'envoi de l\'email. Veuillez réessayer.', 'danger')
    
    return redirect(url_for('verify_email_pending', email=email))



# ============================================
# 5. FILTRES POUR LES TEMPLATES
# ============================================

@app.template_filter('stars')
def stars_filter(value):
    """Convertit une note en étoiles"""
    if not value:
        return ''
    full_stars = int(value)
    half_star = 1 if value - full_stars >= 0.5 else 0
    empty_stars = 5 - full_stars - half_star
    
    stars = '★' * full_stars
    if half_star:
        stars += '½'
    stars += '☆' * empty_stars
    
    return stars

# ============================================
# 6. ROUTES PRINCIPALESe
# ============================================

@app.route('/')
def index():
    """Page d'accueil avec recherche, filtres et tris"""
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    artists = request.args.getlist('artist')
    museums = request.args.getlist('museum')
    movements = request.args.getlist('movement')
    sort = request.args.get('sort', 'relevance')
    
    # S'il y a une recherche ou des filtres, on utilise la recherche normale
    if query or artists or museums or movements:
        base_query = get_filtered_query(query, artists, museums, movements)
        
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
        
        pagination = base_query.paginate(page=page, per_page=per_page, error_out=False)
        results_page = pagination.items
        
    else:
        # Page d'accueil sans recherche : afficher 20 œuvres aléatoires
        total_oeuvres = Artwork.query.count()
        
        if total_oeuvres > 0:
            # Prendre 20 œuvres aléatoires
            random_query = Artwork.query.order_by(func.random()).limit(per_page)
            
            if page == 1:
                results_page = random_query.all()
                total = min(total_oeuvres, per_page)
                total_pages = 1
            else:
                # Pour les pages suivantes, on prend d'autres œuvres aléatoires
                offset = (page - 1) * per_page
                results_page = Artwork.query.order_by(func.random()).offset(offset).limit(per_page).all()
                total = total_oeuvres
                total_pages = (total_oeuvres + per_page - 1) // per_page
            
            pagination = type('Pagination', (), {
                'items': results_page,
                'total': total,
                'pages': total_pages
            })()
        else:
            # Pas d'œuvres dans la BDD
            results_page = []
            pagination = type('Pagination', (), {
                'items': [],
                'total': 0,
                'pages': 1
            })()
    
    # ✅ AJOUTER ICI : Calculer le nombre de favoris pour chaque œuvre
    favorite_counts = {}
    for artwork in results_page:
        count = Favorite.query.filter_by(artwork_id=artwork.id).count()
        favorite_counts[artwork.id] = count
    
    return render_template('index.html', 
                         query=query,
                         results=[a.to_dict() for a in results_page],
                         count=pagination.total,
                         page=page,
                         total_pages=pagination.pages,
                         artists=artists,
                         museums=museums,
                         movements=movements,
                         sort=sort,
                         favorite_counts=favorite_counts)  # ← AJOUTÉ ICI


@app.route('/oeuvre/<string:oeuvre_id>')
def oeuvre_detail(oeuvre_id):
    """Page détaillée d'une œuvre"""
    artwork = Artwork.query.get(oeuvre_id)
    
    if artwork:
        return render_template('detail.html', oeuvre=artwork.to_dict())
    else:
        return "Œuvre non trouvée", 404

# ============================================
# 7. API POUR LES FILTRES
# ============================================

@app.route('/api/artists')
def api_artists():
    """Retourne la liste des artistes avec leur nombre d'œuvres"""
    query = request.args.get('q', '')
    current_artists = request.args.getlist('artist')
    current_museums = request.args.getlist('museum')
    current_movements = request.args.getlist('movement')
    
    base_query = get_filtered_query(query, current_artists, current_museums, current_movements)
    
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
    """Retourne la liste des musées avec leur nombre d'œuvres"""
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
    """Retourne la liste des mouvements avec leur nombre d'œuvres"""
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


@app.route('/api/suggestions')
def suggestions():
    """API pour l'autocomplete"""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    search = f"%{query}%"
    
    artists = db.session.query(Artwork.createur).filter(
        Artwork.createur.ilike(search),
        Artwork.createur != 'Inconnu'
    ).distinct().limit(3).all()
    
    titles = db.session.query(Artwork.titre).filter(
        Artwork.titre.ilike(search),
        Artwork.titre != 'Inconnu'
    ).distinct().limit(3).all()
    
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
# 8. ROUTES PAGES STATIQUES
# ============================================
@app.route('/api/favorites/list')
def list_favorites():
    """Liste tous les IDs des favoris de l'utilisateur connecté"""
    if 'user_id' not in session:
        return jsonify([])
    
    favorites = Favorite.query.filter_by(user_id=session['user_id']).all()
    return jsonify([fav.artwork_id for fav in favorites])


@app.route('/api/comments/<artwork_id>')
def get_comments(artwork_id):
    """Récupère tous les commentaires d'une œuvre"""
    ratings = Rating.query.filter_by(artwork_id=artwork_id)\
        .filter(Rating.commentaire.isnot(None))\
        .filter(Rating.commentaire != '')\
        .order_by(Rating.created_at.desc())\
        .all()
    
    comments = []
    for rating in ratings:
        user = User.query.get(rating.user_id)
        comments.append({
            'username': user.username if user else 'Anonyme',
            'commentaire': rating.commentaire,
            'note_globale': rating.note_globale,
            'created_at': rating.created_at.strftime('%d/%m/%Y'),
            'notes': {
                'technique': rating.note_technique,
                'originalite': rating.note_originalite,
                'emotion': rating.note_emotion
            }
        })
    
    return jsonify(comments)

@app.route('/stats')
def statistics():
    """Page de statistiques"""
    try:
        total_oeuvres = Artwork.query.count()
        
        total_artistes = db.session.query(Artwork.createur).filter(
            Artwork.createur != 'Inconnu'
        ).distinct().count()
        
        total_musees = db.session.query(Artwork.lieu).filter(
            Artwork.lieu != 'Inconnu'
        ).distinct().count()
        
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
        
        last_update = datetime.now().strftime('%d/%m/%Y à %H:%M')
        
        return render_template('stats.html',
                             total_oeuvres=total_oeuvres,
                             total_artistes=total_artistes,
                             total_musees=total_musees,
                             top_artistes=top_artistes_data,
                             top_musees=top_musees_data,
                             last_update=last_update)
    except Exception as e:
        print(f"❌ Erreur dans stats: {e}")
        return f"Erreur: {e}", 500


@app.route('/about')
def about():
    """Page à propos"""
    try:
        return render_template('about.html')
    except Exception as e:
        print(f"❌ Erreur dans about: {e}")
        return f"Erreur: {e}", 500

# ============================================
# 9. ROUTES D'AUTHENTIFICATION
# ============================================
@limiter.limit("3 per minute")
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Page d'inscription avec vérification d'email"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        print("\n" + "="*50)
        print(f"🔍 NOUVELLE TENTATIVE D'INSCRIPTION")
        print(f"📝 Username: {username}")
        print(f"📧 Email: {email}")
        print("="*50)
        
        errors = []
        
        if not username or not email or not password or not confirm_password:
            errors.append("Tous les champs sont obligatoires")
        
        if password != confirm_password:
            errors.append("Les mots de passe ne correspondent pas")
        
        if len(password) < 8:
            errors.append("Le mot de passe doit contenir au moins 8 caractères")
        
        if not re.search(r"[A-Z]", password):
            errors.append("Le mot de passe doit contenir au moins une majuscule")
        
        if not re.search(r"[a-z]", password):
            errors.append("Le mot de passe doit contenir au moins une minuscule")
        
        if not re.search(r"[0-9]", password):
            errors.append("Le mot de passe doit contenir au moins un chiffre")
        
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            errors.append("Format d'email invalide")
        
        if errors:
            security_logger.warning(f"Tentative inscription échouée - IP: {request.remote_addr} - Email: {email} - Erreurs: {', '.join(errors)}")
            return render_template('register.html', errors=errors, 
                                 username=username, email=email)
        
        try:
            existing_user_by_username = User.query.filter_by(username=username).first()
            existing_user_by_email = User.query.filter_by(email=email).first()
        except Exception as e:
            logger.error(f"Erreur recherche utilisateur: {e}")
            flash('Erreur de base de données.', 'danger')
            return render_template('register.html', username=username, email=email)
        
        if existing_user_by_username:
            errors.append("Ce nom d'utilisateur est déjà pris")
        
        if existing_user_by_email:
            if existing_user_by_email.email_verified:
                errors.append("Cet email est déjà utilisé")
            else:
                return handle_unverified_user(existing_user_by_email, email)
        
        if errors:
            return render_template('register.html', errors=errors, 
                                 username=username, email=email)
        
        try:
            db.session.execute(text('SELECT 1'))
            
            user = User(
                username=username,
                email=email,
                email_verified=False
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            
            code = EmailVerification.generate_code()
            token = EmailVerification.generate_token()
            expires_at = datetime.utcnow() + timedelta(hours=24)
            
            verification = EmailVerification(
                user_id=user.id,
                token=token,
                code=code,
                expires_at=expires_at
            )
            db.session.add(verification)
            db.session.commit()
            
            if send_verification_email(email, username, code, token):
                flash('Inscription réussie ! Un email de vérification vous a été envoyé.', 'success')
                return redirect(url_for('verify_email_pending', email=email))
            else:
                flash('Compte créé mais erreur d\'envoi d\'email. Contactez le support.', 'warning')
                return redirect(url_for('login'))
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erreur lors de l'inscription: {e}")
            flash('Une erreur est survenue. Veuillez réessayer.', 'danger')
            return render_template('register.html', username=username, email=email)
    
    return render_template('register.html')
@limiter.limit("5 per minute")
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion avec email"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()  # ← Changé: email au lieu de username
        password = request.form.get('password', '')
        
        print(f"\n🔍 TENTATIVE DE CONNEXION")
        print(f"📧 Email: {email}")
        
        # Recherche par email (pas par username)
        user = User.query.filter_by(email=email).first()
        
        if user:
            print(f"✅ Utilisateur trouvé: {user.username}")
            print(f"🔐 Vérification mot de passe: {'OK' if user.check_password(password) else 'ÉCHEC'}")
            print(f"📧 Email vérifié: {user.email_verified}")
        else:
            print(f"❌ Aucun utilisateur avec cet email")
        
        if user and user.check_password(password):
            if not user.email_verified:
                print("❌ Email non vérifié")
                security_logger.warning(f"Tentative connexion échouée - IP: {request.remote_addr} - Email: {email}")
                flash('Veuillez vérifier votre email avant de vous connecter.', 'warning')
                return redirect(url_for('verify_email_pending', email=user.email))
            
            # Connexion réussie
            session['user_id'] = user.id
            session['username'] = user.username  # On garde le username en session pour l'affichage
            
            # Mettre à jour last_login
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            print(f"✅ Connexion réussie pour {user.username}")
            flash(f'Bienvenue {user.username} !', 'success')
            return redirect(url_for('index'))
        else:
            print("❌ Email ou mot de passe incorrect")
            flash('Email ou mot de passe incorrect', 'danger')
    
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
    if not user:
        session.clear()
        flash('Utilisateur non trouvé', 'danger')
        return redirect(url_for('login'))
    
    return render_template('profile.html', user=user.to_dict())

# ============================================
# GESTION DU COMPTE (MOT DE PASSE & SUPPRESSION)
# ============================================
@limiter.limit("10 per hour")
@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    """Changer le mot de passe"""
    if 'user_id' not in session:
        flash('Veuillez vous connecter', 'warning')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        errors = []
        
        # Vérifier l'ancien mot de passe
        if not user.check_password(current_password):
            errors.append("Mot de passe actuel incorrect")
            security_logger.warning(f"Tentative changement mot de passe échouée - IP: {request.remote_addr} - User: {session.get('username')}")
        
        # Vérifier le nouveau mot de passe
        if new_password != confirm_password:
            errors.append("Les nouveaux mots de passe ne correspondent pas")
        
        if len(new_password) < 8:
            errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères")
        
        if not re.search(r"[A-Z]", new_password):
            errors.append("Le nouveau mot de passe doit contenir au moins une majuscule")
        
        if not re.search(r"[a-z]", new_password):
            errors.append("Le nouveau mot de passe doit contenir au moins une minuscule")
        
        if not re.search(r"[0-9]", new_password):
            errors.append("Le nouveau mot de passe doit contenir au moins un chiffre")
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('change_password.html')
        
        # Changer le mot de passe
        user.set_password(new_password)
        db.session.commit()
        
        flash('Mot de passe modifié avec succès !', 'success')
        return redirect(url_for('profile'))
    
    return render_template('change_password.html')


@app.route('/delete-account', methods=['POST'])
def delete_account():
    """Supprimer son compte"""
    if 'user_id' not in session:
        flash('Veuillez vous connecter', 'warning')
        return redirect(url_for('login'))
    
    password = request.form.get('password', '')
    user = User.query.get(session['user_id'])
    
    # Vérifier le mot de passe
    if not user.check_password(password):
        flash('Mot de passe incorrect', 'danger')
        return redirect(url_for('profile'))
    
    try:
        # Supprimer les données associées
        EmailVerification.query.filter_by(user_id=user.id).delete()
        Favorite.query.filter_by(user_id=user.id).delete()
        Rating.query.filter_by(user_id=user.id).delete()
        
        # Supprimer l'utilisateur
        db.session.delete(user)
        db.session.commit()
        
        # Déconnecter
        session.clear()
        flash('Votre compte a été supprimé', 'info')
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur suppression compte: {e}")
        flash('Erreur lors de la suppression', 'danger')
        return redirect(url_for('profile'))

# ============================================
# 10. ROUTES DE VÉRIFICATION D'EMAIL
# ============================================

@app.route('/verify-email-pending')
def verify_email_pending():
    """Page d'attente de vérification"""
    email = request.args.get('email', '')
    return render_template('verify_email_pending.html', email=email)


@app.route('/verify-email')
def verify_email():
    """Vérification par lien"""
    token = request.args.get('token', '')
    
    verification = EmailVerification.query.filter_by(
        token=token, used=False
    ).first()
    
    if not verification or not verification.is_valid():
        flash('Lien de vérification invalide ou expiré.', 'danger')
        return redirect(url_for('login'))
    
    user = verification.user
    user.email_verified = True
    verification.used = True
    db.session.commit()
    
    flash('Email vérifié avec succès ! Vous pouvez maintenant vous connecter.', 'success')
    return redirect(url_for('login'))


@app.route('/verify-code', methods=['POST'])
def verify_code():
    """Vérification par code"""
    code = request.form.get('code', '').strip()
    email = request.form.get('email', '')
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Utilisateur non trouvé.', 'danger')
        return redirect(url_for('login'))
    
    verification = EmailVerification.query.filter_by(
        user_id=user.id, used=False
    ).first()
    
    if not verification or verification.code != code or not verification.is_valid():
        flash('Code invalide ou expiré.', 'danger')
        return redirect(url_for('verify_email_pending', email=email))
    
    user.email_verified = True
    verification.used = True
    db.session.commit()
    
    flash('Email vérifié avec succès ! Vous pouvez maintenant vous connecter.', 'success')
    return redirect(url_for('login'))


@app.route('/resend-verification', methods=['POST'])
def resend_verification():
    """Renvoyer l'email de vérification"""
    email = request.form.get('email', '')
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Utilisateur non trouvé.', 'danger')
        return redirect(url_for('register'))
    
    if user.email_verified:
        flash('Cet email est déjà vérifié.', 'info')
        return redirect(url_for('login'))
    
    old_verifications = EmailVerification.query.filter_by(
        user_id=user.id, used=False
    ).all()
    for v in old_verifications:
        v.used = True
    
    code = EmailVerification.generate_code()
    token = EmailVerification.generate_token()
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    verification = EmailVerification(
        user_id=user.id,
        token=token,
        code=code,
        expires_at=expires_at
    )
    db.session.add(verification)
    db.session.commit()
    
    if send_verification_email(email, user.username, code, token):
        flash('Nouvel email de vérification envoyé !', 'success')
    else:
        flash('Erreur lors de l\'envoi. Veuillez réessayer.', 'danger')
    
    return redirect(url_for('verify_email_pending', email=email))

# ============================================
# 11. ROUTES POUR LES FAVORIS ET NOTES
# ============================================

@app.route('/api/favorite/toggle', methods=['POST'])
def toggle_favorite():
    """Ajoute ou retire un favori"""
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    artwork_id = data.get('artwork_id')
    
    if not artwork_id:
        return jsonify({'error': 'ID œuvre manquant'}), 400
    
    favorite = Favorite.query.filter_by(
        user_id=session['user_id'],
        artwork_id=artwork_id
    ).first()
    
    if favorite:
        db.session.delete(favorite)
        db.session.commit()
        return jsonify({'favorite': False, 'message': 'Retiré des favoris'})
    else:
        favorite = Favorite(
            user_id=session['user_id'],
            artwork_id=artwork_id
        )
        db.session.add(favorite)
        db.session.commit()
        return jsonify({'favorite': True, 'message': 'Ajouté aux favoris'})


@app.route('/api/favorite/check/<artwork_id>')
def check_favorite(artwork_id):
    """Vérifie si une œuvre est en favori"""
    if 'user_id' not in session:
        return jsonify({'favorite': False})
    
    favorite = Favorite.query.filter_by(
        user_id=session['user_id'],
        artwork_id=artwork_id
    ).first()
    
    return jsonify({'favorite': favorite is not None})


@app.route('/favoris')
def favorites_page():
    """Page des favoris"""
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour voir vos favoris', 'warning')
        return redirect(url_for('login'))
    
    favorites = Favorite.query.filter_by(user_id=session['user_id']).all()
    artworks = [fav.artwork.to_dict() for fav in favorites if fav.artwork]
    
    return render_template('favorites.html', artworks=artworks)


@app.route('/api/rating/save', methods=['POST'])
def save_rating():
    """Sauvegarde une note"""
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    artwork_id = data.get('artwork_id')
    
    def validate_note(note):
        try:
            n = float(note)
            return n >= 0 and n <= 5 and (n * 2).is_integer()
        except:
            return False
    
    if not all([
        validate_note(data.get('note_globale')),
        validate_note(data.get('note_technique')),
        validate_note(data.get('note_originalite')),
        validate_note(data.get('note_emotion'))
    ]):
        return jsonify({'error': 'Notes invalides'}), 400
    
    rating = Rating.query.filter_by(
        user_id=session['user_id'],
        artwork_id=artwork_id
    ).first()
    
    if rating:
        rating.note_globale = float(data['note_globale'])
        rating.note_technique = float(data['note_technique'])
        rating.note_originalite = float(data['note_originalite'])
        rating.note_emotion = float(data['note_emotion'])
        rating.commentaire = data.get('commentaire', '')
        message = 'Note mise à jour'
    else:
        rating = Rating(
            user_id=session['user_id'],
            artwork_id=artwork_id,
            note_globale=float(data['note_globale']),
            note_technique=float(data['note_technique']),
            note_originalite=float(data['note_originalite']),
            note_emotion=float(data['note_emotion']),
            commentaire=data.get('commentaire', '')
        )
        db.session.add(rating)
        message = 'Note enregistrée'
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': message,
        'rating': rating.to_dict()
    })


@app.route('/api/rating/get/<artwork_id>')
def get_rating(artwork_id):
    """Récupère la note d'un utilisateur"""
    if 'user_id' not in session:
        return jsonify({'has_rating': False})
    
    rating = Rating.query.filter_by(
        user_id=session['user_id'],
        artwork_id=artwork_id
    ).first()
    
    if rating:
        return jsonify({
            'has_rating': True,
            'rating': rating.to_dict()
        })
    else:
        return jsonify({'has_rating': False})


@app.route('/mes-oeuvres')
def my_rated_works():
    """Page des œuvres notées"""
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour voir vos œuvres notées', 'warning')
        return redirect(url_for('login'))
    
    ratings = Rating.query.filter_by(user_id=session['user_id']).all()
    
    works = []
    for rating in ratings:
        artwork = Artwork.query.get(rating.artwork_id)
        if artwork:
            work_data = artwork.to_dict()
            work_data['rating'] = rating.to_dict()
            works.append(work_data)
    
    return render_template('my_works.html', works=works)


@app.route('/api/artwork/stats/<artwork_id>')
def artwork_stats(artwork_id):
    """Statistiques d'une œuvre"""
    artwork = Artwork.query.get(artwork_id)
    if not artwork:
        return jsonify({'error': 'Œuvre non trouvée'}), 404
    
    ratings = Rating.query.filter_by(artwork_id=artwork_id).all()
    
    if ratings:
        stats = {
            'total_notes': len(ratings),
            'moyenne_globale': round(sum(r.note_globale for r in ratings) / len(ratings), 1),
            'moyenne_technique': round(sum(r.note_technique for r in ratings) / len(ratings), 1),
            'moyenne_originalite': round(sum(r.note_originalite for r in ratings) / len(ratings), 1),
            'moyenne_emotion': round(sum(r.note_emotion for r in ratings) / len(ratings), 1),
        }
    else:
        stats = {
            'total_notes': 0,
            'moyenne_globale': 0,
            'moyenne_technique': 0,
            'moyenne_originalite': 0,
            'moyenne_emotion': 0,
        }
    
    return jsonify(stats)


@app.route('/test-email')
def test_email():
    """Route de test pour vérifier SendGrid"""
    try:
        test_email = "alexandre.brief2.0@gmail.com"
        test_code = "123456"
        test_token = "test-token-123"
        
        result = send_verification_email(test_email, "TestUser", test_code, test_token)
        
        if result:
            return "✅ Email de test envoyé avec succès ! Vérifie ta boîte de réception."
        else:
            return "❌ Échec de l'envoi. Vérifie les logs."
            
    except Exception as e:
        return f"❌ Erreur: {str(e)}"
# ============================================
# 12. CONTEXT PROCESSOR (variables globales)
# ============================================

@app.context_processor
def inject_global_vars():
    """Injecte des variables dans tous les templates"""
    return dict(
        site_name="Blue Gallery",
        current_year=datetime.now().year,
        now=datetime.now(),
        is_authenticated='user_id' in session,
        current_user=session.get('username', '')
    )

# ============================================
# 13. LANCEMENT DE L'APPLICATION
# ============================================
if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('users')]
            
            if 'is_verified' not in columns and 'email_verified' not in columns:
                db.session.execute(text('ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE'))
                db.session.commit()
                print("✅ Colonne email_verified ajoutée à la table users")
            
            print("✅ Tables PostgreSQL vérifiées/créées")
            print(f"📧 SendGrid configuré avec FROM_EMAIL: {FROM_EMAIL}")
            print(f"🔗 URL de base: {BASE_URL}")
            
        except Exception as e:
            print(f"⚠️  Attention: {e}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
