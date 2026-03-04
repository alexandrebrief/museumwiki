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

# Remplacer la configuration Talisman actuelle par :
Talisman(app,
    content_security_policy={
        'default-src': ["'self'"],
        # Ajouter 'unsafe-inline' pour le développement
        'script-src': ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", 
                      "https://code.jquery.com", "https://cdnjs.cloudflare.com"],
        'style-src': ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", 
                     "https://fonts.googleapis.com", "https://cdnjs.cloudflare.com"],
        'font-src': ["'self'", "https://fonts.gstatic.com", "https://cdnjs.cloudflare.com"],
        'img-src': ["'self'", "data:", "https:", "http:", "*"],
    },
    force_https=False,  # Désactivé en développement
    strict_transport_security=True,
    session_cookie_secure=False,  # False en développement
    session_cookie_http_only=True,
    referrer_policy='strict-origin-when-cross-origin'
)

# ============================================
# 2.2 SÉCURITÉ - RATE LIMITING (Flask-Limiter)
# ============================================


limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "100 per hour"],
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
# Modèle pour les tokens de réinitialisation
class PasswordReset(db.Model):
    __tablename__ = 'password_resets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User', backref='password_resets')
    
    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(32)
    
    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at


# Fonction pour envoyer l'email de réinitialisation
def send_reset_email(user_email, username, reset_link):
    """Envoie un email de réinitialisation de mot de passe"""
    
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
            <h1>Réinitialisation de votre mot de passe</h1>
            <p>Bonjour {username},</p>
            <p>Vous avez demandé la réinitialisation de votre mot de passe. Cliquez sur le lien ci-dessous pour créer un nouveau mot de passe :</p>
            
            <a href="{reset_link}" class="button">Réinitialiser mon mot de passe</a>
            
            <p>Ce lien expirera dans 24 heures.</p>
            
            <div class="footer">
                <p>Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.</p>
                <p>© 2025 MuseumWiki · Collection d'œuvres d'art · Données Wikidata</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=user_email,
        subject='Bluetocus - Confirmation de votre email',
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


# Route API pour mot de passe oublié
@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    """Demande de réinitialisation de mot de passe"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email:
        return jsonify({'error': 'Email requis'}), 400
    
    user = User.query.filter_by(email=email).first()
    
    # Toujours répondre de la même façon pour éviter de révéler si l'email existe
    if not user:
        return jsonify({'message': 'Si cet email existe, un lien de réinitialisation a été envoyé'}), 200
    
    # Désactiver les anciens tokens
    old_resets = PasswordReset.query.filter_by(user_id=user.id, used=False).all()
    for r in old_resets:
        r.used = True
    
    # Créer un nouveau token
    token = PasswordReset.generate_token()
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    reset = PasswordReset(
        user_id=user.id,
        token=token,
        expires_at=expires_at
    )
    db.session.add(reset)
    db.session.commit()
    
    # Créer le lien de réinitialisation
    reset_link = f"{BASE_URL}/reset-password?token={token}"
    
    # Envoyer l'email
    if send_reset_email(email, user.username, reset_link):
        return jsonify({'message': 'Un email de réinitialisation a été envoyé'}), 200
    else:
        return jsonify({'error': "Erreur lors de l'envoi de l'email"}), 500


# Page de réinitialisation de mot de passe
@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Page de réinitialisation de mot de passe"""
    token = request.args.get('token', '')
    
    if request.method == 'POST':
        token = request.form.get('token', '')
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        reset = PasswordReset.query.filter_by(token=token, used=False).first()
        
        if not reset or not reset.is_valid():
            flash('Lien de réinitialisation invalide ou expiré', 'danger')
            return redirect(url_for('login'))
        
        if password != confirm_password:
            flash('Les mots de passe ne correspondent pas', 'danger')
            return render_template('reset_password.html', token=token)
        
        password_errors = validate_password_strength(password)
        if password_errors:
            for error in password_errors:
                flash(error, 'danger')
            return render_template('reset_password.html', token=token)
        
        user = reset.user
        user.set_password(password)
        reset.used = True
        db.session.commit()
        
        flash('Mot de passe modifié avec succès ! Vous pouvez vous connecter', 'success')
        return redirect(url_for('login'))
    
    # GET - afficher le formulaire
    reset = PasswordReset.query.filter_by(token=token, used=False).first()
    if not reset or not reset.is_valid():
        flash('Lien de réinitialisation invalide ou expiré', 'danger')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', token=token)


class Artwork(db.Model):
    __tablename__ = 'artworks'
    
    # Identifiants
    id = db.Column(db.String(50), primary_key=True)  # Q1000128
    
    # Labels / Titres
    label_fr = db.Column(db.Text)  # VARCHAR(500) → TEXT
    label_en = db.Column(db.Text)
    label_fallback_fr = db.Column(db.Text)
    label_fallback_en = db.Column(db.Text)
    
    # Créateurs
    creator_fr = db.Column(db.Text)
    creator_en = db.Column(db.Text)
    creator_fallback_fr = db.Column(db.Text)
    creator_fallback_en = db.Column(db.Text)
    
    # Dates et images
    inception = db.Column(db.Text)  
    image_url = db.Column(db.Text)  
    
    # Collections et lieux
    collection_fr = db.Column(db.Text)
    collection_en = db.Column(db.Text)
    location_fr = db.Column(db.Text)
    location_en = db.Column(db.Text)
    
    # Type d'œuvre
    instance_of_fr = db.Column(db.Text)
    instance_of_en = db.Column(db.Text)
    
    # Matériaux
    made_from_material_fr = db.Column(db.Text)
    made_from_material_en = db.Column(db.Text)
    
    # Genres
    genre_fr = db.Column(db.Text)
    genre_en = db.Column(db.Text)
    
    # Mouvements
    movement_fr = db.Column(db.Text)
    movement_en = db.Column(db.Text)
    
    # Dimensions (ceux-ci restent FLOAT)
    width = db.Column(db.Float)
    height = db.Column(db.Float)
    
    # Copyright
    copyright_status_fr = db.Column(db.Text)
    copyright_status_en = db.Column(db.Text)
    
    # URL Wikidata
    url_wikidata = db.Column(db.Text)  
    
    # Propriétés pour l'affichage multilingue
    @property
    def titre(self):
        """Retourne le titre dans la langue de la session"""
        if session.get('language') == 'fr':
            return self.label_fallback_fr or self.label_fr or 'Titre inconnu'
        else:
            return self.label_fallback_en or self.label_en or 'Unknown title'
    
    @property
    def titre_fr(self):
        """Retourne le titre en français"""
        return self.label_fallback_fr or self.label_fr or 'Titre inconnu'
    
    @property
    def titre_en(self):
        """Retourne le titre en anglais"""
        return self.label_fallback_en or self.label_en or 'Unknown title'
    
    @property
    def createur(self):
        """Retourne le créateur dans la langue de la session"""
        if session.get('language') == 'fr':
            return self.creator_fallback_fr or self.creator_fr or 'Artiste inconnu'
        else:
            return self.creator_fallback_en or self.creator_en or 'Unknown artist'
    
    
    
    @property
    def lieu(self):
        """Retourne le lieu dans la langue de la session"""
        if session.get('language') == 'fr':
            return self.collection_fr or self.location_fr or 'Lieu inconnu'
        else:
            return self.collection_en or self.location_en or 'Unknown location'
    
    @property
    def mouvement(self):
        """Retourne le mouvement dans la langue de la session"""
        if session.get('language') == 'fr':
            return self.movement_fr or 'Mouvement inconnu'
        else:
            return self.movement_en or 'Unknown movement'
    
    @property
    def genre_display(self):
        """Retourne le genre dans la langue de la session"""
        if session.get('language') == 'fr':
            return self.genre_fr or 'Genre inconnu'
        else:
            return self.genre_en or 'Unknown genre'
    
    @property
    def date(self):
        """Retourne la date (alias pour inception)"""
        return self.inception
    
    @property
    def wikidata_url(self):
        """Retourne l'URL Wikidata (alias)"""
        return self.url_wikidata
    
    @property
    def instance_of(self):
        """Retourne le type d'œuvre en français (alias)"""
        return self.instance_of_fr or 'Type inconnu'
    
    @property
    def copyright(self):
        """Retourne le copyright en français (alias)"""
        return self.copyright_status_fr or self.copyright_status_en or 'Inconnu'
    
    def to_dict(self):
        """Convertit l'objet en dictionnaire pour les templates"""
        return {
            'id': self.id,
            'titre': self.titre,
            'titre_fr': self.titre_fr,
            'titre_en': self.titre_en,
            'createur': self.createur,  
            'creator_fr': self.creator_fr,
            'creator_en': self.creator_en,
            'creator_fallback_fr': self.creator_fallback_fr,
            'creator_fallback_en': self.creator_fallback_en,
            'date': self.date,
            'inception': self.inception,
            'image_url': self.image_url,
            'lieu': self.lieu,
            'location_fr': self.location_fr,
            'location_en': self.location_en,
            'collection_fr': self.collection_fr,
            'collection_en': self.collection_en,
            'genre': self.genre_display,
            'genre_fr': self.genre_fr,
            'genre_en': self.genre_en,
            'mouvement': self.mouvement,
            'movement_fr': self.movement_fr,
            'movement_en': self.movement_en,
            'wikidata_url': self.wikidata_url,
            'url_wikidata': self.url_wikidata,
            'instance_of': self.instance_of,
            'instance_of_fr': self.instance_of_fr,
            'instance_of_en': self.instance_of_en,
            'copyright': self.copyright,
            'copyright_status_fr': self.copyright_status_fr,
            'copyright_status_en': self.copyright_status_en,
            'width': self.width,
            'height': self.height
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
            <h1>Bienvenue sur Bluetocus, {username} !</h1>
            <p>Veuillez utiliser le code de vérification ci-dessous :</p>
            
            <div class="code">{code}</div>
            
            <p>Le lien de vérification:</p>
            <a href="{verification_link}" class="button">Vérifier mon email</a>
            
            <p>Ce code et ce lien expireront dans 24 heures.</p>
            
            <div class="footer">
                <p>Si vous n'avez pas créé de compte sur Bluetocus, ignorez cet email.</p>
                <p>© 2026 Bluetocus</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=user_email,
        subject='Bluetocus - Confirmation de votre email',
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


def get_filtered_query(query, artists, museums, movements, types=None, genres=None, copyrights=None):
    """Construit une requête SQLAlchemy filtrée pour les œuvres"""
    q = Artwork.query
    
    if query:
        search = f"%{query}%"
        q = q.filter(
            (Artwork.label_fr.ilike(search)) |
            (Artwork.label_en.ilike(search)) |
            (Artwork.label_fallback_fr.ilike(search)) |
            (Artwork.label_fallback_en.ilike(search)) |
            (Artwork.creator_fr.ilike(search)) |
            (Artwork.creator_en.ilike(search)) |
            (Artwork.creator_fallback_fr.ilike(search)) |
            (Artwork.creator_fallback_en.ilike(search)) |
            (Artwork.location_fr.ilike(search)) |
            (Artwork.location_en.ilike(search)) |
            (Artwork.collection_fr.ilike(search)) |
            (Artwork.collection_en.ilike(search)) |
            (Artwork.genre_fr.ilike(search)) |
            (Artwork.genre_en.ilike(search))
        )
    
    if artists:
        artist_filters = []
        for artist in artists:
            artist_filters.append(Artwork.creator_fr.ilike(f"%{artist}%"))
            artist_filters.append(Artwork.creator_en.ilike(f"%{artist}%"))
            artist_filters.append(Artwork.creator_fallback_fr.ilike(f"%{artist}%"))
            artist_filters.append(Artwork.creator_fallback_en.ilike(f"%{artist}%"))
        q = q.filter(db.or_(*artist_filters))
    
    if museums:
        museum_filters = []
        for museum in museums:
            museum_filters.append(Artwork.location_fr.ilike(f"%{museum}%"))
            museum_filters.append(Artwork.location_en.ilike(f"%{museum}%"))
            museum_filters.append(Artwork.collection_fr.ilike(f"%{museum}%"))
            museum_filters.append(Artwork.collection_en.ilike(f"%{museum}%"))
        q = q.filter(db.or_(*museum_filters))
    
    if movements:
        movement_filters = []
        for movement in movements:
            movement_filters.append(Artwork.movement_fr.ilike(f"%{movement}%"))
            movement_filters.append(Artwork.movement_en.ilike(f"%{movement}%"))
        q = q.filter(db.or_(*movement_filters))
    
    # NOUVEAUX FILTRES
    if types:
        type_filters = []
        for type_name in types:
            type_filters.append(Artwork.instance_of_fr.ilike(f"%{type_name}%"))
            type_filters.append(Artwork.instance_of_en.ilike(f"%{type_name}%"))
        q = q.filter(db.or_(*type_filters))
    
    if genres:
        genre_filters = []
        for genre in genres:
            genre_filters.append(Artwork.genre_fr.ilike(f"%{genre}%"))
            genre_filters.append(Artwork.genre_en.ilike(f"%{genre}%"))
        q = q.filter(db.or_(*genre_filters))
    
    if copyrights:
        copyright_filters = []
        for copyright in copyrights:
            copyright_filters.append(Artwork.copyright_status_fr.ilike(f"%{copyright}%"))
            copyright_filters.append(Artwork.copyright_status_en.ilike(f"%{copyright}%"))
        q = q.filter(db.or_(*copyright_filters))

    return q  # ← MAINTENANT BIEN INDENTÉ AU NIVEAU DE LA FONCTION


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
# 4.1 VALIDATION DES MOTS DE PASSE (AJOUTE ICI)
# ============================================

def validate_password_strength(password):
    """Valide la force du mot de passe et retourne une liste d'erreurs"""
    errors = []
    
    if len(password) < 8:
        errors.append("8 caractères minimum")
    
    if not re.search(r"[A-Z]", password):
        errors.append("une majuscule requise")
    
    if not re.search(r"[a-z]", password):
        errors.append("une minuscule requise")
    
    if not re.search(r"[0-9]", password):
        errors.append("un chiffre requis")
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        errors.append("un caractère spécial requis")
    
    # Mots de passe courants à éviter
    common_passwords = [
        'password', '123456', 'qwerty', 'admin', 'password123', 
        'azerty', 'motdepasse', '12345678', '111111', '123456789',
        '000000', 'abc123', 'password1', '12345', 'letmein',
        'monkey', 'football', 'iloveyou', '123123', '654321'
    ]
    
    if password.lower() in common_passwords:
        errors.append("mot de passe trop commun")
    
    return errors

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
# 6. ROUTES PRINCIPALES
# ============================================

@app.route('/set-language/<lang>')
def set_language(lang):
    """Change la langue de l'interface"""
    if lang in ['fr', 'en']:
        session['language'] = lang
    # Rediriger vers la page précédente
    return redirect(request.referrer or url_for('index'))

@app.route('/')
def index():
    """Page d'accueil avec recherche, filtres, tris et scroll infini"""
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    artists = request.args.getlist('artist')
    museums = request.args.getlist('museum')
    movements = request.args.getlist('movement')
    
    # Nouveaux filtres
    types = request.args.getlist('type')
    genres = request.args.getlist('genre')
    copyrights = request.args.getlist('copyright')
    
    sort = request.args.get('sort', 'relevance')
    
    # Détection des requêtes AJAX pour le scroll infini
    is_ajax = request.args.get('ajax', '0') == '1'
    
    # Vérifier TOUS les filtres
    if (query or artists or museums or movements or 
        types or genres or copyrights):
        
        # Passer TOUS les filtres à get_filtered_query
        base_query = get_filtered_query(
            query, artists, museums, movements, 
            types, genres, copyrights
        )
        
        # GESTION DU TRI
        if sort == 'date_asc':
            base_query = base_query.order_by(Artwork.inception)
        elif sort == 'date_desc':
            base_query = base_query.order_by(Artwork.inception.desc())
        elif sort == 'title_asc':
            # Trier par titre selon la langue
            if session.get('language') == 'fr':
                base_query = base_query.order_by(Artwork.label_fallback_fr, Artwork.label_fr)
            else:
                base_query = base_query.order_by(Artwork.label_fallback_en, Artwork.label_en)
        elif sort == 'title_desc':
            if session.get('language') == 'fr':
                base_query = base_query.order_by(Artwork.label_fallback_fr.desc(), Artwork.label_fr.desc())
            else:
                base_query = base_query.order_by(Artwork.label_fallback_en.desc(), Artwork.label_en.desc())
        elif sort == 'artist_asc':
            if session.get('language') == 'fr':
                base_query = base_query.order_by(Artwork.creator_fallback_fr, Artwork.creator_fr)
            else:
                base_query = base_query.order_by(Artwork.creator_fallback_en, Artwork.creator_en)
        elif sort == 'artist_desc':
            if session.get('language') == 'fr':
                base_query = base_query.order_by(Artwork.creator_fallback_fr.desc(), Artwork.creator_fr.desc())
            else:
                base_query = base_query.order_by(Artwork.creator_fallback_en.desc(), Artwork.creator_en.desc())
        
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
    
    # Calculer le nombre de favoris pour chaque œuvre
    favorite_counts = {}
    for artwork in results_page:
        count = Favorite.query.filter_by(artwork_id=artwork.id).count()
        favorite_counts[artwork.id] = count
    
    # Pour l'affichage, on utilise les propriétés .titre et .createur
    # qui gèrent automatiquement la langue de la session
    results_dicts = []
    for artwork in results_page:
        artwork_dict = artwork.to_dict()
        results_dicts.append(artwork_dict)
    
    # 👇 SI C'EST UNE REQUÊTE AJAX (SCROLL INFINI), ON RENVOIE SEULEMENT LES CARTES
    if is_ajax:
        from flask import render_template_string
        
        card_template = '''
        {% for artwork in results %}
        <a href="/oeuvre/{{ artwork.id }}" class="work-card" style="text-decoration: none; color: inherit; display: block; position: relative; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 6px rgba(44,62,80,0.05); border: 1px solid #e0d6c8;">
            <!-- BOUTON FAVORI -->
            <div class="favorite-icon" data-artwork-id="{{ artwork.id }}" onclick="event.preventDefault(); event.stopPropagation(); toggleFavorite('{{ artwork.id }}', this)">
                <i class="far fa-heart" id="favorite-icon-{{ artwork.id }}"></i>
            </div>
            
            <!-- Image carrée -->
            {% if artwork.image_url and artwork.image_url != '' %}
            <img src="{{ artwork.image_url }}" alt="{{ artwork.titre_fr or artwork.titre_en or 'Sans titre' }}" class="work-image" loading="lazy" style="width: 100%; aspect-ratio: 1/1; object-fit: contain; background: #f5f0e8;">
            {% else %}
            <div class="work-image-placeholder" style="width: 100%; aspect-ratio: 1/1; background: linear-gradient(145deg, #e6d8c3, #d4c9b9); display: flex; align-items: center; justify-content: center; color: #5d6d7e; font-size: 2rem;">
                <i class="fas fa-image"></i>
            </div>
            {% endif %}
            
            <!-- Informations -->
            <div style="padding: 0.4rem;">
                <div class="artwork-title" title="{{ artwork.titre }}">{{ artwork.titre if artwork.titre else 'Sans titre' }}</div>
                <div class="artwork-artist" title="{{ artwork.createur }}">{{ artwork.createur }}</div>
            </div>
        </a>
        {% endfor %}
        '''
        
        return render_template_string(card_template, results=results_dicts)
    
    # 👇 SINON (REQUÊTE NORMALE), ON RENVOIE LA PAGE COMPLÈTE
    return render_template('index.html', 
                         query=query,
                         results=results_dicts,
                         count=pagination.total,
                         page=page,
                         total_pages=pagination.pages,
                         artists=artists,
                         museums=museums,
                         movements=movements,
                         types=types,
                         genres=genres,
                         copyrights=copyrights,
                         sort=sort,
                         favorite_counts=favorite_counts)

@app.route('/oeuvre/<string:oeuvre_id>')
def oeuvre_detail(oeuvre_id):
    # Chercher d'abord par id (Q1000659)
    artwork = Artwork.query.filter_by(id=oeuvre_id).first()
    
    # Si pas trouvé, chercher par id_q (l'URL complète)
    if not artwork:
        artwork = Artwork.query.filter_by(id_q=oeuvre_id).first()
    
    # Si toujours pas trouvé, chercher par id_q qui contient l'ID
    if not artwork:
        artwork = Artwork.query.filter(Artwork.id_q.like(f'%{oeuvre_id}%')).first()
    
    if artwork:
        return render_template('detail.html', oeuvre=artwork.to_dict())
    else:
        return "Œuvre non trouvée", 404
@app.route('/28012003')
def kathy_page():
    return render_template('28012003.html')
    
    
@app.route('/api/filters/update')
def api_filters_update():
    """Retourne tous les filtres mis à jour en fonction des filtres actuels"""
    query = request.args.get('q', '')
    current_artists = request.args.getlist('artist')
    current_museums = request.args.getlist('museum')
    current_movements = request.args.getlist('movement')
    current_types = request.args.getlist('type')
    current_genres = request.args.getlist('genre')
    current_copyrights = request.args.getlist('copyright')
    
    # Obtenir la requête de base avec tous les filtres actuels
    base_query = get_filtered_query(
        query, 
        current_artists, 
        current_museums, 
        current_movements,
        current_types,
        current_genres,
        current_copyrights
    )
    
    # Récupérer les IDs des œuvres filtrées
    filtered_ids = base_query.with_entities(Artwork.id).subquery()
    
    def get_filter_counts_bilingual(field_fr, field_en):
        """Retourne les filtres dans la langue de la session"""
        filter_query = db.session.query(
            field_fr.label('name_fr'),
            field_en.label('name_en'),
            func.count(Artwork.id).label('count')
        ).filter(Artwork.id.in_(filtered_ids))
        
        filter_query = filter_query.filter(
            field_fr != 'Inconnu',
            field_fr != '',
            field_fr.isnot(None)
        )
        
        results = filter_query.group_by(field_fr, field_en).order_by(func.count(Artwork.id).desc()).limit(30).all()
        
        formatted_results = []
        for r in results:
            if session.get('language') == 'fr':
                name = r.name_fr or r.name_en or 'Inconnu'
            else:
                name = r.name_en or r.name_fr or 'Unknown'
            formatted_results.append({'name': name, 'count': r.count})
        
        return formatted_results
    
    # Récupérer tous les filtres
    artists = get_filter_counts_bilingual(Artwork.creator_fallback_fr, Artwork.creator_fallback_en)
    museums = get_filter_counts_bilingual(Artwork.collection_fr, Artwork.collection_en)
    movements = get_filter_counts_bilingual(Artwork.movement_fr, Artwork.movement_en)
    types = get_filter_counts_bilingual(Artwork.instance_of_fr, Artwork.instance_of_en)
    
    return jsonify({
        'artists': artists,
        'museums': museums,
        'movements': movements,
        'types': types,
        'genres': [],
        'copyrights': []
    })
        
# ============================================
# 7. API POUR LES NOUVEAUX FILTRES
# ============================================
@app.route('/api/quick-register', methods=['POST'])
def quick_register():
    """Inscription rapide depuis la modale"""
    data = request.get_json()
    
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    errors = []
    
    # Validations
    if not username or not email or not password:
        return jsonify({'error': 'Tous les champs sont obligatoires'}), 400
    
    # Validation du mot de passe
    password_errors = validate_password_strength(password)
    if password_errors:
        return jsonify({'errors': password_errors}), 400
    
    # Vérifier si l'utilisateur existe déjà
    existing_user = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()
    
    if existing_user:
        if existing_user.username == username:
            return jsonify({'error': 'Ce nom d\'utilisateur est déjà pris'}), 400
        if existing_user.email == email:
            return jsonify({'error': 'Cet email est déjà utilisé'}), 400
    
    try:
        # Créer l'utilisateur
        user = User(
            username=username,
            email=email,
            email_verified=False
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        
        # Créer la vérification
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
        
        # Envoyer l'email
        if send_verification_email(email, username, code, token):
            return jsonify({
                'success': True,
                'message': 'Inscription réussie ! Un email de vérification vous a été envoyé.',
                'email': email
            }), 200
        else:
            return jsonify({
                'success': True,
                'message': 'Compte créé mais erreur d\'envoi d\'email. Contactez le support.',
                'email': email
            }), 200
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur inscription rapide: {e}")
        return jsonify({'error': 'Erreur lors de l\'inscription'}), 500

@app.route('/api/instance_of')
def api_instance_of():
    """Retourne la liste des types d'œuvres avec leur nombre"""
    query = request.args.get('q', '')
    current_artists = request.args.getlist('artist')
    current_museums = request.args.getlist('museum')
    current_movements = request.args.getlist('movement')
    
    base_query = get_filtered_query(query, current_artists, current_museums, current_movements)
    
    # Récupérer les IDs filtrés
    filtered_ids = base_query.with_entities(Artwork.id).subquery()
    
    results = db.session.query(
        Artwork.instance_of_fr.label('name_fr'),
        Artwork.instance_of_en.label('name_en'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.id.in_(filtered_ids),
        Artwork.instance_of_fr != 'Inconnu',
        Artwork.instance_of_fr != '',
        Artwork.instance_of_fr.isnot(None)
    ).group_by(
        Artwork.instance_of_fr, Artwork.instance_of_en
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    # Formater selon la langue
    formatted_results = []
    for r in results:
        if session.get('language') == 'fr':
            name = r.name_fr or r.name_en or 'Inconnu'
        else:
            name = r.name_en or r.name_fr or 'Unknown'
        formatted_results.append({'name': name, 'count': r.count})
    
    return jsonify(formatted_results)

"""
@app.route('/api/genres')
def api_genres():
    query = request.args.get('q', '')
    current_artists = request.args.getlist('artist')
    current_museums = request.args.getlist('museum')
    current_movements = request.args.getlist('movement')
    
    base_query = get_filtered_query(query, current_artists, current_museums, current_movements)
    
    # Récupérer les IDs filtrés
    filtered_ids = base_query.with_entities(Artwork.id).subquery()
    
    results = db.session.query(
        Artwork.genre_fr.label('name_fr'),
        Artwork.genre_en.label('name_en'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.id.in_(filtered_ids),
        Artwork.genre_fr != 'Inconnu',
        Artwork.genre_fr != '',
        Artwork.genre_fr.isnot(None)
    ).group_by(
        Artwork.genre_fr, Artwork.genre_en
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    # Formater selon la langue
    formatted_results = []
    for r in results:
        if session.get('language') == 'fr':
            name = r.name_fr or r.name_en or 'Inconnu'
        else:
            name = r.name_en or r.name_fr or 'Unknown'
        formatted_results.append({'name': name, 'count': r.count})
    
    return jsonify(formatted_results)
"""

@app.route('/api/copyrights')
def api_copyrights():
    """Retourne la liste des statuts copyright avec leur nombre"""
    query = request.args.get('q', '')
    current_artists = request.args.getlist('artist')
    current_museums = request.args.getlist('museum')
    current_movements = request.args.getlist('movement')
    
    base_query = get_filtered_query(query, current_artists, current_museums, current_movements)
    
    filtered_ids = base_query.with_entities(Artwork.id).subquery()
    
    results = db.session.query(
        Artwork.copyright_status_fr.label('name_fr'),
        Artwork.copyright_status_en.label('name_en'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.id.in_(filtered_ids),
        Artwork.copyright_status_fr != 'Inconnu',
        Artwork.copyright_status_fr != '',
        Artwork.copyright_status_fr.isnot(None)
    ).group_by(
        Artwork.copyright_status_fr, Artwork.copyright_status_en
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    formatted_results = []
    for r in results:
        if session.get('language') == 'fr':
            name = r.name_fr or r.name_en or 'Inconnu'
        else:
            name = r.name_en or r.name_fr or 'Unknown'
        formatted_results.append({'name': name, 'count': r.count})
    
    return jsonify(formatted_results)

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
    current_types = request.args.getlist('type')
    current_genres = request.args.getlist('genre')
    current_copyrights = request.args.getlist('copyright')   
    base_query = get_filtered_query(query, current_artists, current_museums, current_movements)
    
    # Récupérer les IDs filtrés
    filtered_ids = base_query.with_entities(Artwork.id).subquery()
    
    results = db.session.query(
        Artwork.creator_fallback_fr.label('name_fr'),
        Artwork.creator_fallback_en.label('name_en'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.id.in_(filtered_ids),
        Artwork.creator_fallback_fr != 'Artiste inconnu',
        Artwork.creator_fallback_fr != '',
        Artwork.creator_fallback_fr.isnot(None)
    ).group_by(
        Artwork.creator_fallback_fr, Artwork.creator_fallback_en
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    # Formater selon la langue
    formatted_results = []
    for r in results:
        if session.get('language') == 'fr':
            name = r.name_fr or r.name_en or 'Artiste inconnu'
        else:
            name = r.name_en or r.name_fr or 'Unknown artist'
        formatted_results.append({'name': name, 'count': r.count})
    
    return jsonify(formatted_results)


@app.route('/api/museums')
def api_museums():
    """Retourne la liste des musées avec leur nombre d'œuvres"""
    query = request.args.get('q', '')
    current_artists = request.args.getlist('artist')
    current_museums = request.args.getlist('museum')
    current_movements = request.args.getlist('movement')
    current_types = request.args.getlist('type')
    current_genres = request.args.getlist('genre')
    current_copyrights = request.args.getlist('copyright')
    base_query = get_filtered_query(query, current_artists, current_museums, current_movements)
    
    # Récupérer les IDs filtrés
    filtered_ids = base_query.with_entities(Artwork.id).subquery()
    
    results = db.session.query(
        Artwork.location_fr.label('name_fr'),
        Artwork.location_en.label('name_en'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.id.in_(filtered_ids),
        Artwork.location_fr != 'Lieu inconnu',
        Artwork.location_fr != '',
        Artwork.location_fr.isnot(None)
    ).group_by(
        Artwork.location_fr, Artwork.location_en
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    # Formater selon la langue
    formatted_results = []
    for r in results:
        if session.get('language') == 'fr':
            name = r.name_fr or r.name_en or 'Lieu inconnu'
        else:
            name = r.name_en or r.name_fr or 'Unknown location'
        formatted_results.append({'name': name, 'count': r.count})
    
    return jsonify(formatted_results)


@app.route('/api/movements')
def api_movements():
    """Retourne la liste des mouvements avec leur nombre d'œuvres"""
    query = request.args.get('q', '')
    current_artists = request.args.getlist('artist')
    current_museums = request.args.getlist('museum')
    current_movements = request.args.getlist('movement')
    current_types = request.args.getlist('type')
    current_genres = request.args.getlist('genre')
    current_copyrights = request.args.getlist('copyright')    
    base_query = get_filtered_query(query, current_artists, current_museums, current_movements)
    
    # Récupérer les IDs filtrés
    filtered_ids = base_query.with_entities(Artwork.id).subquery()
    
    results = db.session.query(
        Artwork.movement_fr.label('name_fr'),
        Artwork.movement_en.label('name_en'),
        func.count(Artwork.id).label('count')
    ).filter(
        Artwork.id.in_(filtered_ids),
        Artwork.movement_fr != 'Mouvement inconnu',
        Artwork.movement_fr != '',
        Artwork.movement_fr.isnot(None)
    ).group_by(
        Artwork.movement_fr, Artwork.movement_en
    ).order_by(
        func.count(Artwork.id).desc()
    ).limit(30).all()
    
    # Formater selon la langue
    formatted_results = []
    for r in results:
        if session.get('language') == 'fr':
            name = r.name_fr or r.name_en or 'Mouvement inconnu'
        else:
            name = r.name_en or r.name_fr or 'Unknown movement'
        formatted_results.append({'name': name, 'count': r.count})
    
    return jsonify(formatted_results)


@app.route('/api/suggestions')
def suggestions():
    """API pour l'autocomplete - résultats dans la langue de la session"""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    search = f"%{query}%"
    lang = session.get('language', 'fr')  # Langue de la session (défaut: fr)
    
    suggestions_list = []
    
    # 1. RECHERCHE PAR ID (toujours affiché)
    id_results = db.session.query(Artwork.id).filter(
        Artwork.id.ilike(search)
    ).distinct().limit(2).all()
    
    for id_result in id_results:
        suggestions_list.append({'texte': id_result[0], 'categorie': 'id'})
    
    # 2. ARTISTES - selon la langue
    if lang == 'fr':
        artists = db.session.query(Artwork.creator_fallback_fr).filter(
            Artwork.creator_fallback_fr.ilike(search),
            Artwork.creator_fallback_fr != 'Artiste inconnu',
            Artwork.creator_fallback_fr != ''
        ).distinct().limit(4).all()
        artist_field = 'creator_fallback_fr'
    else:
        artists = db.session.query(Artwork.creator_fallback_en).filter(
            Artwork.creator_fallback_en.ilike(search),
            Artwork.creator_fallback_en != 'Unknown artist',
            Artwork.creator_fallback_en != ''
        ).distinct().limit(4).all()
        artist_field = 'creator_fallback_en'
    
    for artist in artists:
        suggestions_list.append({'texte': artist[0], 'categorie': 'artiste'})

    # 4. MUSÉES - selon la langue
    if lang == 'fr':
        museums = db.session.query(Artwork.collection_fr).filter(
            Artwork.collection_fr.ilike(search),
            Artwork.collection_fr != 'Inconnu',
            Artwork.collection_fr != ''
        ).distinct().limit(4).all()
    else:
        museums = db.session.query(Artwork.collection_en).filter(
            Artwork.collection_en.ilike(search),
            Artwork.collection_en != 'Unknown',
            Artwork.collection_en != ''
        ).distinct().limit(4).all()
    
    for museum in museums:
        suggestions_list.append({'texte': museum[0], 'categorie': 'musée'})

    # 3. TITRES - selon la langue
    if lang == 'fr':
        titles = db.session.query(Artwork.label_fallback_fr).filter(
            Artwork.label_fallback_fr.ilike(search),
            Artwork.label_fallback_fr != 'Titre inconnu',
            Artwork.label_fallback_fr != ''
        ).distinct().limit(4).all()
    else:
        titles = db.session.query(Artwork.label_fallback_en).filter(
            Artwork.label_fallback_en.ilike(search),
            Artwork.label_fallback_en != 'Unknown title',
            Artwork.label_fallback_en != ''
        ).distinct().limit(4).all()
    
    for title in titles:
        suggestions_list.append({'texte': title[0], 'categorie': 'œuvre'})
    

    
    return jsonify(suggestions_list[:12])



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

@app.route('/easteregg')
def easteregg():
    """Page easter egg surprise"""
    return render_template('easteregg.html')

@app.route('/about')
def about():
    """Page à propos avec statistiques dynamiques"""
    try:
        # Forcer une connexion à la base
        db.session.execute(text('SELECT 1'))
        
        # Statistiques avec gestion d'erreur
        total_oeuvres = Artwork.query.count()
        print(f"📊 about - total_oeuvres: {total_oeuvres}")
        
        total_artistes = db.session.query(Artwork.creator_fallback_fr).filter(
            Artwork.creator_fallback_fr != 'Artiste inconnu',
            Artwork.creator_fallback_fr != '',
            Artwork.creator_fallback_fr.isnot(None)
        ).distinct().count()
        print(f"📊 about - total_artistes: {total_artistes}")
        
        total_musees = db.session.query(Artwork.location_fr).filter(
            Artwork.location_fr != 'Lieu inconnu',
            Artwork.location_fr != '',
            Artwork.location_fr.isnot(None)
        ).distinct().count()
        print(f"📊 about - total_musees: {total_musees}")
        
        total_users = User.query.count()
        print(f"📊 about - total_users: {total_users}")
        
        # Si tout est à 0 mais que tu sais que la base est pleine
        if total_oeuvres == 0:
            # Requête brute pour vérifier
            result = db.session.execute(text('SELECT COUNT(*) FROM artworks')).scalar()
            print(f"📊 about - COUNT brut artworks: {result}")
            total_oeuvres = result or 0
            
            result = db.session.execute(text('SELECT COUNT(DISTINCT creator_fallback_fr) FROM artworks WHERE creator_fallback_fr NOT IN (\'Artiste inconnu\', \'\')')).scalar()
            print(f"📊 about - COUNT brut artistes: {result}")
            total_artistes = result or 0
            
            result = db.session.execute(text('SELECT COUNT(DISTINCT location_fr) FROM artworks WHERE location_fr NOT IN (\'Lieu inconnu\', \'\')')).scalar()
            print(f"📊 about - COUNT brut musees: {result}")
            total_musees = result or 0
        
        last_update = datetime.now().strftime('%d/%m/%Y à %H:%M')
        
        return render_template('about.html',
                             total_oeuvres=total_oeuvres,
                             total_artistes=total_artistes,
                             total_musees=total_musees,
                             total_users=total_users,
                             last_update=last_update)
    except Exception as e:
        print(f"❌ Erreur dans about: {e}")
        # Valeurs de fallback (non nulles pour le test)
        return render_template('about.html',
                             total_oeuvres=560,  # Fallback avec tes vraies données
                             total_artistes=350,
                             total_musees=45,
                             total_users=5,
                             last_update=datetime.now().strftime('%d/%m/%Y à %H:%M'))

# ============================================
# 9. ROUTES D'AUTHENTIFICATION
# ============================================

@limiter.limit("3 per minute")
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Page d'inscription sans confirmation de mot de passe"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        # ✅ PLUS DE confirm_password
        
        print("\n" + "="*50)
        print(f"🔍 NOUVELLE TENTATIVE D'INSCRIPTION")
        print(f"📝 Username: {username}")
        print(f"📧 Email: {email}")
        print("="*50)
        
        errors = []
        
        # ✅ CORRECTION ICI : SUPPRIMEZ 'or not confirm_password'
        if not username or not email or not password:
            errors.append("Tous les champs sont obligatoires")

        
        password_errors = validate_password_strength(password)
        errors.extend(password_errors)
        
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
    """Page de connexion avec email et redirection"""
    
    # 👇 1. RÉCUPÉRER L'URL DE REDIRECTION (depuis l'URL)
    next_url = request.args.get('next', '')
    
    if request.method == 'POST':
        # 👇 2. RÉCUPÉRER AUSSI DU FORMULAIRE (champ caché)
        next_url = request.form.get('next', next_url)
        
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        print(f"\n🔍 TENTATIVE DE CONNEXION")
        print(f"📧 Email: {email}")
        print(f"↪️ Next URL: {next_url}")  # 👈 Ajoute ce print
        
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
            session['username'] = user.username
            
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            print(f"✅ Connexion réussie pour {user.username}")
            flash(f'Bienvenue {user.username} !', 'success')
            
            # 👇 3. REDIRECTION INTELLIGENTE
            if next_url and next_url.startswith('/'):
                # Sécurité : seulement les URLs relatives
                return redirect(next_url)
            return redirect(url_for('index'))
        else:
            print("❌ Email ou mot de passe incorrect")
            flash('Email ou mot de passe incorrect', 'danger')
    
    return render_template('login.html', next=next_url)  # 👈 Passe next au template



@app.route('/logout')
def logout():
    """Déconnexion avec retour à la page précédente"""
    
    # 👇 RÉCUPÈRE L'URL DE REDIRECTION
    next_url = request.args.get('next', '')
    
    # Déconnexion
    session.clear()
    flash('Vous avez été déconnecté', 'info')
    
    # 👇 REDIRECTION
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
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


@app.route('/api/update-username', methods=['POST'])
def update_username():
    """Modifier le nom d'utilisateur"""
    print("="*50)
    print("🔵 Route update-username appelée")
    print(f"Session user_id: {session.get('user_id')}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Data brute: {request.get_data()}")
    
    try:
        data = request.get_json()
        print(f"JSON parsé: {data}")
    except Exception as e:
        print(f"❌ Erreur parsing JSON: {e}")
        return jsonify({'error': 'Format JSON invalide'}), 400
    
    if 'user_id' not in session:
        print("❌ Utilisateur non connecté")
        return jsonify({'error': 'Non connecté'}), 401
    
    if not data:
        return jsonify({'error': 'Données invalides'}), 400
    
    new_username = data.get('username', '').strip()
    print(f"Nouveau username: {new_username}")
    
    if not new_username:
        return jsonify({'error': 'Nom d\'utilisateur requis'}), 400
    
    if len(new_username) > 80:
        return jsonify({'error': 'Nom d\'utilisateur trop long (max 80 caractères)'}), 400
    
    # Vérifier si le nom d'utilisateur est déjà pris
    existing_user = User.query.filter_by(username=new_username).first()
    if existing_user and existing_user.id != session['user_id']:
        return jsonify({'error': 'Ce nom d\'utilisateur est déjà pris'}), 400
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'Utilisateur non trouvé'}), 404
            
        old_username = user.username
        user.username = new_username
        session['username'] = new_username
        db.session.commit()
        
        print(f"✅ Username changé: {old_username} -> {new_username}")
        
        return jsonify({
            'success': True, 
            'message': 'Nom d\'utilisateur modifié avec succès'
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur BD: {e}")
        logger.error(f"Erreur modification username: {e}")
        return jsonify({'error': 'Erreur lors de la modification'}), 500
        
        
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
        
        password_errors = validate_password_strength(new_password)
        errors.extend(password_errors)
        
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
    """Vérification par lien avec connexion automatique"""
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
    
    # ✅ CONNEXION AUTOMATIQUE
    session['user_id'] = user.id
    session['username'] = user.username
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    flash(f'Bienvenue {user.username} ! Votre email a été vérifié.', 'success')
    return redirect(url_for('index'))

@app.route('/verify-code', methods=['POST'])
def verify_code():
    """Vérification par code avec connexion automatique"""
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
    
    # ✅ Marquer l'email comme vérifié
    user.email_verified = True
    verification.used = True
    db.session.commit()
    
    # ✅ CONNEXION AUTOMATIQUE
    session['user_id'] = user.id
    session['username'] = user.username
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    flash(f'Bienvenue {user.username} ! Votre email a été vérifié.', 'success')
    return redirect(url_for('index'))

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
@app.route('/api/quick-login', methods=['POST'])
def quick_login():
    """Connexion rapide depuis la modale"""
    data = request.get_json()
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email et mot de passe requis'}), 400
    
    user = User.query.filter_by(email=email).first()
    
    if not user or not user.check_password(password):
        return jsonify({'error': 'Email ou mot de passe incorrect'}), 401
    
    if not user.email_verified:
        return jsonify({'error': 'Veuillez vérifier votre email avant de vous connecter'}), 401
    
    # Connexion réussie
    session['user_id'] = user.id
    session['username'] = user.username
    
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Connexion réussie',
        'username': user.username
    }), 200
    
    
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
    print("🔵 save_rating appelée")
    print("Session user_id:", session.get('user_id'))
    
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    print("Données reçues:", data)
    
    artwork_id = data.get('artwork_id')
    
    def validate_note(note):
        try:
            n = float(note)
            return n >= 0 and n <= 5 and (n * 2).is_integer()
        except:
            return False
    
    # Validation avec valeurs par défaut à 0 si non présentes
    if not all([
        validate_note(data.get('note_globale', 0)),
        validate_note(data.get('note_technique', 0)),
        validate_note(data.get('note_originalite', 0)),
        validate_note(data.get('note_emotion', 0))
    ]):
        print("❌ Notes invalides")
        return jsonify({'error': 'Notes invalides'}), 400
    
    rating = Rating.query.filter_by(
        user_id=session['user_id'],
        artwork_id=artwork_id
    ).first()
    
    if rating:
        print("🔄 Mise à jour note existante")
        rating.note_globale = float(data.get('note_globale', 0))
        rating.note_technique = float(data.get('note_technique', 0))
        rating.note_originalite = float(data.get('note_originalite', 0))
        rating.note_emotion = float(data.get('note_emotion', 0))
        rating.commentaire = data.get('commentaire', '')
        message = 'Note mise à jour'
    else:
        print("➕ Création nouvelle note")
        rating = Rating(
            user_id=session['user_id'],
            artwork_id=artwork_id,
            note_globale=float(data.get('note_globale', 0)),
            note_technique=float(data.get('note_technique', 0)),
            note_originalite=float(data.get('note_originalite', 0)),
            note_emotion=float(data.get('note_emotion', 0)),
            commentaire=data.get('commentaire', '')
        )
        db.session.add(rating)
        message = 'Note enregistrée'
    
    db.session.commit()
    print("✅ Note sauvegardée, ID:", rating.id)
    
    return jsonify({
        'success': True,
        'message': message,
        'rating': rating.to_dict()
    })

# 👇 ICI tu peux ajouter la nouvelle fonction delete_rating
@app.route('/api/rating/delete', methods=['POST'])
def delete_rating():
    """Supprime la note et le commentaire de l'utilisateur"""
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    artwork_id = data.get('artwork_id')
    
    rating = Rating.query.filter_by(
        user_id=session['user_id'],
        artwork_id=artwork_id
    ).first()
    
    if rating:
        db.session.delete(rating)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Commentaire supprimé'})
    else:
        return jsonify({'error': 'Commentaire non trouvé'}), 404


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
        
        
        
@app.route('/api/rated-works')
def get_rated_works():
    if 'user_id' not in session:
        return jsonify({'works': [], 'hasMore': False})
    
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 32))
    offset = (page - 1) * limit
    
    ratings = Rating.query.filter_by(user_id=session['user_id'])\
        .order_by(Rating.created_at.desc())\
        .offset(offset)\
        .limit(limit + 1)\
        .all()
    
    has_more = len(ratings) > limit
    ratings = ratings[:limit]
    
    works_data = []
    for rating in ratings:
        artwork = Artwork.query.get(rating.artwork_id)
        if artwork:
            work_data = artwork.to_dict()
            work_data['rating'] = rating.to_dict()
            work_data['is_favorite'] = Favorite.query.filter_by(
                user_id=session['user_id'],
                artwork_id=artwork.id
            ).first() is not None
            works_data.append(work_data)
    
    return jsonify({
        'works': works_data,
        'hasMore': has_more,
        'page': page,
        'total': len(works_data)
    })

@app.route('/mes-oeuvres')
def my_rated_works():
    """Page des œuvres notées"""
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour voir vos œuvres notées', 'warning')
        return redirect(url_for('login'))
    
    print(f"\n🔍 DEBUG - User ID: {session['user_id']}")
    
    # Récupérer les notes de l'utilisateur
    ratings = Rating.query.filter_by(user_id=session['user_id']).all()
    print(f"📊 Nombre de ratings trouvés: {len(ratings)}")
    
    if ratings:
        for r in ratings:
            print(f"   - Rating ID: {r.id}, artwork_id: {r.artwork_id}")
    
    works = []
    for rating in ratings:
        artwork = Artwork.query.get(rating.artwork_id)
        if artwork:
            print(f"✅ Artwork trouvé: {artwork.id} - {artwork.titre_fr}")
            work_data = artwork.to_dict()
            work_data['rating'] = rating.to_dict()
            
            # Vérifier si l'œuvre est en favori
            favorite = Favorite.query.filter_by(
                user_id=session['user_id'],
                artwork_id=artwork.id
            ).first()
            work_data['is_favorite'] = favorite is not None
            
            works.append(work_data)
        else:
            print(f"❌ Artwork NON trouvé pour rating.artwork_id: {rating.artwork_id}")
    
    print(f"🏁 Nombre d'œuvres finales: {len(works)}")
    
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
        site_name="Bluetocus",
        current_year=datetime.now().year,
        now=datetime.now(),
        is_authenticated='user_id' in session,
        current_user=session.get('username', ''),
        current_language=session.get('language', 'fr')  # AJOUTER ICI
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
