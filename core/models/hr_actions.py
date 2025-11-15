# models/hr_actions.py
from core.addons.extensions import BaseModel, db
from sqlalchemy.dialects.mysql import ENUM, JSON
import json

class HRAction(BaseModel):
    __tablename__ = 'hr_actions'
    
    # Enums
    action_type_enum = ENUM(
        'profile_update', 'status_change', 'contract_update', 'salary_change',
        'leave_maternity', 'leave_sick', 'leave_commute', 'leave_unauthorized',
        'disciplinary_action', 'compliance_update', 'exit_processing', 'payroll_action',
        name='hr_action_type'
    )
    status_enum = ENUM('pending', 'completed', 'cancelled', name='hr_action_status')
    
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    action_type = db.Column(action_type_enum, nullable=False)
    action_date = db.Column(db.DateTime, nullable=False, default=db.func.now())
    effective_date = db.Column(db.Date, nullable=False)
    performed_by = db.Column(db.Integer, nullable=False)  # User ID
    details = db.Column(JSON, nullable=False)
    summary = db.Column(db.Text, nullable=False)
    status = db.Column(status_enum, nullable=False, default='completed')
    requires_approval = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer)
    approval_date = db.Column(db.DateTime)
    comments = db.Column(db.Text)
    
    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'action_type': self.action_type,
            'action_date': self.action_date.isoformat() if self.action_date else None,
            'effective_date': self.effective_date.isoformat() if self.effective_date else None,
            'performed_by': self.performed_by,
            'details': self.details if isinstance(self.details, dict) else json.loads(self.details) if self.details else {},
            'summary': self.summary,
            'status': self.status,
            'requires_approval': self.requires_approval,
            'approved_by': self.approved_by,
            'approval_date': self.approval_date.isoformat() if self.approval_date else None,
            'comments': self.comments,
            'employee_name': f"{self.employee.first_name} {self.employee.last_name}" if self.employee else None
        }