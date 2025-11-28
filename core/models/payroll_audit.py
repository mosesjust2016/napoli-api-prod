from core.addons.extensions import db
from datetime import datetime
import json

class PayrollAudit(db.Model):
    __tablename__ = 'payroll_audits'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50), nullable=False)   # 'PayrollPeriod' or 'PayrollRecord'
    entity_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20), nullable=False)        # created, updated, deleted
    performed_by = db.Column(db.Integer, nullable=True)      # user id (from JWT) when available
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    before_data = db.Column(db.Text)                         # JSON string
    after_data = db.Column(db.Text)                          # JSON string
    comment = db.Column(db.String(255), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action": self.action,
            "performed_by": self.performed_by,
            "timestamp": self.timestamp.isoformat(),
            "before_data": json.loads(self.before_data) if self.before_data else None,
            "after_data": json.loads(self.after_data) if self.after_data else None,
            "comment": self.comment
        }
