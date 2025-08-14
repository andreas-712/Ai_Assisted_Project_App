import os

from flask import Flask, jsonify
from flask_smorest import Api
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate

from db import db
from models.tokens_blocklist import TokenBlocklist

from resources.project import blp as ProjectBlueprint
from resources.label import blp as LabelBlueprint
from resources.user import blp as UserBlueprint
from resources.gemini import blp as GeminiBlueprint
from resources.image import blp as ImageBlueprint
from resources.task import blp as TaskBlueprint

from datetime import timedelta
from flask_cors import CORS


def create_app(db_url = None):
    app = Flask(__name__)


    FRONTEND_URL = os.getenv("FRONTEND_URL")

    CORS(
        app,
        resources={r"/*": {
            "origins": [FRONTEND_URL],
            "supports_credentials": True,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "Accept"],
            "expose_headers": ["Content-Type", "Authorization"],
            "max_age": 86400
        }},
    )


    app.config["PROPAGATE_EXCEPTIONS"] = True
    app.config["API_TITLE"] = "ProjPool -- Project Database"
    app.config["API_VERSION"] = "v1"
    app.config["OPENAPI_VERSION"] = "3.0.3"
    app.config["OPENAPI_URL_PREFIX"] = "/"
    app.config["OPENAPI_SWAGGER_UI_PATH"] = "/swagger-ui"
    app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    # To store secret information which you don't want other programmers accessing
    # Like if you don't want others to have access to your database
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["GCS_BUCKET_NAME"] = os.getenv("GCS_BUCKET_NAME")
    app.config["GOOGLE_CLOUD_PROJECT_ID"] = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    app.config["GOOGLE_CLOUD_GEMINI_MODEL_ID"] = os.getenv("GOOGLE_CLOUD_GEMINI_MODEL_ID")
    # Set a secret key used for signing the JWT
    # Prevents tampering with JWTs from others
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
    # Connects Flask app to SQLAlchemy
    db.init_app(app)
    api = Api(app)

    # Initialize flask migrate
    migrate = Migrate(app, db)

    # Create instance
    jwt = JWTManager(app)
    # Expiry for full access tokens
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours = 3)

    # Admin priviledges (not given yet)
    '''
    @jwt.additional_claims_loader
    def add_claims_to_jwt(identity):
        # Look into database and see if user is admin
        # Just a rough example for now
        if identity == str(1):
            return {"is_admin": True}
        return {"is_admin": False}
    '''
    
    # Whenever we receive a JWT, this function checks if it is inside blocklist
    # If returns True, the request is terminated (access is revoked)
    @jwt.token_in_blocklist_loader
    def check_if_token_in_blocklist(jwt_header, jwt_payload):
        jti = jwt_payload["jti"]
        return bool(TokenBlocklist.query.filter_by(jti=jti).first())
    
    # Shows error message
    @jwt.revoked_token_loader
    # Note, jwt header makes it read the header in Insomnia, which has access info
    def revoked_token_callback(jwt_header, jwt_payload):
        return (
            jsonify(
                {"description": "Token has been revoked", "error": "token_revoked"}
            ),
            401
        )

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return (jsonify({"message": "Token has expired", "error": "token_expired"}), 401)
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return (jsonify({"message": "Signature verification failed", "error": "invalid_token"}), 401)

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return (
            jsonify(
                {
                    "description": "Request does not contain access token",
                    "error": "authorization_required"
                }
            ),
            401
        )

    # Creates all our tables in our database, if tables don't already exist
    # SQLAlchemy knows what to import because we imported "models"
    # In models folder, we have store.py, and item.py with their __tablename__ variables defined
    # Table names are result of __tablename__, columns are variables below (like id, price, etc)

    api.register_blueprint(ImageBlueprint)
    api.register_blueprint(LabelBlueprint)
    api.register_blueprint(ProjectBlueprint)
    api.register_blueprint(UserBlueprint)
    api.register_blueprint(GeminiBlueprint)
    api.register_blueprint(TaskBlueprint)

    return app