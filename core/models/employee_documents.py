# models/employee_documents.py
from core.addons.extensions import BaseModel, db
from sqlalchemy.dialects.mysql import ENUM

class EmployeeDocument(BaseModel):
    __tablename__ = 'employee_documents'
    
    # Enums
    document_type_enum = ENUM(
        'id_card', 'contract', 'certificate', 'degree', 'resume', 
        'bank_details', 'tax_form', 'pension_form', 'other',
        name='document_type'
    )
    
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    document_type = db.Column(document_type_enum, nullable=False)
    document_name = db.Column(db.String(255), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=db.func.now())
    uploaded_by = db.Column(db.Integer, nullable=False)  # User ID
    expiry_date = db.Column(db.Date)
    is_verified = db.Column(db.Boolean, default=False)
    verified_by = db.Column(db.Integer)
    comments = db.Column(db.Text)
    
    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'document_type': self.document_type,
            'document_name': self.document_name,
            'file_url': self.file_url,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None,
            'uploaded_by': self.uploaded_by,
            'expiry_date': self.expiry_date.isoformat() if self.expiry_date else None,
            'is_verified': self.is_verified,
            'verified_by': self.verified_by,
            'comments': self.comments,
            'employee_name': f"{self.employee.first_name} {self.employee.last_name}" if self.employee else None
        }