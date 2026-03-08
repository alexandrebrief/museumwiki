#!/usr/bin/env python3
"""
Bluegreencliff — Application Flask
PostgreSQL · Authentification · Favoris · Notations
"""

# ============================================================
# IMPORTS
# ============================================================

import json
import logging
import os
import re
import secrets
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
load_dotenv() 
from flask import (Flask, flash, jsonify, redirect, render_template,
                   render_template_string, request, session, url_for)
from flask import make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from sqlalchemy import func, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy.sql.expression import func
from sqlalchemy.dialects.postgresql import dialect as pg_dialect

# Enregistrer unaccent comme fonction SQL
unaccent = func.unaccent

# ============================================================
# APPLICATION & CONFIGURATION
# ============================================================

app = Flask(__name__)

# Secret key — obligatoire
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise ValueError("SECRET_KEY n'est pas définie")

# Base de données — obligatoire
_DB_USER     = os.environ.get('DB_USER')
_DB_PASSWORD = os.environ.get('DB_PASSWORD')
_DB_HOST     = os.environ.get('DB_HOST')
_DB_NAME     = os.environ.get('DB_NAME')

if not all([_DB_USER, _DB_PASSWORD, _DB_HOST, _DB_NAME]):
    raise ValueError("Variables d'environnement DB_* incomplètes")

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'postgresql://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}/{_DB_NAME}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ===== AJOUTE LE CACHE ICI =====
@app.after_request
def add_cache_headers(response):
    """Ajoute des en-têtes de cache pour les ressources statiques"""
    if request.path.startswith('/static/'):
        # Cache d'1 jour pour les fichiers statiques
        response.cache_control.max_age = 86400
        response.cache_control.public = True
    else:
        # Pas de cache pour les pages dynamiques
        response.cache_control.no_cache = True
        response.cache_control.no_store = True
        response.cache_control.must_revalidate = True
    return response
# ===== FIN DU CACHE =====

# SendGrid — optionnel
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')
FROM_EMAIL       = os.environ.get('FROM_EMAIL', 'alexandre.brief2.0@gmail.com')
BASE_URL         = os.environ.get('BASE_URL', 'http://localhost:5000')


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
    default_limits=["200 per day", "100 per hour"],
    storage_uri="memory://",
)

csrf = CSRFProtect(app)


# ============================================================
# MODÈLES
# ============================================================

class Artwork(db.Model):
    __tablename__ = 'artworks'

    id                   = db.Column(db.String(50), primary_key=True)
    label_fr             = db.Column(db.Text)
    label_en             = db.Column(db.Text)
    label_fallback_fr    = db.Column(db.Text)
    label_fallback_en    = db.Column(db.Text)
    creator_fr           = db.Column(db.Text)
    creator_en           = db.Column(db.Text)
    creator_fallback_fr  = db.Column(db.Text)
    creator_fallback_en  = db.Column(db.Text)
    inception            = db.Column(db.Text)
    image_url            = db.Column(db.Text)
    collection_fr        = db.Column(db.Text)
    collection_en        = db.Column(db.Text)
    location_fr          = db.Column(db.Text)
    location_en          = db.Column(db.Text)
    instance_of_fr       = db.Column(db.Text)
    instance_of_en       = db.Column(db.Text)
    made_from_material_fr = db.Column(db.Text)
    made_from_material_en = db.Column(db.Text)
    genre_fr             = db.Column(db.Text)
    genre_en             = db.Column(db.Text)
    movement_fr          = db.Column(db.Text)
    movement_en          = db.Column(db.Text)
    width                = db.Column(db.Float)
    height               = db.Column(db.Float)
    copyright_status_fr  = db.Column(db.Text)
    copyright_status_en  = db.Column(db.Text)
    url_wikidata         = db.Column(db.Text)

    # ----------------------------------------------------------
    # Propriétés multilingues
    # ----------------------------------------------------------

    @property
    def _lang(self):
        return session.get('language', 'fr')

    @property
    def titre(self):
        if self._lang == 'fr':
            return self.label_fallback_fr or self.label_fr or 'Titre inconnu'
        return self.label_fallback_en or self.label_en or 'Unknown title'

    @property
    def titre_fr(self):
        return self.label_fallback_fr or self.label_fr or 'Titre inconnu'

    @property
    def titre_en(self):
        return self.label_fallback_en or self.label_en or 'Unknown title'

    @property
    def createur(self):
        if self._lang == 'fr':
            return self.creator_fallback_fr or self.creator_fr or 'Artiste inconnu'
        return self.creator_fallback_en or self.creator_en or 'Unknown artist'

    @property
    def lieu(self):
        if self._lang == 'fr':
            return self.collection_fr or self.location_fr or 'Lieu inconnu'
        return self.collection_en or self.location_en or 'Unknown location'

    @property
    def mouvement(self):
        if self._lang == 'fr':
            return self.movement_fr or 'Mouvement inconnu'
        return self.movement_en or 'Unknown movement'

    @property
    def genre_display(self):
        if self._lang == 'fr':
            return self.genre_fr or 'Genre inconnu'
        return self.genre_en or 'Unknown genre'

    @property
    def date(self):
        return self.inception

    @property
    def wikidata_url(self):
        return self.url_wikidata

    @property
    def instance_of(self):
        return self.instance_of_fr or 'Type inconnu'

    @property
    def copyright(self):
        return self.copyright_status_fr or self.copyright_status_en or 'Inconnu'

    def to_dict(self):
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
            'height': self.height,
        }


class Collection(db.Model):
    __tablename__ = 'collections'

    id             = db.Column(db.String(50), primary_key=True)
    collection_fr  = db.Column(db.Text)
    collection_en  = db.Column(db.Text)
    country_fr     = db.Column(db.Text)
    country_en     = db.Column(db.Text)
    city_fr        = db.Column(db.Text)
    city_en        = db.Column(db.Text)

    @property
    def _lang(self):
        return session.get('language', 'fr')

    @property
    def nom(self):
        if self._lang == 'fr':
            return self.collection_fr or self.collection_en or 'Musée inconnu'
        return self.collection_en or self.collection_fr or 'Unknown museum'

    @property
    def pays(self):
        if self._lang == 'fr':
            return self.country_fr or self.country_en or 'Pays inconnu'
        return self.country_en or self.country_fr or 'Unknown country'

    @property
    def ville(self):
        if self._lang == 'fr':
            return self.city_fr or self.city_en or 'Ville inconnue'
        return self.city_en or self.city_fr or 'Unknown city'


class ArtworkCollection(db.Model):
    __tablename__ = 'artwork_collections'

    artwork_id    = db.Column(db.String(50), db.ForeignKey('artworks.id'), primary_key=True)
    collection_id = db.Column(db.String(50), db.ForeignKey('collections.id'), primary_key=True)

    artwork    = db.relationship('Artwork', backref='collection_links')
    collection = db.relationship('Collection', backref='artwork_links')


class User(db.Model):
    __tablename__ = 'users'

    id                        = db.Column(db.Integer, primary_key=True)
    username                  = db.Column(db.String(80), unique=True, nullable=False)
    email                     = db.Column(db.String(120), unique=True, nullable=False)
    password_hash             = db.Column(db.String(200), nullable=False)
    email_verified            = db.Column(db.Boolean, default=False)
    email_verification_token  = db.Column(db.String(100), unique=True)
    verification_token        = db.Column(db.String(100), unique=True)
    last_login                = db.Column(db.DateTime)
    created_at                = db.Column(db.DateTime, default=datetime.utcnow)

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
            'created_at': self.created_at.strftime('%d/%m/%Y'),
        }


class EmailVerification(db.Model):
    __tablename__ = 'email_verifications'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token      = db.Column(db.String(100), unique=True, nullable=False)
    code       = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)

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
    __tablename__ = 'favorites'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    artwork_id = db.Column(db.String, db.ForeignKey('artworks.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user    = db.relationship('User', backref='favorites')
    artwork = db.relationship('Artwork', backref='favorited_by')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'artwork_id', name='unique_user_artwork_favorite'),
    )


class Rating(db.Model):
    __tablename__ = 'ratings'

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    artwork_id       = db.Column(db.String, db.ForeignKey('artworks.id'), nullable=False)
    note_globale     = db.Column(db.Float, nullable=False)
    note_technique   = db.Column(db.Float, nullable=False)
    note_originalite = db.Column(db.Float, nullable=False)
    note_emotion     = db.Column(db.Float, nullable=False)
    commentaire      = db.Column(db.Text, nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow)

    user    = db.relationship('User', backref='ratings')
    artwork = db.relationship('Artwork', backref='ratings')

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
            'created_at': self.created_at.strftime('%d/%m/%Y'),
            'updated_at': self.updated_at.strftime('%d/%m/%Y') if self.updated_at else None,
        }


class PasswordReset(db.Model):
    __tablename__ = 'password_resets'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token      = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref='password_resets')

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(32)

    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at


# ============================================================
# UTILITAIRES
# ============================================================

def validate_password_strength(password):
    """Retourne une liste d'erreurs de validation du mot de passe."""
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

    common = {
        'password', '123456', 'qwerty', 'admin', 'password123',
        'azerty', 'motdepasse', '12345678', '111111', '123456789',
        '000000', 'abc123', 'password1', '12345', 'letmein',
        'monkey', 'football', 'iloveyou', '123123', '654321',
    }
    if password.lower() in common:
        errors.append("mot de passe trop commun")
    return errors


def get_filtered_query(query, artists, museums, movements,
                       types=None, genres=None, copyrights=None):
    """Construit une requête SQLAlchemy filtrée pour les œuvres."""
    q = Artwork.query

    if query:
        s = f"%{query}%"
        q = q.filter(
            db.or_(
                Artwork.label_fr.ilike(s),
                Artwork.label_en.ilike(s),
                Artwork.label_fallback_fr.ilike(s),
                Artwork.label_fallback_en.ilike(s),
                Artwork.creator_fr.ilike(s),
                Artwork.creator_en.ilike(s),
                Artwork.creator_fallback_fr.ilike(s),
                Artwork.creator_fallback_en.ilike(s),
                Artwork.location_fr.ilike(s),
                Artwork.location_en.ilike(s),
                Artwork.collection_fr.ilike(s),
                Artwork.collection_en.ilike(s),
                Artwork.genre_fr.ilike(s),
                Artwork.genre_en.ilike(s),
            )
        )

    if artists:
        q = q.filter(db.or_(*(
            f for a in artists for f in [
                Artwork.creator_fr.ilike(f"%{a}%"),
                Artwork.creator_en.ilike(f"%{a}%"),
                Artwork.creator_fallback_fr.ilike(f"%{a}%"),
                Artwork.creator_fallback_en.ilike(f"%{a}%"),
            ]
        )))

    if museums:
        # 🔥 NOUVEAU : Utiliser la table de liaison pour les musées
        q = q.join(ArtworkCollection).join(Collection).filter(
            db.or_(*(
                Collection.collection_fr.ilike(f"%{m}%") |
                Collection.collection_en.ilike(f"%{m}%")
                for m in museums
            ))
        ).group_by(Artwork.id)  # Pour éviter les doublons

    if movements:
        q = q.filter(db.or_(*(
            f for mv in movements for f in [
                Artwork.movement_fr.ilike(f"%{mv}%"),
                Artwork.movement_en.ilike(f"%{mv}%"),
            ]
        )))

    if types:
        q = q.filter(db.or_(*(
            f for t in types for f in [
                Artwork.instance_of_fr.ilike(f"%{t}%"),
                Artwork.instance_of_en.ilike(f"%{t}%"),
            ]
        )))

    if genres:
        q = q.filter(db.or_(*(
            f for g in genres for f in [
                Artwork.genre_fr.ilike(f"%{g}%"),
                Artwork.genre_en.ilike(f"%{g}%"),
            ]
        )))

    if copyrights:
        q = q.filter(db.or_(*(
            f for c in copyrights for f in [
                Artwork.copyright_status_fr.ilike(f"%{c}%"),
                Artwork.copyright_status_en.ilike(f"%{c}%"),
            ]
        )))

    return q


def handle_unverified_user(user, email):
    """Renvoie un email de vérification pour un compte non confirmé."""
    EmailVerification.query.filter_by(user_id=user.id, used=False).update({'used': True})

    code  = EmailVerification.generate_code()
    token = EmailVerification.generate_token()
    verification = EmailVerification(
        user_id=user.id,
        token=token,
        code=code,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.session.add(verification)
    db.session.commit()

    if send_verification_email(email, user.username, code, token):
        flash('Un email de vérification a été renvoyé. Vérifiez votre boîte de réception.', 'info')
    else:
        flash("Erreur lors de l'envoi de l'email. Veuillez réessayer.", 'danger')

    return redirect(url_for('verify_email_pending', email=email))


# ============================================================
# EMAILS (SendGrid)
# ============================================================

_EMAIL_BASE_STYLE = """
<style>
  body { font-family: 'Inter', sans-serif; background: #f5f0e8; margin: 0; padding: 20px; line-height: 1.6; }
  .container { max-width: 500px; margin: 0 auto; background: #fff; border-radius: 16px;
               padding: 35px 30px; box-shadow: 0 4px 12px rgba(44,62,80,0.05); }
  h1 { font-family: 'Playfair Display', serif; font-weight: 700; color: #1e2b3a;
       font-size: 1.8rem; margin: 0 0 10px 0; text-align: center; }
  .sub  { color: #5d6d7e; font-size: .95rem; text-align: center; margin-bottom: 25px; }
  .btn-wrap { text-align: center; margin: 30px 0; }
  .btn  { display: inline-block; background: #2c3e50; color: #e6d8c3 !important;
          font-weight: 500; font-size: 1rem; padding: 14px 32px; text-decoration: none;
          border-radius: 30px; box-shadow: 0 2px 8px rgba(44,62,80,.1); }
  .btn:hover { background: #1e2b3a; }
  .footer { color: #8e9aab; font-size: .8rem; text-align: center;
            margin-top: 25px; padding-top: 15px; border-top: 1px solid #e6d8c3; }
</style>
"""

_EMAIL_FONTS = (
    '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:'
    'wght@400;700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">'
)


def send_verification_email(user_email, username, code, token):
    """Envoie l'email de vérification de compte."""
    link = f"{BASE_URL}/verify-email?token={token}"
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{_EMAIL_FONTS}
{_EMAIL_BASE_STYLE}</head><body><div class="container">
  <h1>Bienvenue {username} sur Bluegreencliff !</h1>
  <p class="sub">Voici votre code de vérification.</p>
  <div style="background:#f5f0e8;border-radius:12px;padding:25px;text-align:center;
              border:1px solid #e0d6c8;margin:20px 0;">
    <div style="color:#5d6d7e;font-size:.8rem;text-transform:uppercase;
                letter-spacing:1px;margin-bottom:10px;">Code de vérification</div>
    <div style="font-size:2.5rem;font-weight:600;color:#2c3e50;letter-spacing:8px;">{code}</div>
  </div>
  <div class="btn-wrap"><a href="{link}" class="btn">Lien de vérification</a></div>
  <div class="footer">Code et lien valables 24 heures.</div>
</div></body></html>"""
    return _send_email(user_email, 'Bluegreencliff - Vérification de votre email', html)


def send_reset_email(user_email, username, reset_link):
    """Envoie l'email de réinitialisation de mot de passe."""
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{_EMAIL_FONTS}
{_EMAIL_BASE_STYLE}</head><body><div class="container">
  <h1>Réinitialisation de votre mot de passe</h1>
  <p class="sub">Bonjour {username},</p>
  <p class="sub">Cliquez sur le bouton ci-dessous pour créer un nouveau mot de passe.</p>
  <div class="btn-wrap"><a href="{reset_link}" class="btn">Réinitialiser mon mot de passe</a></div>
  <div class="footer">Ce lien expirera dans 24 heures.</div>
</div></body></html>"""
    return _send_email(user_email,
                       'Bluegreencliff - Réinitialisation de votre mot de passe', html)


def _send_email(to_email, subject, html_content):
    """Envoi générique via SendGrid. Retourne True si succès."""
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(Mail(
            from_email=FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html_content,
        ))
        logger.info("Email envoyé à %s — statut %s", to_email, response.status_code)
        return True
    except Exception as exc:
        logger.error("Erreur envoi email vers %s : %s", to_email, exc)
        return False


# ============================================================
# FILTRES DE TEMPLATE
# ============================================================

@app.template_filter('stars')
def stars_filter(value):
    if not value:
        return ''
    full  = int(value)
    half  = 1 if value - full >= 0.5 else 0
    empty = 5 - full - half
    return '★' * full + ('½' if half else '') + '☆' * empty




# ============================================================
# ROUTES — GÉNÉRALES
# ============================================================

@app.route('/')
def index():
    query      = request.args.get('q', '')
    page       = request.args.get('page', 1, type=int)
    per_page   = 20
    artists    = request.args.getlist('artist')
    museums    = request.args.getlist('museum')
    movements  = request.args.getlist('movement')
    types      = request.args.getlist('type')
    genres     = request.args.getlist('genre')
    copyrights = request.args.getlist('copyright')
    sort       = request.args.get('sort', 'relevance')
    is_ajax    = request.args.get('ajax', '0') == '1'

    # Construction de la requête de base
    if query or artists or museums or movements or types or genres or copyrights:
        base_q = get_filtered_query(query, artists, museums, movements,
                                    types, genres, copyrights)

        _sort_map = {
            'date_asc':    lambda q: q.order_by(Artwork.inception),
            'date_desc':   lambda q: q.order_by(Artwork.inception.desc()),
            'title_asc':   lambda q: q.order_by(
                Artwork.label_fallback_fr if session.get('language') == 'fr'
                else Artwork.label_fallback_en),
            'title_desc':  lambda q: q.order_by(
                Artwork.label_fallback_fr.desc() if session.get('language') == 'fr'
                else Artwork.label_fallback_en.desc()),
            'artist_asc':  lambda q: q.order_by(
                Artwork.creator_fallback_fr if session.get('language') == 'fr'
                else Artwork.creator_fallback_en),
            'artist_desc': lambda q: q.order_by(
                Artwork.creator_fallback_fr.desc() if session.get('language') == 'fr'
                else Artwork.creator_fallback_en.desc()),
        }
        if sort in _sort_map:
            base_q = _sort_map[sort](base_q)

        pagination   = base_q.paginate(page=page, per_page=per_page, error_out=False)
        results_page = pagination.items

    else:
        total = Artwork.query.count()
        if total:
            if page == 1:
                results_page = Artwork.query.order_by(func.random()).limit(per_page).all()
                pagination   = type('P', (), {'items': results_page, 'total': per_page, 'pages': 1})()
            else:
                offset       = (page - 1) * per_page
                results_page = Artwork.query.order_by(func.random()).offset(offset).limit(per_page).all()
                pagination   = type('P', (), {
                    'items': results_page, 'total': total,
                    'pages': (total + per_page - 1) // per_page,
                })()
        else:
            results_page = []
            pagination   = type('P', (), {'items': [], 'total': 0, 'pages': 1})()

    # ===== OPTIMISATION : UNE SEULE REQUÊTE POUR LES FAVORIS =====
    favorite_counts = {}
    if results_page and session.get('user_id'):
        artwork_ids = [a.id for a in results_page]
        fav_results = db.session.query(
            Favorite.artwork_id, 
            func.count(Favorite.id).label('count')
        ).filter(
            Favorite.artwork_id.in_(artwork_ids)
        ).group_by(Favorite.artwork_id).all()
        
        favorite_counts = {id: count for id, count in fav_results}
    # ===== FIN OPTIMISATION =====

    results_dicts = [a.to_dict() for a in results_page]

    if is_ajax:
        _card_tpl = '''
        {% for artwork in results %}
        <a href="/oeuvre/{{ artwork.id }}" class="work-card"
           style="text-decoration:none;color:inherit;display:block;position:relative;
                  background:white;border-radius:8px;overflow:hidden;
                  box-shadow:0 2px 6px rgba(44,62,80,.05);border:1px solid #e0d6c8;">
          <div class="favorite-icon" data-artwork-id="{{ artwork.id }}"
               onclick="event.preventDefault();event.stopPropagation();toggleFavorite('{{ artwork.id }}',this)">
            <i class="far fa-heart" id="favorite-icon-{{ artwork.id }}"></i>
          </div>
          {% if artwork.image_url and artwork.image_url != '' %}
<img src="https://images.weserv.nl/?url={{ artwork.image_url|urlencode }}&w=300&h=300&fit=cover&a=attention&output=webp&q=70&we&maxage=7d" 
     alt="{{ artwork.titre if artwork.titre else 'Sans titre' }}" 
     loading="lazy"
     onerror="this.onerror=null; this.src='{{ artwork.image_url }}';">
          {% else %}
          <div class="work-image-placeholder"
               style="width:100%;aspect-ratio:1/1;background:linear-gradient(145deg,#e6d8c3,#d4c9b9);
                      display:flex;align-items:center;justify-content:center;color:#5d6d7e;font-size:2rem;">
            <i class="fas fa-image"></i>
          </div>
          {% endif %}
          <div style="padding:.4rem;">
            <div class="artwork-title" title="{{ artwork.titre }}">{{ artwork.titre or 'Sans titre' }}</div>
            <div class="artwork-artist" title="{{ artwork.createur }}">{{ artwork.createur }}</div>
          </div>
        </a>
        {% endfor %}
        '''
        return render_template_string(_card_tpl, results=results_dicts, favorite_counts=favorite_counts)

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
    artwork = (
        Artwork.query.filter_by(id=oeuvre_id).first()
        or Artwork.query.filter_by(id_q=oeuvre_id).first()
        or Artwork.query.filter(Artwork.id_q.like(f'%{oeuvre_id}%')).first()
    )
    if artwork:
        return render_template('detail.html', oeuvre=artwork.to_dict())
    return "Œuvre non trouvée", 404


@app.route('/28012003')
def kathy_page():
    return render_template('28012003.html')


@app.route('/easteregg')
def easteregg():
    return render_template('easteregg.html')


@app.route('/about')
def about():
    try:
        db.session.execute(text('SELECT 1'))

        total_oeuvres  = Artwork.query.count()
        total_artistes = (
            db.session.query(Artwork.creator_fallback_fr)
            .filter(Artwork.creator_fallback_fr.notin_(['Artiste inconnu', '']),
                    Artwork.creator_fallback_fr.isnot(None))
            .distinct().count()
        )
        total_musees = (
            db.session.query(Artwork.location_fr)
            .filter(Artwork.location_fr.notin_(['Lieu inconnu', '']),
                    Artwork.location_fr.isnot(None))
            .distinct().count()
        )
        total_users = User.query.count()

        if total_oeuvres == 0:
            total_oeuvres  = db.session.execute(text('SELECT COUNT(*) FROM artworks')).scalar() or 0
            total_artistes = db.session.execute(
                text("SELECT COUNT(DISTINCT creator_fallback_fr) FROM artworks "
                     "WHERE creator_fallback_fr NOT IN ('Artiste inconnu','')")).scalar() or 0
            total_musees   = db.session.execute(
                text("SELECT COUNT(DISTINCT location_fr) FROM artworks "
                     "WHERE location_fr NOT IN ('Lieu inconnu','')")).scalar() or 0

    except Exception as exc:
        logger.error("Erreur route /about : %s", exc)
        total_oeuvres, total_artistes, total_musees, total_users = 560, 350, 45, 5

    return render_template('about.html',
                           total_oeuvres=total_oeuvres,
                           total_artistes=total_artistes,
                           total_musees=total_musees,
                           total_users=total_users,
                           last_update=datetime.now().strftime('%d/%m/%Y à %H:%M'))


# ============================================================
# ROUTES — AUTHENTIFICATION
# ============================================================

@limiter.limit("3 per minute")
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method != 'POST':
        return render_template('register.html')

    username = request.form.get('username', '').strip()
    email    = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    errors = []
    if not username or not email or not password:
        errors.append("Tous les champs sont obligatoires")
    errors.extend(validate_password_strength(password))
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        errors.append("Format d'email invalide")

    if errors:
        security_logger.warning("Inscription échouée — IP:%s email:%s erreurs:%s",
                                request.remote_addr, email, errors)
        return render_template('register.html', errors=errors,
                               username=username, email=email)

    try:
        existing_username = User.query.filter_by(username=username).first()
        existing_email    = User.query.filter_by(email=email).first()
    except Exception as exc:
        logger.error("Erreur BDD /register : %s", exc)
        flash('Erreur de base de données.', 'danger')
        return render_template('register.html', username=username, email=email)

    if existing_username:
        errors.append("Ce nom d'utilisateur est déjà pris")
    if existing_email:
        if existing_email.email_verified:
            errors.append("Cet email est déjà utilisé")
        else:
            return handle_unverified_user(existing_email, email)
    if errors:
        return render_template('register.html', errors=errors,
                               username=username, email=email)

    try:
        user = User(username=username, email=email, email_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        code  = EmailVerification.generate_code()
        token = EmailVerification.generate_token()
        db.session.add(EmailVerification(
            user_id=user.id, token=token, code=code,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        ))
        db.session.commit()

        if send_verification_email(email, username, code, token):
            flash("Inscription réussie ! Un email de vérification vous a été envoyé.", 'success')
        else:
            flash("Compte créé mais erreur d'envoi d'email. Contactez le support.", 'warning')
        return redirect(url_for('verify_email_pending', email=email))

    except Exception as exc:
        db.session.rollback()
        logger.error("Erreur inscription : %s", exc)
        flash('Une erreur est survenue. Veuillez réessayer.', 'danger')
        return render_template('register.html', username=username, email=email)


@limiter.limit("5 per minute")
@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next', '')

    if request.method != 'POST':
        return render_template('login.html', next=next_url)

    next_url = request.form.get('next', next_url)
    email    = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    user = User.query.filter_by(email=email).first()

    if user and user.check_password(password):
        if not user.email_verified:
            security_logger.warning("Connexion refusée (non vérifié) — IP:%s email:%s",
                                    request.remote_addr, email)
            flash('Veuillez vérifier votre email avant de vous connecter.', 'warning')
            return redirect(url_for('verify_email_pending', email=user.email))

        session['user_id']  = user.id
        session['username'] = user.username
        user.last_login     = datetime.utcnow()
        db.session.commit()

        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect(url_for('index'))

    flash('Email ou mot de passe incorrect', 'danger')
    return render_template('login.html', next=next_url)


@app.route('/logout')
def logout():
    next_url = request.args.get('next', '')
    session.clear()
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('index'))


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Utilisateur non trouvé', 'danger')
        return redirect(url_for('login'))
    return render_template('profile.html', user=user.to_dict())


@limiter.limit("10 per hour")
@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        flash('Veuillez vous connecter', 'warning')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    if request.method != 'POST':
        return render_template('change_password.html')

    current  = request.form.get('current_password', '')
    new_pwd  = request.form.get('new_password', '')
    confirm  = request.form.get('confirm_password', '')
    errors   = []

    if not user.check_password(current):
        errors.append("Mot de passe actuel incorrect")
        security_logger.warning("Changement mdp échoué — IP:%s user:%s",
                                request.remote_addr, session.get('username'))
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


@app.route('/delete-account', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        flash('Veuillez vous connecter', 'warning')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user.check_password(request.form.get('password', '')):
        flash('Mot de passe incorrect', 'danger')
        return redirect(url_for('profile'))

    try:
        EmailVerification.query.filter_by(user_id=user.id).delete()
        Favorite.query.filter_by(user_id=user.id).delete()
        Rating.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        session.clear()
        return redirect(url_for('index'))
    except Exception as exc:
        db.session.rollback()
        logger.error("Erreur suppression compte : %s", exc)
        flash('Erreur lors de la suppression', 'danger')
        return redirect(url_for('profile'))


# ============================================================
# ROUTES — VÉRIFICATION EMAIL
# ============================================================

@app.route('/verify-email-pending')
def verify_email_pending():
    return render_template('verify_email_pending.html',
                           email=request.args.get('email', ''))


@app.route('/verify-email')
def verify_email():
    token        = request.args.get('token', '')
    verification = EmailVerification.query.filter_by(token=token, used=False).first()

    if not verification or not verification.is_valid():
        flash('Lien de vérification invalide ou expiré.', 'danger')
        return redirect(url_for('login'))

    user               = verification.user
    user.email_verified = True
    verification.used  = True
    session['user_id']  = user.id
    session['username'] = user.username
    user.last_login     = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/verify-code', methods=['POST'])
def verify_code():
    code  = request.form.get('code', '').strip()
    email = request.form.get('email', '')
    user  = User.query.filter_by(email=email).first()

    if not user:
        flash('Utilisateur non trouvé.', 'danger')
        return redirect(url_for('login'))

    verification = EmailVerification.query.filter_by(user_id=user.id, used=False).first()
    if not verification or verification.code != code or not verification.is_valid():
        flash('Code invalide ou expiré.', 'danger')
        return redirect(url_for('verify_email_pending', email=email))

    user.email_verified = True
    verification.used   = True
    session['user_id']  = user.id
    session['username'] = user.username
    user.last_login     = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/resend-verification', methods=['POST'])
def resend_verification():
    email = request.form.get('email', '')
    user  = User.query.filter_by(email=email).first()

    if not user:
        flash('Utilisateur non trouvé.', 'danger')
        return redirect(url_for('register'))
    if user.email_verified:
        flash('Cet email est déjà vérifié.', 'info')
        return redirect(url_for('login'))

    EmailVerification.query.filter_by(user_id=user.id, used=False).update({'used': True})

    code  = EmailVerification.generate_code()
    token = EmailVerification.generate_token()
    db.session.add(EmailVerification(
        user_id=user.id, token=token, code=code,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    ))
    db.session.commit()

    if send_verification_email(email, user.username, code, token):
        flash('Nouvel email de vérification envoyé !', 'success')
    else:
        flash('Erreur lors de l\'envoi. Veuillez réessayer.', 'danger')
    return redirect(url_for('verify_email_pending', email=email))


# ============================================================
# ROUTES — MOT DE PASSE OUBLIÉ
# ============================================================

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data  = request.get_json() or {}
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

    reset_link = f"{BASE_URL}/reset-password?token={token}"
    if send_reset_email(email, user.username, reset_link):
        return jsonify({'message': 'Un email de réinitialisation a été envoyé'}), 200
    return jsonify({'error': "Erreur lors de l'envoi de l'email"}), 500


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token', '')

    if request.method == 'POST':
        token    = request.form.get('token', '')
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')
        reset    = PasswordReset.query.filter_by(token=token, used=False).first()

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
# ROUTES — API FAVORIS & NOTES
# ============================================================

@app.route('/api/favorite/toggle', methods=['POST'])
def toggle_favorite():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    artwork_id = (request.get_json() or {}).get('artwork_id')
    if not artwork_id:
        return jsonify({'error': 'ID œuvre manquant'}), 400

    fav = Favorite.query.filter_by(user_id=session['user_id'],
                                   artwork_id=artwork_id).first()
    if fav:
        db.session.delete(fav)
        db.session.commit()
        return jsonify({'favorite': False, 'message': 'Retiré des favoris'})

    db.session.add(Favorite(user_id=session['user_id'], artwork_id=artwork_id))
    db.session.commit()
    return jsonify({'favorite': True, 'message': 'Ajouté aux favoris'})


@app.route('/api/favorite/check/<artwork_id>')
def check_favorite(artwork_id):
    if 'user_id' not in session:
        return jsonify({'favorite': False})
    fav = Favorite.query.filter_by(user_id=session['user_id'],
                                   artwork_id=artwork_id).first()
    return jsonify({'favorite': fav is not None})


@app.route('/api/favorites/list')
def list_favorites():
    if 'user_id' not in session:
        return jsonify([])
    favs = Favorite.query.filter_by(user_id=session['user_id']).all()
    return jsonify([f.artwork_id for f in favs])


@app.route('/favoris')
def favorites_page():
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour voir vos favoris', 'warning')
        return redirect(url_for('login'))
    favs     = Favorite.query.filter_by(user_id=session['user_id']).all()
    artworks = [f.artwork.to_dict() for f in favs if f.artwork]
    return render_template('favorites.html', artworks=artworks)


@app.route('/api/rating/save', methods=['POST'])
def save_rating():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    data       = request.get_json() or {}
    artwork_id = data.get('artwork_id')

    def valid_note(n):
        try:
            v = float(n)
            return 0 <= v <= 5 and (v * 2).is_integer()
        except (TypeError, ValueError):
            return False

    if not all(valid_note(data.get(k, 0))
               for k in ('note_globale', 'note_technique',
                         'note_originalite', 'note_emotion')):
        return jsonify({'error': 'Notes invalides'}), 400

    rating = Rating.query.filter_by(user_id=session['user_id'],
                                    artwork_id=artwork_id).first()
    is_new = rating is None
    if is_new:
        rating = Rating(user_id=session['user_id'], artwork_id=artwork_id)

    rating.note_globale     = float(data.get('note_globale', 0))
    rating.note_technique   = float(data.get('note_technique', 0))
    rating.note_originalite = float(data.get('note_originalite', 0))
    rating.note_emotion     = float(data.get('note_emotion', 0))
    rating.commentaire      = data.get('commentaire', '')

    if is_new:
        db.session.add(rating)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Note enregistrée' if is_new else 'Note mise à jour',
        'rating': rating.to_dict(),
    })


@app.route('/api/rating/delete', methods=['POST'])
def delete_rating():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    artwork_id = (request.get_json() or {}).get('artwork_id')
    rating     = Rating.query.filter_by(user_id=session['user_id'],
                                        artwork_id=artwork_id).first()
    if not rating:
        return jsonify({'error': 'Commentaire non trouvé'}), 404

    db.session.delete(rating)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Commentaire supprimé'})


@app.route('/api/rating/get/<artwork_id>')
def get_rating(artwork_id):
    if 'user_id' not in session:
        return jsonify({'has_rating': False})
    rating = Rating.query.filter_by(user_id=session['user_id'],
                                    artwork_id=artwork_id).first()
    if rating:
        return jsonify({'has_rating': True, 'rating': rating.to_dict()})
    return jsonify({'has_rating': False})


@app.route('/api/comments/<artwork_id>')
def get_comments(artwork_id):
    ratings = (
        Rating.query
        .filter_by(artwork_id=artwork_id)
        .filter(Rating.commentaire.isnot(None), Rating.commentaire != '')
        .order_by(Rating.created_at.desc())
        .all()
    )
    comments = []
    for r in ratings:
        u = User.query.get(r.user_id)
        comments.append({
            'username': u.username if u else 'Anonyme',
            'commentaire': r.commentaire,
            'note_globale': r.note_globale,
            'created_at': r.created_at.strftime('%d/%m/%Y'),
            'notes': {
                'technique': r.note_technique,
                'originalite': r.note_originalite,
                'emotion': r.note_emotion,
            },
        })
    return jsonify(comments)


@app.route('/api/artwork/stats/<artwork_id>')
def artwork_stats(artwork_id):
    if not Artwork.query.get(artwork_id):
        return jsonify({'error': 'Œuvre non trouvée'}), 404
    ratings = Rating.query.filter_by(artwork_id=artwork_id).all()
    if ratings:
        n = len(ratings)
        stats = {
            'total_notes':        n,
            'moyenne_globale':    round(sum(r.note_globale     for r in ratings) / n, 1),
            'moyenne_technique':  round(sum(r.note_technique   for r in ratings) / n, 1),
            'moyenne_originalite':round(sum(r.note_originalite for r in ratings) / n, 1),
            'moyenne_emotion':    round(sum(r.note_emotion     for r in ratings) / n, 1),
        }
    else:
        stats = {k: 0 for k in ('total_notes', 'moyenne_globale',
                                 'moyenne_technique', 'moyenne_originalite',
                                 'moyenne_emotion')}
    return jsonify(stats)


@app.route('/api/rated-works')
def get_rated_works():
    if 'user_id' not in session:
        return jsonify({'works': [], 'hasMore': False})

    page   = int(request.args.get('page', 1))
    limit  = int(request.args.get('limit', 32))
    offset = (page - 1) * limit

    ratings  = (Rating.query.filter_by(user_id=session['user_id'])
                .order_by(Rating.created_at.desc())
                .offset(offset).limit(limit + 1).all())
    has_more = len(ratings) > limit
    ratings  = ratings[:limit]

    works = []
    for r in ratings:
        artwork = Artwork.query.get(r.artwork_id)
        if artwork:
            d = artwork.to_dict()
            d['rating']      = r.to_dict()
            d['is_favorite'] = Favorite.query.filter_by(
                user_id=session['user_id'], artwork_id=artwork.id).first() is not None
            works.append(d)

    return jsonify({'works': works, 'hasMore': has_more,
                    'page': page, 'total': len(works)})


@app.route('/mes-oeuvres')
def my_rated_works():
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour voir vos œuvres notées', 'warning')
        return redirect(url_for('login'))

    ratings = Rating.query.filter_by(user_id=session['user_id']).all()
    works   = []
    for r in ratings:
        artwork = Artwork.query.get(r.artwork_id)
        if artwork:
            d = artwork.to_dict()
            d['rating']      = r.to_dict()
            d['is_favorite'] = Favorite.query.filter_by(
                user_id=session['user_id'], artwork_id=artwork.id).first() is not None
            works.append(d)
    return render_template('my_works.html', works=works)


# ============================================================
# ROUTES — API FILTRES & SUGGESTIONS
# ============================================================

def _bilingual_filter_counts(field_fr, field_en, filtered_ids,
                              exclude_fr=None, limit=30):
    """Retourne [{name, count}] selon la langue de session."""
    q = (
        db.session.query(field_fr.label('nfr'), field_en.label('nen'),
                         func.count(Artwork.id).label('cnt'))
        .filter(Artwork.id.in_(filtered_ids),
                field_fr.isnot(None), field_fr != '')
    )
    if exclude_fr:
        q = q.filter(field_fr != exclude_fr)
    rows = q.group_by(field_fr, field_en).order_by(func.count(Artwork.id).desc()).limit(limit).all()

    lang = session.get('language', 'fr')
    return [
        {'name': (r.nfr or r.nen) if lang == 'fr' else (r.nen or r.nfr), 'count': r.cnt}
        for r in rows
    ]


@app.route('/api/filters/update')
def api_filters_update():
    q          = get_filtered_query(
        request.args.get('q', ''),
        request.args.getlist('artist'),
        request.args.getlist('museum'),
        request.args.getlist('movement'),
        request.args.getlist('type'),
        request.args.getlist('genre'),
        request.args.getlist('copyright'),
    )
    ids = q.with_entities(Artwork.id).subquery()
    return jsonify({
        'artists':   _bilingual_filter_counts(Artwork.creator_fallback_fr, Artwork.creator_fallback_en, ids, 'Artiste inconnu'),
        'museums':   _bilingual_filter_counts(Artwork.collection_fr, Artwork.collection_en, ids, 'Inconnu'),
        'movements': _bilingual_filter_counts(Artwork.movement_fr, Artwork.movement_en, ids, 'Mouvement inconnu'),
        'types':     _bilingual_filter_counts(Artwork.instance_of_fr, Artwork.instance_of_en, ids, 'Inconnu'),
        'genres':    [],
        'copyrights':[],
    })


@app.route('/api/artists')
def api_artists():
    q   = get_filtered_query(request.args.get('q', ''),
                              request.args.getlist('artist'),
                              request.args.getlist('museum'),
                              request.args.getlist('movement'))
    ids = q.with_entities(Artwork.id).subquery()
    return jsonify(_bilingual_filter_counts(
        Artwork.creator_fallback_fr, Artwork.creator_fallback_en, ids, 'Artiste inconnu'))


@app.route('/api/museums')
def api_museums():
    # Récupérer les IDs des œuvres filtrées
    q = get_filtered_query(
        request.args.get('q', ''),
        request.args.getlist('artist'),
        [],
        request.args.getlist('movement')
    )
    artwork_ids = q.with_entities(Artwork.id).subquery()
    
    # Compter les musées liés à ces œuvres
    lang = session.get('language', 'fr')
    results = (
        db.session.query(
            Collection.id,
            Collection.collection_fr,
            Collection.collection_en,
            func.count(ArtworkCollection.artwork_id).label('cnt')
        )
        .join(ArtworkCollection, Collection.id == ArtworkCollection.collection_id)
        .filter(ArtworkCollection.artwork_id.in_(artwork_ids))
        .group_by(Collection.id, Collection.collection_fr, Collection.collection_en)
        .order_by(func.count(ArtworkCollection.artwork_id).desc())
        .limit(30)
        .all()
    )

    return jsonify([
        {
            'name': r.collection_fr if lang == 'fr' else r.collection_en,
            'count': r.cnt,
            'id': r.id
        }
        for r in results
    ])

@app.route('/api/museum/<museum_id>/works')
def api_museum_works(museum_id):
    """Récupère les œuvres d'un musée spécifique"""
    museum = Collection.query.get(museum_id)
    if not museum:
        return jsonify({'error': 'Musée non trouvé'}), 404
    
    # Récupérer les œuvres liées à ce musée
    artworks = Artwork.query.join(ArtworkCollection).filter(
        ArtworkCollection.collection_id == museum_id
    ).limit(50).all()
    
    works = []
    for a in artworks:
        d = a.to_dict()
        works.append({
            'id': d['id'],
            'titre': d['titre'],
            'image_url': d['image_url']
        })
    
    return jsonify({
        'museum': {
            'id': museum.id,
            'nom': museum.nom,
            'ville': museum.ville,
            'pays': museum.pays
        },
        'works': works
    })

@app.route('/api/movements')
def api_movements():
    q   = get_filtered_query(request.args.get('q', ''),
                              request.args.getlist('artist'),
                              request.args.getlist('museum'),
                              request.args.getlist('movement'))
    ids = q.with_entities(Artwork.id).subquery()
    return jsonify(_bilingual_filter_counts(
        Artwork.movement_fr, Artwork.movement_en, ids, 'Mouvement inconnu'))


@app.route('/api/instance_of')
def api_instance_of():
    q   = get_filtered_query(request.args.get('q', ''),
                              request.args.getlist('artist'),
                              request.args.getlist('museum'),
                              request.args.getlist('movement'))
    ids = q.with_entities(Artwork.id).subquery()
    return jsonify(_bilingual_filter_counts(
        Artwork.instance_of_fr, Artwork.instance_of_en, ids, 'Inconnu'))


@app.route('/api/copyrights')
def api_copyrights():
    q   = get_filtered_query(request.args.get('q', ''),
                              request.args.getlist('artist'),
                              request.args.getlist('museum'),
                              request.args.getlist('movement'))
    ids = q.with_entities(Artwork.id).subquery()
    return jsonify(_bilingual_filter_counts(
        Artwork.copyright_status_fr, Artwork.copyright_status_en, ids, 'Inconnu'))


# ============================================================
# ROUTE POUR LES SUGGESTIONS AVANCÉES (avec villes et pays)
# ============================================================



# ============================================================
# ROUTE POUR LES SUGGESTIONS AVEC PLUS DE RÉSULTATS
# ============================================================

import unicodedata

def normalize_string(s):
    """Enlève les accents et met en minuscules"""
    if not s:
        return ''
    # Normaliser et enlever les diacritiques (accents)
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                  if unicodedata.category(c) != 'Mn').lower()



@app.route('/api/search-suggestions')
def search_suggestions():
    """API pour les suggestions de recherche optimisée"""
    try:
        query = request.args.get('q', '').strip()
        
        if len(query) < 2:
            return jsonify({'artistes': [], 'oeuvres': [], 'musees': [], 'villes': [], 'pays': []})
        
        lang = session.get('language', 'fr')
        normalized_query = normalize_string(query)
        pattern = f"%{query}%"

        def accent_filter(field):
            return db.or_(
                field.ilike(pattern),
                func.unaccent(field).ilike(f"%{normalized_query}%")
            )

        results = {'artistes': [], 'oeuvres': [], 'musees': [], 'villes': [], 'pays': []}
        # ===== ARTISTES - avec LIMIT directement =====

        artist_field = Artwork.creator_fallback_fr if lang == 'fr' else Artwork.creator_fallback_en
        artists = db.session.query(
            artist_field.label('nom'),
            func.count(Artwork.id).label('oeuvres_count')
).filter(
    accent_filter(artist_field),
    artist_field != '',
    artist_field.isnot(None)
        ).group_by(artist_field).limit(5).all()
        
        for a in artists:
            results['artistes'].append({
                'nom': a.nom,
                'oeuvres_count': a.oeuvres_count
            })

        # ===== ŒUVRES - avec LIMIT =====
        title_field = Artwork.label_fallback_fr if lang == 'fr' else Artwork.label_fallback_en
        works = db.session.query(
            title_field.label('titre'),
            Artwork.creator_fallback_fr.label('artiste'),
            Artwork.id
).filter(
    accent_filter(title_field),
    title_field != '',
    title_field.isnot(None)
        ).limit(4).all()
        
        for w in works:
            results['oeuvres'].append({
                'id': w.id,
                'titre': w.titre,
                'artiste': w.artiste or 'Artiste inconnu'
            })

        # ===== MUSÉES - avec JOIN et LIMIT =====
        museum_field = Collection.collection_fr if lang == 'fr' else Collection.collection_en
        museums = db.session.query(
            Collection.id,
            museum_field.label('nom'),
            Collection.city_fr.label('ville'),
            func.count(ArtworkCollection.artwork_id).label('oeuvres_count')
        ).outerjoin(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id
).filter(
    accent_filter(museum_field),
    museum_field != '',
    museum_field.isnot(None)
        ).group_by(Collection.id, museum_field, Collection.city_fr).limit(4).all()
        
        for m in museums:
            results['musees'].append({
                'id': m.id,
                'nom': m.nom,
                'ville': m.ville or '',
                'oeuvres_count': m.oeuvres_count
            })

        # ===== VILLES - avec LIMIT =====
        city_field = Collection.city_fr if lang == 'fr' else Collection.city_en
        cities = db.session.query(
            city_field.label('nom'),
            func.count(Collection.id).label('musees_count'),
            func.count(ArtworkCollection.artwork_id).label('oeuvres_count')
        ).outerjoin(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id
        ).filter(
).filter(
    accent_filter(city_field),
    city_field != '',
    city_field.isnot(None)
        ).group_by(city_field).limit(5).all()
        
        for c in cities:
            results['villes'].append({
                'nom': c.nom,
                'musees_count': c.musees_count,
                'oeuvres_count': c.oeuvres_count
            })

        # ===== PAYS - avec LIMIT =====
        country_field = Collection.country_fr if lang == 'fr' else Collection.country_en
        countries = db.session.query(
            country_field.label('nom'),
            func.count(Collection.id).label('musees_count'),
            func.count(ArtworkCollection.artwork_id).label('oeuvres_count')
        ).outerjoin(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id
).filter(
    accent_filter(country_field),
    country_field != '',
    country_field.isnot(None)
        ).group_by(country_field).limit(4).all()
        
        for c in countries:
            results['pays'].append({
                'nom': c.nom,
                'musees_count': c.musees_count,
                'oeuvres_count': c.oeuvres_count
            })

        return jsonify(results)
        
    except Exception as e:
        print(f"❌ ERREUR: {str(e)}")
        return jsonify({'artistes': [], 'oeuvres': [], 'musees': [], 'villes': [], 'pays': []})

# ============================================================
# CONTEXT PROCESSOR POUR LA LANGUE DANS LES TEMPLATES
# ============================================================

@app.context_processor
def inject_language():
    """Injecte la langue actuelle dans tous les templates"""
    return dict(
        current_language=session.get('language', 'fr'),
        is_french=session.get('language', 'fr') == 'fr',
        is_english=session.get('language', 'fr') == 'en'
    )


# ============================================================
# ROUTE POUR CHANGER LA LANGUE (améliorée)
# ============================================================

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in ('fr', 'en'):
        session['language'] = lang
        # Optionnel : stocker dans un cookie pour persister
        resp = make_response(redirect(request.referrer or url_for('index')))
        resp.set_cookie('preferred_language', lang, max_age=30*24*3600)  # 30 jours
        return resp
    return redirect(request.referrer or url_for('index'))



def load_translations():
    """Charge les fichiers de traduction JSON"""
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


# Fonction de traduction pour les templates
@app.template_global()
def _(text):
    """Traduction pour les templates"""
    lang = session.get('language', 'fr')
    return TRANSLATIONS.get(lang, {}).get(text, text)



@app.route('/api/suggestions')
def suggestions():
    """Ancienne route pour suggestions simples - à conserver pour compatibilité"""
    query = request.args.get('q', '').strip()
    
    if len(query) < 2:
        return jsonify([])

    lang = session.get('language', 'fr')
    s = f"%{query}%"
    
    out = []

    # Artistes
    artist_field = Artwork.creator_fallback_fr if lang == 'fr' else Artwork.creator_fallback_en
    artist_excl = 'Artiste inconnu' if lang == 'fr' else 'Unknown artist'
    for row in db.session.query(artist_field).filter(
        artist_field.ilike(s),
        artist_field != artist_excl,
        artist_field != '',
        artist_field.isnot(None)
    ).distinct().limit(5):
        out.append({'texte': row[0], 'categorie': 'artiste'})

    # Titres
    title_field = Artwork.label_fallback_fr if lang == 'fr' else Artwork.label_fallback_en
    title_excl = 'Titre inconnu' if lang == 'fr' else 'Unknown title'
    for row in db.session.query(title_field).filter(
        title_field.ilike(s),
        title_field != title_excl,
        title_field != '',
        title_field.isnot(None)
    ).distinct().limit(3):
        out.append({'texte': row[0], 'categorie': 'œuvre'})

    # Musées
    museum_field = Collection.collection_fr if lang == 'fr' else Collection.collection_en
    for row in db.session.query(museum_field).filter(
        museum_field.ilike(s),
        museum_field != '',
        museum_field.isnot(None)
    ).distinct().limit(3):
        out.append({'texte': row[0], 'categorie': 'musée'})

    # Villes (si vous voulez les inclure dans l'ancienne route)
    city_field = Collection.city_fr if lang == 'fr' else Collection.city_en
    for row in db.session.query(city_field).filter(
        city_field.ilike(s),
        city_field != '',
        city_field.isnot(None)
    ).distinct().limit(2):
        out.append({'texte': row[0], 'categorie': 'ville'})

    return jsonify(out[:15])


@app.route('/museums')
def museums_page():
    print("="*50)
    print("🔵 ROUTE MUSEUMS APPELÉE")
    print("="*50)
    
    try:
        # Vérifier que le template existe
        import os
        template_path = os.path.join('templates', 'museum.html')
        if os.path.exists(template_path):
            print(f"✅ Template trouvé: {template_path}")
        else:
            print(f"❌ Template manquant: {template_path}")
        
        # Essayer de render
        return render_template('museum.html')
        
    except Exception as e:
        print(f"❌ ERREUR: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Erreur: {str(e)}", 500
@app.route('/api/museums/countries')
def api_museums_countries():
    """Retourne la liste des pays avec nombre de musées et d'œuvres"""
    lang = request.args.get('lang', 'fr')
    
    country_field = Collection.country_fr if lang == 'fr' else Collection.country_en
    
    results = db.session.query(
        country_field.label('name'),
        func.count(Collection.id).label('museums'),
        func.count(ArtworkCollection.artwork_id).label('works')
    ).outerjoin(
        ArtworkCollection, Collection.id == ArtworkCollection.collection_id
    ).filter(
        country_field.isnot(None),
        country_field != ''
    ).group_by(country_field).order_by(func.count(Collection.id).desc()).all()
    
    return jsonify([{
        'name': r[0],
        'museums': r[1],
        'works': r[2]
    } for r in results])

@app.route('/api/museums/cities')
def api_museums_cities():
    """Retourne les villes d'un pays avec stats"""
    country = request.args.get('country', '')
    lang = request.args.get('lang', 'fr')
    
    city_field = Collection.city_fr if lang == 'fr' else Collection.city_en
    country_field = Collection.country_fr if lang == 'fr' else Collection.country_en
    
    results = db.session.query(
        city_field.label('name'),
        func.count(Collection.id).label('museums'),
        func.count(ArtworkCollection.artwork_id).label('works')
    ).outerjoin(
        ArtworkCollection, Collection.id == ArtworkCollection.collection_id
    ).filter(
        country_field == country,
        city_field.isnot(None),
        city_field != ''
    ).group_by(city_field).order_by(func.count(Collection.id).desc()).all()
    
    return jsonify([{
        'name': r[0],
        'museums': r[1],
        'works': r[2]
    } for r in results])

@app.route('/api/museums/list')
def api_museums_list():
    """Retourne tous les musées avec leurs stats"""
    lang = request.args.get('lang', 'fr')
    
    name_field = Collection.collection_fr if lang == 'fr' else Collection.collection_en
    city_field = Collection.city_fr if lang == 'fr' else Collection.city_en
    country_field = Collection.country_fr if lang == 'fr' else Collection.country_en
    
    results = db.session.query(
        Collection.id,
        name_field.label('nom'),
        city_field.label('ville'),
        country_field.label('pays'),
        func.count(ArtworkCollection.artwork_id).label('oeuvres_count')
    ).outerjoin(
        ArtworkCollection, Collection.id == ArtworkCollection.collection_id
    ).group_by(
        Collection.id, name_field, city_field, country_field
    ).order_by(name_field).all()
    
    return jsonify([{
        'id': r[0],
        'nom': r[1] or 'Musée inconnu',
        'ville': r[2] or 'Ville inconnue',
        'pays': r[3] or 'Pays inconnu',
        'oeuvres_count': r[4]
    } for r in results])
    
    


@app.route('/home')
def home():
    """Page d'accueil optimisée"""
    
    # ===== 1. STATS : SÉPARÉES =====
    # Compter les œuvres
    total_oeuvres = db.session.query(func.count(Artwork.id)).scalar() or 0
    
    # Compter les artistes distincts
    total_artistes = db.session.query(
        func.count(func.distinct(Artwork.creator_fallback_fr))
    ).filter(
        Artwork.creator_fallback_fr.isnot(None),
        Artwork.creator_fallback_fr != ''
    ).scalar() or 0
    
    # Compter les musées distincts
    total_musees = db.session.query(
        func.count(func.distinct(Artwork.collection_fr))
    ).filter(
        Artwork.collection_fr.isnot(None),
        Artwork.collection_fr != ''
    ).scalar() or 0
    
    # Compter les utilisateurs
    total_users = db.session.query(func.count(User.id)).scalar() or 0
    
    print("=== STATS DEBUG ===")
    print(f"total_oeuvres: {total_oeuvres}")
    print(f"total_artistes: {total_artistes}")
    print(f"total_musees: {total_musees}")
    print(f"total_users: {total_users}")
    print("==================")
    
    # ===== 2. MOSAÏQUE =====
    mosaic_artworks = Artwork.query.filter(
        Artwork.image_url.isnot(None),
        Artwork.image_url != ''
    ).order_by(func.random()).limit(18).all()
    
    # ... reste du code
    
    # ===== 3. TOP RATED =====
    top_rated_data = db.session.query(
        Artwork,
        func.avg(Rating.note_globale).label('avg_rating'),
        func.count(Rating.id).label('rating_count')
    ).outerjoin(Rating).filter(
        Artwork.image_url.isnot(None),
        Artwork.image_url != ''
    ).group_by(Artwork.id).having(
        func.avg(Rating.note_globale).isnot(None)
    ).order_by(
        func.avg(Rating.note_globale).desc()
    ).limit(10).all()
    
    top_rated_list = []
    for artwork, avg_rating, rating_count in top_rated_data:
        d = artwork.to_dict()
        d['avg_rating'] = round(avg_rating, 1) if avg_rating else 0
        d['rating_count'] = rating_count
        top_rated_list.append(d)
    
    # ===== 4. FAVORIS POPULAIRES =====
    popular_data = db.session.query(
        Artwork,
        func.count(Favorite.id).label('fav_count')
    ).outerjoin(Favorite).filter(
        Artwork.image_url.isnot(None),
        Artwork.image_url != ''
    ).group_by(Artwork.id).having(
        func.count(Favorite.id) > 0
    ).order_by(
        func.count(Favorite.id).desc()
    ).limit(10).all()
    
    popular_list = []
    for artwork, fav_count in popular_data:
        d = artwork.to_dict()
        d['favorites_count'] = fav_count
        popular_list.append(d)
    
    # ===== 5. DERNIÈRES CRITIQUES =====
    recent_data = db.session.query(
        Rating,
        User.username,
        Artwork
    ).join(User).join(Artwork).filter(
        Rating.commentaire.isnot(None),
        Rating.commentaire != '',
        Artwork.image_url.isnot(None),
        Artwork.image_url != ''
    ).order_by(
        Rating.created_at.desc()
    ).limit(5).all()
    
    reviews_list = []
    for rating, username, artwork in recent_data:
        reviews_list.append({
            'username': username,
            'artwork': artwork.to_dict(),
            'note_globale': rating.note_globale,
            'commentaire': rating.commentaire,
            'created_at': rating.created_at.strftime('%d/%m/%Y')
        })
    
    # ===== 6. MUSÉES EN VEDETTE =====
    museums_data = db.session.query(
        Collection.id,
        Collection.collection_fr.label('nom'),
        Collection.city_fr.label('ville'),
        Collection.country_fr.label('pays'),
        func.count(ArtworkCollection.artwork_id).label('oeuvres_count')
    ).outerjoin(ArtworkCollection).filter(
        Collection.collection_fr.isnot(None),
        Collection.collection_fr != ''
    ).group_by(
        Collection.id, Collection.collection_fr, Collection.city_fr, Collection.country_fr
    ).order_by(
        func.count(ArtworkCollection.artwork_id).desc()
    ).limit(10).all()
    
    museums_list = []
    for m in museums_data:
        museums_list.append({
            'id': m.id,
            'nom': m.nom or 'Musée',
            'ville': m.ville or '',
            'pays': m.pays or '',
            'oeuvres_count': m.oeuvres_count or 0
        })
    
    # Formatage des stats avec séparateur de milliers
    total_oeuvres_fmt = f"{total_oeuvres:,}".replace(',', ' ')
    total_artistes_fmt = f"{total_artistes:,}".replace(',', ' ')
    total_musees_fmt = f"{total_musees:,}".replace(',', ' ')
    total_users_fmt = f"{total_users:,}".replace(',', ' ')
    
    return render_template('home.html',
        mosaic_artworks=mosaic_artworks,
        top_rated=top_rated_list,
        popular_favorites=popular_list,
        recent_reviews=reviews_list,
        featured_museums=museums_list,
        total_oeuvres=total_oeuvres_fmt,
        total_artistes=total_artistes_fmt,
        total_musees=total_musees_fmt,
        total_users=total_users_fmt
    )


# ============================================================
# ROUTES — API AUTH (modales)
# ============================================================

@app.route('/api/quick-login', methods=['POST'])
def quick_login():
    data  = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    pwd   = data.get('password', '')

    if not email or not pwd:
        return jsonify({'error': 'Email et mot de passe requis'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(pwd):
        return jsonify({'error': 'Email ou mot de passe incorrect'}), 401
    if not user.email_verified:
        return jsonify({'error': 'Veuillez vérifier votre email avant de vous connecter'}), 401

    session['user_id']  = user.id
    session['username'] = user.username
    user.last_login     = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Connexion réussie',
                    'username': user.username}), 200


@app.route('/api/quick-register', methods=['POST'])
def quick_register():
    data     = request.get_json() or {}
    username = data.get('username', '').strip()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'error': 'Tous les champs sont obligatoires'}), 400

    errors = validate_password_strength(password)
    if errors:
        return jsonify({'errors': errors}), 400

    existing = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()
    if existing:
        if existing.username == username:
            return jsonify({'error': "Ce nom d'utilisateur est déjà pris"}), 400
        return jsonify({'error': 'Cet email est déjà utilisé'}), 400

    try:
        user = User(username=username, email=email, email_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        code  = EmailVerification.generate_code()
        token = EmailVerification.generate_token()
        db.session.add(EmailVerification(
            user_id=user.id, token=token, code=code,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        ))
        db.session.commit()

        if send_verification_email(email, username, code, token):
            return jsonify({'success': True,
                            'message': 'Inscription réussie ! Un email de vérification vous a été envoyé.',
                            'email': email}), 200
        return jsonify({'success': True,
                        'message': "Compte créé mais erreur d'envoi d'email. Contactez le support.",
                        'email': email}), 200
    except Exception as exc:
        db.session.rollback()
        logger.error("Erreur quick-register : %s", exc)
        return jsonify({'error': "Erreur lors de l'inscription"}), 500


@app.route('/api/update-username', methods=['POST'])
def update_username():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    data         = request.get_json() or {}
    new_username = data.get('username', '').strip()

    if not new_username:
        return jsonify({'error': "Nom d'utilisateur requis"}), 400
    if len(new_username) > 80:
        return jsonify({'error': "Nom d'utilisateur trop long (max 80 caractères)"}), 400

    existing = User.query.filter_by(username=new_username).first()
    if existing and existing.id != session['user_id']:
        return jsonify({'error': "Ce nom d'utilisateur est déjà pris"}), 400

    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'Utilisateur non trouvé'}), 404
        user.username       = new_username
        session['username'] = new_username
        db.session.commit()
        return jsonify({'success': True, 'message': "Nom d'utilisateur modifié avec succès"}), 200
    except Exception as exc:
        db.session.rollback()
        logger.error("Erreur update-username : %s", exc)
        return jsonify({'error': 'Erreur lors de la modification'}), 500

@app.route('/research')
def research():
    """Page d'exploration avec scroll infini"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # Pagination simple
    works_query = Artwork.query.order_by(func.random()).paginate(
        page=page, per_page=limit, error_out=False
    )
    
    works = [w.to_dict() for w in works_query.items]
    total = works_query.total
    
    return render_template('research.html',
        works=works,
        total_oeuvres=total,
        current_page=page
    )

@app.route('/api/works')
def api_works():
    """API pour le scroll infini"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # Pagination
    works_query = Artwork.query.order_by(func.random()).paginate(
        page=page, per_page=limit, error_out=False
    )
    
    works = []
    for w in works_query.items:
        d = w.to_dict()
        # Optionnel : filtrer pour n'avoir que les infos nécessaires
        works.append({
            'id': d['id'],
            'titre': d['titre'],
            'createur': d['createur'],
            'image_url': d['image_url']
        })
    
    return jsonify({
        'works': works,
        'page': page,
        'has_more': works_query.has_next,
        'total': works_query.total
    })
# ============================================================
# ROUTES — TESTS (développement uniquement)
# ============================================================

@app.route('/test-email')
def test_email():
    ok = send_verification_email(
        'alexandre.brief2.0@gmail.com', 'TestUser', '123456', 'test-token-123')
    return ("✅ Email de test envoyé ! Vérifie ta boîte de réception."
            if ok else "❌ Échec de l'envoi. Vérifie les logs.")


@app.route('/test-reset-email')
def test_reset_email():
    ok = send_reset_email(
        'alexandre.brief2.0@gmail.com', 'TestUser',
        f"{BASE_URL}/reset-password?token=test-token-123")
    return ("✅ Email de test envoyé ! Vérifie ta boîte de réception."
            if ok else "❌ Échec de l'envoi. Vérifie les logs.")


# ============================================================
# DÉMARRAGE
# ============================================================

if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            inspector = inspect(db.engine)
            columns   = [c['name'] for c in inspector.get_columns('users')]
            if 'email_verified' not in columns:
                db.session.execute(
                    text('ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE'))
                db.session.commit()
                logger.info("Colonne email_verified ajoutée à la table users")
            logger.info("Tables PostgreSQL vérifiées/créées")
        except Exception as exc:
            logger.warning("Init DB : %s", exc)

    app.run(host='0.0.0.0', port=5000, debug=True)
