# models/auditLogModel.py
from datetime import datetime
from ..addons.extensions import db, BaseModel

class AuditLog(BaseModel):
    __tablename__ = 'audit_logs'

    # REMOVE these if BaseModel already provides them:
    # id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    employee_id = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    performed_by = db.Column(db.String(50), nullable=False)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convert model to dictionary for JSON responses."""
        data = {
            "employee_id": self.employee_id,
            "action": self.action,
            "performed_by": self.performed_by,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }
        
        # Add BaseModel fields if they exist
        if hasattr(self, 'id'):
            data['id'] = self.id
        if hasattr(self, 'created_at') and self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if hasattr(self, 'updated_at') and self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
            
        return data