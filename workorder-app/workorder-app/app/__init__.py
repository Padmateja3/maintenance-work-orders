import os

from flask import Flask, send_from_directory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=os.path.join(ROOT, "static"), static_url_path="/static")
    app.json.sort_keys = False
    app.config.from_mapping(DATABASE=os.environ.get("WORKORDER_DB", os.path.join(ROOT, "workorders.db")))
    if config:
        app.config.update(config)

    from . import db, errors, routes

    db.init_app(app)
    errors.register(app)
    app.register_blueprint(routes.bp)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app
