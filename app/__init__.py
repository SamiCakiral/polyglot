from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
login_manager.login_message_category = 'info'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    db.init_app(app)
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))
    
    # Register blueprints
    from app.routes import main, decks, cards, categories, training, stats
    app.register_blueprint(main.bp)
    app.register_blueprint(decks.bp)
    app.register_blueprint(cards.bp)
    app.register_blueprint(categories.bp)
    app.register_blueprint(training.bp)
    app.register_blueprint(stats.bp)
    
    from app.routes import auth
    app.register_blueprint(auth.bp)
    
    from app.routes import programs
    app.register_blueprint(programs.bp)
    
    from app.routes import session as session_routes
    app.register_blueprint(session_routes.bp)
    
    from app.routes import pillars
    app.register_blueprint(pillars.bp)

    from app.routes import pillar_exercises
    app.register_blueprint(pillar_exercises.bp)

    from app.routes import pillar_chat
    app.register_blueprint(pillar_chat.bp)

    from app.routes import assessments
    app.register_blueprint(assessments.bp)
    
    from app.routes import tts
    app.register_blueprint(tts.bp)
    
    return app

