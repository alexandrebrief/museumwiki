#!/usr/bin/env python3
"""
Application Flask - POLOUM
Plateforme de notation et découverte d'œuvres d'art
"""

# ============================================================
# IMPORTS
# ============================================================
import requests
import random
import json
import logging
import os
import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from functools import lru_cache

from dotenv import load_dotenv
load_dotenv()

from flask import (Flask, flash, jsonify, redirect, render_template,
                   render_template_string, request, session, url_for, make_response)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, inspect, text, Index, case
from werkzeug.security import check_password_hash, generate_password_hash

# ============================================================
# CONFIGURATION DE L'APPLICATION
# ============================================================

SITE_NAME = 'POLOUM'
app = Flask(__name__)

# --- Configuration de base ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise ValueError("SECRET_KEY n'est pas définie")

# --- Base de données PostgreSQL ---
_DB_USER = os.environ.get('DB_USER')
_DB_PASSWORD = os.environ.get('DB_PASSWORD')
_DB_HOST = os.environ.get('DB_HOST')
_DB_NAME = os.environ.get('DB_NAME')

if not all([_DB_USER, _DB_PASSWORD, _DB_HOST, _DB_NAME]):
    raise ValueError("Variables d'environnement DB_* incomplètes")

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'postgresql://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}/{_DB_NAME}'
)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'max_overflow': 20,
    'pool_pre_ping': True,
    'pool_recycle': 3600,
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Session permanente ---
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# --- Services externes ---
MAILGUN_API_KEY = os.environ.get('MAILGUN_API_KEY', '')
MAILGUN_DOMAIN = os.environ.get('MAILGUN_DOMAIN', '')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'contact@poloum.com')
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

security_logger = logging.getLogger('security')
security_logger.setLevel(logging.WARNING)
_sec_handler = RotatingFileHandler('security.log', maxBytes=10_000, backupCount=3)
_sec_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
security_logger.addHandler(_sec_handler)


# ============================================================
# EXTENSIONS
# ============================================================

db = SQLAlchemy(app)

Talisman(
    app,
    content_security_policy={
        'default-src': ["'self'"],
        'script-src': [
            "'self'", "'unsafe-inline'",
            "https://cdn.jsdelivr.net", "https://code.jquery.com",
            "https://cdnjs.cloudflare.com",
        ],
        'style-src': [
            "'self'", "'unsafe-inline'",
            "https://cdn.jsdelivr.net", "https://fonts.googleapis.com",
            "https://cdnjs.cloudflare.com",
        ],
        'font-src': [
            "'self'",
            "https://fonts.gstatic.com", "https://cdnjs.cloudflare.com",
        ],
        'img-src': ["'self'", "data:", "https:", "http:", "*"],
    },
    force_https=False,
    strict_transport_security=True,
    session_cookie_secure=False,
    session_cookie_http_only=True,
    referrer_policy='strict-origin-when-cross-origin',
)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="memory://",
)

csrf = CSRFProtect(app)


# ============================================================
# MODÈLES DE BASE DE DONNÉES
# ============================================================

# ---- Modèle Artwork (œuvre d'art) ----
class Artwork(db.Model):
    __tablename__ = 'artworks'

    id = db.Column(db.String(50), primary_key=True)
    label_fr = db.Column(db.Text)
    label_en = db.Column(db.Text)
    creator_id = db.Column(db.Text)
    creator_fr = db.Column(db.Text)
    creator_en = db.Column(db.Text)
    instance_of_id = db.Column(db.Text)
    instance_of_fr = db.Column(db.Text)
    instance_of_en = db.Column(db.Text)
    inception = db.Column(db.Text)
    image_url = db.Column(db.Text)
    collection_id = db.Column(db.Text)
    collection_fr = db.Column(db.Text)
    collection_en = db.Column(db.Text)
    location_id = db.Column(db.Text)
    location_fr = db.Column(db.Text)
    location_en = db.Column(db.Text)
    country_id = db.Column(db.Text)
    country_fr = db.Column(db.Text)
    country_en = db.Column(db.Text)
    city_id = db.Column(db.Text)
    city_fr = db.Column(db.Text)
    city_en = db.Column(db.Text)
    made_from_material_fr = db.Column(db.Text)
    made_from_material_en = db.Column(db.Text)
    genre_fr = db.Column(db.Text)
    genre_en = db.Column(db.Text)
    movement_fr = db.Column(db.Text)
    movement_en = db.Column(db.Text)
    width = db.Column(db.Float)
    height = db.Column(db.Float)
    copyright_status_fr = db.Column(db.Text)
    copyright_status_en = db.Column(db.Text)
    url_wikidata = db.Column(db.Text)

    @property
    def _lang(self):
        return session.get('language', 'fr')

    @property
    def titre(self):
        if self._lang == 'fr':
            return self.label_fr or self.label_en or 'Titre inconnu'
        return self.label_en or self.label_fr or 'Unknown title'

    @property
    def createur(self):
        if self._lang == 'fr':
            return self.creator_fr or self.creator_en or 'Artiste inconnu'
        return self.creator_en or self.creator_fr or 'Unknown artist'

    @property
    def lieu(self):
        if self._lang == 'fr':
            return self.collection_fr or self.location_fr or 'Lieu inconnu'
        return self.collection_en or self.location_en or 'Unknown location'

    @property
    def date(self):
        return self.inception

    def to_dict(self):
        lang = session.get('language', 'fr')
        return {
            'id': self.id,
            'titre': self.titre,
            'createur': self.createur,
            'date': self.date,
            'inception': self.inception,
            'image_url': self.image_url,
            'lieu': self.lieu,
            'instance_of': self.instance_of_fr if lang == 'fr' else self.instance_of_en,
            'instance_of_fr': self.instance_of_fr,
            'instance_of_en': self.instance_of_en,
            'made_from_material_fr': self.made_from_material_fr,
            'made_from_material_en': self.made_from_material_en,
            'genre_fr': self.genre_fr,
            'genre_en': self.genre_en,
            'movement_fr': self.movement_fr,
            'movement_en': self.movement_en,
            'width': self.width,
            'height': self.height,
            'copyright_status_fr': self.copyright_status_fr,
            'copyright_status_en': self.copyright_status_en,
            'url_wikidata': self.url_wikidata,
            'collection_fr': self.collection_fr,
            'collection_en': self.collection_en,
            'collection_id': self.collection_id,
            'location_fr': self.location_fr,
            'location_en': self.location_en,
            'country_fr': self.country_fr,
            'country_en': self.country_en,
            'city_fr': self.city_fr,
            'city_en': self.city_en,
        }


# ---- Modèle User (utilisateur) ----
class User(db.Model):
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


# ---- Modèle EmailVerification (vérification email) ----
class EmailVerification(db.Model):
    __tablename__ = 'email_verifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    user = db.relationship('User')

    @staticmethod
    def generate_code():
        return ''.join(secrets.choice('0123456789') for _ in range(6))

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(32)

    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at


# ---- Modèle Favorite (favoris) ----
class Favorite(db.Model):
    __tablename__ = 'favorites'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    artwork_id = db.Column(db.String, db.ForeignKey('artworks.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    artwork = db.relationship('Artwork', lazy='joined')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'artwork_id', name='unique_user_artwork_favorite'),
    )


# ---- Modèle ArtworkStats (statistiques des œuvres) ----
class ArtworkStats(db.Model):
    __tablename__ = 'artwork_stats'
    
    artwork_id = db.Column(db.String(50), primary_key=True)
    avg_rating = db.Column(db.Float, default=0)
    rating_count = db.Column(db.Integer, default=0)
    fav_count = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---- Modèle Rating (notes et commentaires) ----
class Rating(db.Model):
    __tablename__ = 'ratings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    artwork_id = db.Column(db.String, db.ForeignKey('artworks.id'), nullable=False)
    note_globale = db.Column(db.Float, nullable=False)
    note_technique = db.Column(db.Float, nullable=False)
    note_originalite = db.Column(db.Float, nullable=False)
    note_emotion = db.Column(db.Float, nullable=False)
    commentaire = db.Column(db.Text, nullable=True)
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'artwork_id', name='unique_user_artwork_rating'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'note_globale': self.note_globale,
            'note_technique': self.note_technique,
            'note_originalite': self.note_originalite,
            'note_emotion': self.note_emotion,
            'commentaire': self.commentaire,
            'is_public': self.is_public,
            'created_at': self.created_at.strftime('%d/%m/%Y'),
        }


# ---- Modèle PasswordReset (réinitialisation mot de passe) ----
class PasswordReset(db.Model):
    __tablename__ = 'password_resets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    user = db.relationship('User')

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(32)

    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at


# ---- Modèle VisitCounter (compteur de visites) ----
class VisitCounter(db.Model):
    __tablename__ = 'visit_counters'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False, default=datetime.utcnow().date)
    count = db.Column(db.Integer, default=0)
    
    @staticmethod
    def increment():
        try:
            today = datetime.utcnow().date()
            visit = VisitCounter.query.filter_by(date=today).first()
            if visit:
                visit.count += 1
            else:
                visit = VisitCounter(date=today, count=1)
                db.session.add(visit)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erreur compteur: {e}")
    
    @staticmethod
    def get_total():
        result = db.session.query(db.func.sum(VisitCounter.count)).scalar()
        return result or 0


# ============================================================
# INDEX DE LA BASE DE DONNÉES
# ============================================================

Index('idx_creator_fr', Artwork.creator_fr)
Index('idx_creator_en', Artwork.creator_en)
Index('idx_label_fr', Artwork.label_fr)
Index('idx_label_en', Artwork.label_en)
Index('idx_collection_fr', Artwork.collection_fr)
Index('idx_collection_en', Artwork.collection_en)
Index('idx_city_fr', Artwork.city_fr)
Index('idx_city_en', Artwork.city_en)
Index('idx_country_fr', Artwork.country_fr)
Index('idx_country_en', Artwork.country_en)
Index('idx_instance_of_fr', Artwork.instance_of_fr)
Index('idx_instance_of_en', Artwork.instance_of_en)
Index('idx_inception', Artwork.inception)
Index('idx_rating_artwork', Rating.artwork_id)
Index('idx_rating_user', Rating.user_id)
Index('idx_favorite_user', Favorite.user_id)
Index('idx_favorite_artwork', Favorite.artwork_id)
Index('idx_artwork_has_image', Artwork.image_url, postgresql_where=Artwork.image_url.isnot(None))
Index('idx_rating_artwork_public', Rating.artwork_id, Rating.is_public)
Index('idx_rating_created_at_desc', Rating.created_at.desc())
Index('idx_artwork_inception', Artwork.inception)
Index('idx_label_fr_trgm', Artwork.label_fr, postgresql_using='gin', postgresql_ops={'label_fr': 'gin_trgm_ops'})
Index('idx_label_en_trgm', Artwork.label_en, postgresql_using='gin', postgresql_ops={'label_en': 'gin_trgm_ops'})
Index('idx_creator_fr_trgm', Artwork.creator_fr, postgresql_using='gin', postgresql_ops={'creator_fr': 'gin_trgm_ops'})
Index('idx_creator_en_trgm', Artwork.creator_en, postgresql_using='gin', postgresql_ops={'creator_en': 'gin_trgm_ops'})


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

# ---- Mise à jour des statistiques des œuvres ----
def update_artwork_stats():
    db.session.execute(text("""
        INSERT INTO artwork_stats (artwork_id, avg_rating, rating_count, fav_count, updated_at)
        SELECT 
            a.id,
            COALESCE(ROUND(AVG(r.note_globale)::numeric, 1), 0),
            COUNT(r.id),
            COUNT(DISTINCT f.id),
            NOW()
        FROM artworks a
        LEFT JOIN ratings r ON a.id = r.artwork_id AND r.is_public = true
        LEFT JOIN favorites f ON a.id = f.artwork_id
        WHERE a.image_url IS NOT NULL AND a.image_url != ''
        GROUP BY a.id
        ON CONFLICT (artwork_id) 
        DO UPDATE SET 
            avg_rating = EXCLUDED.avg_rating,
            rating_count = EXCLUDED.rating_count,
            fav_count = EXCLUDED.fav_count,
            updated_at = EXCLUDED.updated_at
    """))
    db.session.commit()


# ---- Validation de la force du mot de passe ----
def validate_password_strength(password):
    errors = []
    if len(password) < 8:
        errors.append("8 caractères minimum")
    if not re.search(r"[A-Z]", password):
        errors.append("une majuscule requise")
    if not re.search(r"[a-z]", password):
        errors.append("une minuscule requise")
    if not re.search(r"[0-9]", password):
        errors.append("un chiffre requis")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("un caractère spécial requis")
    
    common = {'password', '123456', 'qwerty', 'admin', 'password123', 'azerty', 
              'motdepasse', '12345678', '111111', '123456789', '000000', 'abc123', 
              'password1', '12345', 'letmein', 'monkey', 'football', 'iloveyou', 
              '123123', '654321'}
    if password.lower() in common:
        errors.append("mot de passe trop commun")
    return errors


# ---- Gestion des utilisateurs non vérifiés ----
def handle_unverified_user(user, email):
    EmailVerification.query.filter_by(user_id=user.id, used=False).update({'used': True})
    code = EmailVerification.generate_code()
    token = EmailVerification.generate_token()
    verification = EmailVerification(
        user_id=user.id, token=token, code=code,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.session.add(verification)
    db.session.commit()
    if send_verification_email(email, user.username, code, token):
        flash('Un email de vérification a été renvoyé. Vérifiez votre boîte de réception.', 'info')
    else:
        flash("Erreur lors de l'envoi de l'email. Veuillez réessayer.", 'danger')
    return redirect(url_for('verify_email_pending', email=email))


# ---- Normalisation des chaînes ----
def normalize_string(s):
    if not s:
        return ''
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn').lower()


# ---- Nettoyage des requêtes de recherche ----
def clean_search_query(q):
    if not q:
        return ''
    import re
    q = re.sub(r'[\"`]', '', q)
    q = q.strip()
    return q


# ============================================================
# FONCTIONS D'ENVOI D'EMAILS
# ============================================================

_EMAIL_BASE_STYLE = """
<style>
  body { 
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif; 
    background: #f2f2f2; 
    margin: 0; 
    padding: 20px; 
    line-height: 1.5; 
  }
  .container { 
    max-width: 480px; 
    margin: 0 auto; 
    background: #ffffff; 
    border-radius: 24px; 
    padding: 48px 40px; 
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }
  h1 { 
    font-family: 'Space Grotesk', -apple-system, sans-serif; 
    font-weight: 600; 
    color: #1a1a1a; 
    font-size: 1.5rem; 
    margin: 0 0 8px 0; 
    text-align: center; 
    letter-spacing: -0.02em;
  }
  .sub { 
    color: #666666; 
    font-size: 0.9rem; 
    text-align: center; 
    margin-bottom: 32px; 
  }
  .code-box { 
    background: #f7f7f7; 
    border-radius: 16px; 
    padding: 24px; 
    text-align: center; 
    margin: 24px 0; 
  }
  .code-value { 
    font-size: 2rem; 
    font-weight: 600; 
    color: #6c5ce7; 
    letter-spacing: 6px; 
    font-family: 'Space Grotesk', monospace;
  }
  .btn-wrap { 
    text-align: center; 
    margin: 32px 0 24px; 
  }
  .btn { 
    display: inline-block; 
    background: #6c5ce7; 
    color: #ffffff !important; 
    font-weight: 500; 
    font-size: 0.85rem; 
    padding: 12px 28px; 
    text-decoration: none; 
    border-radius: 30px; 
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }
  .footer { 
    color: #999999; 
    font-size: 0.7rem; 
    text-align: center; 
    margin-top: 32px; 
    padding-top: 24px; 
    border-top: 1px solid #eeeeee; 
  }
  .footer a {
    color: #6c5ce7;
    text-decoration: none;
  }
</style>
"""

_EMAIL_FONTS = '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">'


def send_verification_email(user_email, username, code, token):
    link = f"{BASE_URL}/verify-email?token={token}"
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    {_EMAIL_FONTS}
    {_EMAIL_BASE_STYLE}
</head>
<body>
    <div class="container">
        <h1>{SITE_NAME}</h1>
        <p class="sub">Connectez-vous avec le lien sécurisé ci-dessous</p>
        <div class="code-box">
            <div class="code-value">{code}</div>
        </div>
        <div class="btn-wrap">
            <a href="{link}" class="btn">Vérifier mon email</a>
        </div>
        <div class="footer">
            Ce lien est valable 24 heures.<br>
            Si vous n'avez pas demandé cet email, vous pouvez l'ignorer.
        </div>
    </div>
</body>
</html>"""
    return _send_email(user_email, f'{SITE_NAME} - Vérification de votre email', html)


def send_reset_email(user_email, username, reset_link):
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    {_EMAIL_FONTS}
    {_EMAIL_BASE_STYLE}
</head>
<body>
    <div class="container">
        <h1>{SITE_NAME}</h1>
        <p class="sub">Réinitialisation de votre mot de passe</p>
        <div class="btn-wrap">
            <a href="{reset_link}" class="btn">Réinitialiser mon mot de passe</a>
        </div>
        <div class="footer">
            Ce lien est valable 24 heures.<br>
            Si vous n'avez pas demandé cet email, vous pouvez l'ignorer.
        </div>
    </div>
</body>
</html>"""
    return _send_email(user_email, f'{SITE_NAME} - Réinitialisation de votre mot de passe', html)


def _send_email(to_email, subject, html_content):
    try:
        response = requests.post(
            f"https://api.eu.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
            auth=("api", MAILGUN_API_KEY),
            data={
                "from": FROM_EMAIL,
                "to": to_email,
                "subject": subject,
                "html": html_content
            }
        )
        logger.info("Email envoyé à %s — statut %s", to_email, response.status_code)
        return response.status_code == 200
    except Exception as exc:
        logger.error("Erreur envoi email vers %s : %s", to_email, exc)
        return False


# ============================================================
# FILTRES JINJA
# ============================================================

@app.template_filter('stars')
def stars_filter(value):
    if not value:
        return ''
    full = int(value)
    half = 1 if value - full >= 0.5 else 0
    empty = 5 - full - half
    return '★' * full + ('½' if half else '') + '☆' * empty


# ============================================================
# CONTEXT PROCESSORS
# ============================================================

@app.context_processor
def inject_language():
    return dict(
        current_language=session.get('language', 'fr'),
        is_french=session.get('language', 'fr') == 'fr',
        is_english=session.get('language', 'fr') == 'en'
    )


@app.context_processor
def inject_site_name():
    return dict(site_name=SITE_NAME)


@app.template_global()
def _(text):
    lang = session.get('language', 'fr')
    return TRANSLATIONS.get(lang, {}).get(text, text)


# ============================================================
# HELPERS DE REQUÊTES
# ============================================================

def _build_artwork_query(artists, country, cities, museums, types=None, q='', movements=None, genres=None, materials=None):
    query = Artwork.query.filter(
        Artwork.image_url.isnot(None),
        Artwork.image_url != ''
    )

    if q and not country and not cities and not museums and not artists:
        s = f"%{q}%"
        ns = f"%{normalize_string(q)}%"
        lang = session.get('language', 'fr')
        
        if lang == 'fr':
            query = query.filter(
                db.or_(
                    Artwork.label_fr.ilike(s),
                    func.unaccent(Artwork.label_fr).ilike(ns)
                )
            )
        else:
            query = query.filter(
                db.or_(
                    Artwork.label_en.ilike(s),
                    func.unaccent(Artwork.label_en).ilike(ns)
                )
            )

    if country:
        nc = f"%{normalize_string(country)}%"
        query = query.filter(db.or_(
            Artwork.country_fr.ilike(f"%{country}%"),
            Artwork.country_en.ilike(f"%{country}%"),
            func.unaccent(Artwork.country_fr).ilike(nc),
            func.unaccent(Artwork.country_en).ilike(nc),
        ))

    if artists:
        filters = []
        for a in artists:
            na = f"%{normalize_string(a)}%"
            filters.append(db.or_(
                Artwork.creator_fr.ilike(f"%{a}%"),
                Artwork.creator_en.ilike(f"%{a}%"),
                func.unaccent(Artwork.creator_fr).ilike(na),
                func.unaccent(Artwork.creator_en).ilike(na),
            ))
        if filters:
            query = query.filter(db.or_(*filters))

    if cities:
        filters = []
        for c in cities:
            nc = f"%{normalize_string(c)}%"
            filters.append(db.or_(
                Artwork.city_fr.ilike(f"%{c}%"),
                Artwork.city_en.ilike(f"%{c}%"),
                func.unaccent(Artwork.city_fr).ilike(nc),
                func.unaccent(Artwork.city_en).ilike(nc),
            ))
        if filters:
            query = query.filter(db.or_(*filters))

    if museums:
        museum_filters = []
        for m in museums:
            if m == 'divers':
                museum_filters.append(
                    db.and_(
                        db.or_(
                            Artwork.collection_id.is_(None),
                            Artwork.collection_id == '',
                            Artwork.collection_fr.is_(None),
                            Artwork.collection_fr == '',
                            Artwork.collection_en.is_(None),
                            Artwork.collection_en == ''
                        )
                    )
                )
            else:
                nm = f"%{normalize_string(m)}%"
                museum_filters.append(
                    db.or_(
                        Artwork.collection_id == m,
                        Artwork.collection_fr.ilike(f"%{m}%"),
                        Artwork.collection_en.ilike(f"%{m}%"),
                        func.unaccent(Artwork.collection_fr).ilike(nm),
                        func.unaccent(Artwork.collection_en).ilike(nm),
                    )
                )
        if museum_filters:
            query = query.filter(db.and_(*museum_filters))

    if types:
        type_filters = []
        for t in types:
            nt = f"%{normalize_string(t)}%"
            type_filters.append(Artwork.instance_of_fr.ilike(f"%{t}%"))
            type_filters.append(Artwork.instance_of_en.ilike(f"%{t}%"))
            type_filters.append(func.unaccent(Artwork.instance_of_fr).ilike(nt))
            type_filters.append(func.unaccent(Artwork.instance_of_en).ilike(nt))
        if type_filters:
            query = query.filter(db.or_(*type_filters))

    if movements:
        movement_filters = []
        for m in movements:
            movement_filters.append(Artwork.movement_fr.ilike(f"%{m}%"))
            movement_filters.append(Artwork.movement_en.ilike(f"%{m}%"))
        if movement_filters:
            query = query.filter(db.or_(*movement_filters))
    
    if genres:
        genre_filters = []
        for g in genres:
            genre_filters.append(Artwork.genre_fr.ilike(f"%{g}%"))
            genre_filters.append(Artwork.genre_en.ilike(f"%{g}%"))
        if genre_filters:
            query = query.filter(db.or_(*genre_filters))
    
    if materials:
        material_filters = []
        for mat in materials:
            material_filters.append(Artwork.made_from_material_fr.ilike(f"%{mat}%"))
            material_filters.append(Artwork.made_from_material_en.ilike(f"%{mat}%"))
        if material_filters:
            query = query.filter(db.or_(*material_filters))

    return query


def _apply_sort(query, sort):
    lang = session.get('language', 'fr')
    
    if sort == 'date_desc':
        return query.order_by(Artwork.inception.desc().nullslast())
    elif sort == 'date_asc':
        return query.order_by(Artwork.inception.asc().nullslast())
    elif sort == 'title_asc':
        col = Artwork.label_fr if lang == 'fr' else Artwork.label_en
        return query.order_by(col.asc().nullslast())
    elif sort == 'artist_asc':
        col = Artwork.creator_fr if lang == 'fr' else Artwork.creator_en
        return query.order_by(col.asc().nullslast())
    elif sort in ('rating_desc', 'rating_asc'):
        avg_subquery = db.session.query(
            Rating.artwork_id,
            func.avg(Rating.note_globale).label('avg_rating')
        ).group_by(Rating.artwork_id).subquery()
        query = query.outerjoin(avg_subquery, Artwork.id == avg_subquery.c.artwork_id)
        if sort == 'rating_desc':
            return query.order_by(avg_subquery.c.avg_rating.desc().nullslast())
        else:
            return query.order_by(avg_subquery.c.avg_rating.asc().nullslast())
    else:
        count = query.count()
        if count > 10000:
            offset = random.randint(0, min(count - 100, 50000))
            return query.offset(offset).limit(1000)
        elif count > 1000:
            offset = random.randint(0, min(count - 100, 50000))
            return query.offset(offset)
        else:
            return query.order_by(func.random())


# ============================================================
# ROUTES - PAGES PRINCIPALES
# ============================================================

# ---- Route racine ----
@app.route('/')
def index():
    return redirect(url_for('home'))


# ---- Page d'accueil ----
@app.route('/home')
def home():
    # Image aléatoire pour le hero
    hero_image = db.session.query(Artwork.image_url).filter(
        Artwork.image_url.isnot(None),
        Artwork.image_url != ''
    ).order_by(func.random()).first()
    hero_image_url = hero_image[0] if hero_image else None
    
    # Récupération de l'œuvre en vedette (La Joconde)
    spotlight_artwork = Artwork.query.filter_by(id='Q12418').first()
    
    if spotlight_artwork:
        spotlight_image = spotlight_artwork.image_url
        spotlight_title = spotlight_artwork.titre
        spotlight_artist = spotlight_artwork.createur
    else:
        spotlight_image = None
        spotlight_title = 'La Joconde'
        spotlight_artist = 'Léonard de Vinci'
    
    return render_template('home.html',
        hero_image=hero_image_url,
        spotlight_image=spotlight_image,
        spotlight_title=spotlight_title,
        spotlight_artist=spotlight_artist
    )

# ---- Page À propos ----
_about_stats_cache = {}
_about_stats_cache_time = None

@app.route('/about')
def about():
    global _about_stats_cache, _about_stats_cache_time
    
    now = datetime.utcnow()
    
    if hasattr(app, '_about_stats_cache_time') and app._about_stats_cache_time and (now - app._about_stats_cache_time).seconds < 300:
        stats = app._about_stats_cache
    else:
        total_oeuvres = Artwork.query.count()
        total_artistes = db.session.query(
            func.count(func.distinct(Artwork.creator_fr))
        ).filter(
            Artwork.creator_fr.isnot(None),
            Artwork.creator_fr != ''
        ).scalar() or 0
        total_musees = db.session.query(
            func.count(func.distinct(Artwork.collection_fr))
        ).filter(
            Artwork.collection_fr.isnot(None),
            Artwork.collection_fr != ''
        ).scalar() or 0
        total_users = User.query.count()
        total_visits = VisitCounter.get_total()
        
        stats = {
            'total_oeuvres': f"{total_oeuvres:,}".replace(',', ' '),
            'total_artistes': f"{total_artistes:,}".replace(',', ' '),
            'total_musees': f"{total_musees:,}".replace(',', ' '),
            'total_users': f"{total_users:,}".replace(',', ' '),
            'total_visits': f"{total_visits:,}".replace(',', ' ')
        }
        app._about_stats_cache = stats
        app._about_stats_cache_time = now
    
    return render_template('about.html', **stats)


# ---- Page Découvrir ----
_cache_time = {}
_cache_data = {}

def cached_discover_data():
    global _cache_time, _cache_data
    now = datetime.utcnow()
    if 'discover' in _cache_time and (now - _cache_time['discover']).seconds < 3600:
        return _cache_data['discover']
    
    lang = session.get('language', 'fr')

    if lang == 'fr':
        mov_col = 'movement_fr'
        type_col = 'instance_of_fr'
        art_col = 'creator_fr'
        city_col = 'city_fr'
        country_col = 'country_fr'
        genre_col = 'genre_fr'
        museum_col = 'collection_fr'
    else:
        mov_col = 'movement_en'
        type_col = 'instance_of_en'
        art_col = 'creator_en'
        city_col = 'city_en'
        country_col = 'country_en'
        genre_col = 'genre_en'
        museum_col = 'collection_en'

    def get_first_image(field, table_alias='a'):
        return f"""
            (SELECT image_url FROM artworks 
             WHERE {field} = {table_alias}.{field} 
             AND image_url IS NOT NULL AND image_url != '' 
             LIMIT 1)
        """

    mov_sql = text(f"""
        SELECT {mov_col} as name, COUNT(*) as count, {get_first_image(mov_col, 'm')} as image
        FROM artworks m
        WHERE {mov_col} IS NOT NULL AND {mov_col} != ''
          AND image_url IS NOT NULL AND image_url != ''
        GROUP BY {mov_col}
        ORDER BY count DESC LIMIT 12
    """)
    movements = [{'name': r.name, 'count': r.count, 'image': r.image} for r in db.session.execute(mov_sql)]

    type_sql = text(f"""
        SELECT {type_col} as name, COUNT(*) as count, {get_first_image(type_col, 't')} as image
        FROM artworks t
        WHERE {type_col} IS NOT NULL AND {type_col} != ''
          AND image_url IS NOT NULL AND image_url != ''
        GROUP BY {type_col}
        ORDER BY count DESC LIMIT 12
    """)
    types = [{'name': r.name, 'count': r.count, 'image': r.image} for r in db.session.execute(type_sql)]

    museums_sql = text(f"""
        SELECT {museum_col} as name, COUNT(*) as count
        FROM artworks
        WHERE {museum_col} IS NOT NULL AND {museum_col} != ''
          AND image_url IS NOT NULL AND image_url != ''
        GROUP BY {museum_col}
        ORDER BY count DESC LIMIT 12
    """)
    museums = [{'name': r.name, 'count': r.count} for r in db.session.execute(museums_sql)]

    artist_ids = ['Q762', 'Q483992', 'Q351746', 'Q325961', 'Q12345227', 'Q102135']
    artist_sql = text(f"""
        SELECT DISTINCT ON (a.{art_col})
            a.{art_col} as name, a.creator_id,
            COUNT(*) OVER (PARTITION BY a.{art_col}) as count,
            {get_first_image(art_col, 'a')} as image
        FROM artworks a
        WHERE a.creator_id IN ({','.join([f"'{id}'" for id in artist_ids])})
          AND a.image_url IS NOT NULL AND a.image_url != ''
          AND a.{art_col} IS NOT NULL AND a.{art_col} != ''
        GROUP BY a.{art_col}, a.creator_id, a.image_url
        ORDER BY a.{art_col} LIMIT 6
    """)
    artists = [{'name': r.name, 'count': r.count, 'image': r.image, 'creator_id': r.creator_id} for r in db.session.execute(artist_sql)]

    city_sql = text(f"""
        SELECT {city_col} as name, COUNT(*) as count
        FROM artworks
        WHERE {city_col} IS NOT NULL AND {city_col} != ''
          AND image_url IS NOT NULL AND image_url != ''
        GROUP BY {city_col}
        ORDER BY count DESC LIMIT 5
    """)
    cities = [{'name': r.name, 'count': r.count} for r in db.session.execute(city_sql)]

    country_sql = text(f"""
        SELECT {country_col} as name, COUNT(*) as count
        FROM artworks
        WHERE {country_col} IS NOT NULL AND {country_col} != ''
          AND image_url IS NOT NULL AND image_url != ''
        GROUP BY {country_col}
        ORDER BY count DESC LIMIT 5
    """)
    countries = [{'name': r.name, 'count': r.count} for r in db.session.execute(country_sql)]

    genre_sql = text(f"""
        SELECT {genre_col} as name, COUNT(*) as count
        FROM artworks
        WHERE {genre_col} IS NOT NULL AND {genre_col} != ''
          AND image_url IS NOT NULL AND image_url != ''
        GROUP BY {genre_col}
        ORDER BY count DESC LIMIT 12
    """)
    genres = [{'name': r.name, 'count': r.count} for r in db.session.execute(genre_sql)]

    result = {
        'movements': movements,
        'types': types,
        'museums': museums,
        'cities': cities,
        'countries': countries,
        'genres': genres,
        'artists': artists
    }
    
    _cache_time['discover'] = now
    _cache_data['discover'] = result
    return result


@app.route('/discover')
def discover():
    static_data = cached_discover_data()
    
    hero_sql = text("""
        SELECT image_url
        FROM artworks
        WHERE image_url IS NOT NULL AND image_url != ''
          AND (instance_of_fr ILIKE '%peinture%' OR instance_of_en ILIKE '%painting%')
        ORDER BY random() LIMIT 1
    """)
    hero_result = db.session.execute(hero_sql).first()
    hero_image = hero_result.image_url if hero_result else None
    
    if not hero_image:
        hero_fallback_sql = text("""
            SELECT image_url FROM artworks
            WHERE image_url IS NOT NULL AND image_url != ''
            ORDER BY random() LIMIT 1
        """)
        hero_result = db.session.execute(hero_fallback_sql).first()
        hero_image = hero_result.image_url if hero_result else None

    daily_selection = []
    artist_name = ""
    
    artist_with_3_works_sql = text("""
        SELECT creator_fr, creator_en, COUNT(*) as work_count
        FROM artworks
        WHERE image_url IS NOT NULL AND image_url != ''
          AND creator_fr IS NOT NULL AND creator_fr != ''
          AND creator_fr NOT IN ('Artiste inconnu', 'Unknown artist')
        GROUP BY creator_fr, creator_en
        HAVING COUNT(*) >= 3
        ORDER BY random() LIMIT 1
    """)
    
    random_artist = db.session.execute(artist_with_3_works_sql).first()
    
    if random_artist:
        creator_fr = random_artist.creator_fr
        creator_en = random_artist.creator_en
        artist_name = creator_fr or creator_en or "un artiste"
        
        artist_works_sql = text("""
            SELECT id, COALESCE(label_fr, label_en, 'Sans titre') as title,
                   COALESCE(creator_fr, creator_en, 'Artiste inconnu') as creator, image_url
            FROM artworks
            WHERE image_url IS NOT NULL AND image_url != ''
              AND (creator_fr = :creator_fr OR creator_en = :creator_en)
            ORDER BY random() LIMIT 3
        """)
        for r in db.session.execute(artist_works_sql, {'creator_fr': creator_fr, 'creator_en': creator_en}):
            daily_selection.append({
                'id': r.id, 'title': r.title or 'Sans titre',
                'creator': r.creator or 'Artiste inconnu', 'image_url': r.image_url
            })
    
    if not daily_selection:
        fallback_sql = text("""
            SELECT id, COALESCE(label_fr, label_en, 'Sans titre') as title,
                   COALESCE(creator_fr, creator_en, 'Artiste inconnu') as creator, image_url
            FROM artworks
            WHERE image_url IS NOT NULL AND image_url != ''
            ORDER BY random() LIMIT 3
        """)
        for r in db.session.execute(fallback_sql):
            daily_selection.append({
                'id': r.id, 'title': r.title or 'Sans titre',
                'creator': r.creator or 'Artiste inconnu', 'image_url': r.image_url
            })
        artist_name = daily_selection[0]['creator'] if daily_selection else "un artiste"

    lang = session.get('language', 'fr')
    creator_col = 'creator_fr' if lang == 'fr' else 'creator_en'
    
    creators_with_works_sql = text(f"""
        SELECT {creator_col} as name, COUNT(*) as work_count
        FROM artworks
        WHERE {creator_col} IS NOT NULL AND {creator_col} != ''
          AND {creator_col} NOT IN ('Artiste inconnu', 'Unknown artist')
          AND image_url IS NOT NULL AND image_url != ''
        GROUP BY {creator_col}
        HAVING COUNT(*) >= 4
        ORDER BY random() LIMIT 3
    """)
    
    creators_list = db.session.execute(creators_with_works_sql).fetchall()
    
    creators_with_works = []
    for creator_row in creators_list:
        creator_name = creator_row.name
        works_sql = text(f"""
            SELECT id, COALESCE(label_fr, label_en, 'Sans titre') as title, image_url
            FROM artworks
            WHERE image_url IS NOT NULL AND image_url != ''
              AND {creator_col} = :creator_name
            ORDER BY random() LIMIT 4
        """)
        works = db.session.execute(works_sql, {'creator_name': creator_name}).fetchall()
        creators_with_works.append({
            'name': creator_name,
            'works': [{'id': w.id, 'title': w.title, 'image_url': w.image_url} for w in works]
        })

    return render_template('discover.html',
        hero_image=hero_image,
        movements=static_data['movements'],
        types=static_data['types'],
        museums=static_data['museums'],
        cities=static_data['cities'],
        countries=static_data['countries'],
        genres=static_data['genres'],
        artists=static_data['artists'],
        daily_selection=daily_selection,
        daily_artist=artist_name,
        creators_with_works=creators_with_works
    )


# ---- Page Top (classements) ----
@app.route('/top')
def top():
    lang = session.get('language', 'fr')

    top_rated_rows = db.session.query(
        Artwork, ArtworkStats.avg_rating, ArtworkStats.rating_count
    ).join(ArtworkStats, Artwork.id == ArtworkStats.artwork_id).filter(
        Artwork.image_url.isnot(None), Artwork.image_url != '',
        ArtworkStats.rating_count >= 1
    ).order_by(ArtworkStats.avg_rating.desc()).limit(50).all()

    top_fav_rows = db.session.query(
        Artwork, ArtworkStats.fav_count
    ).join(ArtworkStats, Artwork.id == ArtworkStats.artwork_id).filter(
        Artwork.image_url.isnot(None), Artwork.image_url != ''
    ).order_by(ArtworkStats.fav_count.desc()).limit(50).all()

    recent_comments = db.session.query(
        Artwork, Rating.note_globale, Rating.commentaire, Rating.created_at, User.username
    ).join(Rating, Artwork.id == Rating.artwork_id).join(
        User, Rating.user_id == User.id
    ).filter(
        Artwork.image_url.isnot(None), Artwork.image_url != '',
        Rating.commentaire.isnot(None), Rating.commentaire != '',
        Rating.is_public == True
    ).order_by(Rating.created_at.desc()).limit(50).all()

    return render_template('top.html',
        top_rated=top_rated_rows,
        top_fav=top_fav_rows,
        recent_comments=recent_comments
    )


# ---- Page Recherche ----
@app.route('/research')
def research():
    page = request.args.get('page', 1, type=int)
    limit = min(request.args.get('limit', 12, type=int), 40)
    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types = request.args.getlist('type')
    movements = request.args.getlist('movement')
    genres = request.args.getlist('genre')
    materials = request.args.getlist('material')
    sort = request.args.get('sort', 'relevance')
    q = request.args.get('q', '').strip()
    view = request.args.get('view', 4, type=int)
    
    query = _build_artwork_query(artists, country, cities, museums, types, q=q, 
                                  movements=movements, genres=genres, materials=materials)
    total = query.count()
    query = _apply_sort(query, sort)
    works_page = query.offset((page - 1) * limit).limit(limit).all()
    works = [w.to_dict() for w in works_page]

    search_results = None
    if q and page == 1:
        lang = session.get('language', 'fr')
        pattern = f"%{q}%"
        normalized_q = f"%{normalize_string(q)}%"

        artist_field = Artwork.creator_fr if lang == 'fr' else Artwork.creator_en
        sr_artists = db.session.query(
            artist_field.label('nom'), func.count(Artwork.id).label('count')
        ).filter(
            db.or_(artist_field.ilike(pattern), func.unaccent(artist_field).ilike(normalized_q)),
            artist_field.isnot(None), artist_field != ''
        ).group_by(artist_field).order_by(func.count(Artwork.id).desc()).limit(40).all()

        city_field = Artwork.city_fr if lang == 'fr' else Artwork.city_en
        sr_cities = db.session.query(
            city_field.label('nom'),
            func.count(func.distinct(Artwork.collection_id)).label('musees_count'),
            func.count(Artwork.id).label('oeuvres_count')
        ).filter(
            db.or_(city_field.ilike(pattern), func.unaccent(city_field).ilike(normalized_q)),
            city_field.isnot(None), city_field != ''
        ).group_by(city_field).order_by(func.count(Artwork.id).desc()).limit(40).all()

        country_field = Artwork.country_fr if lang == 'fr' else Artwork.country_en
        sr_countries = db.session.query(
            country_field.label('nom'),
            func.count(func.distinct(Artwork.city_fr)).label('villes_count'),
            func.count(Artwork.id).label('oeuvres_count')
        ).filter(
            db.or_(country_field.ilike(pattern), func.unaccent(country_field).ilike(normalized_q)),
            country_field.isnot(None), country_field != ''
        ).group_by(country_field).order_by(func.count(Artwork.id).desc()).limit(40).all()

        museum_field = Artwork.collection_fr if lang == 'fr' else Artwork.collection_en
        sr_museums = db.session.query(
            museum_field.label('nom'), func.count(Artwork.id).label('count')
        ).filter(
            db.or_(museum_field.ilike(pattern), func.unaccent(museum_field).ilike(normalized_q)),
            museum_field.isnot(None), museum_field != ''
        ).group_by(museum_field).order_by(func.count(Artwork.id).desc()).limit(40).all()

        if any([sr_artists, sr_countries, sr_cities, sr_museums]):
            search_results = {
                'query': q,
                'artists': [{'nom': a.nom, 'count': a.count} for a in sr_artists],
                'countries': [{'nom': c.nom, 'villes_count': c.villes_count, 'oeuvres_count': c.oeuvres_count, 'count': c.oeuvres_count} for c in sr_countries],
                'cities': [{'nom': c.nom, 'musees_count': c.musees_count, 'oeuvres_count': c.oeuvres_count, 'count': c.oeuvres_count} for c in sr_cities],
                'museums': [{'id': m.nom, 'nom': m.nom, 'count': m.count} for m in sr_museums],
            }

    museum_names = {}
    selected_museums = request.args.getlist('museum')
    if selected_museums:
        lang = session.get('language', 'fr')
        museum_field = Artwork.collection_fr if lang == 'fr' else Artwork.collection_en
        museums_data = db.session.query(
            Artwork.collection_id, museum_field.label('name')
        ).filter(Artwork.collection_id.in_(selected_museums)).distinct().all()
        museum_names = {m.collection_id: m.name for m in museums_data}

    return render_template('research.html',
        works=works, total_oeuvres=total, current_page=page,
        current_view=view, search_results=search_results, q=q,
        museum_names=museum_names
    )


# ---- Page Favoris ----
@app.route('/favoris')
def favorites_page():
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour voir vos favoris', 'warning')
        return redirect(url_for('login'))

    favs = Favorite.query.filter_by(user_id=session['user_id']).all()
    if not favs:
        return render_template('favorites.html', artworks=[], total_artworks=0,
                               has_more=False, museum_names={})

    fav_ids = [f.artwork_id for f in favs]
    fav_date_map = {f.artwork_id: f.created_at for f in favs}

    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types = request.args.getlist('type')
    movements = request.args.getlist('movement')
    genres = request.args.getlist('genre')
    materials = request.args.getlist('material')
    sort = request.args.get('sort', 'date_added')
    limit = 12

    query = Artwork.query.filter(Artwork.id.in_(fav_ids))

    if artists:
        query = query.filter(db.or_(*[
            db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
            for a in artists
        ]))
    if country:
        query = query.filter(db.or_(
            Artwork.country_fr.ilike(f"%{country}%"),
            Artwork.country_en.ilike(f"%{country}%")
        ))
    if cities:
        query = query.filter(db.or_(*[
            db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
            for c in cities
        ]))
    if museums:
        query = query.filter(db.or_(*[
            db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                   Artwork.collection_en.ilike(f"%{m}%"))
            for m in museums
        ]))
    if types:
        query = query.filter(db.or_(*[
            db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
            for t in types
        ]))
    if movements:
        query = query.filter(db.or_(*[
            db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
            for m in movements
        ]))
    if genres:
        query = query.filter(db.or_(*[
            db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
            for g in genres
        ]))
    if materials:
        query = query.filter(db.or_(*[
            db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"),
                   Artwork.made_from_material_en.ilike(f"%{mat}%"))
            for mat in materials
        ]))

    if sort == 'date_added':
        all_artworks = query.all()
        all_artworks.sort(key=lambda a: fav_date_map.get(a.id, datetime.min), reverse=True)
        total_filtered = len(all_artworks)
        artworks = [a.to_dict() for a in all_artworks[:limit]]
    else:
        query = _apply_sort(query, sort)
        total_filtered = query.count()
        artworks = [a.to_dict() for a in query.limit(limit).all()]

    has_more = total_filtered > limit

    return render_template('favorites.html',
        artworks=artworks, total_artworks=len(fav_ids),
        has_more=has_more, museum_names={}
    )


# ---- Page Mes notes (rated) ----
@app.route('/rated')
def rated_page():
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour voir vos notes', 'warning')
        return redirect(url_for('login'))

    user_id = session['user_id']
    
    rated_ids = db.session.query(Rating.artwork_id).filter_by(user_id=user_id).all()
    rated_ids = [r[0] for r in rated_ids]
    
    if not rated_ids:
        return render_template('rated.html', artworks=[], total_ratings=0, has_more=False)

    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types = request.args.getlist('type')
    movements = request.args.getlist('movement')
    genres = request.args.getlist('genre')
    materials = request.args.getlist('material')
    rating_global = request.args.get('rating_global', '')
    rating_technique = request.args.get('rating_technique', '')
    rating_originalite = request.args.get('rating_originalite', '')
    rating_emotion = request.args.get('rating_emotion', '')
    sort = request.args.get('sort', 'rating_desc')
    page = request.args.get('page', 1, type=int)
    limit = 12

    query = Artwork.query.filter(Artwork.id.in_(rated_ids))

    if artists:
        query = query.filter(db.or_(*[
            db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
            for a in artists
        ]))
    if country:
        query = query.filter(db.or_(
            Artwork.country_fr.ilike(f"%{country}%"),
            Artwork.country_en.ilike(f"%{country}%")
        ))
    if cities:
        query = query.filter(db.or_(*[
            db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
            for c in cities
        ]))
    if museums:
        query = query.filter(db.or_(*[
            db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                   Artwork.collection_en.ilike(f"%{m}%"))
            for m in museums
        ]))
    if types:
        query = query.filter(db.or_(*[
            db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
            for t in types
        ]))
    if movements:
        query = query.filter(db.or_(*[
            db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
            for m in movements
        ]))
    if genres:
        query = query.filter(db.or_(*[
            db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
            for g in genres
        ]))
    if materials:
        query = query.filter(db.or_(*[
            db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
            for mat in materials
        ]))

    if rating_global:
        exact_rating = float(rating_global)
        rated_ids_filtered = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_globale == exact_rating
        ).subquery()
        query = query.filter(Artwork.id.in_(rated_ids_filtered))
    if rating_technique:
        exact_rating = float(rating_technique)
        rated_ids_filtered = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_technique == exact_rating
        ).subquery()
        query = query.filter(Artwork.id.in_(rated_ids_filtered))
    if rating_originalite:
        exact_rating = float(rating_originalite)
        rated_ids_filtered = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_originalite == exact_rating
        ).subquery()
        query = query.filter(Artwork.id.in_(rated_ids_filtered))
    if rating_emotion:
        exact_rating = float(rating_emotion)
        rated_ids_filtered = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_emotion == exact_rating
        ).subquery()
        query = query.filter(Artwork.id.in_(rated_ids_filtered))

    if sort == 'rating_desc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.note_globale.desc())
    elif sort == 'rating_asc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.note_globale.asc())
    elif sort == 'technique_desc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.note_technique.desc())
    elif sort == 'originalite_desc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.note_originalite.desc())
    elif sort == 'emotion_desc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.note_emotion.desc())
    elif sort == 'date_desc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.created_at.desc())
    elif sort == 'date_asc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.created_at.asc())
    elif sort == 'title_asc':
        col = Artwork.label_fr if session.get('language', 'fr') == 'fr' else Artwork.label_en
        query = query.order_by(col)
    elif sort == 'artist_asc':
        col = Artwork.creator_fr if session.get('language', 'fr') == 'fr' else Artwork.creator_en
        query = query.order_by(col)

    total = query.count()
    start = (page - 1) * limit
    has_more = (start + limit) < total
    works_page = query.offset(start).limit(limit).all()

    artworks = []
    for artwork in works_page:
        rating = Rating.query.filter_by(user_id=user_id, artwork_id=artwork.id).first()
        artwork_dict = artwork.to_dict()
        artwork_dict['user_rating_global'] = rating.note_globale if rating else 0
        artwork_dict['user_rating_technique'] = rating.note_technique if rating else 0
        artwork_dict['user_rating_originalite'] = rating.note_originalite if rating else 0
        artwork_dict['user_rating_emotion'] = rating.note_emotion if rating else 0
        artworks.append(artwork_dict)

    return render_template('rated.html',
        artworks=artworks, total_ratings=total,
        has_more=has_more, current_page=page
    )


# ---- Page Toutes les œuvres notées ----
@app.route('/all-rated')
def all_rated():
    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types = request.args.getlist('type')
    movements = request.args.getlist('movement')
    genres = request.args.getlist('genre')
    materials = request.args.getlist('material')
    rating_filter = request.args.get('rating', '')
    sort = request.args.get('sort', 'rating_desc')
    page = request.args.get('page', 1, type=int)
    limit = 12

    rating_subquery = db.session.query(
        Rating.artwork_id,
        func.avg(Rating.note_globale).label('avg_rating'),
        func.count(Rating.id).label('rating_count')
    ).group_by(Rating.artwork_id).subquery()

    query = Artwork.query.join(rating_subquery, Artwork.id == rating_subquery.c.artwork_id).filter(
        Artwork.image_url.isnot(None), Artwork.image_url != ''
    )

    if artists:
        query = query.filter(db.or_(*[
            db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
            for a in artists
        ]))
    if country:
        query = query.filter(db.or_(
            Artwork.country_fr.ilike(f"%{country}%"),
            Artwork.country_en.ilike(f"%{country}%")
        ))
    if cities:
        query = query.filter(db.or_(*[
            db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
            for c in cities
        ]))
    if museums:
        query = query.filter(db.or_(*[
            db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                   Artwork.collection_en.ilike(f"%{m}%"))
            for m in museums
        ]))
    if types:
        query = query.filter(db.or_(*[
            db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
            for t in types
        ]))
    if movements:
        query = query.filter(db.or_(*[
            db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
            for m in movements
        ]))
    if genres:
        query = query.filter(db.or_(*[
            db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
            for g in genres
        ]))
    if materials:
        query = query.filter(db.or_(*[
            db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
            for mat in materials
        ]))

    if rating_filter:
        min_rating = int(rating_filter)
        query = query.filter(rating_subquery.c.avg_rating >= min_rating)

    if sort == 'rating_desc':
        query = query.order_by(rating_subquery.c.avg_rating.desc().nullslast())
    elif sort == 'rating_asc':
        query = query.order_by(rating_subquery.c.avg_rating.asc().nullslast())
    elif sort == 'count_desc':
        query = query.order_by(rating_subquery.c.rating_count.desc().nullslast())
    elif sort == 'title_asc':
        col = Artwork.label_fr if session.get('language', 'fr') == 'fr' else Artwork.label_en
        query = query.order_by(col)
    elif sort == 'artist_asc':
        col = Artwork.creator_fr if session.get('language', 'fr') == 'fr' else Artwork.creator_en
        query = query.order_by(col)
    elif sort == 'date_desc':
        query = query.order_by(Artwork.inception.desc().nullslast())
    elif sort == 'date_asc':
        query = query.order_by(Artwork.inception.asc().nullslast())

    total = query.count()
    start = (page - 1) * limit
    has_more = (start + limit) < total
    works_page = query.offset(start).limit(limit).all()

    artworks = []
    for artwork in works_page:
        artwork_dict = artwork.to_dict()
        stats = db.session.query(
            func.avg(Rating.note_globale).label('avg_rating'),
            func.count(Rating.id).label('rating_count')
        ).filter_by(artwork_id=artwork.id).first()
        artwork_dict['avg_rating'] = stats.avg_rating if stats.avg_rating else 0
        artwork_dict['rating_count'] = stats.rating_count or 0
        artworks.append(artwork_dict)

    return render_template('all_rated.html',
        artworks=artworks, total_artworks=total,
        has_more=has_more, current_page=page
    )


# ---- Page détail d'une œuvre ----
@app.route('/oeuvre/<string:oeuvre_id>')
def oeuvre_detail(oeuvre_id):
    artwork = Artwork.query.filter_by(id=oeuvre_id).first()
    if not artwork:
        return "Œuvre non trouvée", 404

    oeuvre_dict = artwork.to_dict()
    stats = get_artwork_stats(artwork.id)

    return render_template('detail.html', oeuvre=oeuvre_dict, stats=stats)


# ---- Fonction utilitaire pour les stats d'œuvre ----
def get_artwork_stats(artwork_id):
    stats = db.session.query(
        func.count(Rating.id).label('total'),
        func.avg(Rating.note_globale).label('moyenne')
    ).filter_by(artwork_id=artwork_id).first()

    favorites_count = Favorite.query.filter_by(artwork_id=artwork_id).count()

    if not stats or not stats.total:
        return {
            'total_notes': 0,
            'moyenne_globale': 0,
            'distribution': {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
            'favorites_count': favorites_count
        }

    distribution_rows = db.session.query(
        func.round(Rating.note_globale).label('note'),
        func.count(Rating.id).label('count')
    ).filter_by(artwork_id=artwork_id).group_by(func.round(Rating.note_globale)).all()

    distribution = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for row in distribution_rows:
        note = int(row.note)
        if note in distribution:
            distribution[note] = row.count

    return {
        'total_notes': stats.total,
        'moyenne_globale': round(float(stats.moyenne), 1),
        'distribution': distribution,
        'favorites_count': favorites_count
    }


# ============================================================
# ROUTES - AUTHENTIFICATION
# ============================================================

# ---- Inscription ----
@limiter.limit("3 per minute")
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method != 'POST':
        return render_template('register.html')

    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    errors = []
    if not username or not email or not password:
        errors.append("Tous les champs sont obligatoires")
    errors.extend(validate_password_strength(password))
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        errors.append("Format d'email invalide")

    if errors:
        return render_template('register.html', errors=errors, username=username, email=email)

    existing_username = User.query.filter_by(username=username).first()
    existing_email = User.query.filter_by(email=email).first()

    if existing_username:
        errors.append("Ce nom d'utilisateur est déjà pris")
    if existing_email:
        if existing_email.email_verified:
            errors.append("Cet email est déjà utilisé")
        else:
            return handle_unverified_user(existing_email, email)
    if errors:
        return render_template('register.html', errors=errors, username=username, email=email)

    try:
        user = User(username=username, email=email, email_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        code = EmailVerification.generate_code()
        token = EmailVerification.generate_token()
        db.session.add(EmailVerification(
            user_id=user.id, token=token, code=code,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        ))
        db.session.commit()

        verify_link = f"{request.scheme}://{request.host}/verify-email?token={token}"
        if send_verification_email(email, username, code, verify_link):
            flash("Inscription réussie ! Un email de vérification vous a été envoyé.", 'success')
        else:
            flash("Compte créé mais erreur d'envoi d'email. Contactez le support.", 'warning')
        return redirect(url_for('verify_email_pending', email=email))

    except Exception as exc:
        db.session.rollback()
        logger.error("Erreur inscription : %s", exc)
        flash('Une erreur est survenue. Veuillez réessayer.', 'danger')
        return render_template('register.html', username=username, email=email)


# ---- Connexion ----
@limiter.limit("5 per minute")
@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next', '')

    if request.method != 'POST':
        return render_template('login.html', next=next_url)

    next_url = request.form.get('next', next_url)
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    user = User.query.filter_by(email=email).first()

    if user and user.check_password(password):
        if not user.email_verified:
            flash('Veuillez vérifier votre email avant de vous connecter.', 'warning')
            return redirect(url_for('verify_email_pending', email=user.email))

        session['user_id'] = user.id
        session['username'] = user.username
        user.last_login = datetime.utcnow()
        db.session.commit()

        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect(url_for('index'))

    flash('Email ou mot de passe incorrect', 'danger')
    return render_template('login.html', next=next_url)


# ---- Déconnexion ----
@app.route('/logout')
def logout():
    next_url = request.args.get('next', '')
    session.clear()
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('index'))


# ---- Profil utilisateur ----
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Utilisateur non trouvé', 'danger')
        return redirect(url_for('login'))
    return render_template('profile.html', user=user)


# ---- Changement de mot de passe ----
@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        flash('Veuillez vous connecter', 'warning')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    if request.method != 'POST':
        return render_template('change_password.html')

    current = request.form.get('current_password', '')
    new_pwd = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')
    errors = []

    if not user.check_password(current):
        errors.append("Mot de passe actuel incorrect")
    if new_pwd != confirm:
        errors.append("Les nouveaux mots de passe ne correspondent pas")
    errors.extend(validate_password_strength(new_pwd))

    if errors:
        for e in errors:
            flash(e, 'danger')
        return render_template('change_password.html')

    user.set_password(new_pwd)
    db.session.commit()
    flash('Mot de passe modifié avec succès !', 'success')
    return redirect(url_for('profile'))


# ---- Suppression de compte ----
@app.route('/delete-account', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        flash('Veuillez vous connecter', 'warning')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Utilisateur non trouvé', 'danger')
        return redirect(url_for('login'))
    
    password = request.form.get('password', '')
    if not user.check_password(password):
        flash('Mot de passe incorrect', 'danger')
        return redirect(url_for('profile'))

    try:
        EmailVerification.query.filter_by(user_id=user.id).delete()
        PasswordReset.query.filter_by(user_id=user.id).delete()
        Favorite.query.filter_by(user_id=user.id).delete()
        Rating.query.filter_by(user_id=user.id).delete()
        
        db.session.delete(user)
        db.session.commit()
        
        session.clear()
        flash('Votre compte a été supprimé avec succès', 'success')
        return redirect(url_for('index'))
        
    except Exception as exc:
        db.session.rollback()
        logger.error(f"Erreur suppression compte: {exc}")
        flash('Une erreur est survenue lors de la suppression', 'danger')
        return redirect(url_for('profile'))


# ---- Mise à jour du nom d'utilisateur ----
@app.route('/api/update-username', methods=['POST'])
def update_username():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    data = request.get_json() or {}
    new_username = data.get('username', '').strip()

    if not new_username:
        return jsonify({'error': 'Nom d\'utilisateur vide'}), 400
    if len(new_username) > 80:
        return jsonify({'error': 'Trop long (max 80 caractères)'}), 400

    existing = User.query.filter_by(username=new_username).first()
    if existing and existing.id != session['user_id']:
        return jsonify({'error': 'Ce nom d\'utilisateur est déjà pris'}), 409

    user = db.session.get(User, session['user_id'])
    user.username = new_username
    session['username'] = new_username
    db.session.commit()

    return jsonify({'success': True, 'username': new_username})


# ============================================================
# ROUTES - VÉRIFICATION EMAIL
# ============================================================

@app.route('/verify-email-pending')
def verify_email_pending():
    return render_template('verify_email_pending.html',
                           email=request.args.get('email', ''))


@app.route('/verify-email')
def verify_email():
    token = request.args.get('token', '')
    verification = EmailVerification.query.filter_by(token=token, used=False).first()

    if not verification or not verification.is_valid():
        flash('Lien de vérification invalide ou expiré.', 'danger')
        return redirect(url_for('login'))

    user = verification.user
    user.email_verified = True
    verification.used = True
    session['user_id'] = user.id
    session['username'] = user.username
    user.last_login = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/verify-code', methods=['POST'])
def verify_code():
    code = request.form.get('code', '').strip()
    email = request.form.get('email', '')
    user = User.query.filter_by(email=email).first()

    if not user:
        flash('Utilisateur non trouvé.', 'danger')
        return redirect(url_for('login'))

    verification = EmailVerification.query.filter_by(user_id=user.id, used=False).first()
    if not verification or verification.code != code or not verification.is_valid():
        flash('Code invalide ou expiré.', 'danger')
        return redirect(url_for('verify_email_pending', email=email))

    user.email_verified = True
    verification.used = True
    session['user_id'] = user.id
    session['username'] = user.username
    user.last_login = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/resend-verification', methods=['POST'])
def resend_verification():
    email = request.form.get('email', '')
    user = User.query.filter_by(email=email).first()

    if not user:
        flash('Utilisateur non trouvé.', 'danger')
        return redirect(url_for('register'))
    if user.email_verified:
        flash('Cet email est déjà vérifié.', 'info')
        return redirect(url_for('login'))

    EmailVerification.query.filter_by(user_id=user.id, used=False).update({'used': True})

    code = EmailVerification.generate_code()
    token = EmailVerification.generate_token()
    db.session.add(EmailVerification(
        user_id=user.id, token=token, code=code,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    ))
    db.session.commit()

    if send_verification_email(email, user.username, code, token):
        flash('Nouvel email de vérification envoyé !', 'success')
    else:
        flash("Erreur lors de l'envoi. Veuillez réessayer.", 'danger')
    return redirect(url_for('verify_email_pending', email=email))


# ============================================================
# ROUTES - MOT DE PASSE OUBLIÉ
# ============================================================

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({'error': 'Email requis'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'message': 'Si cet email existe, un lien de réinitialisation a été envoyé'}), 200

    PasswordReset.query.filter_by(user_id=user.id, used=False).update({'used': True})

    token = PasswordReset.generate_token()
    db.session.add(PasswordReset(
        user_id=user.id, token=token,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    ))
    db.session.commit()

    reset_link = f"{request.scheme}://{request.host}/reset-password?token={token}"
    
    if send_reset_email(email, user.username, reset_link):
        return jsonify({'message': 'Un email de réinitialisation a été envoyé'}), 200
    return jsonify({'error': "Erreur lors de l'envoi de l'email"}), 500


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token', '') or request.form.get('token', '')
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        
        reset = PasswordReset.query.filter_by(token=token, used=False).first()
        
        if not reset or not reset.is_valid():
            flash('Lien de réinitialisation invalide ou expiré', 'danger')
            return redirect(url_for('login'))
        
        if password != confirm:
            flash('Les mots de passe ne correspondent pas', 'danger')
            return render_template('reset_password.html', token=token)
        
        errors = validate_password_strength(password)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('reset_password.html', token=token)
        
        reset.user.set_password(password)
        reset.used = True
        db.session.commit()
        
        flash('Mot de passe modifié avec succès ! Vous pouvez vous connecter', 'success')
        return redirect(url_for('login'))
    
    reset = PasswordReset.query.filter_by(token=token, used=False).first()
    if not reset or not reset.is_valid():
        flash('Lien de réinitialisation invalide ou expiré', 'danger')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', token=token)


# ============================================================
# ROUTES - API FAVORIS & NOTES
# ============================================================

# ---- Vérification de session ----
@app.route('/api/check-session')
def check_session():
    return jsonify({'authenticated': 'user_id' in session, 'user_id': session.get('user_id')})


# ---- Favoris ----
@app.route('/api/favorite/toggle', methods=['POST'])
def toggle_favorite():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    artwork_id = (request.get_json() or {}).get('artwork_id')
    if not artwork_id:
        return jsonify({'error': 'ID œuvre manquant'}), 400

    fav = Favorite.query.filter_by(user_id=session['user_id'], artwork_id=artwork_id).first()
    if fav:
        db.session.delete(fav)
        db.session.commit()
        return jsonify({'favorite': False, 'message': 'Retiré des favoris'})
    else:
        db.session.add(Favorite(user_id=session['user_id'], artwork_id=artwork_id))
        db.session.commit()
        return jsonify({'favorite': True, 'message': 'Ajouté aux favoris'})


@app.route('/api/favorite/check/<artwork_id>')
def check_favorite(artwork_id):
    if 'user_id' not in session:
        return jsonify({'favorite': False})
    fav = Favorite.query.filter_by(user_id=session['user_id'], artwork_id=artwork_id).first()
    return jsonify({'favorite': fav is not None})


# ---- Notes ----
@app.route('/api/rating/save', methods=['POST'])
def save_rating():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    data = request.get_json() or {}
    artwork_id = data.get('artwork_id')

    rating = Rating.query.filter_by(user_id=session['user_id'], artwork_id=artwork_id).first()
    is_new = rating is None
    if is_new:
        rating = Rating(user_id=session['user_id'], artwork_id=artwork_id)

    rating.note_globale = float(data.get('note_globale', 0))
    rating.note_technique = float(data.get('note_technique', 0))
    rating.note_originalite = float(data.get('note_originalite', 0))
    rating.note_emotion = float(data.get('note_emotion', 0))
    rating.is_public = data.get('is_public', True)

    if 'commentaire' in data and data['commentaire'] != '':
        rating.commentaire = data['commentaire']

    if is_new:
        db.session.add(rating)
    db.session.commit()

    return jsonify({'success': True, 'rating': rating.to_dict()})


@app.route('/api/rating/delete', methods=['POST'])
def delete_rating():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    artwork_id = (request.get_json() or {}).get('artwork_id')
    rating = Rating.query.filter_by(user_id=session['user_id'], artwork_id=artwork_id).first()
    if not rating:
        return jsonify({'error': 'Commentaire non trouvé'}), 404

    db.session.delete(rating)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/rating/get/<artwork_id>')
def get_rating(artwork_id):
    if 'user_id' not in session:
        return jsonify({'has_rating': False})
    rating = Rating.query.filter_by(user_id=session['user_id'], artwork_id=artwork_id).first()
    if rating:
        return jsonify({'has_rating': True, 'rating': rating.to_dict()})
    return jsonify({'has_rating': False})


# ---- Commentaires ----
@app.route('/api/comments/<artwork_id>')
def get_comments(artwork_id):
    rows = db.session.query(Rating, User.username).join(
        User, Rating.user_id == User.id
    ).filter(
        Rating.artwork_id == artwork_id,
        Rating.commentaire.isnot(None),
        Rating.commentaire != '',
        Rating.is_public == True
    ).order_by(Rating.created_at.desc()).all()

    comments = []
    for rating, username in rows:
        comments.append({
            'username': username or 'Anonyme',
            'commentaire': rating.commentaire,
            'note_globale': rating.note_globale,
            'created_at': rating.created_at.strftime('%d/%m/%Y'),
        })
    return jsonify(comments)


# ---- Statistiques des œuvres ----
@app.route('/api/artwork/public-averages/<artwork_id>')
def artwork_public_averages(artwork_id):
    result = db.session.query(
        func.avg(Rating.note_technique).label('technique'),
        func.avg(Rating.note_originalite).label('originalite'),
        func.avg(Rating.note_emotion).label('emotion')
    ).filter(
        Rating.artwork_id == artwork_id,
        Rating.is_public == True
    ).first()
    
    return jsonify({
        'technique': float(result.technique) if result.technique else None,
        'originalite': float(result.originalite) if result.originalite else None,
        'emotion': float(result.emotion) if result.emotion else None
    })


@app.route('/api/artwork/stats/<artwork_id>')
def artwork_stats(artwork_id):
    if not Artwork.query.get(artwork_id):
        return jsonify({'error': 'Œuvre non trouvée'}), 404
    stats = get_artwork_stats(artwork_id)
    return jsonify(stats)


# ============================================================
# ROUTES - API CHARGEMENT INFINI
# ============================================================

# ---- Chargement des œuvres notées par l'utilisateur ----
@app.route('/api/rated/works')
def api_rated_works():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    user_id = session['user_id']
    
    rated_ids = db.session.query(Rating.artwork_id).filter_by(user_id=user_id).all()
    rated_ids = [r[0] for r in rated_ids]
    
    if not rated_ids:
        return jsonify({'works': [], 'has_more': False, 'total': 0})

    page = request.args.get('page', 1, type=int)
    limit = 12
    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types = request.args.getlist('type')
    movements = request.args.getlist('movement')
    genres = request.args.getlist('genre')
    materials = request.args.getlist('material')
    rating_global = request.args.get('rating_global', '')
    rating_technique = request.args.get('rating_technique', '')
    rating_originalite = request.args.get('rating_originalite', '')
    rating_emotion = request.args.get('rating_emotion', '')
    sort = request.args.get('sort', 'rating_desc')

    query = Artwork.query.filter(Artwork.id.in_(rated_ids))

    if artists:
        query = query.filter(db.or_(*[
            db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
            for a in artists
        ]))
    if country:
        query = query.filter(db.or_(
            Artwork.country_fr.ilike(f"%{country}%"),
            Artwork.country_en.ilike(f"%{country}%")
        ))
    if cities:
        query = query.filter(db.or_(*[
            db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
            for c in cities
        ]))
    if museums:
        query = query.filter(db.or_(*[
            db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                   Artwork.collection_en.ilike(f"%{m}%"))
            for m in museums
        ]))
    if types:
        query = query.filter(db.or_(*[
            db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
            for t in types
        ]))
    if movements:
        query = query.filter(db.or_(*[
            db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
            for m in movements
        ]))
    if genres:
        query = query.filter(db.or_(*[
            db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
            for g in genres
        ]))
    if materials:
        query = query.filter(db.or_(*[
            db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
            for mat in materials
        ]))

    if rating_global:
        exact_rating = float(rating_global)
        rated_ids_filtered = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_globale == exact_rating
        ).subquery()
        query = query.filter(Artwork.id.in_(rated_ids_filtered))
    if rating_technique:
        exact_rating = float(rating_technique)
        rated_ids_filtered = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_technique == exact_rating
        ).subquery()
        query = query.filter(Artwork.id.in_(rated_ids_filtered))
    if rating_originalite:
        exact_rating = float(rating_originalite)
        rated_ids_filtered = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_originalite == exact_rating
        ).subquery()
        query = query.filter(Artwork.id.in_(rated_ids_filtered))
    if rating_emotion:
        exact_rating = float(rating_emotion)
        rated_ids_filtered = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_emotion == exact_rating
        ).subquery()
        query = query.filter(Artwork.id.in_(rated_ids_filtered))

    if sort == 'rating_desc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.note_globale.desc())
    elif sort == 'rating_asc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.note_globale.asc())
    elif sort == 'technique_desc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.note_technique.desc())
    elif sort == 'originalite_desc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.note_originalite.desc())
    elif sort == 'emotion_desc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.note_emotion.desc())
    elif sort == 'date_desc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.created_at.desc())
    elif sort == 'date_asc':
        query = query.join(Rating, Artwork.id == Rating.artwork_id).filter(Rating.user_id == user_id)
        query = query.order_by(Rating.created_at.asc())
    elif sort == 'title_asc':
        col = Artwork.label_fr if session.get('language', 'fr') == 'fr' else Artwork.label_en
        query = query.order_by(col)
    elif sort == 'artist_asc':
        col = Artwork.creator_fr if session.get('language', 'fr') == 'fr' else Artwork.creator_en
        query = query.order_by(col)

    total = query.count()
    start = (page - 1) * limit
    has_more = (start + limit) < total
    works_page = query.offset(start).limit(limit).all()

    works = []
    for artwork in works_page:
        rating = Rating.query.filter_by(user_id=user_id, artwork_id=artwork.id).first()
        works.append({
            'id': artwork.id,
            'titre': artwork.titre,
            'createur': artwork.createur,
            'image_url': artwork.image_url,
            'user_rating_global': rating.note_globale if rating else 0,
            'user_rating_technique': rating.note_technique if rating else 0,
            'user_rating_originalite': rating.note_originalite if rating else 0,
            'user_rating_emotion': rating.note_emotion if rating else 0
        })

    return jsonify({'works': works, 'has_more': has_more, 'total': total})


# ---- Chargement de toutes les œuvres notées ----
@app.route('/api/all-rated/works')
def api_all_rated_works():
    page = request.args.get('page', 1, type=int)
    limit = 12
    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types = request.args.getlist('type')
    movements = request.args.getlist('movement')
    genres = request.args.getlist('genre')
    materials = request.args.getlist('material')
    rating_filter = request.args.get('rating', '')
    sort = request.args.get('sort', 'rating_desc')

    rating_subquery = db.session.query(
        Rating.artwork_id,
        func.avg(Rating.note_globale).label('avg_rating'),
        func.count(Rating.id).label('rating_count')
    ).group_by(Rating.artwork_id).subquery()

    query = Artwork.query.join(rating_subquery, Artwork.id == rating_subquery.c.artwork_id).filter(
        Artwork.image_url.isnot(None), Artwork.image_url != ''
    )

    if artists:
        query = query.filter(db.or_(*[
            db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
            for a in artists
        ]))
    if country:
        query = query.filter(db.or_(
            Artwork.country_fr.ilike(f"%{country}%"),
            Artwork.country_en.ilike(f"%{country}%")
        ))
    if cities:
        query = query.filter(db.or_(*[
            db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
            for c in cities
        ]))
    if museums:
        query = query.filter(db.or_(*[
            db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                   Artwork.collection_en.ilike(f"%{m}%"))
            for m in museums
        ]))
    if types:
        query = query.filter(db.or_(*[
            db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
            for t in types
        ]))
    if movements:
        query = query.filter(db.or_(*[
            db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
            for m in movements
        ]))
    if genres:
        query = query.filter(db.or_(*[
            db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
            for g in genres
        ]))
    if materials:
        query = query.filter(db.or_(*[
            db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
            for mat in materials
        ]))

    if rating_filter:
        min_rating = int(rating_filter)
        query = query.filter(rating_subquery.c.avg_rating >= min_rating)

    if sort == 'rating_desc':
        query = query.order_by(rating_subquery.c.avg_rating.desc().nullslast())
    elif sort == 'rating_asc':
        query = query.order_by(rating_subquery.c.avg_rating.asc().nullslast())
    elif sort == 'count_desc':
        query = query.order_by(rating_subquery.c.rating_count.desc().nullslast())
    elif sort == 'title_asc':
        col = Artwork.label_fr if session.get('language', 'fr') == 'fr' else Artwork.label_en
        query = query.order_by(col)
    elif sort == 'artist_asc':
        col = Artwork.creator_fr if session.get('language', 'fr') == 'fr' else Artwork.creator_en
        query = query.order_by(col)
    elif sort == 'date_desc':
        query = query.order_by(Artwork.inception.desc().nullslast())
    elif sort == 'date_asc':
        query = query.order_by(Artwork.inception.asc().nullslast())

    total = query.count()
    start = (page - 1) * limit
    has_more = (start + limit) < total
    works_page = query.offset(start).limit(limit).all()

    works = []
    for artwork in works_page:
        stats = db.session.query(
            func.avg(Rating.note_globale).label('avg_rating'),
            func.count(Rating.id).label('rating_count')
        ).filter_by(artwork_id=artwork.id).first()
        works.append({
            'id': artwork.id,
            'titre': artwork.titre,
            'createur': artwork.createur,
            'image_url': artwork.image_url,
            'avg_rating': stats.avg_rating if stats.avg_rating else 0,
            'rating_count': stats.rating_count or 0
        })

    return jsonify({'works': works, 'has_more': has_more, 'total': total})


# ---- Chargement des favoris ----
@app.route('/api/favorites/works')
def api_favorites_works():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    favs = Favorite.query.filter_by(user_id=session['user_id']).all()
    if not favs:
        return jsonify({'works': [], 'has_more': False, 'total': 0})

    fav_ids = [f.artwork_id for f in favs]
    fav_date_map = {f.artwork_id: f.created_at for f in favs}

    page = request.args.get('page', 1, type=int)
    limit = 12
    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types = request.args.getlist('type')
    sort = request.args.get('sort', 'date_added')

    query = Artwork.query.filter(Artwork.id.in_(fav_ids))

    if artists:
        query = query.filter(db.or_(*[
            db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
            for a in artists
        ]))
    if country:
        query = query.filter(db.or_(
            Artwork.country_fr.ilike(f"%{country}%"),
            Artwork.country_en.ilike(f"%{country}%")
        ))
    if cities:
        query = query.filter(db.or_(*[
            db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
            for c in cities
        ]))
    if museums:
        query = query.filter(db.or_(*[
            db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                   Artwork.collection_en.ilike(f"%{m}%"))
            for m in museums
        ]))
    if types:
        type_filters = []
        for t in types:
            type_filters.append(Artwork.instance_of_fr.ilike(f"%{t}%"))
            type_filters.append(Artwork.instance_of_en.ilike(f"%{t}%"))
        query = query.filter(db.or_(*type_filters))

    start = (page - 1) * limit

    if sort == 'date_added':
        all_artworks = query.all()
        all_artworks.sort(key=lambda a: fav_date_map.get(a.id, datetime.min), reverse=True)
        total = len(all_artworks)
        page_artworks = all_artworks[start:start + limit]
    else:
        query = _apply_sort(query, sort)
        total = query.count()
        page_artworks = query.offset(start).limit(limit).all()

    has_more = (start + limit) < total
    works = [{
        'id': w.id, 'titre': w.titre,
        'createur': w.createur, 'image_url': w.image_url
    } for w in page_artworks]

    return jsonify({'works': works, 'has_more': has_more, 'total': total})


# ============================================================
# ROUTES - API FILTRES & RECHERCHE
# ============================================================

# ---- Suggestions de recherche ----
@app.route('/api/search-suggestions')
def search_suggestions():
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify({'artistes': [], 'oeuvres': [], 'musees': [], 'villes': [], 'pays': []})

        query = clean_search_query(query)
        lang = session.get('language', 'fr')
        pattern = f"%{query}%"
        
        results = {'artistes': [], 'oeuvres': [], 'musees': [], 'villes': [], 'pays': []}

        if lang == 'fr':
            artist_field = Artwork.creator_fr
            title_field = Artwork.label_fr
            museum_field = Artwork.collection_fr
            city_field = Artwork.city_fr
            country_field = Artwork.country_fr
        else:
            artist_field = Artwork.creator_en
            title_field = Artwork.label_en
            museum_field = Artwork.collection_en
            city_field = Artwork.city_en
            country_field = Artwork.country_en

        artists = db.session.query(
            artist_field.label('nom'), func.count(Artwork.id).label('c')
        ).filter(
            artist_field.ilike(pattern),
            artist_field.isnot(None), artist_field != '',
            artist_field != 'Artiste inconnu', artist_field != 'Unknown artist'
        ).group_by(artist_field).order_by(func.count(Artwork.id).desc()).limit(3).all()
        results['artistes'] = [{'nom': a.nom, 'oeuvres_count': a.c} for a in artists]

        musees = db.session.query(
            museum_field.label('nom'), func.count(Artwork.id).label('c')
        ).filter(
            museum_field.ilike(pattern), museum_field.isnot(None), museum_field != ''
        ).group_by(museum_field).order_by(func.count(Artwork.id).desc()).limit(3).all()
        results['musees'] = [{'nom': m.nom, 'oeuvres_count': m.c} for m in musees]

        pays = db.session.query(
            country_field.label('nom'), func.count(Artwork.id).label('c')
        ).filter(
            country_field.ilike(pattern), country_field.isnot(None), country_field != ''
        ).group_by(country_field).order_by(func.count(Artwork.id).desc()).limit(3).all()
        results['pays'] = [{'nom': p.nom, 'oeuvres_count': p.c} for p in pays]

        villes = db.session.query(
            city_field.label('nom'), func.count(Artwork.id).label('c')
        ).filter(
            city_field.ilike(pattern), city_field.isnot(None), city_field != ''
        ).group_by(city_field).order_by(func.count(Artwork.id).desc()).limit(3).all()
        results['villes'] = [{'nom': v.nom, 'oeuvres_count': v.c} for v in villes]

        works = db.session.query(
            title_field.label('titre'), Artwork.id
        ).filter(
            title_field.ilike(pattern), title_field.isnot(None), title_field != ''
        ).limit(3).all()
        results['oeuvres'] = [{'id': w.id, 'titre': w.titre} for w in works]

        return jsonify(results)

    except Exception as e:
        print(f"❌ ERREUR: {str(e)}")
        return jsonify({'artistes': [], 'oeuvres': [], 'musees': [], 'villes': [], 'pays': []})


# ---- API de filtres (Artistes, Pays, Villes, Musées, Types, Mouvements, Genres, Matériaux) ----
@app.route('/api/filter-artists')
def api_filter_artists():
    try:
        lang = session.get('language', 'fr')
        artist_field = Artwork.creator_fr if lang == 'fr' else Artwork.creator_en

        selected_artists = request.args.getlist('artist')
        selected_country = request.args.get('country', '')
        selected_cities = request.args.getlist('city')
        selected_museums = request.args.getlist('museum')
        selected_types = request.args.getlist('type')
        selected_movements = request.args.getlist('movement')
        selected_genres = request.args.getlist('genre')
        selected_materials = request.args.getlist('material')
        q = request.args.get('q', '')

        query = db.session.query(
            artist_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            artist_field.isnot(None), artist_field != '',
            artist_field != 'Artiste inconnu', artist_field != 'Unknown artist'
        )

        if selected_country:
            query = query.filter(db.or_(
                Artwork.country_fr.ilike(f"%{selected_country}%"),
                Artwork.country_en.ilike(f"%{selected_country}%")
            ))
        if selected_cities:
            query = query.filter(db.or_(*[
                db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
                for c in selected_cities
            ]))
        if selected_museums:
            filters = []
            for m in selected_museums:
                if m == 'divers':
                    filters.append(db.or_(
                        Artwork.collection_id.is_(None), Artwork.collection_id == '',
                        Artwork.collection_fr.is_(None), Artwork.collection_fr == ''
                    ))
                else:
                    filters.append(db.or_(
                        Artwork.collection_id == m,
                        Artwork.collection_fr.ilike(f"%{m}%"),
                        Artwork.collection_en.ilike(f"%{m}%")
                    ))
            query = query.filter(db.or_(*filters))
        if selected_types:
            query = query.filter(db.or_(*[
                db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
                for t in selected_types
            ]))
        if selected_movements:
            query = query.filter(db.or_(*[
                db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
                for m in selected_movements
            ]))
        if selected_genres:
            query = query.filter(db.or_(*[
                db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
                for g in selected_genres
            ]))
        if selected_materials:
            query = query.filter(db.or_(*[
                db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
                for mat in selected_materials
            ]))
        if q:
            s = f"%{q}%"
            query = query.filter(db.or_(
                Artwork.label_fr.ilike(s), Artwork.label_en.ilike(s),
                Artwork.creator_fr.ilike(s), Artwork.creator_en.ilike(s),
            ))

        artists = query.group_by(artist_field).order_by(func.count(Artwork.id).desc()).limit(100).all()

        return jsonify([{
            'id': a.name, 'name': a.name, 'count': a.count,
            'selected': a.name in selected_artists
        } for a in artists])

    except Exception as e:
        print(f"Erreur filter-artists: {e}")
        return jsonify([])


@app.route('/api/filter-countries')
def api_filter_countries():
    try:
        lang = session.get('language', 'fr')
        country_field = Artwork.country_fr if lang == 'fr' else Artwork.country_en

        selected_artists = request.args.getlist('artist')
        selected_cities = request.args.getlist('city')
        selected_museums = request.args.getlist('museum')
        selected_country = request.args.get('country', '')
        selected_types = request.args.getlist('type')
        selected_movements = request.args.getlist('movement')
        selected_genres = request.args.getlist('genre')
        selected_materials = request.args.getlist('material')
        q = request.args.get('q', '')

        query = db.session.query(
            country_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(country_field.isnot(None), country_field != '')

        if selected_artists:
            query = query.filter(db.or_(*[
                db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
                for a in selected_artists
            ]))
        if selected_cities:
            query = query.filter(db.or_(*[
                db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
                for c in selected_cities
            ]))
        if selected_museums:
            filters = []
            for m in selected_museums:
                if m == 'divers':
                    filters.append(db.or_(
                        Artwork.collection_id.is_(None), Artwork.collection_id == '',
                        Artwork.collection_fr.is_(None), Artwork.collection_fr == ''
                    ))
                else:
                    filters.append(db.or_(
                        Artwork.collection_id == m,
                        Artwork.collection_fr.ilike(f"%{m}%"),
                        Artwork.collection_en.ilike(f"%{m}%")
                    ))
            query = query.filter(db.or_(*filters))
        if selected_types:
            query = query.filter(db.or_(*[
                db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
                for t in selected_types
            ]))
        if selected_movements:
            query = query.filter(db.or_(*[
                db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
                for m in selected_movements
            ]))
        if selected_genres:
            query = query.filter(db.or_(*[
                db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
                for g in selected_genres
            ]))
        if selected_materials:
            query = query.filter(db.or_(*[
                db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
                for mat in selected_materials
            ]))
        if q:
            s = f"%{q}%"
            query = query.filter(db.or_(
                Artwork.label_fr.ilike(s), Artwork.label_en.ilike(s),
                Artwork.creator_fr.ilike(s), Artwork.creator_en.ilike(s),
            ))

        countries = query.group_by(country_field).order_by(func.count(Artwork.id).desc()).limit(50).all()

        return jsonify([{
            'id': c.name, 'name': c.name, 'count': c.count,
            'selected': c.name == selected_country
        } for c in countries])

    except Exception as e:
        print(f"Erreur filter-countries: {e}")
        return jsonify([])


@app.route('/api/filter-cities')
def api_filter_cities():
    try:
        lang = session.get('language', 'fr')
        city_field = Artwork.city_fr if lang == 'fr' else Artwork.city_en
        country_field = Artwork.country_fr if lang == 'fr' else Artwork.country_en

        selected_artists = request.args.getlist('artist')
        selected_country = request.args.get('country', '')
        selected_cities = request.args.getlist('city')
        selected_museums = request.args.getlist('museum')
        selected_types = request.args.getlist('type')
        selected_movements = request.args.getlist('movement')
        selected_genres = request.args.getlist('genre')
        selected_materials = request.args.getlist('material')

        query = db.session.query(
            city_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(city_field.isnot(None), city_field != '')

        if selected_artists:
            query = query.filter(db.or_(*[
                db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
                for a in selected_artists
            ]))
        if selected_country:
            query = query.filter(db.or_(
                country_field.ilike(f"%{selected_country}%"),
                func.unaccent(country_field).ilike(f"%{selected_country}%")
            ))
        if selected_museums:
            query = query.filter(db.or_(*[
                db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                       Artwork.collection_en.ilike(f"%{m}%"))
                for m in selected_museums
            ]))
        if selected_types:
            query = query.filter(db.or_(*[
                db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
                for t in selected_types
            ]))
        if selected_movements:
            query = query.filter(db.or_(*[
                db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
                for m in selected_movements
            ]))
        if selected_genres:
            query = query.filter(db.or_(*[
                db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
                for g in selected_genres
            ]))
        if selected_materials:
            query = query.filter(db.or_(*[
                db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
                for mat in selected_materials
            ]))

        cities = query.group_by(city_field).order_by(func.count(Artwork.id).desc()).limit(50).all()

        return jsonify([{
            'id': c.name, 'name': c.name, 'count': c.count,
            'selected': c.name in selected_cities
        } for c in cities])

    except Exception as e:
        print(f"Erreur filter-cities: {e}")
        return jsonify([])


@app.route('/api/filter-museums')
def api_filter_museums():
    try:
        lang = session.get('language', 'fr')
        museum_field = Artwork.collection_fr if lang == 'fr' else Artwork.collection_en

        selected_artists = request.args.getlist('artist')
        selected_country = request.args.get('country', '')
        selected_cities = request.args.getlist('city')
        selected_museums = request.args.getlist('museum')
        selected_types = request.args.getlist('type')
        selected_movements = request.args.getlist('movement')
        selected_genres = request.args.getlist('genre')
        selected_materials = request.args.getlist('material')

        query = db.session.query(
            museum_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            museum_field.isnot(None), museum_field != '',
            Artwork.image_url.isnot(None), Artwork.image_url != ''
        )

        if selected_artists:
            query = query.filter(db.or_(*[
                db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
                for a in selected_artists
            ]))
        if selected_country:
            query = query.filter(db.or_(
                Artwork.country_fr.ilike(f"%{selected_country}%"),
                Artwork.country_en.ilike(f"%{selected_country}%")
            ))
        if selected_cities:
            query = query.filter(db.or_(*[
                db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
                for c in selected_cities
            ]))
        if selected_types:
            query = query.filter(db.or_(*[
                db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
                for t in selected_types
            ]))
        if selected_movements:
            query = query.filter(db.or_(*[
                db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
                for m in selected_movements
            ]))
        if selected_genres:
            query = query.filter(db.or_(*[
                db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
                for g in selected_genres
            ]))
        if selected_materials:
            query = query.filter(db.or_(*[
                db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
                for mat in selected_materials
            ]))

        museums = query.group_by(museum_field).order_by(func.count(Artwork.id).desc()).limit(100).all()

        return jsonify([{
            'id': m.name, 'name': m.name, 'count': m.count,
            'selected': m.name in selected_museums
        } for m in museums])

    except Exception as e:
        print(f"Erreur filter-museums: {e}")
        return jsonify([])


@app.route('/api/filter-types')
def api_filter_types():
    try:
        lang = session.get('language', 'fr')
        type_field = Artwork.instance_of_fr if lang == 'fr' else Artwork.instance_of_en

        selected_artists = request.args.getlist('artist')
        selected_country = request.args.get('country', '')
        selected_cities = request.args.getlist('city')
        selected_museums = request.args.getlist('museum')
        selected_movements = request.args.getlist('movement')
        selected_genres = request.args.getlist('genre')
        selected_materials = request.args.getlist('material')
        selected_types = request.args.getlist('type')
        search_term = request.args.get('search', '').strip()

        query = db.session.query(
            type_field.label('name'), func.count(func.distinct(Artwork.id)).label('count')
        ).filter(
            type_field.isnot(None), type_field != '',
            Artwork.image_url.isnot(None), Artwork.image_url != ''
        )

        if selected_artists:
            query = query.filter(db.or_(*[
                db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
                for a in selected_artists
            ]))
        if selected_country:
            query = query.filter(db.or_(
                Artwork.country_fr.ilike(f"%{selected_country}%"),
                Artwork.country_en.ilike(f"%{selected_country}%")
            ))
        if selected_cities:
            query = query.filter(db.or_(*[
                db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
                for c in selected_cities
            ]))
        if selected_museums:
            query = query.filter(db.or_(*[
                db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                       Artwork.collection_en.ilike(f"%{m}%"))
                for m in selected_museums
            ]))
        if selected_movements:
            query = query.filter(db.or_(*[
                db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
                for m in selected_movements
            ]))
        if selected_genres:
            query = query.filter(db.or_(*[
                db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
                for g in selected_genres
            ]))
        if selected_materials:
            query = query.filter(db.or_(*[
                db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
                for mat in selected_materials
            ]))

        if search_term:
            query = query.filter(type_field.ilike(f"%{search_term}%"))
            types = query.group_by(type_field).order_by(
                func.count(func.distinct(Artwork.id)).desc()
            ).all()
        else:
            types = query.group_by(type_field).order_by(
                func.count(func.distinct(Artwork.id)).desc()
            ).limit(200).all()

        return jsonify([{
            'name': t.name, 'count': t.count, 'selected': t.name in selected_types
        } for t in types])

    except Exception as e:
        print(f"Erreur filter-types: {e}")
        return jsonify([])


@app.route('/api/filter-movements')
def api_filter_movements():
    try:
        lang = session.get('language', 'fr')
        movement_field = Artwork.movement_fr if lang == 'fr' else Artwork.movement_en
        
        selected_artists = request.args.getlist('artist')
        selected_country = request.args.get('country', '')
        selected_cities = request.args.getlist('city')
        selected_museums = request.args.getlist('museum')
        selected_types = request.args.getlist('type')
        selected_genres = request.args.getlist('genre')
        selected_materials = request.args.getlist('material')
        selected_movements = request.args.getlist('movement')
        
        query = db.session.query(
            movement_field.label('name'), func.count(func.distinct(Artwork.id)).label('count')
        ).filter(
            movement_field.isnot(None), movement_field != '',
            Artwork.image_url.isnot(None), Artwork.image_url != ''
        )
        
        if selected_artists:
            query = query.filter(db.or_(*[
                db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
                for a in selected_artists
            ]))
        if selected_country:
            query = query.filter(db.or_(
                Artwork.country_fr.ilike(f"%{selected_country}%"),
                Artwork.country_en.ilike(f"%{selected_country}%")
            ))
        if selected_cities:
            query = query.filter(db.or_(*[
                db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
                for c in selected_cities
            ]))
        if selected_museums:
            query = query.filter(db.or_(*[
                db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                       Artwork.collection_en.ilike(f"%{m}%"))
                for m in selected_museums
            ]))
        if selected_types:
            query = query.filter(db.or_(*[
                db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
                for t in selected_types
            ]))
        if selected_genres:
            query = query.filter(db.or_(*[
                db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
                for g in selected_genres
            ]))
        if selected_materials:
            query = query.filter(db.or_(*[
                db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
                for mat in selected_materials
            ]))
        
        movements = query.group_by(movement_field).order_by(
            func.count(func.distinct(Artwork.id)).desc()
        ).limit(100).all()
        
        return jsonify([{
            'name': m.name, 'count': m.count, 'selected': m.name in selected_movements
        } for m in movements])
        
    except Exception as e:
        print(f"Erreur filter-movements: {e}")
        return jsonify([])


@app.route('/api/filter-genres')
def api_filter_genres():
    try:
        lang = session.get('language', 'fr')
        genre_field = Artwork.genre_fr if lang == 'fr' else Artwork.genre_en
        
        selected_artists = request.args.getlist('artist')
        selected_country = request.args.get('country', '')
        selected_cities = request.args.getlist('city')
        selected_museums = request.args.getlist('museum')
        selected_types = request.args.getlist('type')
        selected_movements = request.args.getlist('movement')
        selected_materials = request.args.getlist('material')
        selected_genres = request.args.getlist('genre')
        
        query = db.session.query(
            genre_field.label('name'), func.count(func.distinct(Artwork.id)).label('count')
        ).filter(
            genre_field.isnot(None), genre_field != '',
            Artwork.image_url.isnot(None), Artwork.image_url != ''
        )
        
        if selected_artists:
            query = query.filter(db.or_(*[
                db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
                for a in selected_artists
            ]))
        if selected_country:
            query = query.filter(db.or_(
                Artwork.country_fr.ilike(f"%{selected_country}%"),
                Artwork.country_en.ilike(f"%{selected_country}%")
            ))
        if selected_cities:
            query = query.filter(db.or_(*[
                db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
                for c in selected_cities
            ]))
        if selected_museums:
            query = query.filter(db.or_(*[
                db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                       Artwork.collection_en.ilike(f"%{m}%"))
                for m in selected_museums
            ]))
        if selected_types:
            query = query.filter(db.or_(*[
                db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
                for t in selected_types
            ]))
        if selected_movements:
            query = query.filter(db.or_(*[
                db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
                for m in selected_movements
            ]))
        if selected_materials:
            query = query.filter(db.or_(*[
                db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
                for mat in selected_materials
            ]))
        
        genres = query.group_by(genre_field).order_by(
            func.count(func.distinct(Artwork.id)).desc()
        ).limit(100).all()
        
        return jsonify([{
            'name': g.name, 'count': g.count, 'selected': g.name in selected_genres
        } for g in genres])
        
    except Exception as e:
        print(f"Erreur filter-genres: {e}")
        return jsonify([])


@app.route('/api/filter-materials')
def api_filter_materials():
    try:
        lang = session.get('language', 'fr')
        material_field = Artwork.made_from_material_fr if lang == 'fr' else Artwork.made_from_material_en
        
        selected_artists = request.args.getlist('artist')
        selected_country = request.args.get('country', '')
        selected_cities = request.args.getlist('city')
        selected_museums = request.args.getlist('museum')
        selected_types = request.args.getlist('type')
        selected_movements = request.args.getlist('movement')
        selected_genres = request.args.getlist('genre')
        selected_materials = request.args.getlist('material')
        
        query = db.session.query(
            material_field.label('name'), func.count(func.distinct(Artwork.id)).label('count')
        ).filter(
            material_field.isnot(None), material_field != '',
            Artwork.image_url.isnot(None), Artwork.image_url != ''
        )
        
        if selected_artists:
            query = query.filter(db.or_(*[
                db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
                for a in selected_artists
            ]))
        if selected_country:
            query = query.filter(db.or_(
                Artwork.country_fr.ilike(f"%{selected_country}%"),
                Artwork.country_en.ilike(f"%{selected_country}%")
            ))
        if selected_cities:
            query = query.filter(db.or_(*[
                db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
                for c in selected_cities
            ]))
        if selected_museums:
            query = query.filter(db.or_(*[
                db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                       Artwork.collection_en.ilike(f"%{m}%"))
                for m in selected_museums
            ]))
        if selected_types:
            query = query.filter(db.or_(*[
                db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
                for t in selected_types
            ]))
        if selected_movements:
            query = query.filter(db.or_(*[
                db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
                for m in selected_movements
            ]))
        if selected_genres:
            query = query.filter(db.or_(*[
                db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
                for g in selected_genres
            ]))
        
        materials = query.group_by(material_field).order_by(
            func.count(func.distinct(Artwork.id)).desc()
        ).limit(100).all()
        
        return jsonify([{
            'name': m.name, 'count': m.count, 'selected': m.name in selected_materials
        } for m in materials])
        
    except Exception as e:
        print(f"Erreur filter-materials: {e}")
        return jsonify([])


@app.route('/api/filter-options')
def api_filter_options():
    """Endpoint unifié pour récupérer toutes les options de filtres"""
    # Cette route est un alias pour api_all_rated_filter_options
    return api_all_rated_filter_options()


@app.route('/api/all-rated/filter-options')
def api_all_rated_filter_options():
    try:
        lang = session.get('language', 'fr')
        rated_artwork_ids = db.session.query(Rating.artwork_id).distinct().subquery()

        result = {}
        
        artist_field = Artwork.creator_fr if lang == 'fr' else Artwork.creator_en
        artists = db.session.query(
            artist_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(rated_artwork_ids), artist_field.isnot(None), artist_field != '',
            artist_field != 'Artiste inconnu', artist_field != 'Unknown artist'
        ).group_by(artist_field).order_by(func.count(Artwork.id).desc()).limit(50).all()
        result['artists'] = [{'id': a.name, 'name': a.name, 'count': a.count} for a in artists]

        museum_field = Artwork.collection_fr if lang == 'fr' else Artwork.collection_en
        museums = db.session.query(
            museum_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(rated_artwork_ids), museum_field.isnot(None), museum_field != ''
        ).group_by(museum_field).order_by(func.count(Artwork.id).desc()).limit(50).all()
        result['museums'] = [{'id': m.name, 'name': m.name, 'count': m.count} for m in museums]

        country_field = Artwork.country_fr if lang == 'fr' else Artwork.country_en
        countries = db.session.query(
            country_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(rated_artwork_ids), country_field.isnot(None), country_field != ''
        ).group_by(country_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['countries'] = [{'id': c.name, 'name': c.name, 'count': c.count} for c in countries]

        city_field = Artwork.city_fr if lang == 'fr' else Artwork.city_en
        cities = db.session.query(
            city_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(rated_artwork_ids), city_field.isnot(None), city_field != ''
        ).group_by(city_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['cities'] = [{'id': c.name, 'name': c.name, 'count': c.count} for c in cities]

        type_field = Artwork.instance_of_fr if lang == 'fr' else Artwork.instance_of_en
        types = db.session.query(
            type_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(rated_artwork_ids), type_field.isnot(None), type_field != ''
        ).group_by(type_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['types'] = [{'name': t.name, 'count': t.count} for t in types]

        movement_field = Artwork.movement_fr if lang == 'fr' else Artwork.movement_en
        movements = db.session.query(
            movement_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(rated_artwork_ids), movement_field.isnot(None), movement_field != ''
        ).group_by(movement_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['movements'] = [{'name': m.name, 'count': m.count} for m in movements]

        genre_field = Artwork.genre_fr if lang == 'fr' else Artwork.genre_en
        genres = db.session.query(
            genre_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(rated_artwork_ids), genre_field.isnot(None), genre_field != ''
        ).group_by(genre_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['genres'] = [{'name': g.name, 'count': g.count} for g in genres]

        material_field = Artwork.made_from_material_fr if lang == 'fr' else Artwork.made_from_material_en
        materials = db.session.query(
            material_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(rated_artwork_ids), material_field.isnot(None), material_field != ''
        ).group_by(material_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['materials'] = [{'name': m.name, 'count': m.count} for m in materials]

        return jsonify(result)

    except Exception as e:
        print(f"Erreur api_all_rated_filter_options: {e}")
        return jsonify({'artists': [], 'museums': [], 'types': [], 'movements': [], 'genres': [], 'materials': [], 'countries': [], 'cities': []})


@app.route('/api/rated/filter-options')
def api_rated_filter_options():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    user_id = session['user_id']

    rated_ids = db.session.query(Rating.artwork_id).filter_by(user_id=user_id).all()
    rated_ids = [r[0] for r in rated_ids]
    if not rated_ids:
        return jsonify({'artists': [], 'museums': [], 'countries': [], 'cities': [],
                        'types': [], 'movements': [], 'genres': [], 'materials': []})

    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types = request.args.getlist('type')
    movements = request.args.getlist('movement')
    genres = request.args.getlist('genre')
    materials = request.args.getlist('material')
    rating_global = request.args.getlist('rating_global')
    rating_technique = request.args.getlist('rating_technique')
    rating_originalite = request.args.getlist('rating_originalite')
    rating_emotion = request.args.getlist('rating_emotion')

    query = Artwork.query.filter(Artwork.id.in_(rated_ids))

    if artists:
        query = query.filter(db.or_(*[
            db.or_(Artwork.creator_fr.ilike(f"%{a}%"), Artwork.creator_en.ilike(f"%{a}%"))
            for a in artists
        ]))
    if country:
        query = query.filter(db.or_(
            Artwork.country_fr.ilike(f"%{country}%"),
            Artwork.country_en.ilike(f"%{country}%")
        ))
    if cities:
        query = query.filter(db.or_(*[
            db.or_(Artwork.city_fr.ilike(f"%{c}%"), Artwork.city_en.ilike(f"%{c}%"))
            for c in cities
        ]))
    if museums:
        query = query.filter(db.or_(*[
            db.or_(Artwork.collection_id == m, Artwork.collection_fr.ilike(f"%{m}%"),
                   Artwork.collection_en.ilike(f"%{m}%"))
            for m in museums
        ]))
    if types:
        query = query.filter(db.or_(*[
            db.or_(Artwork.instance_of_fr.ilike(f"%{t}%"), Artwork.instance_of_en.ilike(f"%{t}%"))
            for t in types
        ]))
    if movements:
        query = query.filter(db.or_(*[
            db.or_(Artwork.movement_fr.ilike(f"%{m}%"), Artwork.movement_en.ilike(f"%{m}%"))
            for m in movements
        ]))
    if genres:
        query = query.filter(db.or_(*[
            db.or_(Artwork.genre_fr.ilike(f"%{g}%"), Artwork.genre_en.ilike(f"%{g}%"))
            for g in genres
        ]))
    if materials:
        query = query.filter(db.or_(*[
            db.or_(Artwork.made_from_material_fr.ilike(f"%{mat}%"), Artwork.made_from_material_en.ilike(f"%{mat}%"))
            for mat in materials
        ]))
    if rating_global:
        vals = [float(v) for v in rating_global]
        sub = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_globale.in_(vals)
        ).subquery()
        query = query.filter(Artwork.id.in_(sub))
    if rating_technique:
        vals = [float(v) for v in rating_technique]
        sub = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_technique.in_(vals)
        ).subquery()
        query = query.filter(Artwork.id.in_(sub))
    if rating_originalite:
        vals = [float(v) for v in rating_originalite]
        sub = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_originalite.in_(vals)
        ).subquery()
        query = query.filter(Artwork.id.in_(sub))
    if rating_emotion:
        vals = [float(v) for v in rating_emotion]
        sub = db.session.query(Rating.artwork_id).filter(
            Rating.user_id == user_id, Rating.note_emotion.in_(vals)
        ).subquery()
        query = query.filter(Artwork.id.in_(sub))

    works = query.all()
    lang = session.get('language', 'fr')

    def unique_sorted(values):
        return sorted({v.strip() for w in values for v in (w or '').split(';') if v.strip()})

    creator_field = 'creator_fr' if lang == 'fr' else 'creator_en'
    artists_raw = unique_sorted([getattr(w, creator_field) for w in works])
    artists_out = [{'id': a, 'name': a} for a in artists_raw]

    collection_field = 'collection_fr' if lang == 'fr' else 'collection_en'
    museums_raw = unique_sorted([getattr(w, collection_field) for w in works])
    museums_out = [{'id': m, 'name': m} for m in museums_raw]

    country_field = 'country_fr' if lang == 'fr' else 'country_en'
    countries_raw = unique_sorted([getattr(w, country_field) for w in works])
    countries_out = [{'id': c, 'name': c} for c in countries_raw]

    city_field = 'city_fr' if lang == 'fr' else 'city_en'
    cities_raw = unique_sorted([getattr(w, city_field) for w in works])
    cities_out = [{'id': c, 'name': c} for c in cities_raw]

    type_field = 'instance_of_fr' if lang == 'fr' else 'instance_of_en'
    types_raw = unique_sorted([getattr(w, type_field) for w in works])
    types_out = [{'name': t} for t in types_raw]

    movement_field = 'movement_fr' if lang == 'fr' else 'movement_en'
    movements_raw = unique_sorted([getattr(w, movement_field) for w in works])
    movements_out = [{'name': m} for m in movements_raw]

    genre_field = 'genre_fr' if lang == 'fr' else 'genre_en'
    genres_raw = unique_sorted([getattr(w, genre_field) for w in works])
    genres_out = [{'name': g} for g in genres_raw]

    material_field = 'made_from_material_fr' if lang == 'fr' else 'made_from_material_en'
    materials_raw = unique_sorted([getattr(w, material_field) for w in works])
    materials_out = [{'name': m} for m in materials_raw]

    return jsonify({
        'artists': artists_out, 'museums': museums_out,
        'countries': countries_out, 'cities': cities_out,
        'types': types_out, 'movements': movements_out,
        'genres': genres_out, 'materials': materials_out,
    })


@app.route('/api/favorites/filter-options')
def api_favorites_filter_options():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    try:
        lang = session.get('language', 'fr')
        fav_ids = [f.artwork_id for f in Favorite.query.filter_by(user_id=session['user_id']).all()]
        if not fav_ids:
            return jsonify({'artists': [], 'museums': [], 'types': [], 'movements': [], 'genres': [], 'materials': [], 'countries': [], 'cities': []})

        result = {}
        
        artist_field = Artwork.creator_fr if lang == 'fr' else Artwork.creator_en
        artists = db.session.query(
            artist_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(fav_ids), artist_field.isnot(None), artist_field != '',
            artist_field != 'Artiste inconnu', artist_field != 'Unknown artist'
        ).group_by(artist_field).order_by(func.count(Artwork.id).desc()).limit(50).all()
        result['artists'] = [{'id': a.name, 'name': a.name, 'count': a.count} for a in artists]

        museum_field = Artwork.collection_fr if lang == 'fr' else Artwork.collection_en
        museums = db.session.query(
            museum_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(fav_ids), museum_field.isnot(None), museum_field != ''
        ).group_by(museum_field).order_by(func.count(Artwork.id).desc()).limit(50).all()
        result['museums'] = [{'id': m.name, 'name': m.name, 'count': m.count} for m in museums]

        country_field = Artwork.country_fr if lang == 'fr' else Artwork.country_en
        countries = db.session.query(
            country_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(fav_ids), country_field.isnot(None), country_field != ''
        ).group_by(country_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['countries'] = [{'id': c.name, 'name': c.name, 'count': c.count} for c in countries]

        city_field = Artwork.city_fr if lang == 'fr' else Artwork.city_en
        cities = db.session.query(
            city_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(fav_ids), city_field.isnot(None), city_field != ''
        ).group_by(city_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['cities'] = [{'id': c.name, 'name': c.name, 'count': c.count} for c in cities]

        type_field = Artwork.instance_of_fr if lang == 'fr' else Artwork.instance_of_en
        types = db.session.query(
            type_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(fav_ids), type_field.isnot(None), type_field != ''
        ).group_by(type_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['types'] = [{'name': t.name, 'count': t.count} for t in types]

        movement_field = Artwork.movement_fr if lang == 'fr' else Artwork.movement_en
        movements = db.session.query(
            movement_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(fav_ids), movement_field.isnot(None), movement_field != ''
        ).group_by(movement_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['movements'] = [{'name': m.name, 'count': m.count} for m in movements]

        genre_field = Artwork.genre_fr if lang == 'fr' else Artwork.genre_en
        genres = db.session.query(
            genre_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(fav_ids), genre_field.isnot(None), genre_field != ''
        ).group_by(genre_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['genres'] = [{'name': g.name, 'count': g.count} for g in genres]

        material_field = Artwork.made_from_material_fr if lang == 'fr' else Artwork.made_from_material_en
        materials = db.session.query(
            material_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            Artwork.id.in_(fav_ids), material_field.isnot(None), material_field != ''
        ).group_by(material_field).order_by(func.count(Artwork.id).desc()).limit(30).all()
        result['materials'] = [{'name': m.name, 'count': m.count} for m in materials]

        return jsonify(result)

    except Exception as e:
        print(f"Erreur api_favorites_filter_options: {e}")
        return jsonify({'artists': [], 'museums': [], 'types': [], 'movements': [], 'genres': [], 'materials': [], 'countries': [], 'cities': []})


# ---- Autres endpoints de recherche ----
@app.route('/api/search-artists')
def api_search_artists():
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify([])

        lang = session.get('language', 'fr')
        normalized_query = normalize_string(query)
        pattern = f"%{query}%"
        artist_field = Artwork.creator_fr if lang == 'fr' else Artwork.creator_en

        artists = db.session.query(
            artist_field.label('nom'), func.count(Artwork.id).label('oeuvres_count')
        ).filter(
            db.or_(artist_field.ilike(pattern), func.unaccent(artist_field).ilike(f"%{normalized_query}%")),
            artist_field != '', artist_field.isnot(None),
            artist_field != 'Artiste inconnu', artist_field != 'Unknown artist'
        ).group_by(artist_field).order_by(
            case((artist_field.ilike(f"{query}%"), 0), else_=1),
            func.count(Artwork.id).desc()
        ).limit(20).all()

        return jsonify([{'nom': a.nom, 'oeuvres_count': a.oeuvres_count} for a in artists])

    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify([])


@app.route('/api/search-cities')
def api_search_cities():
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify([])

        lang = session.get('language', 'fr')
        normalized_query = normalize_string(query)
        pattern = f"%{query}%"
        city_field = Artwork.city_fr if lang == 'fr' else Artwork.city_en

        cities = db.session.query(
            city_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            db.or_(city_field.ilike(pattern), func.unaccent(city_field).ilike(f"%{normalized_query}%")),
            city_field != '', city_field.isnot(None)
        ).group_by(city_field).order_by(func.count(Artwork.id).desc()).limit(30).all()

        return jsonify([{'nom': c.name, 'oeuvres_count': c.count} for c in cities])

    except Exception as e:
        print(f"Erreur search-cities: {e}")
        return jsonify([])


@app.route('/api/search-countries')
def api_search_countries():
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify([])

        lang = session.get('language', 'fr')
        normalized_query = normalize_string(query)
        pattern = f"%{query}%"
        country_field = Artwork.country_fr if lang == 'fr' else Artwork.country_en

        countries = db.session.query(
            country_field.label('name'), func.count(Artwork.id).label('count')
        ).filter(
            db.or_(country_field.ilike(pattern), func.unaccent(country_field).ilike(f"%{normalized_query}%")),
            country_field != '', country_field.isnot(None)
        ).group_by(country_field).order_by(func.count(Artwork.id).desc()).limit(30).all()

        return jsonify([{'nom': c.name, 'oeuvres_count': c.count} for c in countries])

    except Exception as e:
        print(f"Erreur search-countries: {e}")
        return jsonify([])


@app.route('/api/search-museums')
def api_search_museums():
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify([])

        lang = session.get('language', 'fr')
        normalized_query = normalize_string(query)
        pattern = f"%{query}%"
        museum_field = Artwork.collection_fr if lang == 'fr' else Artwork.collection_en

        museums = db.session.query(
            museum_field.label('nom'), func.count(Artwork.id).label('count')
        ).filter(
            db.or_(museum_field.ilike(pattern), func.unaccent(museum_field).ilike(f"%{normalized_query}%")),
            museum_field != '', museum_field.isnot(None),
            Artwork.image_url.isnot(None), Artwork.image_url != ''
        ).group_by(museum_field).order_by(func.count(Artwork.id).desc()).limit(30).all()

        return jsonify([{'nom': m.nom, 'oeuvres_count': m.count} for m in museums])

    except Exception as e:
        print(f"Erreur search-museums: {e}")
        return jsonify([])


# ============================================================
# ROUTES - DIVERS
# ============================================================

@app.route('/api/srp-detail')
def api_srp_detail():
    try:
        lang = session.get('language', 'fr')
        city = request.args.get('city', '')
        country = request.args.get('country', '')
        museum_field = Artwork.collection_fr if lang == 'fr' else Artwork.collection_en
        city_field = Artwork.city_fr if lang == 'fr' else Artwork.city_en
        country_field = Artwork.country_fr if lang == 'fr' else Artwork.country_en

        if country and not city:
            total_oeuvres = db.session.query(func.count(Artwork.id)).filter(
                country_field.ilike(f"%{country}%"),
                Artwork.image_url.isnot(None), Artwork.image_url != ''
            ).scalar() or 0

            total_villes = db.session.query(func.count(func.distinct(city_field))).filter(
                country_field.ilike(f"%{country}%"),
                city_field.isnot(None), city_field != '',
                Artwork.image_url.isnot(None), Artwork.image_url != ''
            ).scalar() or 0

            cities = db.session.query(
                city_field.label('nom'),
                func.count(func.distinct(Artwork.collection_id)).label('musees_count'),
                func.count(Artwork.id).label('oeuvres_count')
            ).filter(
                country_field.ilike(f"%{country}%"),
                city_field.isnot(None), city_field != '',
                Artwork.image_url.isnot(None), Artwork.image_url != ''
            ).group_by(city_field).order_by(func.count(Artwork.id).desc()).limit(300).all()

            return jsonify({
                'type': 'cities', 'name': country,
                'total_oeuvres': total_oeuvres, 'total_villes': total_villes,
                'items': [{'nom': c.nom, 'musees_count': c.musees_count, 'oeuvres_count': c.oeuvres_count} for c in cities]
            })
        else:
            total_oeuvres = db.session.query(func.count(Artwork.id)).filter(
                city_field.ilike(f"%{city}%"),
                Artwork.image_url.isnot(None), Artwork.image_url != ''
            ).scalar() or 0

            total_musees = db.session.query(func.count(func.distinct(Artwork.collection_fr))).filter(
                city_field.ilike(f"%{city}%"),
                Artwork.image_url.isnot(None), Artwork.image_url != ''
            ).scalar() or 0

            museums = db.session.query(
                museum_field.label('nom'), func.count(Artwork.id).label('count')
            ).filter(
                Artwork.image_url.isnot(None), Artwork.image_url != ''
            )
            if city:
                museums = museums.filter(city_field.ilike(f"%{city}%"))

            museums = museums.group_by(museum_field).order_by(func.count(Artwork.id).desc()).limit(200).all()

            return jsonify({
                'type': 'museums', 'name': city,
                'total_oeuvres': total_oeuvres, 'total_musees': total_musees,
                'items': [{'id': m.nom or 'divers', 'nom': m.nom or 'Divers', 'count': m.count} for m in museums]
            })

    except Exception as e:
        return jsonify({'items': []}), 500


@app.route('/api/works')
def api_works():
    page = request.args.get('page', 1, type=int)
    limit = min(request.args.get('limit', 12, type=int), 40)
    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types = request.args.getlist('type')
    movements = request.args.getlist('movement')
    genres = request.args.getlist('genre')
    materials = request.args.getlist('material')
    sort = request.args.get('sort', 'relevance')
    q = request.args.get('q', '').strip()
    
    query = _build_artwork_query(artists, country, cities, museums, types, q=q,
                                  movements=movements, genres=genres, materials=materials)
    query = _apply_sort(query, sort)
    total = query.count()
    start = (page - 1) * limit
    has_more = (start + limit) < total

    works_page = query.offset(start).limit(limit).all()
    works = [{'id': w.id, 'titre': w.titre, 'createur': w.createur, 'image_url': w.image_url} for w in works_page]

    return jsonify({'works': works, 'page': page, 'has_more': has_more, 'total': total})


@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in ('fr', 'en'):
        session['language'] = lang
        resp = make_response(redirect(request.referrer or url_for('index')))
        resp.set_cookie('preferred_language', lang, max_age=30*24*3600)
        return resp
    return redirect(request.referrer or url_for('index'))


@app.route('/28012003')
def pour_kathy():
    return render_template('28012003.html')


@app.route('/easteregg')
def easter_egg():
    return render_template('easteregg.html')


@app.after_request
def add_cache_headers(response):
    if request.path.startswith('/static/'):
        response.cache_control.max_age = 86400
        response.cache_control.public = True
    else:
        response.cache_control.no_cache = True
        response.cache_control.no_store = True
        response.cache_control.must_revalidate = True
    return response


@app.before_request
def track_visit():
    if 'language' not in session:
        lang_from_cookie = request.cookies.get('preferred_language')
        if lang_from_cookie in ('fr', 'en'):
            session['language'] = lang_from_cookie
        else:
            session['language'] = 'fr'

    if request.endpoint and not request.endpoint.startswith('api'):
        if request.endpoint not in ['static', 'logout', 'login', 'register']:
            today = datetime.utcnow().date().isoformat()
            session_key = f'visited_{today}'
            
            if not session.get(session_key):
                try:
                    VisitCounter.increment()
                    session[session_key] = True
                except Exception as e:
                    print(f"Erreur compteur: {e}")
                    session[session_key] = True


# ============================================================
# TRADUCTIONS
# ============================================================

def load_translations():
    translations = {'fr': {}, 'en': {}}
    translations_dir = os.path.join(app.root_path, 'translations')
    for lang in ['fr', 'en']:
        file_path = os.path.join(translations_dir, f'{lang}.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                translations[lang] = json.load(f)
            logger.info(f"✅ Traductions {lang} chargées")
        except FileNotFoundError:
            logger.warning(f"⚠️ Fichier de traduction manquant: {file_path}")
        except Exception as e:
            logger.error(f"❌ Erreur chargement {lang}.json: {e}")
    return translations


TRANSLATIONS = load_translations()


# ============================================================
# DÉMARRAGE
# ============================================================

if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            logger.info("Tables PostgreSQL vérifiées/créées")
        except Exception as exc:
            logger.warning("Init DB : %s", exc)

    app.run(host='0.0.0.0', port=5000, debug=True)
