from db import db
from datetime import datetime, timezone

class TokenBlocklist(db.Model):
    __tablename__ = "token_blocklist"
    id = db.Column(db.Integer, primary_key = True)
    jti = db.Column(db.String(100), unique = True, nullable = False, index = True)
    created_at = db.Column(
        db.DateTime(timezone = True),
        default = lambda: datetime.now(timezone.utc),
        nullable = False
    )
    
    