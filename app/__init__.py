from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    db.init_app(app)
    
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
    
    return app
