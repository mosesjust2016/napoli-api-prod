# models/employees.py
from ..addons.extensions import BaseModel, db
from datetime import datetime, timedelta
from sqlalchemy.dialects.mysql import ENUM

class Employee(BaseModel):
    __tablename__ = 'employees'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True)
    
    # Custom Employee ID
    employee_id = db.Column(db.String(20), unique=True, nullable=False)
    
    # Personal Information
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=False)
    personal_email = db.Column(db.String(255))
    date_of_birth = db.Column(db.Date, nullable=False)
    
    # Nationality and Identity Information
    nationality = db.Column(db.String(100), nullable=False, default='Zambian')
    identity_type = db.Column(db.String(20), default='NRC', nullable=False)
    national_id = db.Column(db.String(50), unique=True, nullable=True)
    work_permit_number = db.Column(db.String(100), unique=True, nullable=True)
    work_permit_valid_from = db.Column(db.Date, nullable=True)
    work_permit_valid_to = db.Column(db.Date, nullable=True)
    work_permit_expiry_notified = db.Column(db.Boolean, default=False)
    
    # Additional fields for document generation
    middle_name = db.Column(db.String(100), nullable=True)
    napsa_number = db.Column(db.String(50), nullable=True)
    nhima_number = db.Column(db.String(50), nullable=True)
    tpin = db.Column(db.String(50), nullable=True)
    account_number = db.Column(db.String(50), nullable=True)
    sort_code = db.Column(db.String(50), nullable=True)
    next_of_kin = db.Column(db.String(200), nullable=True)
    physical_address = db.Column(db.Text, nullable=True)
    
    # Enums - UPDATED with expanded employment types
    gender_enum = ENUM('Male', 'Female', 'Other', name='gender_enum')
    marital_status_enum = ENUM('Single', 'Married', 'Divorced', 'Widowed', name='marital_status_enum')
    employment_type_enum = ENUM(
        'Full-time', 
        'Part-time', 
        'Contract', 
        'Fixed-Term',      # Added
        'Intern',          # Added
        'Apprentice',      # Added
        'Consultant',      # Added
        name='employment_type_enum'
    )
    employment_status_enum = ENUM('Active', 'Probation', 'Inactive', 'Expired Contract', name='employment_status_enum')
    payment_frequency_enum = ENUM('Monthly', 'Bi-weekly', 'Weekly', name='payment_frequency_enum')
    
    gender = db.Column(gender_enum, nullable=False)
    marital_status = db.Column(marital_status_enum)
    address = db.Column(db.Text)
    
    # Emergency Contact
    emergency_contact_name = db.Column(db.String(100), nullable=False)
    emergency_contact_phone = db.Column(db.String(20), nullable=False)
    emergency_contact_relationship = db.Column(db.String(50), nullable=False)
    
    # Employment Details
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100), nullable=False)
    employment_type = db.Column(employment_type_enum, nullable=False)
    employment_status = db.Column(employment_status_enum, nullable=False, default='Active')
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    probation_end_date = db.Column(db.Date)
    contract_end_date = db.Column(db.Date)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('employees.id'))
    work_location = db.Column(db.String(255))
    
    # Compensation
    salary = db.Column(db.Numeric(15, 2), nullable=False)
    salary_currency = db.Column(db.String(3), nullable=False, default='ZMW')
    payment_frequency = db.Column(payment_frequency_enum, nullable=False)
    
    # Bank & Tax
    bank_name = db.Column(db.String(100))
    bank_account = db.Column(db.String(50))
    tax_id = db.Column(db.String(50))
    pension_number = db.Column(db.String(50))
    
    # Flags
    has_live_disciplinary = db.Column(db.Boolean, default=False)
    
    # Audit
    created_by = db.Column(db.Integer, nullable=False)
    updated_by = db.Column(db.Integer)
    
    # Relationships
    supervisor = db.relationship(
        'Employee', 
        remote_side=[id],
        backref='subordinates',
        foreign_keys=[supervisor_id]
    )
    hr_actions = db.relationship('HRAction', backref='employee', lazy=True)
    disciplinary_records = db.relationship('DisciplinaryRecord', backref='employee', lazy=True)
    leave_records = db.relationship('LeaveRecord', backref='employee', lazy=True)
    documents = db.relationship('EmployeeDocument', backref='employee', lazy=True)
    
    def to_dict(self):
        """Safe to_dict method with error handling"""
        try:
            data = {
                'employee_id': self.employee_id,
                'id': self.id,
                'first_name': self.first_name,
                'last_name': self.last_name,
                'email': self.email,
                'phone': self.phone,
                'personal_email': self.personal_email,
                'date_of_birth': self.date_of_birth.isoformat() if self.date_of_birth else None,
                
                # Nationality and identity fields
                'nationality': self.nationality,
                'identity_type': self.identity_type,
                'national_id': self.national_id,
                'work_permit_number': self.work_permit_number,
                'work_permit_valid_from': self.work_permit_valid_from.isoformat() if self.work_permit_valid_from else None,
                'work_permit_valid_to': self.work_permit_valid_to.isoformat() if self.work_permit_valid_to else None,
                'work_permit_expiry_notified': self.work_permit_expiry_notified,
                
                # Additional fields
                'middle_name': self.middle_name,
                'napsa_number': self.napsa_number,
                'nhima_number': self.nhima_number,
                'tpin': self.tpin,
                'account_number': self.account_number,
                'sort_code': self.sort_code,
                'next_of_kin': self.next_of_kin,
                'physical_address': self.physical_address,
                
                'gender': self.gender,
                'marital_status': self.marital_status,
                'address': self.address,
                'emergency_contact_name': self.emergency_contact_name,
                'emergency_contact_phone': self.emergency_contact_phone,
                'emergency_contact_relationship': self.emergency_contact_relationship,
                'company_id': self.company_id,
                'department': self.department,
                'position': self.position,
                'employment_type': self.employment_type,
                'employment_status': self.employment_status,
                'start_date': self.start_date.isoformat() if self.start_date else None,
                'end_date': self.end_date.isoformat() if self.end_date else None,
                'probation_end_date': self.probation_end_date.isoformat() if self.probation_end_date else None,
                'contract_end_date': self.contract_end_date.isoformat() if self.contract_end_date else None,
                'supervisor_id': self.supervisor_id,
                'work_location': self.work_location,
                'salary': float(self.salary) if self.salary else None,
                'salary_currency': self.salary_currency,
                'payment_frequency': self.payment_frequency,
                'bank_name': self.bank_name,
                'bank_account': self.bank_account,
                'tax_id': self.tax_id,
                'pension_number': self.pension_number,
                'has_live_disciplinary': self.has_live_disciplinary,
                'created_by': self.created_by,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            }
            
            # Add computed fields for identity document status
            try:
                today = datetime.now().date()
                
                # Determine primary identity number based on nationality
                if self.nationality and self.nationality.lower() in ['zambia', 'zambian']:
                    data['primary_identity_number'] = self.national_id
                    data['identity_document_is_expired'] = False
                    data['identity_document_expires_soon'] = False
                    data['requires_work_permit_renewal'] = False
                else:
                    data['primary_identity_number'] = self.work_permit_number
                    if self.work_permit_valid_to:
                        data['identity_document_is_expired'] = self.work_permit_valid_to < today
                        data['identity_document_expires_soon'] = (
                            self.work_permit_valid_to >= today and 
                            self.work_permit_valid_to <= today + timedelta(days=30)
                        )
                        data['requires_work_permit_renewal'] = (
                            self.work_permit_valid_to <= today + timedelta(days=30)
                        )
                    else:
                        data['identity_document_is_expired'] = False
                        data['identity_document_expires_soon'] = False
                        data['requires_work_permit_renewal'] = False
                    
            except Exception as e:
                print(f"Error computing identity document status for employee {self.id}: {str(e)}")
                data['identity_document_is_expired'] = False
                data['identity_document_expires_soon'] = False
                data['requires_work_permit_renewal'] = False
                data['primary_identity_number'] = None
            
            # Safe company name access
            try:
                if hasattr(self, 'company') and self.company:
                    data['company_name'] = self.company.name
                    data['company_code'] = self.company.company_code
                else:
                    data['company_name'] = None
                    data['company_code'] = None
            except Exception as e:
                print(f"Error getting company name for employee {self.id}: {str(e)}")
                data['company_name'] = None
                data['company_code'] = None
            
            # Safe supervisor name access
            try:
                if hasattr(self, 'supervisor') and self.supervisor:
                    data['supervisor_name'] = f"{self.supervisor.first_name} {self.supervisor.last_name}"
                else:
                    data['supervisor_name'] = None
            except Exception as e:
                print(f"Error getting supervisor name for employee {self.id}: {str(e)}")
                data['supervisor_name'] = None
                
            return data
            
        except Exception as e:
            print(f"Critical error in Employee.to_dict() for employee {getattr(self, 'id', 'unknown')}: {str(e)}")
            # Return minimal safe data
            return {
                'employee_id': getattr(self, 'employee_id', 'Unknown'),
                'id': getattr(self, 'id', None),
                'first_name': getattr(self, 'first_name', 'Unknown'),
                'last_name': getattr(self, 'last_name', 'Unknown'),
                'email': getattr(self, 'email', None),
                'company_id': getattr(self, 'company_id', None),
                'error': f'Data retrieval error: {str(e)}'
            }

    def __repr__(self):
        return f"<Employee {self.employee_id} - {self.first_name} {self.last_name} ({self.email or 'No email'})>"