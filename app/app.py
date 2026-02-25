#!/usr/bin/env python3
"""
Application Flask pour MuseumWiki
Version PostgreSQL (locale et VPS) avec filtres dynamiques et authentification
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
from config import SENDGRID_API_KEY, FROM_EMAIL, BASE_URL
FROM_EMAIL = 'alexandre.brief2.0@gmail.com'
BASE_URL = 'http://localhost:5000'  # À changer en production

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialisation SQLAlchemy
db = SQLAlchemy(app)

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
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email_verified = db.Column(db.Boolean, default=False)  # ← changé
    email_verification_token = db.Column(db.String(100), unique=True)  # ← ajouté
    verification_token = db.Column(db.String(100), unique=True)  # ← ajouté
    last_login = db.Column(db.DateTime)  # ← ajouté
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
            'email_verified': self.email_verified,  # ← changé
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
        """Génère un code à 6 chiffres"""
        return ''.join(secrets.choice('0123456789') for _ in range(6))
    
    @staticmethod
    def generate_token():
        """Génère un token unique"""
        return secrets.token_urlsafe(32)
    
    def is_valid(self):
        """Vérifie si la vérification est encore valide"""
        return not self.used and datetime.utcnow() < self.expires_at


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


# ============================================
# 5. ROUTES PRINCIPALES
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
    
    pagination = base_query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('index.html', 
                         query=query,
                         results=[a.to_dict() for a in pagination.items],
                         count=pagination.total,
                         page=page,
                         total_pages=pagination.pages,
                         artists=artists,
                         museums=museums,
                         movements=movements,
                         sort=sort)


# ============================================
# 6. API POUR LES FILTRES
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
# 7. ROUTES PAGES STATIQUES
# ============================================
@app.route('/test-email')
def test_email():
    """Route de test pour vérifier SendGrid"""
    try:
        test_email = "alexandre.brief2.0@gmail.com"  # Ton email
        test_code = "123456"
        test_token = "test-token-123"
        
        result = send_verification_email(test_email, "TestUser", test_code, test_token)
        
        if result:
            return "✅ Email de test envoyé avec succès ! Vérifie ta boîte de réception."
        else:
            return "❌ Échec de l'envoi. Vérifie les logs."
            
    except Exception as e:
        return f"❌ Erreur: {str(e)}"
        
        
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
        
        # Validation
        errors = []
        
        if not username or not email or not password or not confirm_password:
            errors.append("Tous les champs sont obligatoires")
            print("❌ Erreur: Champs manquants")
        
        if password != confirm_password:
            errors.append("Les mots de passe ne correspondent pas")
            print("❌ Erreur: Mots de passe différents")
        
        if len(password) < 8:
            errors.append("Le mot de passe doit contenir au moins 8 caractères")
            print("❌ Erreur: Mot de passe trop court")
        
        if not re.search(r"[A-Z]", password):
            errors.append("Le mot de passe doit contenir au moins une majuscule")
            print("❌ Erreur: Pas de majuscule")
        
        if not re.search(r"[a-z]", password):
            errors.append("Le mot de passe doit contenir au moins une minuscule")
            print("❌ Erreur: Pas de minuscule")
        
        if not re.search(r"[0-9]", password):
            errors.append("Le mot de passe doit contenir au moins un chiffre")
            print("❌ Erreur: Pas de chiffre")
        
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            errors.append("Format d'email invalide")
            print("❌ Erreur: Email invalide")
        
        if errors:
            print(f"❌ Validation échouée: {errors}")
            return render_template('register.html', errors=errors, 
                                 username=username, email=email)
        
        print("✅ Validation passée, vérification de l'existence...")
        
        # Vérifier si l'utilisateur existe déjà
        try:
            existing_user_by_username = User.query.filter_by(username=username).first()
            existing_user_by_email = User.query.filter_by(email=email).first()
            
            print(f"👤 Recherche username existant: {existing_user_by_username is not None}")
            print(f"👤 Recherche email existant: {existing_user_by_email is not None}")
            
        except Exception as e:
            print(f"❌ Erreur lors de la recherche: {e}")
            import traceback
            traceback.print_exc()
            flash('Erreur de base de données.', 'danger')
            return render_template('register.html', username=username, email=email)
        
        if existing_user_by_username:
            errors.append("Ce nom d'utilisateur est déjà pris")
            print(f"❌ Username déjà pris: {username}")
        
        # Gestion spéciale pour l'email existant mais non vérifié
        if existing_user_by_email:
            print(f"📧 Email existant: {email}, email_verified: {existing_user_by_email.email_verified}")
            
            if existing_user_by_email.email_verified:
                errors.append("Cet email est déjà utilisé")
            else:
                # Email non vérifié - on renvoie un nouveau code
                try:
                    print("🔄 Renvoi de code pour email non vérifié")
                    
                    # Désactiver les anciennes vérifications
                    old_verifications = EmailVerification.query.filter_by(
                        user_id=existing_user_by_email.id, used=False
                    ).all()
                    print(f"📊 Anciennes vérifications trouvées: {len(old_verifications)}")
                    
                    for v in old_verifications:
                        v.used = True
                    
                    # Créer une nouvelle vérification
                    code = EmailVerification.generate_code()
                    token = EmailVerification.generate_token()
                    expires_at = datetime.utcnow() + timedelta(hours=24)
                    
                    verification = EmailVerification(
                        user_id=existing_user_by_email.id,
                        token=token,
                        code=code,
                        expires_at=expires_at
                    )
                    db.session.add(verification)
                    db.session.commit()
                    print("✅ Nouvelle vérification créée en BDD")
                    
                    # Envoyer l'email
                    if send_verification_email(email, existing_user_by_email.username, code, token):
                        flash('Un email de vérification a été renvoyé. Vérifiez votre boîte de réception.', 'info')
                        print("✅ Email renvoyé avec succès")
                    else:
                        flash('Erreur lors de l\'envoi de l\'email. Veuillez réessayer.', 'danger')
                        print("❌ Échec envoi email")
                    
                    return redirect(url_for('verify_email_pending', email=email))
                    
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Erreur lors du renvoi de vérification: {e}")
                    print(f"❌ Exception: {e}")
                    import traceback
                    traceback.print_exc()
                    errors.append("Erreur lors du traitement. Veuillez réessayer.")
        
        if errors:
            print(f"❌ Erreurs finales: {errors}")
            return render_template('register.html', errors=errors, 
                                 username=username, email=email)
        
        # Création du nouvel utilisateur
        try:
            print("✅ Création du nouvel utilisateur...")
            
            # Vérifier la connexion à la BDD
            try:
                db.session.execute(text('SELECT 1'))
                print("✅ Connexion BDD OK")
            except Exception as e:
                print(f"❌ Problème de connexion BDD: {e}")
                raise
            
            # Créer l'utilisateur avec les bons noms de colonnes
            user = User(
                username=username,
                email=email,
                email_verified=False,
                # Les autres champs peuvent être NULL
            )
            user.set_password(password)
            
            print(f"👤 User object créé: {user}")
            db.session.add(user)
            print("✅ User ajouté à la session")
            
            db.session.flush()
            print(f"✅ User flushé, ID: {user.id}")
            
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
            print("✅ Vérification ajoutée à la session")
            
            db.session.commit()
            print("✅ COMMIT RÉUSSI !")
            
            # Vérifier que l'utilisateur est bien en BDD
            check_user = User.query.get(user.id)
            if check_user:
                print(f"✅ Vérification: utilisateur trouvé en BDD avec ID {check_user.id}")
            else:
                print(f"❌ Vérification: utilisateur NON trouvé en BDD après commit")
            
            # Envoyer l'email
            if send_verification_email(email, username, code, token):
                flash('Inscription réussie ! Un email de vérification vous a été envoyé.', 'success')
                print("✅ Email envoyé avec succès")
                return redirect(url_for('verify_email_pending', email=email))
            else:
                flash('Compte créé mais erreur d\'envoi d\'email. Contactez le support.', 'warning')
                print("❌ Échec envoi email après création")
                return redirect(url_for('login'))
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erreur lors de l'inscription: {e}")
            print(f"❌ EXCEPTION: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            
            # Message d'erreur plus spécifique
            if "duplicate key" in str(e).lower():
                flash('Cet email ou nom d\'utilisateur existe déjà.', 'danger')
            elif "not null" in str(e).lower():
                flash('Erreur de validation des données. Vérifiez tous les champs.', 'danger')
            else:
                flash(f'Une erreur est survenue: {str(e)[:100]}', 'danger')
            
            return render_template('register.html', username=username, email=email)
    
    return render_template('register.html')











def handle_unverified_user(user, email):
    """Gère le cas d'un utilisateur avec email non vérifié"""
    # Désactiver les anciennes vérifications
    old_verifications = EmailVerification.query.filter_by(
        user_id=user.id, used=False
    ).all()
    for v in old_verifications:
        v.used = True
    
    # Créer une nouvelle vérification
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
    
    # Renvoyer l'email
    if send_verification_email(email, user.username, code, token):
        flash('Un email de vérification a été renvoyé. Vérifiez votre boîte de réception.', 'info')
    else:
        flash('Erreur lors de l\'envoi de l\'email. Veuillez réessayer.', 'danger')
    
    return redirect(url_for('verify_email_pending', email=email))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion avec vérification d'email"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        print(f"\n🔍 TENTATIVE DE CONNEXION")
        print(f"👤 Username: {username}")
        
        user = User.query.filter_by(username=username).first()
        
        if user:
            print(f"✅ Utilisateur trouvé: {user.username}")
            print(f"🔐 Vérification mot de passe: {'OK' if user.check_password(password) else 'ÉCHEC'}")
            print(f"📧 Email vérifié: {user.email_verified}")
        else:
            print(f"❌ Utilisateur non trouvé")
        
        if user and user.check_password(password):
            if not user.email_verified:
                print("❌ Email non vérifié")
                flash('Veuillez vérifier votre email avant de vous connecter.', 'warning')
                return redirect(url_for('verify_email_pending', email=user.email))
            
            # Connexion réussie
            session['user_id'] = user.id
            session['username'] = user.username
            
            # Mettre à jour last_login
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            print(f"✅ Connexion réussie pour {user.username}")
            flash(f'Bienvenue {user.username} !', 'success')
            return redirect(url_for('index'))
        else:
            print("❌ Nom d'utilisateur ou mot de passe incorrect")
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
    if not user:
        session.clear()
        flash('Utilisateur non trouvé', 'danger')
        return redirect(url_for('login'))
    
    return render_template('profile.html', user=user.to_dict())

# ============================================
# 7. ROUTES PAGES STATIQUES
# ============================================

@app.route('/stats')
def statistics():
    """Page de statistiques enrichie"""
    try:
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
        
        # Date de dernière mise à jour
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
        
@app.route('/oeuvre/<string:oeuvre_id>')
def oeuvre_detail(oeuvre_id):
    """Page détaillée d'une œuvre"""
    artwork = Artwork.query.get(oeuvre_id)
    
    if artwork:
        return render_template('detail.html', oeuvre=artwork.to_dict())
    else:
        return "Œuvre non trouvée", 404

# ============================================
# 9. ROUTES DE VÉRIFICATION D'EMAIL
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
    
    # Marquer l'utilisateur comme vérifié
    user = verification.user
    user.is_verified = True
    verification.used = True
    db.session.commit()
    
    flash('Email vérifié avec succès ! Vous pouvez maintenant vous connecter.', 'success')
    return redirect(url_for('login'))


@app.route('/verify-code', methods=['POST'])
def verify_code():
    """Vérification par code"""
    code = request.form.get('code', '').strip()
    email = request.form.get('email', '')
    
    print(f"\n🔍 VÉRIFICATION DE CODE")
    print(f"📧 Email: {email}")
    print(f"🔢 Code reçu: {code}")
    
    user = User.query.filter_by(email=email).first()
    if not user:
        print(f"❌ Utilisateur non trouvé")
        flash('Utilisateur non trouvé.', 'danger')
        return redirect(url_for('login'))
    
    print(f"👤 Utilisateur ID: {user.id}")
    
    # Chercher la vérification
    verification = EmailVerification.query.filter_by(
        user_id=user.id, used=False
    ).first()
    
    if verification:
        print(f"✅ Vérification trouvée en BDD")
        print(f"   - Code en BDD: {verification.code}")
        print(f"   - Code reçu: {code}")
        print(f"   - Expire le: {verification.expires_at}")
        print(f"   - Valide: {verification.is_valid()}")
        
        if verification.code != code:
            print(f"❌ Code incorrect")
            flash('Code incorrect.', 'danger')
            return redirect(url_for('verify_email_pending', email=email))
        
        if not verification.is_valid():
            print(f"❌ Code expiré")
            flash('Code expiré.', 'danger')
            return redirect(url_for('verify_email_pending', email=email))
        
        # Marquer l'utilisateur comme vérifié
        user.email_verified = True
        verification.used = True
        db.session.commit()
        
        print(f"✅ Utilisateur {user.username} vérifié avec succès!")
        flash('Email vérifié avec succès ! Vous pouvez maintenant vous connecter.', 'success')
        return redirect(url_for('login'))
    else:
        print(f"❌ Aucune vérification trouvée pour l'utilisateur {user.id}")
        
        # Vérifie toutes les entrées pour cet utilisateur
        all_verifs = EmailVerification.query.filter_by(user_id=user.id).all()
        print(f"📊 Toutes les vérifications trouvées: {len(all_verifs)}")
        for v in all_verifs:
            print(f"   - ID: {v.id}, Code: {v.code}, used: {v.used}, expires: {v.expires_at}")
        
        flash('Aucune demande de vérification trouvée. Veuillez vous réinscrire.', 'danger')
        return redirect(url_for('register'))


@app.route('/resend-verification', methods=['POST'])
def resend_verification():
    """Renvoyer l'email de vérification"""
    email = request.form.get('email', '')
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Utilisateur non trouvé.', 'danger')
        return redirect(url_for('register'))
    
    if user.is_verified:
        flash('Cet email est déjà vérifié.', 'info')
        return redirect(url_for('login'))
    
    # Désactiver les anciennes vérifications
    old_verifications = EmailVerification.query.filter_by(
        user_id=user.id, used=False
    ).all()
    for v in old_verifications:
        v.used = True
    
    # Créer une nouvelle vérification
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
# 10. CONTEXT PROCESSOR POUR LES TEMPLATES
# ============================================

@app.context_processor
def inject_user():
    """Injecte des variables dans tous les templates"""
    return dict(
        now=datetime.now(),
        is_authenticated='user_id' in session,
        current_user=session.get('username', '')
    )


# ============================================
# 11. LANCEMENT DE L'APPLICATION
# ============================================
if __name__ == '__main__':
    with app.app_context():
        try:
            # Création des tables
            db.create_all()
            
            # Vérifier si la colonne is_verified existe, l'ajouter si nécessaire
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('users')]
            
            if 'is_verified' not in columns:
                db.session.execute('ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE')
                db.session.commit()
                print("✅ Colonne is_verified ajoutée à la table users")
            
            print("✅ Tables PostgreSQL vérifiées/créées")
            print(f"📧 SendGrid configuré avec FROM_EMAIL: {FROM_EMAIL}")
            print(f"🔗 URL de base: {BASE_URL}")
            
        except Exception as e:
            print(f"⚠️  Attention: {e}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
