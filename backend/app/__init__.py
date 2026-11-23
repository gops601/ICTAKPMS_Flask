import logging
import os

from flask import Flask

from .config import Config
from .extensions import api, cors, db, jwt, limiter, migrate


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db.init_app(app)
    from . import models  # noqa: F401  (register models for migrations)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    api.init_app(app)

    from .routes import register_blueprints
    from .utils.errors import register_error_handlers
    from .cli import register_cli
    register_blueprints(app)
    register_error_handlers(app)
    register_cli(app)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    return app
