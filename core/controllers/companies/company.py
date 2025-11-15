from flask_openapi3 import APIBlueprint, Tag
from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, desc, and_, or_
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from ...addons.extensions import db
from ...models import Company, Employee
from ...models.users import User

company_tag = Tag(name="Companies", description="Company management operations")
company_bp = APIBlueprint(
    'company', __name__, url_prefix='/api/companies', abp_tags=[company_tag]
)

# ---------------------- SCHEMAS ---------------------- #
class CompanyResponseSchema(BaseModel):
    id: int = Field(..., description="Company ID")
    name: str = Field(..., description="Company name")
    code: str = Field(..., description="Company code")
    employee_id_prefix: Optional[str] = Field(None, description="Employee ID prefix")
    registration_number: str = Field(..., description="Company registration number")
    employee_count: int = Field(..., description="Number of employees")
    status: str = Field(..., description="Company status")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")

class CompanyCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, description="Company name")
    code: str = Field(..., min_length=1, description="Company code")
    employee_id_prefix: Optional[str] = Field(None, max_length=10, description="Employee ID prefix")
    registration_number: str = Field(..., min_length=1, description="Company registration number")
    employee_count: int = Field(0, ge=0, description="Number of employees")
    status: str = Field("Active", description="Company status")

class CompanyUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, min_length=1, description="Company name")
    code: Optional[str] = Field(None, min_length=1, description="Company code")
    employee_id_prefix: Optional[str] = Field(None, max_length=10, description="Employee ID prefix")
    registration_number: Optional[str] = Field(None, min_length=1, description="Company registration number")
    employee_count: Optional[int] = Field(None, ge=0, description="Number of employees")
    status: Optional[str] = Field(None, description="Company status")
    force_update: Optional[bool] = Field(False, description="Force update")

class EmployeeResponseSchema(BaseModel):
    id: int = Field(..., description="Employee ID")
    first_name: str = Field(..., description="Employee first name")
    last_name: str = Field(..., description="Employee last name")
    email: str = Field(..., description="Employee email")
    phone: Optional[str] = Field(None, description="Employee phone number")
    national_id: Optional[str] = Field(None, description="Employee national ID")
    employment_status: str = Field(..., description="Employment status")
    start_date: str = Field(..., description="Employment start date")
    end_date: Optional[str] = Field(None, description="Employment end date")
    has_live_disciplinary: bool = Field(..., description="Has live disciplinary")
    company_id: int = Field(..., description="Company ID")

class CompanyStatsSchema(BaseModel):
    total_headcount: int = Field(..., description="Total active employees")
    active_employees: int = Field(..., description="Active employees count")
    probation_employees: int = Field(..., description="Probation employees count")
    current_period_leavers: int = Field(..., description="Leavers in current period")
    last_period_leavers: int = Field(..., description="Leavers in last period")
    leavers_trend: int = Field(..., description="Leavers trend (current - last)")
    average_tenure_months: float = Field(..., description="Average tenure in months")
    live_disciplinaries: int = Field(..., description="Employees with live disciplinaries")

class CompanyListResponseSchema(BaseModel):
    companies: List[CompanyResponseSchema] = Field(..., description="List of companies")
    pagination: Dict[str, Any] = Field(..., description="Pagination information")

class EmployeesListResponseSchema(BaseModel):
    employees: List[EmployeeResponseSchema] = Field(..., description="List of employees")
    company: Dict[str, Any] = Field(..., description="Company information")

class CompanyStatsResponseSchema(BaseModel):
    stats: CompanyStatsSchema = Field(..., description="Company statistics")

class ErrorResponse(BaseModel):
    status: int = Field(..., description="HTTP status code")
    isError: bool = Field(True, description="Indicates if the response is an error")
    message: str = Field(..., description="Error message")

class SuccessResponse(BaseModel):
    message: str = Field(..., description="Success message")
    status: int = Field(200, description="HTTP status code")
    isError: bool = Field(False, description="Indicates if the response is an error")

# Path parameter schemas
class CompanyIdPath(BaseModel):
    company_id: int = Field(..., description="Company ID", gt=0)

# ---------------------- GET COMPANIES ---------------------- #
@company_bp.get('/', responses={"200": CompanyListResponseSchema, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_companies():
    """Get paginated list of companies with filtering and sorting
    Returns companies with optional filtering by status and search.
    """
    try:
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)  # Limit page size

        # Base query
        query = Company.query

        # Filtering
        status = request.args.get('status')
        if status:
            query = query.filter(Company.status == status)

        # Search filter
        search = request.args.get('search')
        if search:
            query = query.filter(
                or_(
                    Company.name.ilike(f'%{search}%'),
                    Company.code.ilike(f'%{search}%'),
                    Company.registration_number.ilike(f'%{search}%'),
                    Company.employee_id_prefix.ilike(f'%{search}%')
                )
            )

        # Sorting
        sort_by = request.args.get('sort_by', 'name')
        sort_order = request.args.get('sort_order', 'asc')
        
        if sort_order == 'desc':
            query = query.order_by(desc(sort_by))
        else:
            query = query.order_by(sort_by)

        # Execute paginated query
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )

        companies = pagination.items

        return jsonify({
            "companies": [company.to_dict() for company in companies],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev
            }
        }), 200

    except Exception as e:
        return jsonify({
            "status": 500,
            "isError": True,
            "message": f"Error fetching companies: {str(e)}"
        }), 500

# ---------------------- CREATE COMPANY ---------------------- #
@company_bp.post('/', responses={"201": CompanyResponseSchema, "400": ErrorResponse, "409": ErrorResponse, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def create_company(body: CompanyCreateSchema):
    """Create a new company
    Creates a new company with the provided information.
    """
    try:
        current_user_id = get_jwt_identity()

        # Check if company code already exists
        existing_company_by_code = Company.query.filter_by(code=body.code).first()
        if existing_company_by_code:
            return jsonify({
                'status': 409,
                'isError': True,
                'message': 'A company with this code already exists'
            }), 409
        
        # Check if registration number already exists
        existing_company_by_reg = Company.query.filter_by(registration_number=body.registration_number).first()
        if existing_company_by_reg:
            return jsonify({
                'status': 409,
                'isError': True,
                'message': 'A company with this registration number already exists'
            }), 409
        
        # Create company
        company = Company(
            name=body.name,
            code=body.code.upper(),
            employee_id_prefix=body.employee_id_prefix.upper() if body.employee_id_prefix else None,
            registration_number=body.registration_number,
            employee_count=body.employee_count,
            status=body.status
        )
        
        db.session.add(company)
        db.session.commit()
        
        return jsonify({
            "company": company.to_dict(),
            "message": "Company created successfully"
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'isError': True,
            'message': f'Error creating company: {str(e)}'
        }), 500

# ---------------------- GET SINGLE COMPANY ---------------------- #
@company_bp.get('/<int:company_id>', responses={"200": CompanyResponseSchema, "404": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_company(path: CompanyIdPath):
    """Get a specific company by ID
    Returns detailed information about a single company.
    """
    try:
        company = Company.query.get_or_404(path.company_id)
        
        return jsonify({
            "company": company.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 404,
            'isError': True,
            'message': f'Company not found: {str(e)}'
        }), 404

# ---------------------- UPDATE COMPANY ---------------------- #
@company_bp.put('/<int:company_id>', responses={"200": CompanyResponseSchema, "400": ErrorResponse, "404": ErrorResponse, "409": ErrorResponse, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def update_company(path: CompanyIdPath, body: CompanyUpdateSchema):
    """Update a specific company
    Updates company information with validation for unique fields.
    """
    try:
        company = Company.query.get_or_404(path.company_id)
        
        # Use the validated body parameter
        if body.name is not None:
            company.name = body.name
            
        if body.code is not None:
            # Check if company code is unique
            existing_by_code = Company.query.filter(
                Company.code == body.code.upper(),
                Company.id != path.company_id
            ).first()
            if existing_by_code:
                return jsonify({
                    'status': 409,
                    'isError': True,
                    'message': 'Another company with this code already exists'
                }), 409
            company.code = body.code.upper()
            
        if body.employee_id_prefix is not None:
            company.employee_id_prefix = body.employee_id_prefix.upper() if body.employee_id_prefix else None
            
        if body.registration_number is not None:
            # Check if registration number is unique
            existing_by_reg = Company.query.filter(
                Company.registration_number == body.registration_number,
                Company.id != path.company_id
            ).first()
            if existing_by_reg:
                return jsonify({
                    'status': 409,
                    'isError': True,
                    'message': 'Another company with this registration number already exists'
                }), 409
            company.registration_number = body.registration_number
            
        if body.employee_count is not None:
            company.employee_count = body.employee_count
            
        if body.status is not None:
            company.status = body.status
        
        company.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "company": company.to_dict(),
            "message": "Company updated successfully"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'isError': True,
            'message': f'Error updating company: {str(e)}'
        }), 500

# ---------------------- DELETE COMPANY ---------------------- #
@company_bp.delete('/<int:company_id>', responses={"200": SuccessResponse, "404": ErrorResponse, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def delete_company(path: CompanyIdPath):
    """Delete a specific company
    Permanently removes a company from the system after validation.
    """
    try:
        company = Company.query.get_or_404(path.company_id)
        
        # Check if company has employees
        employee_count = Employee.query.filter_by(company_id=path.company_id).count()
        if employee_count > 0:
            return jsonify({
                'status': 400,
                'isError': True,
                'message': 'Cannot delete company with existing employees'
            }), 400
        
        db.session.delete(company)
        db.session.commit()
        
        return jsonify({
            "message": "Company deleted successfully",
            "status": 200,
            "isError": False
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'isError': True,
            'message': f'Error deleting company: {str(e)}'
        }), 500

# ---------------------- GET COMPANY EMPLOYEES ---------------------- #
@company_bp.get('/<int:company_id>/employees', responses={"200": EmployeesListResponseSchema, "404": ErrorResponse, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_company_employees(path: CompanyIdPath):
    """Get all employees for a specific company
    Returns all employees associated with a specific company with optional filtering.
    """
    try:
        company = Company.query.get_or_404(path.company_id)
        
        # Get query parameters
        status = request.args.get('status', 'active')
        search = request.args.get('search', '')
        
        # Build query
        query = Employee.query.filter_by(company_id=path.company_id)
        
        # Status filter
        if status == 'active':
            query = query.filter(Employee.employment_status.in_(['Active', 'Probation']))
        elif status in ['Active', 'Probation', 'Inactive', 'Expired Contract']:
            query = query.filter_by(employment_status=status)
        
        # Search filter
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Employee.first_name.ilike(search_term),
                    Employee.last_name.ilike(search_term),
                    Employee.email.ilike(search_term),
                    Employee.phone.ilike(search_term),
                    Employee.national_id.ilike(search_term)
                )
            )
        
        employees = query.all()
        
        return jsonify({
            "employees": [employee.to_dict() for employee in employees],
            "company": {
                "id": company.id,
                "name": company.name,
                "code": company.code,
                "employee_id_prefix": company.employee_id_prefix
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 500,
            'isError': True,
            'message': f'Error fetching company employees: {str(e)}'
        }), 500

# ---------------------- GET COMPANY STATISTICS ---------------------- #
@company_bp.get('/<int:company_id>/stats', responses={"200": CompanyStatsResponseSchema, "404": ErrorResponse, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_company_stats(path: CompanyIdPath):
    """Get company statistics and analytics
    Returns comprehensive company statistics including headcount, turnover, and tenure analysis.
    """
    try:
        company = Company.query.get_or_404(path.company_id)
        
        # Calculate statistics
        total_headcount = Employee.query.filter_by(company_id=path.company_id).filter(
            Employee.employment_status.in_(['Active', 'Probation'])
        ).count()
        
        active_employees = Employee.query.filter_by(
            company_id=path.company_id, 
            employment_status='Active'
        ).count()
        
        probation_employees = Employee.query.filter_by(
            company_id=path.company_id, 
            employment_status='Probation'
        ).count()
        
        # Calculate leavers (this period vs last period)
        current_period_start = datetime.now().replace(day=1)
        last_period_start = (current_period_start - timedelta(days=1)).replace(day=1)
        
        current_leavers = Employee.query.filter_by(
            company_id=path.company_id
        ).filter(
            Employee.employment_status == 'Inactive',
            Employee.end_date >= current_period_start
        ).count()
        
        last_leavers = Employee.query.filter_by(
            company_id=path.company_id
        ).filter(
            Employee.employment_status == 'Inactive',
            Employee.end_date >= last_period_start,
            Employee.end_date < current_period_start
        ).count()
        
        # Calculate average tenure
        active_employees_with_tenure = Employee.query.filter_by(
            company_id=path.company_id,
            employment_status='Active'
        ).with_entities(
            func.datediff(func.now(), Employee.start_date).label('tenure_days')
        ).all()
        
        avg_tenure_days = sum(emp.tenure_days for emp in active_employees_with_tenure) / len(active_employees_with_tenure) if active_employees_with_tenure else 0
        avg_tenure_months = round(avg_tenure_days / 30.44, 1)  # Average days in month
        
        live_disciplinaries = Employee.query.filter_by(
            company_id=path.company_id,
            has_live_disciplinary=True
        ).count()
        
        stats = {
            'total_headcount': total_headcount,
            'active_employees': active_employees,
            'probation_employees': probation_employees,
            'current_period_leavers': current_leavers,
            'last_period_leavers': last_leavers,
            'leavers_trend': current_leavers - last_leavers,
            'average_tenure_months': avg_tenure_months,
            'live_disciplinaries': live_disciplinaries
        }
        
        return jsonify({
            "stats": stats
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 500,
            'isError': True,
            'message': f'Error fetching company statistics: {str(e)}'
        }), 500