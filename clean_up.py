from datetime import datetime, timezone, timedelta
from flask import current_app
from models.tokens_blocklist import TokenBlocklist
from db import db

# Delete any revoked-token entries older than lifetime
def cleanup_revoked_tokens():
    # Clean up expired tokens older than an hour
    expires_delta = current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", timedelta(minutes = 60))
    cutoff = datetime.now(timezone.utc) - expires_delta

    # Delete multiple tokens at once
    TokenBlocklist.query.filter(TokenBlocklist.created_at < cutoff).delete()
    db.session.commit()
