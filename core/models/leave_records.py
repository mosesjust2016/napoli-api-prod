# models/leave_records.py
from core.addons.extensions  import BaseModel, db
from sqlalchemy.dialects.mysql import ENUM

class LeaveRecord(BaseModel):
    __tablename__ = 'leave_records'
    
    # Enums
    leave_type_enum = ENUM('maternity', 'sick', 'annual', 'commute', 'unauthorized', name='leave_type')
    status_enum = ENUM('pending', 'approved', 'rejected', 'completed', name='leave_status')
    deduction_type_enum = ENUM('pay_deduction', 'leave_deduction', name='deduction_type')
    
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    hr_action_id = db.Column(db.Integer, db.ForeignKey('hr_actions.id'))
    leave_type = db.Column(leave_type_enum, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days_count = db.Column(db.Integer, nullable=False)
    status = db.Column(status_enum, nullable=False, default='approved')
    approved_by = db.Column(db.Integer)
    doctor_note_url = db.Column(db.String(500))
    commute_value = db.Column(db.Numeric(15, 2))
    deduction_type = db.Column(deduction_type_enum)
    deduction_amount = db.Column(db.Numeric(15, 2))
    return_to_work_date = db.Column(db.Date)
    reminder_date = db.Column(db.Date)
    comments = db.Column(db.Text)
    
    # Relationships
    hr_action = db.relationship('HRAction', backref='leave_record', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'hr_action_id': self.hr_action_id,
            'leave_type': self.leave_type,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'days_count': self.days_count,
            'status': self.status,
            'approved_by': self.approved_by,
            'doctor_note_url': self.doctor_note_url,
            'commute_value': float(self.commute_value) if self.commute_value else None,
            'deduction_type': self.deduction_type,
            'deduction_amount': float(self.deduction_amount) if self.deduction_amount else None,
            'return_to_work_date': self.return_to_work_date.isoformat() if self.return_to_work_date else None,
            'reminder_date': self.reminder_date.isoformat() if self.reminder_date else None,
            'comments': self.comments,
            'employee_name': f"{self.employee.first_name} {self.employee.last_name}" if self.employee else None
        }