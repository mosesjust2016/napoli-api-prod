# models/company.py
from core.addons.extensions import BaseModel, db

class Company(BaseModel):
    __tablename__ = 'companies'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    employee_id_prefix = db.Column(db.String(10), nullable=True) 
    registration_number = db.Column(db.String(100), unique=True, nullable=False)
    employee_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default='Active')
    
    # Relationships
    employees = db.relationship('Employee', backref='company', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'employee_id_prefix': self.employee_id_prefix,
            'registration_number': self.registration_number,
            'employee_count': self.employee_count,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    


