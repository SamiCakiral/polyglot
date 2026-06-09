from flask import Blueprint, render_template, redirect, url_for, flash, request, g, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app import db
from sqlalchemy.orm.attributes import flag_modified
import random
import json
from urllib.parse import urljoin, urlparse

bp = Blueprint('auth', __name__)

COLORS = ['#3498db', '#e74c3c', '#2ecc71', '#9b59b6', '#f1c40f', '#e67e22', '#1abc9c', '#34495e']


def is_safe_redirect_url(target):
    """Allow redirects only inside the current host."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@bp.before_app_request
def load_logged_in_user():
    """Set g.user from flask-login's current_user for backward compatibility."""
    if current_user.is_authenticated:
        g.user = current_user
    else:
        g.user = None


@bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        
        errors = []
        
        if not username:
            errors.append('Le nom d\'utilisateur est obligatoire.')
        elif len(username) < 2:
            errors.append('Le nom d\'utilisateur doit faire au moins 2 caractères.')
        elif len(username) > 80:
            errors.append('Le nom d\'utilisateur est trop long (max 80 caractères).')
        
        if not password:
            errors.append('Le mot de passe est obligatoire.')
        elif len(password) < 4:
            errors.append('Le mot de passe doit faire au moins 4 caractères.')
        
        if password != password_confirm:
            errors.append('Les mots de passe ne correspondent pas.')
        
        if User.query.filter_by(username=username).first():
            errors.append('Ce nom d\'utilisateur est déjà pris.')
        
        if errors:
            for err in errors:
                flash(err, 'error')
            return render_template('auth/register.html', username=username)
        
        # Create user
        color = random.choice(COLORS)
        user = User(username=username, avatar_color=color)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Auto-login after registration
        login_user(user, remember=True)
        flash(f'Bienvenue {username} ! Votre compte a été créé.', 'success')
        return redirect(url_for('main.index'))
    
    return render_template('auth/register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login page."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        
        user = User.query.filter_by(username=username).first()
        
        if user is None or not user.check_password(password):
            flash('Nom d\'utilisateur ou mot de passe incorrect.', 'error')
            return render_template('auth/login.html', username=username)
        
        login_user(user, remember=remember)
        
        # Redirect to next page if it exists
        next_page = request.args.get('next')
        if is_safe_redirect_url(next_page):
            return redirect(next_page)
        return redirect(url_for('main.index'))
    
    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    """Log out current user."""
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/profile/settings', methods=['GET', 'POST'])
@login_required
def profile_settings():
    """User profile settings page - enriched learner profile."""
    user = current_user
    
    if request.method == 'POST':
        # Update learner profile with enriched structure
        profile = user.learner_profile or {}
        
        # Native language
        profile['native_language'] = request.form.get('native_language', 'fr')
        
        # Known languages - parse JSON from hidden field
        known_languages_json = request.form.get('known_languages_json', '[]')
        try:
            known_languages = json.loads(known_languages_json)
            profile['known_languages'] = [
                {
                    'code': l.get('code', ''),
                    'level': l.get('level', 'A1'),
                    'years': int(l.get('years', 0))
                }
                for l in known_languages if l.get('code')
            ]
        except (json.JSONDecodeError, TypeError):
            profile['known_languages'] = []
        
        profile['learning_style'] = request.form.get('learning_style', 'balanced')
        profile['correction_preference'] = request.form.get('correction_preference', 'moderate')
        
        goals = request.form.getlist('goals')
        profile['goals'] = goals if goals else []
        
        try:
            daily_time = int(request.form.get('daily_time_available', 30))
            profile['daily_time_available'] = min(max(daily_time, 5), 120)
        except (ValueError, TypeError):
            profile['daily_time_available'] = 30
        
        # TTS accent preference
        tts_accent = request.form.get('tts_accent', '')
        if tts_accent:
            profile['tts_accent'] = tts_accent
        
        user.learner_profile = profile
        
        if request.form.get('avatar_color'):
            user.avatar_color = request.form.get('avatar_color')
        
        flag_modified(user, 'learner_profile')
        db.session.commit()
        
        flash('Profil mis à jour !', 'success')
        return redirect(url_for('auth.profile_settings'))
    
    # GET
    profile = user.learner_profile or {
        'native_language': 'fr',
        'known_languages': [],
        'learning_style': 'balanced',
        'correction_preference': 'moderate',
        'goals': [],
        'daily_time_available': 30,
        'tts_accent': ''
    }
    
    return render_template('auth/profile_settings.html', user=user, profile=profile)


# =============================================================================
# API: Auto-save profile fields (debounced from frontend)
# =============================================================================

@bp.route('/api/profile/save', methods=['POST'])
@login_required
def api_profile_save():
    """Auto-save any profile field via JSON. Used by debounced frontend."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    
    user = current_user
    profile = user.learner_profile or {}
    changed = False
    
    # Known languages
    if 'known_languages' in data:
        try:
            langs = data['known_languages']
            if isinstance(langs, list):
                profile['known_languages'] = [
                    {
                        'code': l.get('code', ''),
                        'level': l.get('level', 'A1'),
                        'years': int(l.get('years', 0))
                    }
                    for l in langs if l.get('code')
                ]
                changed = True
        except (TypeError, ValueError):
            pass
    
    # Simple string/int fields
    SIMPLE_FIELDS = [
        'native_language', 'learning_style', 'correction_preference', 'tts_accent'
    ]
    for field in SIMPLE_FIELDS:
        if field in data:
            profile[field] = data[field]
            changed = True
    
    # Goals (list of strings)
    if 'goals' in data and isinstance(data['goals'], list):
        profile['goals'] = data['goals']
        changed = True
    
    # Daily time
    if 'daily_time_available' in data:
        try:
            val = int(data['daily_time_available'])
            profile['daily_time_available'] = min(max(val, 5), 120)
            changed = True
        except (ValueError, TypeError):
            pass
    
    # Avatar color
    if 'avatar_color' in data:
        user.avatar_color = data['avatar_color']
        changed = True
    
    if changed:
        user.learner_profile = profile
        flag_modified(user, 'learner_profile')
        db.session.commit()
    
    return jsonify({'ok': True, 'saved': changed})


# =============================================================================
# API: Change password
# =============================================================================

@bp.route('/api/profile/password', methods=['POST'])
@login_required
def api_change_password():
    """Change the current user's password."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    
    current_pw = data.get('current_password', '')
    new_pw = data.get('new_password', '')
    confirm_pw = data.get('confirm_password', '')
    
    if not current_user.check_password(current_pw):
        return jsonify({'error': 'Mot de passe actuel incorrect.'}), 400
    
    if not new_pw or len(new_pw) < 4:
        return jsonify({'error': 'Le nouveau mot de passe doit faire au moins 4 caractères.'}), 400
    
    if new_pw != confirm_pw:
        return jsonify({'error': 'Les mots de passe ne correspondent pas.'}), 400
    
    current_user.set_password(new_pw)
    db.session.commit()
    
    return jsonify({'ok': True, 'message': 'Mot de passe modifié avec succès.'})


# =============================================================================
# API: Change username
# =============================================================================

@bp.route('/api/profile/username', methods=['POST'])
@login_required
def api_change_username():
    """Change the current user's username."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    
    new_username = data.get('username', '').strip()
    
    if not new_username or len(new_username) < 2:
        return jsonify({'error': 'Le nom doit faire au moins 2 caractères.'}), 400
    
    if len(new_username) > 80:
        return jsonify({'error': 'Le nom est trop long (max 80).'}), 400
    
    if new_username != current_user.username:
        existing = User.query.filter_by(username=new_username).first()
        if existing:
            return jsonify({'error': 'Ce nom est déjà pris.'}), 400
        
        current_user.username = new_username
        db.session.commit()
    
    return jsonify({'ok': True, 'message': 'Nom d\'utilisateur modifié.', 'username': new_username})
