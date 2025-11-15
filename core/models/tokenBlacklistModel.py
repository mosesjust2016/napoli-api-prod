from ..addons.extensions import BaseModel, db
from datetime import datetime

class TokenBlacklist(BaseModel):
    __tablename__ = 'token_blacklist'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    token = db.Column(db.String(500), unique=True, nullable=False)
    blacklisted_on = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'token': self.token,
            'blacklisted_on': self.blacklisted_on.isoformat() if self.blacklisted_on else None
        }