# models/disciplinary_records.py
from core.addons.extensions import BaseModel, db
from sqlalchemy.dialects.mysql import ENUM

class DisciplinaryRecord(BaseModel):
    __tablename__ = 'disciplinary_records'
    
    # Enums
    type_enum = ENUM('verbal_warning', 'written_warning', 'final_warning', 'suspension', name='disciplinary_type')
    
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    hr_action_id = db.Column(db.Integer, db.ForeignKey('hr_actions.id'))
    type = db.Column(type_enum, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    issued_date = db.Column(db.Date, nullable=False)
    valid_until = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    issued_by = db.Column(db.Integer, nullable=False)  # User ID
    document_url = db.Column(db.String(500))
    comments = db.Column(db.Text)
    
    # Relationships
    hr_action = db.relationship('HRAction', backref='disciplinary_record', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'hr_action_id': self.hr_action_id,
            'type': self.type,
            'reason': self.reason,
            'issued_date': self.issued_date.isoformat() if self.issued_date else None,
            'valid_until': self.valid_until.isoformat() if self.valid_until else None,
            'is_active': self.is_active,
            'issued_by': self.issued_by,
            'document_url': self.document_url,
            'comments': self.comments,
            'employee_name': f"{self.employee.first_name} {self.employee.last_name}" if self.employee else None
        }