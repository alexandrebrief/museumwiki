#!/usr/bin/env python3
"""
Bluegreencliff — Application Flask
PostgreSQL · Authentification · Favoris · Notations
"""

# ============================================================
# IMPORTS
# ============================================================
import random
import json
import logging
import os
import re
import secrets
from sqlalchemy import case
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

# ===== CACHE HEADERS =====
@app.after_request
def add_cache_headers(response):
    """Ajoute des en-têtes de cache pour les ressources statiques"""
    if request.path.startswith('/static/'):
        response.cache_control.max_age = 86400
        response.cache_control.public = True
    else:
        response.cache_control.no_cache = True
        response.cache_control.no_store = True
        response.cache_control.must_revalidate = True
    return response

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

    @property
    def _lang(self):
        return session.get('language', 'fr')

    @property
    def titre(self):
        if self._lang == 'fr':
            return self.label_fallback_fr or self.label_fr or 'Titre inconnu'
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
    def date(self):
        return self.inception

    # ← ICI : Cette méthode doit être à l'intérieur de la classe, avec 4 espaces d'indentation
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


class ArtworkCollection(db.Model):
    __tablename__ = 'artwork_collections'

    artwork_id    = db.Column(db.String(50), db.ForeignKey('artworks.id'), primary_key=True)
    collection_id = db.Column(db.String(50), db.ForeignKey('collections.id'), primary_key=True)


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


class EmailVerification(db.Model):
    __tablename__ = 'email_verifications'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token      = db.Column(db.String(100), unique=True, nullable=False)
    code       = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)

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
        }


class PasswordReset(db.Model):
    __tablename__ = 'password_resets'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token      = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)

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
# CONTEXT PROCESSOR
# ============================================================

@app.context_processor
def inject_language():
    """Injecte la langue actuelle dans tous les templates"""
    return dict(
        current_language=session.get('language', 'fr'),
        is_french=session.get('language', 'fr') == 'fr',
        is_english=session.get('language', 'fr') == 'en'
    )


@app.template_global()
def _(text):
    """Traduction pour les templates"""
    lang = session.get('language', 'fr')
    return TRANSLATIONS.get(lang, {}).get(text, text)


# ============================================================
# ROUTES — GÉNÉRALES
# ============================================================

@app.route('/')
def index():
    return redirect(url_for('home'))
    
    
    query      = request.args.get('q', '')
    page       = request.args.get('page', 1, type=int)
    per_page   = 20
    artists    = request.args.getlist('artist')
    sort       = request.args.get('sort', 'relevance')
    
    # Construction de la requête de base
    if query or artists:
        base_q = Artwork.query
        
        if query:
            s = f"%{query}%"
            base_q = base_q.filter(
                db.or_(
                    Artwork.label_fallback_fr.ilike(s),
                    Artwork.label_fallback_en.ilike(s),
                    Artwork.creator_fallback_fr.ilike(s),
                    Artwork.creator_fallback_en.ilike(s),
                )
            )
        
        if artists:
            artist_filters = []
            for artist in artists:
                artist_filters.append(Artwork.creator_fallback_fr.ilike(f"%{artist}%"))
                artist_filters.append(Artwork.creator_fallback_en.ilike(f"%{artist}%"))
            base_q = base_q.filter(db.or_(*artist_filters))
        
        # Tri
        if sort == 'date_desc':
            base_q = base_q.order_by(Artwork.inception.desc())
        elif sort == 'date_asc':
            base_q = base_q.order_by(Artwork.inception)
        elif sort == 'title_asc':
            if session.get('language') == 'fr':
                base_q = base_q.order_by(Artwork.label_fallback_fr)
            else:
                base_q = base_q.order_by(Artwork.label_fallback_en)
        elif sort == 'artist_asc':
            if session.get('language') == 'fr':
                base_q = base_q.order_by(Artwork.creator_fallback_fr)
            else:
                base_q = base_q.order_by(Artwork.creator_fallback_en)
        else:
            base_q = base_q.order_by(func.random())
        
        pagination = base_q.paginate(page=page, per_page=per_page, error_out=False)
        results_page = pagination.items
    else:
        total = Artwork.query.count()
        if total:
            if page == 1:
                results_page = Artwork.query.order_by(func.random()).limit(per_page).all()
                pagination = type('P', (), {'items': results_page, 'total': per_page, 'pages': 1})()
            else:
                offset = (page - 1) * per_page
                results_page = Artwork.query.order_by(func.random()).offset(offset).limit(per_page).all()
                pagination = type('P', (), {
                    'items': results_page, 'total': total,
                    'pages': (total + per_page - 1) // per_page,
                })()
        else:
            results_page = []
            pagination = type('P', (), {'items': [], 'total': 0, 'pages': 1})()

    # Compteurs de favoris
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

    results_dicts = [a.to_dict() for a in results_page]

    return render_template('index.html',
                           query=query,
                           results=results_dicts,
                           count=pagination.total,
                           page=page,
                           total_pages=pagination.pages,
                           artists=artists,
                           sort=sort,
                           favorite_counts=favorite_counts)

def get_artwork_stats(artwork_id):
    """Récupère les statistiques complètes pour une œuvre"""
    ratings = Rating.query.filter_by(artwork_id=artwork_id).all()
    favorites_count = Favorite.query.filter_by(artwork_id=artwork_id).count()
    
    if ratings:
        n = len(ratings)
        moyenne = round(sum(r.note_globale for r in ratings) / n, 1)
        
        # Distribution des notes
        distribution = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
        for r in ratings:
            note = int(round(r.note_globale))
            if note in distribution:
                distribution[note] += 1
        
        return {
            'total_notes': n,
            'moyenne_globale': moyenne,
            'distribution': distribution,
            'favorites_count': favorites_count
        }
    else:
        return {
            'total_notes': 0,
            'moyenne_globale': 0,
            'distribution': {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
            'favorites_count': favorites_count
        }

@app.route('/oeuvre/<string:oeuvre_id>')
def oeuvre_detail(oeuvre_id):
    artwork = Artwork.query.filter_by(id=oeuvre_id).first()
    if not artwork:
        return "Œuvre non trouvée", 404
    
    # Récupérer les infos de collection (musée, ville, pays)
    collection_info = db.session.query(
        Collection.collection_fr,
        Collection.collection_en,
        Collection.city_fr,
        Collection.city_en,
        Collection.country_fr,
        Collection.country_en
    ).join(
        ArtworkCollection, Collection.id == ArtworkCollection.collection_id
    ).filter(
        ArtworkCollection.artwork_id == oeuvre_id
    ).first()
    
    # Créer un dictionnaire avec toutes les infos
    oeuvre_dict = artwork.to_dict()
    
    # Ajouter les infos de collection si disponibles
    if collection_info:
        oeuvre_dict['collection_fr'] = collection_info[0] or oeuvre_dict.get('collection_fr')
        oeuvre_dict['collection_en'] = collection_info[1] or oeuvre_dict.get('collection_en')
        oeuvre_dict['city_fr'] = collection_info[2]
        oeuvre_dict['city_en'] = collection_info[3]
        oeuvre_dict['country_fr'] = collection_info[4]
        oeuvre_dict['country_en'] = collection_info[5]
    
    # Récupérer les stats pour cette œuvre
    stats = get_artwork_stats(artwork.id)
    
    return render_template('detail.html', 
                         oeuvre=oeuvre_dict,
                         stats=stats)

@app.route('/about')
def about():
    total_oeuvres = Artwork.query.count()
    total_artistes = db.session.query(
        func.count(func.distinct(Artwork.creator_fallback_fr))
    ).filter(
        Artwork.creator_fallback_fr.isnot(None),
        Artwork.creator_fallback_fr != ''
    ).scalar() or 0
    total_musees = db.session.query(
        func.count(func.distinct(Artwork.collection_fr))
    ).filter(
        Artwork.collection_fr.isnot(None),
        Artwork.collection_fr != ''
    ).scalar() or 0
    total_users = User.query.count()

    return render_template('about.html',
                           total_oeuvres=total_oeuvres,
                           total_artistes=total_artistes,
                           total_musees=total_musees,
                           total_users=total_users,
                           last_update=datetime.now().strftime('%d/%m/%Y à %H:%M'))


@app.route('/home')
def home():
    """Page d'accueil optimisée"""
    
    # Stats
    total_oeuvres = db.session.query(func.count(Artwork.id)).scalar() or 0
    total_artistes = db.session.query(
        func.count(func.distinct(Artwork.creator_fallback_fr))
    ).filter(
        Artwork.creator_fallback_fr.isnot(None),
        Artwork.creator_fallback_fr != ''
    ).scalar() or 0
    total_musees = db.session.query(
        func.count(func.distinct(Artwork.collection_fr))
    ).filter(
        Artwork.collection_fr.isnot(None),
        Artwork.collection_fr != ''
    ).scalar() or 0
    total_users = db.session.query(func.count(User.id)).scalar() or 0
    
    # Mosaïque
    mosaic_artworks = Artwork.query.filter(
        Artwork.image_url.isnot(None),
        Artwork.image_url != ''
    ).order_by(func.random()).limit(12).all()
    
    # Top rated
    top_rated_ids = db.session.query(
        Rating.artwork_id,
        func.avg(Rating.note_globale).label('avg_rating')
    ).group_by(Rating.artwork_id).having(
        func.avg(Rating.note_globale).isnot(None)
    ).order_by(func.avg(Rating.note_globale).desc()).limit(10).all()

    top_rated_list = []
    for row in top_rated_ids:
        artwork = Artwork.query.get(row.artwork_id)
        if artwork and artwork.image_url:
            d = artwork.to_dict()
            d['avg_rating'] = round(row.avg_rating, 1)
            top_rated_list.append(d)

    # Favoris populaires
    popular_ids = db.session.query(
        Favorite.artwork_id,
        func.count(Favorite.id).label('fav_count')
    ).group_by(Favorite.artwork_id).having(
        func.count(Favorite.id) > 0
    ).order_by(func.count(Favorite.id).desc()).limit(10).all()

    popular_list = []
    for row in popular_ids:
        artwork = Artwork.query.get(row.artwork_id)
        if artwork and artwork.image_url:
            d = artwork.to_dict()
            d['favorites_count'] = row.fav_count
            popular_list.append(d)

    # Dernières critiques
    recent_data = db.session.query(
        Rating,
        User.username,
        Artwork
    ).join(User).join(Artwork).filter(
        Rating.commentaire.isnot(None),
        Rating.commentaire != '',
        Artwork.image_url.isnot(None),
        Artwork.image_url != ''
    ).order_by(Rating.created_at.desc()).limit(5).all()

    reviews_list = []
    for rating, username, artwork in recent_data:
        reviews_list.append({
            'username': username,
            'artwork': artwork.to_dict(),
            'note_globale': rating.note_globale,
            'commentaire': rating.commentaire,
        })

    # Formatage des stats
    total_oeuvres_fmt = f"{total_oeuvres:,}".replace(',', ' ')
    total_artistes_fmt = f"{total_artistes:,}".replace(',', ' ')
    total_musees_fmt = f"{total_musees:,}".replace(',', ' ')
    total_users_fmt = f"{total_users:,}".replace(',', ' ')
    
    return render_template('home.html',
        mosaic_artworks=mosaic_artworks,
        top_rated=top_rated_list,
        popular_favorites=popular_list,
        recent_reviews=reviews_list,
        total_oeuvres=total_oeuvres_fmt,
        total_artistes=total_artistes_fmt,
        total_musees=total_musees_fmt,
        total_users=total_users_fmt
    )


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
        return render_template('register.html', errors=errors,
                               username=username, email=email)

    existing_username = User.query.filter_by(username=username).first()
    existing_email    = User.query.filter_by(email=email).first()

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
    return render_template('profile.html', user=user)


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
    else:
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


@app.route('/favoris')
def favorites_page():
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour voir vos favoris', 'warning')
        return redirect(url_for('login'))
    favs = Favorite.query.filter_by(user_id=session['user_id']).all()
    artworks = [f.artwork.to_dict() for f in favs if f.artwork]
    return render_template('favorites.html', artworks=artworks)


@app.route('/api/rating/save', methods=['POST'])
def save_rating():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    data = request.get_json() or {}
    artwork_id = data.get('artwork_id')

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

    return jsonify({'success': True, 'rating': rating.to_dict()})


@app.route('/api/rating/delete', methods=['POST'])
def delete_rating():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    artwork_id = (request.get_json() or {}).get('artwork_id')
    rating = Rating.query.filter_by(user_id=session['user_id'],
                                    artwork_id=artwork_id).first()
    if not rating:
        return jsonify({'error': 'Commentaire non trouvé'}), 404

    db.session.delete(rating)
    db.session.commit()
    return jsonify({'success': True})


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
    ratings = Rating.query.filter_by(artwork_id=artwork_id).filter(
        Rating.commentaire.isnot(None), Rating.commentaire != ''
    ).order_by(Rating.created_at.desc()).all()
    
    comments = []
    for r in ratings:
        u = User.query.get(r.user_id)
        comments.append({
            'username': u.username if u else 'Anonyme',
            'commentaire': r.commentaire,
            'note_globale': r.note_globale,
            'created_at': r.created_at.strftime('%d/%m/%Y'),
        })
    return jsonify(comments)


@app.route('/api/artwork/stats/<artwork_id>')
def artwork_stats(artwork_id):
    if not Artwork.query.get(artwork_id):
        return jsonify({'error': 'Œuvre non trouvée'}), 404
    
    stats = get_artwork_stats(artwork_id)
    return jsonify(stats)

# ============================================================
# ROUTES — RECHERCHE ET FILTRES (FOCUS ARTISTE)
# ============================================================

import unicodedata

def normalize_string(s):
    """Enlève les accents et met en minuscules"""
    if not s:
        return ''
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                  if unicodedata.category(c) != 'Mn').lower()


@app.route('/api/search-suggestions')
def search_suggestions():
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
        
        # ARTISTES (déjà existant)
        artist_field = Artwork.creator_fallback_fr if lang == 'fr' else Artwork.creator_fallback_en
        artists = db.session.query(
            artist_field.label('nom'),
            func.count(Artwork.id).label('oeuvres_count')
        ).filter(
            accent_filter(artist_field),
            artist_field != '',
            artist_field.isnot(None),
            artist_field != 'Artiste inconnu',
            artist_field != 'Unknown artist'
        ).group_by(artist_field).order_by(
            func.count(Artwork.id).desc()
        ).limit(8).all()
        
        for a in artists:
            results['artistes'].append({
                'nom': a.nom,
                'oeuvres_count': a.oeuvres_count
            })

        # ŒUVRES (déjà existant)
        title_field = Artwork.label_fallback_fr if lang == 'fr' else Artwork.label_fallback_en
        works = db.session.query(
            title_field.label('titre'),
            Artwork.creator_fallback_fr.label('artiste'),
            Artwork.id
        ).filter(
            accent_filter(title_field),
            title_field != '',
            title_field.isnot(None),
            title_field != 'Titre inconnu',
            title_field != 'Unknown title'
        ).limit(4).all()
        
        for w in works:
            results['oeuvres'].append({
                'id': w.id,
                'titre': w.titre,
                'artiste': w.artiste or 'Artiste inconnu'
            })

        # MUSÉES — nouveau
        museum_field = Collection.collection_fr if lang == 'fr' else Collection.collection_en
        city_field   = Collection.city_fr if lang == 'fr' else Collection.city_en

        musees = db.session.query(
            Collection.id,
            museum_field.label('nom'),
            city_field.label('ville'),
            func.count(ArtworkCollection.artwork_id).label('oeuvres_count')
        ).join(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id
        ).filter(
            accent_filter(museum_field),
            museum_field != '',
            museum_field.isnot(None),
            museum_field != 'Musée inconnu',
            museum_field != 'Unknown museum'
        ).group_by(Collection.id, museum_field, city_field).order_by(
            func.count(ArtworkCollection.artwork_id).desc()
        ).limit(4).all()

        for m in musees:
            results['musees'].append({
                'id': m.id,
                'nom': m.nom,
                'ville': m.ville or '',
                'oeuvres_count': m.oeuvres_count
            })

# VILLES
        city_field = Collection.city_fr if lang == 'fr' else Collection.city_en

        villes = db.session.query(
            city_field.label('nom'),
            func.count(ArtworkCollection.artwork_id).label('oeuvres_count')
        ).join(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id
        ).filter(
            accent_filter(city_field),
            city_field != '',
            city_field.isnot(None),
            city_field != 'Ville inconnue',
            city_field != 'Unknown city'
        ).group_by(city_field).order_by(
            func.count(ArtworkCollection.artwork_id).desc()
        ).limit(3).all()

        for v in villes:
            results['villes'].append({
                'nom': v.nom,
                'oeuvres_count': v.oeuvres_count
            })

        # PAYS
        country_field = Collection.country_fr if lang == 'fr' else Collection.country_en

        pays = db.session.query(
            country_field.label('nom'),
            func.count(ArtworkCollection.artwork_id).label('oeuvres_count')
        ).join(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id
        ).filter(
            accent_filter(country_field),
            country_field != '',
            country_field.isnot(None),
            country_field != 'Pays inconnu',
            country_field != 'Unknown country'
        ).group_by(country_field).order_by(
            func.count(ArtworkCollection.artwork_id).desc()
        ).limit(3).all()

        for p in pays:
            results['pays'].append({
                'nom': p.nom,
                'oeuvres_count': p.oeuvres_count
            })

        return jsonify(results)
        
    except Exception as e:
        print(f"❌ ERREUR: {str(e)}")
        return jsonify({'artistes': [], 'oeuvres': [], 'musees': [], 'villes': [], 'pays': []})


@app.route('/api/search-artists')
def api_search_artists():
    """Recherche optimisée d'artistes"""
    try:
        query = request.args.get('q', '').strip()
        
        if len(query) < 2:
            return jsonify([])
        
        lang = session.get('language', 'fr')
        normalized_query = normalize_string(query)
        pattern = f"%{query}%"
        
        artist_field = Artwork.creator_fallback_fr if lang == 'fr' else Artwork.creator_fallback_en
        
        # Requête unique et optimisée
        artists = db.session.query(
            artist_field.label('nom'),
            func.count(Artwork.id).label('oeuvres_count')
        ).filter(
            db.or_(
                artist_field.ilike(pattern),
                func.unaccent(artist_field).ilike(f"%{normalized_query}%")
            ),
            artist_field != '',
            artist_field.isnot(None),
            artist_field != 'Artiste inconnu',
            artist_field != 'Unknown artist'
        ).group_by(artist_field).order_by(
            # Priorité à ceux qui commencent par la recherche
            case(
                (artist_field.ilike(f"{query}%"), 0),
                else_=1
            ),
            func.count(Artwork.id).desc()
        ).limit(20).all()  # 20 résultats suffisent pour les suggestions
        
        result = [{
            'nom': artist.nom,
            'oeuvres_count': artist.oeuvres_count
        } for artist in artists]
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify([])






@app.route('/api/filter-artists')
def api_filter_artists():
    """Liste des artistes pour les filtres, en tenant compte des filtres existants"""
    try:
        lang = session.get('language', 'fr')
        artist_field = Artwork.creator_fallback_fr if lang == 'fr' else Artwork.creator_fallback_en
        
        # Récupérer les filtres déjà appliqués
        selected_artists = request.args.getlist('artist')
        selected_country = request.args.get('country', '')
        selected_cities = request.args.getlist('city')
        search = request.args.get('search', '')
        museums = request.args.getlist('museum')
        sort = request.args.get('sort', 'relevance')
        
        # Construire la requête de base
        query = db.session.query(
            artist_field.label('name'),
            func.count(Artwork.id).label('count')
        ).filter(
            artist_field.isnot(None),
            artist_field != '',
            artist_field != 'Artiste inconnu',
            artist_field != 'Unknown artist'
        )
        
        # Si un pays est sélectionné, filtrer par pays
        if selected_country:
            query = query.join(ArtworkCollection).join(Collection).filter(
                db.or_(
                    Collection.country_fr.ilike(f"%{selected_country}%"),
                    Collection.country_en.ilike(f"%{selected_country}%")
                )
            )
        
        # Si des villes sont sélectionnées, filtrer par villes
        if selected_cities:
            city_filters = []
            for city in selected_cities:
                city_filters.append(Collection.city_fr.ilike(f"%{city}%"))
                city_filters.append(Collection.city_en.ilike(f"%{city}%"))
            query = query.join(ArtworkCollection).join(Collection).filter(db.or_(*city_filters))
        
        # Recherche optionnelle
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                db.or_(
                    artist_field.ilike(search_pattern),
                    func.unaccent(artist_field).ilike(f"%{search}%")
                )
            )
        
        artists = query.group_by(artist_field).order_by(
            func.count(Artwork.id).desc()
        ).limit(100).all()
        
        result = []
        for artist in artists:
            result.append({
                'id': artist.name,
                'name': artist.name,
                'count': artist.count,
                'selected': artist.name in selected_artists
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Erreur filter-artists: {e}")
        return jsonify([])








@app.route('/api/filter-countries')
def api_filter_countries():
    """Retourne la liste des pays pour les filtres"""
    try:
        lang = session.get('language', 'fr')
        country_field = Collection.country_fr if lang == 'fr' else Collection.country_en
        
        # Récupérer les filtres déjà appliqués
        selected_artists = request.args.getlist('artist')
        selected_cities = request.args.getlist('city')
        
        # Construire la requête de base
        query = db.session.query(
            country_field.label('name'),
            func.count(ArtworkCollection.artwork_id).label('count')
        ).join(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id
        ).join(
            Artwork, Artwork.id == ArtworkCollection.artwork_id
        ).filter(
            country_field.isnot(None),
            country_field != '',
            country_field != 'Pays inconnu',
            country_field != 'Unknown country'
        )
        
        # Si des artistes sont sélectionnés
        if selected_artists:
            artist_filters = []
            for artist in selected_artists:
                artist_filters.append(Artwork.creator_fallback_fr.ilike(f"%{artist}%"))
                artist_filters.append(Artwork.creator_fallback_en.ilike(f"%{artist}%"))
            query = query.filter(db.or_(*artist_filters))
        
        # Si des villes sont sélectionnées
        if selected_cities:
            city_filters = []
            for city in selected_cities:
                city_filters.append(Collection.city_fr.ilike(f"%{city}%"))
                city_filters.append(Collection.city_en.ilike(f"%{city}%"))
            query = query.filter(db.or_(*city_filters))
        
        # Exécuter la requête
        countries = query.group_by(country_field).order_by(
            func.count(ArtworkCollection.artwork_id).desc()
        ).limit(50).all()
        
        # Pays sélectionné dans l'URL
        selected_country = request.args.get('country', '')
        
        result = []
        for country in countries:
            result.append({
                'id': country.name,
                'name': country.name,
                'count': country.count,
                'selected': country.name == selected_country
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Erreur filter-countries: {e}")
        return jsonify([])

@app.route('/api/filter-cities')
def api_filter_cities():
    """Retourne la liste des villes pour les filtres, en tenant compte des filtres existants"""
    try:
        lang = session.get('language', 'fr')
        city_field = Collection.city_fr if lang == 'fr' else Collection.city_en
        country_field = Collection.country_fr if lang == 'fr' else Collection.country_en
        
        # Récupérer les filtres déjà appliqués
        selected_artists = request.args.getlist('artist')
        selected_country = request.args.get('country', '')
        selected_cities = request.args.getlist('city')
        
        # Construire la requête de base pour les villes
        query = db.session.query(
            city_field.label('name'),
            func.count(ArtworkCollection.artwork_id).label('count')
        ).join(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id
        ).join(
            Artwork, Artwork.id == ArtworkCollection.artwork_id
        ).filter(
            city_field.isnot(None),
            city_field != '',
            city_field != 'Ville inconnue',
            city_field != 'Unknown city'
        )
        
        # Si des artistes sont sélectionnés, filtrer les œuvres par ces artistes
        if selected_artists:
            artist_filters = []
            for artist in selected_artists:
                artist_filters.append(Artwork.creator_fallback_fr.ilike(f"%{artist}%"))
                artist_filters.append(Artwork.creator_fallback_en.ilike(f"%{artist}%"))
            query = query.filter(db.or_(*artist_filters))
        
        # Si un pays est sélectionné, filtrer les villes de ce pays
        if selected_country:
            query = query.filter(
                db.or_(
                    country_field.ilike(f"%{selected_country}%"),
                    func.unaccent(country_field).ilike(f"%{selected_country}%")
                )
            )
        
        # Exécuter la requête
        cities = query.group_by(city_field).order_by(
            func.count(ArtworkCollection.artwork_id).desc()
        ).limit(50).all()
        
        result = []
        for city in cities:
            result.append({
                'id': city.name,
                'name': city.name,
                'count': city.count,
                'selected': city.name in selected_cities
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Erreur filter-cities: {e}")
        return jsonify([])
        
        
        
        
@app.route('/api/search-cities')
def api_search_cities():
    """Recherche de villes pour les suggestions"""
    try:
        query = request.args.get('q', '').strip()
        
        if len(query) < 2:
            return jsonify([])
        
        lang = session.get('language', 'fr')
        normalized_query = normalize_string(query)
        pattern = f"%{query}%"
        
        city_field = Collection.city_fr if lang == 'fr' else Collection.city_en
        
        cities = db.session.query(
            city_field.label('name'),
            func.count(ArtworkCollection.artwork_id).label('count')
        ).join(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id, isouter=True
        ).filter(
            db.or_(
                city_field.ilike(pattern),
                func.unaccent(city_field).ilike(f"%{normalized_query}%")
            ),
            city_field != '',
            city_field.isnot(None),
            city_field != 'Ville inconnue',
            city_field != 'Unknown city'
        ).group_by(city_field).order_by(
            func.count(ArtworkCollection.artwork_id).desc()
        ).limit(30).all()
        
        result = []
        for city in cities:
            result.append({
                'nom': city.name,
                'oeuvres_count': city.count
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Erreur search-cities: {e}")
        return jsonify([])



@app.route('/api/search-countries')
def api_search_countries():
    """Recherche de pays pour les suggestions"""
    try:
        query = request.args.get('q', '').strip()
        
        if len(query) < 2:
            return jsonify([])
        
        lang = session.get('language', 'fr')
        normalized_query = normalize_string(query)
        pattern = f"%{query}%"
        
        country_field = Collection.country_fr if lang == 'fr' else Collection.country_en
        
        # Récupérer les pays avec leur nombre d'œuvres
        countries = db.session.query(
            country_field.label('name'),
            func.count(ArtworkCollection.artwork_id).label('count')
        ).join(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id, isouter=True
        ).filter(
            db.or_(
                country_field.ilike(pattern),
                func.unaccent(country_field).ilike(f"%{normalized_query}%")
            ),
            country_field != '',
            country_field.isnot(None),
            country_field != 'Pays inconnu',
            country_field != 'Unknown country'
        ).group_by(country_field).order_by(
            func.count(ArtworkCollection.artwork_id).desc()
        ).limit(30).all()
        
        result = []
        for country in countries:
            result.append({
                'nom': country.name,
                'oeuvres_count': country.count
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Erreur search-countries: {e}")
        return jsonify([])

@app.route('/api/filter-museums')
def api_filter_museums():
    """Retourne la liste des musées pour les filtres"""
    try:
        lang = session.get('language', 'fr')
        museum_field = Collection.collection_fr if lang == 'fr' else Collection.collection_en
        
        # Récupérer les filtres déjà appliqués
        selected_artists = request.args.getlist('artist')
        selected_country = request.args.get('country', '')
        selected_cities = request.args.getlist('city')
        
        # Construire la requête de base
        query = db.session.query(
            Collection.id,
            museum_field.label('name'),
            func.count(ArtworkCollection.artwork_id).label('count')
        ).join(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id
        ).join(
            Artwork, Artwork.id == ArtworkCollection.artwork_id
        ).filter(
            museum_field.isnot(None),
            museum_field != '',
            museum_field != 'Musée inconnu',
            museum_field != 'Unknown museum'
        )
        
        # Si des artistes sont sélectionnés
        if selected_artists:
            artist_filters = []
            for artist in selected_artists:
                artist_filters.append(Artwork.creator_fallback_fr.ilike(f"%{artist}%"))
                artist_filters.append(Artwork.creator_fallback_en.ilike(f"%{artist}%"))
            query = query.filter(db.or_(*artist_filters))
        
        # Si un pays est sélectionné
        if selected_country:
            query = query.filter(
                db.or_(
                    Collection.country_fr.ilike(f"%{selected_country}%"),
                    Collection.country_en.ilike(f"%{selected_country}%")
                )
            )
        
        # Si des villes sont sélectionnées
        if selected_cities:
            city_filters = []
            for city in selected_cities:
                city_filters.append(Collection.city_fr.ilike(f"%{city}%"))
                city_filters.append(Collection.city_en.ilike(f"%{city}%"))
            query = query.filter(db.or_(*city_filters))
        
        # Exécuter la requête
        museums = query.group_by(Collection.id, museum_field).order_by(
            func.count(ArtworkCollection.artwork_id).desc()
        ).limit(50).all()
        
        # Musées sélectionnés dans l'URL
        selected_museums = request.args.getlist('museum')
        
        result = []
        for museum in museums:
            result.append({
                'id': museum.id,
                'name': museum.name,
                'count': museum.count,
                'selected': museum.id in selected_museums or museum.name in selected_museums
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Erreur filter-museums: {e}")
        return jsonify([])


@app.route('/api/search-museums')
def api_search_museums():
    """Recherche de musées pour les suggestions"""
    try:
        query = request.args.get('q', '').strip()
        
        if len(query) < 2:
            return jsonify([])
        
        lang = session.get('language', 'fr')
        normalized_query = normalize_string(query)
        pattern = f"%{query}%"
        
        museum_field = Collection.collection_fr if lang == 'fr' else Collection.collection_en
        
        museums = db.session.query(
            Collection.id,
            museum_field.label('name'),
            func.count(ArtworkCollection.artwork_id).label('count')
        ).join(
            ArtworkCollection, Collection.id == ArtworkCollection.collection_id, isouter=True
        ).filter(
            db.or_(
                museum_field.ilike(pattern),
                func.unaccent(museum_field).ilike(f"%{normalized_query}%")
            ),
            museum_field != '',
            museum_field.isnot(None),
            museum_field != 'Musée inconnu',
            museum_field != 'Unknown museum'
        ).group_by(Collection.id, museum_field).order_by(
            func.count(ArtworkCollection.artwork_id).desc()
        ).limit(30).all()
        
        result = []
        for museum in museums:
            result.append({
                'id': museum.id,
                'nom': museum.name,
                'oeuvres_count': museum.count
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Erreur search-museums: {e}")
        return jsonify([])

# ============================================================
# ROUTE POUR CHANGER LA LANGUE
# ============================================================

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in ('fr', 'en'):
        session['language'] = lang
        resp = make_response(redirect(request.referrer or url_for('index')))
        resp.set_cookie('preferred_language', lang, max_age=30*24*3600)
        return resp
    return redirect(request.referrer or url_for('index'))

def _build_artwork_query(artists, country, cities, museums, types=None, q=''):
    """Construit la requête de base partagée entre /research et /api/works"""
    query = Artwork.query.filter(
        Artwork.image_url.isnot(None),
        Artwork.image_url != ''
    )

    # Recherche textuelle
    if q:
        s = f"%{q}%"
        query = query.filter(db.or_(
            Artwork.label_fallback_fr.ilike(s),
            Artwork.label_fallback_en.ilike(s),
            Artwork.creator_fallback_fr.ilike(s),
            Artwork.creator_fallback_en.ilike(s),
        ))
    
    if artists:
        query = query.filter(db.or_(*[
            db.or_(
                Artwork.creator_fallback_fr.ilike(f"%{a}%"),
                Artwork.creator_fallback_en.ilike(f"%{a}%")
            ) for a in artists
        ]))
    
    if country or cities or museums:
        query = query.join(ArtworkCollection, isouter=False).join(Collection)
        if country:
            query = query.filter(db.or_(
                Collection.country_fr.ilike(f"%{country}%"),
                Collection.country_en.ilike(f"%{country}%")
            ))
        if cities:
            query = query.filter(db.or_(*[
                db.or_(Collection.city_fr.ilike(f"%{c}%"), Collection.city_en.ilike(f"%{c}%"))
                for c in cities
            ]))
        if museums:
            query = query.filter(db.or_(*[
                db.or_(
                    Collection.id == m,
                    Collection.collection_fr.ilike(f"%{m}%"),
                    Collection.collection_en.ilike(f"%{m}%")
                ) for m in museums
            ]))
    
    # NOUVEAU : Filtre par type d'œuvre
    if types:
        type_filters = []
        for t in types:
            type_filters.append(Artwork.instance_of_fr.ilike(f"%{t}%"))
            type_filters.append(Artwork.instance_of_en.ilike(f"%{t}%"))
        if type_filters:
            query = query.filter(db.or_(*type_filters))
    
    return query


def _apply_sort(query, sort):
    if sort == 'date_desc':
        return query.order_by(Artwork.inception.desc())
    elif sort == 'date_asc':
        return query.order_by(Artwork.inception.asc())
    elif sort == 'title_asc':
        col = Artwork.label_fallback_fr if session.get('language') == 'fr' else Artwork.label_fallback_en
        return query.order_by(col)
    elif sort == 'artist_asc':
        col = Artwork.creator_fallback_fr if session.get('language') == 'fr' else Artwork.creator_fallback_en
        return query.order_by(col)
    else:
        return query.order_by(func.random())


@app.route('/research')
def research():
    page    = request.args.get('page', 1, type=int)
    limit   = min(request.args.get('limit', 24, type=int), 40)  # Changé à 24
    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities  = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types   = request.args.getlist('type')  # NOUVEAU
    sort    = request.args.get('sort', 'relevance')
    q       = request.args.get('q', '').strip() 
    view    = request.args.get('view', 4, type=int)  # ← AJOUTER CETTE LIGNE
    
    query = _build_artwork_query(artists, country, cities, museums, types, q=q)
    query = _apply_sort(query, sort)

    total      = query.count()
    works_page = query.offset((page - 1) * limit).limit(limit).all()
    works      = [w.to_dict() for w in works_page]

    return render_template('research.html',
        works=works,
        total_oeuvres=total,
        current_page=page,
        current_view=view, # ← AJOUTER CETTE LIGNE
)

@app.route('/api/works')
def api_works():
    page    = request.args.get('page', 1, type=int)
    limit   = min(request.args.get('limit', 24, type=int), 40)  # Changé à 24
    artists = request.args.getlist('artist')
    country = request.args.get('country', '')
    cities  = request.args.getlist('city')
    museums = request.args.getlist('museum')
    types   = request.args.getlist('type')  # NOUVEAU
    sort    = request.args.get('sort', 'relevance')
    q       = request.args.get('q', '').strip()

    query   = _build_artwork_query(artists, country, cities, museums, types, q=q)
    query   = _apply_sort(query, sort)

    total    = query.count()
    start    = (page - 1) * limit
    has_more = (start + limit) < total

    works_page = query.offset(start).limit(limit).all()
    works = [{
        'id':        w.id,
        'titre':     w.titre,
        'createur':  w.createur,
        'image_url': w.image_url,
    } for w in works_page]

    return jsonify({'works': works, 'page': page, 'has_more': has_more, 'total': total})
    
    
    
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
