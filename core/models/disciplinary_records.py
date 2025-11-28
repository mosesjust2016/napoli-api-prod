# models/disciplinary_records.py
from core.addons.extensions import BaseModel, db
from sqlalchemy.dialects.mysql import ENUM
import json

class DisciplinaryRecord(BaseModel):
    __tablename__ = 'disciplinary_records'
    
    # Enums - add severity enum
    type_enum = ENUM('verbal_warning', 'written_warning', 'final_warning', 'suspension', name='disciplinary_type')
    severity_enum = ENUM('low', 'medium', 'high', name='disciplinary_severity')
    
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    hr_action_id = db.Column(db.Integer, db.ForeignKey('hr_actions.id'))
    type = db.Column(type_enum, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    issued_date = db.Column(db.Date, nullable=False)
    valid_until = db.Column(db.Date, nullable=False)
    severity = db.Column(severity_enum, nullable=False, default='medium')  # New field
    consequences = db.Column(db.Text)  # Store as JSON string
    is_active = db.Column(db.Boolean, default=True)
    issued_by = db.Column(db.Integer, nullable=False)  # User ID
    requires_acknowledgement = db.Column(db.Boolean, default=True)  # New field
    acknowledged_by_employee = db.Column(db.Boolean, default=False)  # New field
    acknowledgement_date = db.Column(db.DateTime)  # New field
    document_urls = db.Column(db.Text)  # Store as JSON string (renamed from document_url)
    comments = db.Column(db.Text)
    
    # Relationships
    hr_action = db.relationship('HRAction', backref='disciplinary_record', lazy=True)
    
    def to_dict(self):
        # Parse JSON fields safely
        consequences = []
        if self.consequences:
            try:
                consequences = json.loads(self.consequences) if isinstance(self.consequences, str) else self.consequences
            except:
                consequences = []
        
        document_urls = []
        if self.document_urls:
            try:
                document_urls = json.loads(self.document_urls) if isinstance(self.document_urls, str) else self.document_urls
            except:
                document_urls = []
        elif hasattr(self, 'document_url') and self.document_url:  # Handle legacy single URL
            document_urls = [self.document_url]
        
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'hr_action_id': self.hr_action_id,
            'type': self.type,
            'reason': self.reason,
            'issued_date': self.issued_date.isoformat() if self.issued_date else None,
            'valid_until': self.valid_until.isoformat() if self.valid_until else None,
            'severity': getattr(self, 'severity', 'medium'),  # Safe access
            'consequences': consequences,
            'is_active': self.is_active,
            'issued_by': self.issued_by,
            'requires_acknowledgement': getattr(self, 'requires_acknowledgement', True),
            'acknowledged_by_employee': getattr(self, 'acknowledged_by_employee', False),
            'acknowledgement_date': self.acknowledgement_date.isoformat() if getattr(self, 'acknowledgement_date', None) else None,
            'document_urls': document_urls,
            'comments': self.comments,
            'employee_name': f"{self.employee.first_name} {self.employee.last_name}" if self.employee else None
        }