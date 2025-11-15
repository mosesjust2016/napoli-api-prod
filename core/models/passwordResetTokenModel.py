from ..addons.extensions import db, BaseModel
from datetime import datetime, timedelta
import uuid

class PasswordResetToken(BaseModel):
    __tablename__ = 'password_reset_tokens'
    
    # Change this to Integer to match users.id
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('password_reset_tokens', lazy=True))
    
    @classmethod
    def create_token(cls, user_id):
        """Create a new password reset token"""
        token = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(hours=24)
        return cls(user_id=user_id, token=token, expires_at=expires_at)
    
    def is_valid(self):
        """Check if token is still valid"""
        return not self.is_used and datetime.utcnow() < self.expires_at
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'token': self.token,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_used': self.is_used,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }