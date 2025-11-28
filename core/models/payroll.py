# models/payroll.py
from core.addons.extensions import BaseModel, db
from sqlalchemy.dialects.mysql import JSON, DECIMAL
from sqlalchemy import Text
import uuid
import json
from datetime import datetime

class PayrollRecord(BaseModel):
    __tablename__ = 'payroll_records'
    
    # Status enum
    status_enum = db.Enum('Pending', 'Processed', 'Paid', name='payroll_status')
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = db.Column(db.String(50), db.ForeignKey('employees.employee_code'), nullable=False)
    period = db.Column(db.String(7), nullable=False)  # Format: YYYY-MM
    period_type = db.Column(db.Enum('monthly', 'ytd'), nullable=False, default='monthly')
    
    # Earnings
    basic_salary = db.Column(DECIMAL(12, 2), nullable=False)
    allowances = db.Column(JSON, nullable=False, default=dict)  # {housing: 2000, transport: 1500, lunch: 500}
    total_allowances = db.Column(DECIMAL(12, 2), nullable=False)
    gross_pay = db.Column(DECIMAL(12, 2), nullable=False)
    
    # Deductions
    deductions = db.Column(JSON, nullable=False, default=dict)  # {paye: 3250, employee_napsa: 900, ...}
    total_deductions = db.Column(DECIMAL(12, 2), nullable=False)
    net_salary = db.Column(DECIMAL(12, 2), nullable=False)
    
    # Company Contributions
    company_contributions = db.Column(JSON, nullable=False, default=dict)  # {napsa: 900, nhima: 180, ...}
    
    # Status and dates
    status = db.Column(status_enum, nullable=False, default='Pending')
    processed_date = db.Column(db.DateTime)
    paid_date = db.Column(db.DateTime)
    payment_reference = db.Column(db.String(100))
    bank_transaction_id = db.Column(db.String(100))
    
    # Company reference
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    
    # Relationships
    employee = db.relationship('Employee', backref='payroll_records', lazy=True)
    company = db.relationship('Company', backref='payroll_records', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'employee_name': f"{self.employee.first_name} {self.employee.last_name}" if self.employee else '',
            'department': self.employee.department.name if self.employee and self.employee.department else '',
            'basic_salary': float(self.basic_salary) if self.basic_salary else 0,
            'allowances': self.allowances if isinstance(self.allowances, dict) else json.loads(self.allowances) if self.allowances else {},
            'total_allowances': float(self.total_allowances) if self.total_allowances else 0,
            'gross_pay': float(self.gross_pay) if self.gross_pay else 0,
            'deductions': self.deductions if isinstance(self.deductions, dict) else json.loads(self.deductions) if self.deductions else {},
            'total_deductions': float(self.total_deductions) if self.total_deductions else 0,
            'net_salary': float(self.net_salary) if self.net_salary else 0,
            'company_contributions': self.company_contributions if isinstance(self.company_contributions, dict) else json.loads(self.company_contributions) if self.company_contributions else {},
            'period': self.period,
            'period_type': self.period_type,
            'status': self.status,
            'processed_date': self.processed_date.isoformat() if self.processed_date else None,
            'paid_date': self.paid_date.isoformat() if self.paid_date else None,
            'payment_reference': self.payment_reference,
            'bank_transaction_id': self.bank_transaction_id,
            'company_id': self.company_id
        }

class PayrollBatch(BaseModel):
    __tablename__ = 'payroll_batches'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    period = db.Column(db.String(7), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    processed_count = db.Column(db.Integer, nullable=False)
    total_gross_pay = db.Column(DECIMAL(12, 2), nullable=False)
    total_net_pay = db.Column(DECIMAL(12, 2), nullable=False)
    total_company_contributions = db.Column(DECIMAL(12, 2), nullable=False)
    notes = db.Column(Text)
    processed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    company = db.relationship('Company', backref='payroll_batches', lazy=True)
    processed_by_user = db.relationship('User', backref='payroll_batches', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'period': self.period,
            'company_id': self.company_id,
            'processed_count': self.processed_count,
            'total_gross_pay': float(self.total_gross_pay) if self.total_gross_pay else 0,
            'total_net_pay': float(self.total_net_pay) if self.total_net_pay else 0,
            'total_company_contributions': float(self.total_company_contributions) if self.total_company_contributions else 0,
            'notes': self.notes,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'processed_by_name': f"{self.processed_by_user.first_name} {self.processed_by_user.last_name}" if self.processed_by_user else ''
        }