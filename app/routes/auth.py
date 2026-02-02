from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify
from app.models import User
from app import db
import random

bp = Blueprint('auth', __name__)

COLORS = ['#3498db', '#e74c3c', '#2ecc71', '#9b59b6', '#f1c40f', '#e67e22', '#1abc9c', '#34495e']

from flask import g

@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = User.query.get(user_id)

@bp.route('/profiles')
def profiles():
    """Show profile selection screen."""
    users = User.query.all()
    return render_template('auth/profiles.html', users=users)

@bp.route('/profiles/create', methods=['POST'])
def create_profile():
    """Create a new user profile."""
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username:
        flash('Le nom est obligatoire', 'error')
        return redirect(url_for('auth.profiles'))
        
    if User.query.filter_by(username=username).first():
        flash('Ce nom est déjà pris', 'error')
        return redirect(url_for('auth.profiles'))
    
    # Assign random color
    color = random.choice(COLORS)
    
    user = User(username=username, avatar_color=color)
    if password:
        user.set_password(password)
        
    db.session.add(user)
    db.session.commit()
    
    flash('Profil créé !', 'success')
    return redirect(url_for('auth.profiles'))

@bp.route('/login/<int:user_id>', methods=['POST'])
def login(user_id):
    """Login as a specific user."""
    user = User.query.get_or_404(user_id)
    password = request.form.get('password')
    
    if user.password_hash:
        if not password or not user.check_password(password):
            flash('Mot de passe incorrect', 'error')
            return redirect(url_for('auth.profiles'))
            
    session['user_id'] = user.id
    return redirect(url_for('main.index'))

@bp.route('/logout')
def logout():
    """Log out current user."""
    session.pop('user_id', None)
    return redirect(url_for('auth.profiles'))
