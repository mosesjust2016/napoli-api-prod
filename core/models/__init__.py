from ..addons.extensions import db

# Association tables - use Integer to match BaseModel
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True)
)

role_permissions = db.Table('role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True)
)

# Import all models
from .companies import Company
from .disciplinary_records import DisciplinaryRecord
from .employee_documents import EmployeeDocument
from .employees import Employee
from .hr_actions import HRAction
from .leave_records import LeaveRecord
from .tokenBlacklistModel import TokenBlacklist
from .passwordResetTokenModel import PasswordResetToken
from .auditLogModel import AuditLog

# Import new auth models
from .users import User
from .roleModel import Role
from .permissionModel import Permission

__all__ = [
    'db',
    'Company', 
    'DisciplinaryRecord', 
    'EmployeeDocument', 
    'Employee', 
    'HRAction', 
    'LeaveRecord', 
    'TokenBlacklist',
    'PasswordResetToken',
    'User',
    'Role', 
    'Permission',
    'AuditLog', 
    'user_roles',
    'role_permissions'
]