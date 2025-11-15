from flask_openapi3 import APIBlueprint, Tag
from flask import jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt, get_jwt_identity
)
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, EmailStr, validator
from typing import List, Optional

from ...addons.extensions import db
from ...models.users import User
from ...models.roleModel import Role
from ...models.permissionModel import Permission
from ...models.tokenBlacklistModel import TokenBlacklist
from ...models.passwordResetTokenModel import PasswordResetToken
from ...models.companies import Company

auth_tag = Tag(name="Auth", description="Authentication & Authorization")
auth_bp = APIBlueprint(
    'auth', __name__, url_prefix='/api/auth', abp_tags=[auth_tag]
)

# Napoli Company Constants
NAPOLI_COMPANY_CODE = "NAP"
NAPOLI_COMPANY_NAME = "Napoli Property Inv Ltd"
NAPOLI_REGISTRATION_NUMBER = "ZMW/REG-1005/25"

# ---------------------- SCHEMAS ---------------------- #
class LoginSchema(BaseModel):
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=1, description="User's password")

    @validator('email')
    def email_to_lowercase(cls, v):
        return v.strip().lower() if v else v

class LoginResponseSchema(BaseModel):
    success: bool = Field(..., description="Indicates if the login was successful")
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    access_token_expires_at: str = Field(..., description="Access token expiration timestamp")
    refresh_token_expires_at: str = Field(..., description="Refresh token expiration timestamp")
    user: dict = Field(..., description="User information with roles and company")

class RefreshTokenResponseSchema(BaseModel):
    success: bool = Field(..., description="Indicates if the token refresh was successful")
    access_token: str = Field(..., description="New JWT access token")
    refresh_token: str = Field(..., description="New JWT refresh token")
    access_token_expires_at: str = Field(..., description="Access token expiration timestamp")
    refresh_token_expires_at: str = Field(..., description="Refresh token expiration timestamp")
    user: dict = Field(..., description="User information with roles and company")

class LogoutResponseSchema(BaseModel):
    message: str = Field(..., description="Logout status message")

class ResetPasswordSchema(BaseModel):
    email: EmailStr = Field(..., description="Email address for password reset")

    @validator('email')
    def email_to_lowercase(cls, v):
        return v.strip().lower() if v else v

class ResetPasswordResponseSchema(BaseModel):
    message: str = Field(..., description="Status message")
    reset_token: str = Field(None, description="Password reset token")
    expires_at: str = Field(None, description="Token expiration timestamp")

class CompanySchema(BaseModel):
    id: int = Field(..., description="Company ID")
    name: str = Field(..., description="Company name")
    code: str = Field(..., description="Company code")
    registration_number: str = Field(..., description="Company registration number")
    employee_count: int = Field(..., description="Number of employees")
    status: str = Field(..., description="Company status")

class RoleSchema(BaseModel):
    id: int = Field(..., description="Role ID")
    name: str = Field(..., description="Role name")
    tier: int = Field(..., description="Role tier/level")
    description: str = Field(None, description="Role description")

class PermissionSchema(BaseModel):
    id: int = Field(..., description="Permission ID")
    name: str = Field(..., description="Permission name")
    description: str = Field(None, description="Permission description")

class RoleWithPermissionsSchema(BaseModel):
    role: RoleSchema = Field(..., description="Role information")
    permissions: List[PermissionSchema] = Field(..., description="List of permissions")

class RolesListSchema(BaseModel):
    roles: List[RoleSchema] = Field(..., description="List of roles")

class PermissionsListSchema(BaseModel):
    permissions: List[RoleWithPermissionsSchema] = Field(..., description="List of permissions grouped by role")

class CreateUserSchema(BaseModel):
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=8, description="User's password (min 8 chars)")
    name: str = Field(..., min_length=1, description="User's full name")
    role: str = Field(..., description="User's role name")
    company_id: int = Field(..., description="Company ID")

    @validator('email')
    def email_to_lowercase(cls, v):
        return v.strip().lower() if v else v

    @validator('name')
    def name_stripped(cls, v):
        return v.strip() if v else v

class UserResponseSchema(BaseModel):
    id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    name: str = Field(..., description="User name")
    role: str = Field(..., description="User role")
    company: CompanySchema = Field(..., description="User's company")

class CreateUserResponseSchema(BaseModel):
    message: str = Field(..., description="Status message")
    user: UserResponseSchema = Field(..., description="Created user information")

class ErrorResponse(BaseModel):
    status: int = Field(..., description="HTTP status code")
    isError: bool = Field(True, description="Indicates if the response is an error")
    message: str = Field(..., description="Error message")

def get_napoli_company():
    """Get the Napoli company (assume it exists from shell script initialization)"""
    # Try to find the company by code (what shell script created)
    napoli_company = Company.query.filter_by(code=NAPOLI_COMPANY_CODE).first()
    
    # If not found by code, try by registration number
    if not napoli_company:
        napoli_company = Company.query.filter_by(registration_number=NAPOLI_REGISTRATION_NUMBER).first()
    
    return napoli_company

def get_user_company_data(user):
    """Get company data for a user"""
    # Always use Napoli as default company for now
    # Remove the employee relationship check as it's causing issues
    company = get_napoli_company()
    
    if company:
        return {
            "id": company.id,
            "name": company.name,
            "code": company.code,
            "employee_id_prefix": getattr(company, 'employee_id_prefix', None),
            "registration_number": company.registration_number,
            "employee_count": company.employee_count,
            "status": company.status
        }
    else:
        # Return default structure if no company found
        return {
            "id": 0,
            "name": "No Company",
            "code": "NONE",
            "employee_id_prefix": None,
            "registration_number": "",
            "employee_count": 0,
            "status": "Inactive"
        }

# ---------------------- LOGIN ---------------------- #
@auth_bp.post('/login', responses={"200": LoginResponseSchema, "400": ErrorResponse, "401": ErrorResponse})
def login(body: LoginSchema):
    """User login - returns JWT tokens
    Authenticates user credentials and returns access and refresh tokens.
    """
    try:
        email = body.email
        password = body.password

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({"status": 401, "isError": True, "message": "Invalid credentials"}), 401

        if not user.is_active:
            return jsonify({"status": 401, "isError": True, "message": "Account is inactive"}), 401

        # Get user roles and company
        roles = [{"id": r.id, "name": r.name, "tier": r.tier} for r in user.roles]
        company_data = get_user_company_data(user)
        
        # Include company in JWT claims
        claims = {
            "roles": [r["name"] for r in roles],
            "company_id": company_data["id"],
            "company_name": company_data["name"],
            "company_code": company_data["code"]
        }

        access_token = create_access_token(identity=str(user.id), additional_claims=claims)
        refresh_token = create_refresh_token(identity=str(user.id))
        access_token_expires_at = datetime.utcnow() + timedelta(minutes=30)
        refresh_token_expires_at = datetime.utcnow() + timedelta(days=7)

        return jsonify({
            "success": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "access_token_expires_at": access_token_expires_at.isoformat(),
            "refresh_token_expires_at": refresh_token_expires_at.isoformat(),
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "roles": roles,
                "company": company_data
            }
        }), 200

    except Exception as e:
        return jsonify({"status": 500, "isError": True, "message": f"Login error: {str(e)}"}), 500

# ---------------------- REFRESH TOKEN ---------------------- #
@auth_bp.post(
    '/refresh',
    tags=[auth_tag],
    responses={"200": RefreshTokenResponseSchema, "400": ErrorResponse, "403": ErrorResponse, "422": ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required(refresh=True)
def refresh_token():
    """Refresh access and refresh tokens using a valid refresh token."""
    try:
        current_user_id = get_jwt_identity()
        old_jti = get_jwt().get("jti")
        if not old_jti:
            return jsonify({"status": 400, "isError": True, "message": "Invalid refresh token: No JTI found"}), 400
        
        # Query the User model to get user details
        user = User.query.filter_by(id=int(current_user_id)).first()
        if not user or not user.is_active:
            return jsonify({"status": 403, "isError": True, "message": "User not found or inactive"}), 403

        # Blacklist the old refresh token
        db.session.add(TokenBlacklist(token=old_jti))
        
        # Get user roles and company
        roles = [{"id": r.id, "name": r.name, "tier": r.tier} for r in user.roles]
        company_data = get_user_company_data(user)

        claims = {
            "roles": [r["name"] for r in roles],
            "company_id": company_data["id"],
            "company_name": company_data["name"],
            "company_code": company_data["code"]
        }

        # Create new access and refresh tokens
        access_token = create_access_token(identity=str(user.id), additional_claims=claims)
        refresh_token = create_refresh_token(identity=str(user.id))
        access_token_expires_at = datetime.utcnow() + timedelta(minutes=30)
        refresh_token_expires_at = datetime.utcnow() + timedelta(days=7)

        # Commit the blacklist entry
        db.session.commit()

        return jsonify({
            "success": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "access_token_expires_at": access_token_expires_at.isoformat(),
            "refresh_token_expires_at": refresh_token_expires_at.isoformat(),
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "roles": roles,
                "company": company_data
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": 400, "isError": True, "message": f"Error refreshing token: {str(e)}"}), 400

# ---------------------- LOGOUT ---------------------- #
@auth_bp.post('/logout', responses={"200": LogoutResponseSchema, "400": ErrorResponse, "422": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def logout():
    """Invalidate the JWT token
    Adds the current access or refresh token to a blacklist to prevent further use.
    """
    try:
        jti = get_jwt().get("jti")
        if not jti:
            return jsonify({"status": 400, "isError": True, "message": "Invalid token: No JTI found"}), 400

        # Add token to blacklist
        db.session.add(TokenBlacklist(token=jti))
        db.session.commit()
        return jsonify({"message": "Successfully logged out"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": 400, "isError": True, "message": f"Error during logout: {str(e)}"}), 400

# ---------------------- RESET PASSWORD ---------------------- #
@auth_bp.post('/reset-password', responses={"200": ResetPasswordResponseSchema, "400": ErrorResponse})
def reset_password(body: ResetPasswordSchema):
    """Password reset request - sends a token (demo version)
    Initiates a password reset process by generating a reset token.
    In a production environment, this token would be sent via email.
    """
    email = body.email

    user = User.query.filter_by(email=email).first()
    if not user:
        # Return generic message for security
        return jsonify({"message": "If this email exists, a reset link will be sent"}), 200

    reset_token_obj = PasswordResetToken.create_token(user.id)
    db.session.add(reset_token_obj)
    db.session.commit()

    return jsonify({
        "message": "Password reset token created",
        "reset_token": reset_token_obj.token,
        "expires_at": reset_token_obj.expires_at.isoformat()
    }), 200

# ---------------------- GET ROLES ---------------------- #
@auth_bp.get('/roles', responses={"200": RolesListSchema}, security=[{"jwt": []}])
@jwt_required()
def get_roles():
    """List all system roles
    Returns a list of all available roles in the system.
    """
    roles = Role.query.all()
    return jsonify({
        "roles": [{
            "id": r.id,
            "name": r.name,
            "tier": r.tier,
            "description": r.description
        } for r in roles]
    }), 200

# ---------------------- GET PERMISSIONS ---------------------- #
@auth_bp.get('/permissions', responses={"200": PermissionsListSchema}, security=[{"jwt": []}])
@jwt_required()
def get_permissions():
    """List all permissions grouped by role
    Returns a structured list of all permissions organized by role.
    """
    roles = Role.query.all()
    result = []
    for r in roles:
        perms = [{
            "id": p.id,
            "name": p.name,
            "description": p.description
        } for p in r.permissions]
        result.append({
            "role": {"id": r.id, "name": r.name, "tier": r.tier},
            "permissions": perms
        })
    return jsonify({"permissions": result}), 200

# ---------------------- CREATE USER ---------------------- #
@auth_bp.post('/users', responses={"201": CreateUserResponseSchema, "400": ErrorResponse, "409": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def create_user(body: CreateUserSchema):
    """Create a new user
    Creates a new user account with the provided information.
    """
    email = body.email
    password = body.password
    name = body.name
    role_name = body.role
    company_id = body.company_id

    if User.query.filter_by(email=email).first():
        return jsonify({"status": 409, "isError": True, "message": "Email already registered"}), 409

    role = Role.query.filter_by(name=role_name).first()
    if not role:
        return jsonify({"status": 400, "isError": True, "message": f"Role '{role_name}' does not exist"}), 400

    company = Company.query.filter_by(id=company_id).first()
    if not company:
        return jsonify({"status": 400, "isError": True, "message": f"Company with ID {company_id} does not exist"}), 400

    new_user = User(
        email=email,
        name=name,
        is_active=True
    )
    new_user.set_password(password)
    new_user.roles.append(role)

    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        "message": "User created successfully",
        "user": {
            "id": str(new_user.id),
            "email": new_user.email,
            "name": new_user.name,
            "role": role_name,
            "company": {
                "id": company.id,
                "name": company.name,
                "code": company.code,
                "registration_number": company.registration_number,
                "employee_count": company.employee_count,
                "status": company.status
            }
        }
    }), 201

# ---------------------- GET PROFILE ---------------------- #
@auth_bp.get('/profile', responses={"200": UserResponseSchema, "401": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_profile():
    """Get current user profile"""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.filter_by(id=int(current_user_id)).first()
        
        if not user:
            return jsonify({"status": 404, "isError": True, "message": "User not found"}), 404

        roles = [role.name for role in user.roles]
        primary_role = roles[0] if roles else None

        # Get user's company data
        company_data = get_user_company_data(user)

        return jsonify({
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": primary_role,
            "roles": roles,
            "company": company_data,
            "is_active": user.is_active
        }), 200

    except Exception as e:
        return jsonify({"status": 500, "isError": True, "message": f"Error retrieving profile: {str(e)}"}), 500

# ---------------------- GET COMPANIES ---------------------- #
@auth_bp.get('/companies', responses={"200": None}, security=[{"jwt": []}])
@jwt_required()
def get_companies():
    """Get all active companies"""
    try:
        companies = Company.query.filter_by(status='Active').all()
        companies_list = [{
            "id": company.id,
            "name": company.name,
            "code": company.code,
            "registration_number": company.registration_number,
            "employee_count": company.employee_count,
            "status": company.status
        } for company in companies]
        
        return jsonify({
            "companies": companies_list
        }), 200

    except Exception as e:
        return jsonify({"status": 500, "isError": True, "message": f"Error retrieving companies: {str(e)}"}), 500

# ---------------------- INITIAL SETUP ---------------------- #
@auth_bp.post('/setup', responses={"200": None})
def initial_setup():
    """Initial setup - create Napoli company and super admin role"""
    try:
        # Get Napoli company (assume it exists from shell script)
        napoli_company = get_napoli_company()

        # Create super admin role if it doesn't exist
        super_admin_role = Role.query.filter_by(name="super_admin").first()
        if not super_admin_role:
            super_admin_role = Role(
                name="super_admin",
                tier=1,
                description="Super Administrator with full system access"
            )
            db.session.add(super_admin_role)
            db.session.flush()

        # Create admin role if it doesn't exist
        admin_role = Role.query.filter_by(name="admin").first()
        if not admin_role:
            admin_role = Role(
                name="admin",
                tier=2,
                description="Administrator with company-level access"
            )
            db.session.add(admin_role)

        db.session.commit()
        
        return jsonify({
            "message": "Initial setup completed successfully",
            "company": napoli_company.to_dict() if napoli_company else {"name": "No Company Found"},
            "roles": {
                "super_admin": super_admin_role.to_dict(),
                "admin": admin_role.to_dict()
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": 500, "isError": True, "message": f"Error during setup: {str(e)}"}), 500

# ---------------------- GET NAPOLI COMPANY ---------------------- #
@auth_bp.get('/napoli-company', responses={"200": CompanySchema})
def get_napoli_company_endpoint():
    """Get Napoli company details"""
    try:
        napoli_company = get_napoli_company()
        if napoli_company:
            return jsonify(napoli_company.to_dict()), 200
        else:
            return jsonify({"status": 404, "isError": True, "message": "Napoli company not found"}), 404
    except Exception as e:
        return jsonify({"status": 500, "isError": True, "message": f"Error retrieving Napoli company: {str(e)}"}), 500