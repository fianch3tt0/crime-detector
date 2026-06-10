from flask import Flask

from config import config_map
from .extensions import cache, db


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(config_map[config_name])

    db.init_app(app)
    cache.init_app(app)

    from .api.routes import api_bp
    from .frontend.routes import frontend_bp

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(frontend_bp)

    return app
