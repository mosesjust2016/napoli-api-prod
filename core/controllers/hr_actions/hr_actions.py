# controllers/hr_actions/hr_actions.py
from flask import Blueprint, request, jsonify
from flask_openapi3 import APIBlueprint, Tag
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, desc, and_, or_
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict, Any, List
import uuid
import json
import os

# Fixed imports
from core.addons.extensions import db
from core.models.employees import Employee
from core.models.companies import Company
from core.models.hr_actions import HRAction
from core.models.employee_documents import EmployeeDocument
from core.models.disciplinary_records import DisciplinaryRecord
from core.models.leave_records import LeaveRecord
from core.models.users import User
from core.models.auditLogModel import AuditLog

hr_actions_bp = APIBlueprint('hr_actions', __name__, url_prefix='/api/hr-actions')
hr_actions_tag = Tag(name="HR Actions", description="HR actions and workflow operations")

# ---------------------- SCHEMAS ---------------------- #
class UpdateProfileSchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    update_type: str = Field(..., description="Type of update: personal, contact, emergency, documents")
    effective_date: str = Field(..., description="Effective date for the change")
    changes: Dict[str, Any] = Field(..., description="Key-value pairs of changes")
    comments: Optional[str] = Field(None, description="Comments for the update")
    document_urls: Optional[List[str]] = Field(None, description="URLs of supporting documents")

class ChangeStatusSchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    new_status: str = Field(..., description="New employment status")
    effective_date: str = Field(..., description="Effective date for status change")
    reason: str = Field(..., description="Reason for status change")
    notice_period_days: Optional[int] = Field(None, description="Notice period in days")
    final_work_date: Optional[str] = Field(None, description="Final work date if leaving")
    comments: Optional[str] = Field(None, description="Additional comments")
    document_urls: Optional[List[str]] = Field(None, description="Supporting documents")

class UpdateContractSchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    effective_date: str = Field(..., description="Effective date for contract changes")
    changes: Dict[str, Any] = Field(..., description="Contract changes")
    comments: Optional[str] = Field(None, description="Comments for the update")
    document_urls: Optional[List[str]] = Field(None, description="Updated contract documents")

class ChangeSalarySchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    new_salary: float = Field(..., gt=0, description="New salary amount")
    effective_date: str = Field(..., description="Effective date for salary change")
    reason: str = Field(..., description="Reason for salary change")
    salary_components: Optional[Dict[str, float]] = Field(None, description="Salary breakdown")
    requires_director_approval: bool = Field(False, description="Whether director approval is required")
    approval_status: str = Field("pending", description="Approval status")
    comments: Optional[str] = Field(None, description="Additional comments")

class RecordLeaveSchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    leave_type: str = Field(..., description="Type of leave: annual, sick, maternity, etc.")
    start_date: str = Field(..., description="Leave start date")
    end_date: str = Field(..., description="Leave end date")
    reason: str = Field(..., description="Reason for leave")
    emergency_contact: Optional[str] = Field(None, description="Emergency contact during leave")
    doctor_note_url: Optional[str] = Field(None, description="URL to doctor's note if applicable")
    supporting_docs: Optional[List[str]] = Field(None, description="Supporting documents")
    comments: Optional[str] = Field(None, description="Additional comments")

class CommuteLeaveSchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    leave_days: int = Field(..., gt=0, description="Number of leave days to commute")
    commute_value: float = Field(..., gt=0, description="Monetary value per day")
    total_value: float = Field(..., gt=0, description="Total commute value")
    effective_date: str = Field(..., description="Effective date for commutation")
    payment_date: Optional[str] = Field(None, description="Expected payment date")
    comments: Optional[str] = Field(None, description="Additional comments")

class UnauthorizedAbsenceSchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    absence_dates: List[str] = Field(..., description="Dates of unauthorized absence")
    reason: Optional[str] = Field(None, description="Reason for absence if provided")
    deduction_type: str = Field(..., description="Type of deduction: salary, leave, both")
    deduction_amount: Optional[float] = Field(None, description="Deduction amount if applicable")
    leave_days_deducted: Optional[int] = Field(None, description="Leave days deducted if applicable")
    comments: Optional[str] = Field(None, description="Additional comments")
    supporting_docs: Optional[List[str]] = Field(None, description="Supporting documents")

class DisciplinaryActionSchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    action_type: str = Field(..., description="Type of disciplinary action")
    reason: str = Field(..., description="Reason for disciplinary action")
    issued_date: str = Field(..., description="Date action was issued")
    valid_until: str = Field(..., description="Date action is valid until")
    severity: str = Field(..., description="Severity level: low, medium, high")
    consequences: List[str] = Field(..., description="Consequences of the action")
    requires_acknowledgement: bool = Field(True, description="Whether employee acknowledgement is required")
    document_urls: Optional[List[str]] = Field(None, description="Supporting documents")
    comments: Optional[str] = Field(None, description="Additional comments")

class ExitProcessSchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    exit_type: str = Field(..., description="Type of exit: resignation, termination, retirement")
    exit_date: str = Field(..., description="Last working date")
    reason: str = Field(..., description="Reason for exit")
    notice_served: Optional[bool] = Field(None, description="Whether notice period was served")
    final_settlement: Dict[str, Any] = Field(..., description="Final settlement details")
    asset_return: List[Dict[str, Any]] = Field(..., description="Assets to be returned")
    exit_interview: Optional[Dict[str, Any]] = Field(None, description="Exit interview details")
    comments: Optional[str] = Field(None, description="Additional comments")

# ---------------------- 1. UPDATE EMPLOYEE PROFILE ---------------------- #
@hr_actions_bp.post('/update-profile', tags=[hr_actions_tag])
@jwt_required()
def update_employee_profile(body: UpdateProfileSchema):
    """Update employee personal, contact, emergency contact, or document details"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate employee exists
        employee = Employee.query.get(body.employee_id)
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Parse effective date
        effective_date = datetime.strptime(body.effective_date, '%Y-%m-%d').date()
        
        # Apply changes based on update type
        changes_made = []
        allowed_fields = []
        
        if body.update_type == 'personal':
            allowed_fields = ['first_name', 'last_name', 'date_of_birth', 'gender', 'marital_status', 
                            'national_id', 'work_permit_number', 'tax_id', 'pension_number']
        elif body.update_type == 'contact':
            allowed_fields = ['email', 'personal_email', 'phone', 'address', 'work_location']
        elif body.update_type == 'emergency':
            allowed_fields = ['emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship']
        elif body.update_type == 'documents':
            # Handle document updates separately
            pass
        else:
            return jsonify({
                'status': 400,
                'error': 'Invalid update type',
                'message': 'Update type must be: personal, contact, emergency, or documents'
            }), 400
        
        # Apply changes to employee record
        for field, new_value in body.changes.items():
            if field in allowed_fields and hasattr(employee, field):
                old_value = getattr(employee, field)
                setattr(employee, field, new_value)
                changes_made.append({
                    'field': field,
                    'old_value': old_value,
                    'new_value': new_value
                })
        
        # Create HR action record
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            action_type='profile_update',
            action_date=datetime.now(),
            effective_date=effective_date,
            performed_by=current_user_id,
            details={
                'update_type': body.update_type,
                'changes': changes_made,
                'document_urls': body.document_urls or []
            },
            summary=f"Updated {body.update_type} information",
            status='completed',
            comments=body.comments
        )
        
        db.session.add(hr_action)
        db.session.commit()
        
        return jsonify({
            'status': 200,
            'data': {
                'hr_action': hr_action.to_dict(),
                'changes_applied': changes_made,
                'employee_updated': employee.to_dict()
            },
            'message': f'Employee {body.update_type} information updated successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to update employee profile'
        }), 500

# ---------------------- 2. CHANGE EMPLOYMENT STATUS ---------------------- #
@hr_actions_bp.post('/change-status', tags=[hr_actions_tag])
@jwt_required()
def change_employment_status(body: ChangeStatusSchema):
    """Change employee employment status with automatic notice period calculation"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate employee exists
        employee = Employee.query.get(body.employee_id)
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Parse dates
        effective_date = datetime.strptime(body.effective_date, '%Y-%m-%d').date()
        final_work_date = datetime.strptime(body.final_work_date, '%Y-%m-%d').date() if body.final_work_date else None
        
        # Calculate notice period if not provided
        notice_period_days = body.notice_period_days
        if not notice_period_days:
            if body.new_status in ['Resignation', 'Termination']:
                # Default notice periods based on employment type
                if employee.employment_type == 'Probation':
                    notice_period_days = 1  # 24 hours for probation
                else:
                    notice_period_days = 30  # 1 month for permanent staff
        
        # Update employee status
        previous_status = employee.employment_status
        employee.employment_status = body.new_status
        
        # Set end date for termination/resignation
        if body.new_status in ['Resignation', 'Termination', 'Inactive']:
            employee.end_date = final_work_date or effective_date
        
        # Create HR action record
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            action_type='status_change',
            action_date=datetime.now(),
            effective_date=effective_date,
            performed_by=current_user_id,
            details={
                'previous_status': previous_status,
                'new_status': body.new_status,
                'reason': body.reason,
                'notice_period_days': notice_period_days,
                'final_work_date': final_work_date.isoformat() if final_work_date else None,
                'document_urls': body.document_urls or []
            },
            summary=f"Employment status changed from {previous_status} to {body.new_status}",
            status='completed',
            comments=body.comments
        )
        
        db.session.add(hr_action)
        db.session.commit()
        
        return jsonify({
            'status': 200,
            'data': {
                'hr_action': hr_action.to_dict(),
                'previous_status': previous_status,
                'new_status': body.new_status,
                'notice_period_days': notice_period_days,
                'final_work_date': final_work_date
            },
            'message': f'Employment status changed successfully from {previous_status} to {body.new_status}'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to change employment status'
        }), 500

# ---------------------- 3. UPDATE CONTRACT ---------------------- #
@hr_actions_bp.post('/update-contract', tags=[hr_actions_tag])
@jwt_required()
def update_employee_contract(body: UpdateContractSchema):
    """Update employee contract details (job title, department, company, supervisor, location)"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate employee exists
        employee = Employee.query.get(body.employee_id)
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Parse effective date
        effective_date = datetime.strptime(body.effective_date, '%Y-%m-%d').date()
        
        # Track changes
        changes_made = []
        allowed_fields = ['position', 'department', 'company_id', 'supervisor_id', 'work_location', 
                         'employment_type', 'contract_end_date', 'probation_end_date']
        
        # Apply contract changes
        for field, new_value in body.changes.items():
            if field in allowed_fields and hasattr(employee, field):
                old_value = getattr(employee, field)
                
                # Special handling for company_id - validate company exists
                if field == 'company_id':
                    new_company = Company.query.get(new_value)
                    if not new_company:
                        return jsonify({
                            'status': 404,
                            'error': 'Company not found',
                            'message': 'The specified company does not exist'
                        }), 404
                
                # Special handling for supervisor_id - validate employee exists
                if field == 'supervisor_id' and new_value:
                    supervisor = Employee.query.get(new_value)
                    if not supervisor:
                        return jsonify({
                            'status': 404,
                            'error': 'Supervisor not found',
                            'message': 'The specified supervisor does not exist'
                        }), 404
                
                setattr(employee, field, new_value)
                changes_made.append({
                    'field': field,
                    'old_value': old_value,
                    'new_value': new_value
                })
        
        # Create HR action record
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            action_type='contract_update',
            action_date=datetime.now(),
            effective_date=effective_date,
            performed_by=current_user_id,
            details={
                'changes': changes_made,
                'document_urls': body.document_urls or []
            },
            summary=f"Contract updated with {len(changes_made)} changes",
            status='completed',
            comments=body.comments
        )
        
        db.session.add(hr_action)
        db.session.commit()
        
        return jsonify({
            'status': 200,
            'data': {
                'hr_action': hr_action.to_dict(),
                'changes_applied': changes_made,
                'employee_updated': employee.to_dict()
            },
            'message': 'Employee contract updated successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to update employee contract'
        }), 500

# ---------------------- 4. CHANGE SALARY ---------------------- #
@hr_actions_bp.post('/change-salary', tags=[hr_actions_tag])
@jwt_required()
def change_employee_salary(body: ChangeSalarySchema):
    """Adjust employee salary with director approval workflow"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate employee exists
        employee = Employee.query.get(body.employee_id)
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Parse effective date
        effective_date = datetime.strptime(body.effective_date, '%Y-%m-%d').date()
        
        # Track salary change
        previous_salary = employee.salary
        salary_change = body.new_salary - previous_salary
        change_percentage = (salary_change / previous_salary * 100) if previous_salary > 0 else 100
        
        # Determine if director approval is required
        requires_approval = body.requires_director_approval or abs(change_percentage) > 10  # Auto-require for changes > 10%
        
        # Update employee salary if no approval required or already approved
        if not requires_approval or body.approval_status == 'approved':
            employee.salary = body.new_salary
            status = 'completed'
        else:
            status = 'pending_approval'
        
        # Create HR action record
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            action_type='salary_change',
            action_date=datetime.now(),
            effective_date=effective_date,
            performed_by=current_user_id,
            details={
                'previous_salary': previous_salary,
                'new_salary': body.new_salary,
                'salary_change': salary_change,
                'change_percentage': round(change_percentage, 2),
                'reason': body.reason,
                'salary_components': body.salary_components or {},
                'requires_director_approval': requires_approval,
                'approval_status': body.approval_status,
                'effective_date': effective_date.isoformat()
            },
            summary=f"Salary change: {previous_salary} → {body.new_salary} ({round(change_percentage, 2)}%)",
            status=status,
            requires_approval=requires_approval,
            comments=body.comments
        )
        
        db.session.add(hr_action)
        db.session.commit()
        
        response_data = {
            'hr_action': hr_action.to_dict(),
            'salary_change': {
                'previous': previous_salary,
                'new': body.new_salary,
                'change': salary_change,
                'percentage': round(change_percentage, 2)
            },
            'approval_required': requires_approval
        }
        
        if requires_approval and body.approval_status != 'approved':
            response_data['message'] = 'Salary change submitted for director approval'
        else:
            response_data['message'] = 'Salary changed successfully'
        
        return jsonify({
            'status': 200,
            'data': response_data,
            'message': response_data['message']
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to change employee salary'
        }), 500

# ---------------------- 5. RECORD LEAVE ---------------------- #
@hr_actions_bp.post('/leave/record', tags=[hr_actions_tag])
@jwt_required()
def record_employee_leave(body: RecordLeaveSchema):
    """Record all types of employee leave (annual, sick, maternity, etc.)"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate employee exists
        employee = Employee.query.get(body.employee_id)
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Parse dates
        start_date = datetime.strptime(body.start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(body.end_date, '%Y-%m-%d').date()
        
        # Calculate leave duration
        leave_days = (end_date - start_date).days + 1  # Inclusive of both dates
        
        # Validate leave dates
        if end_date < start_date:
            return jsonify({
                'status': 400,
                'error': 'Invalid date range',
                'message': 'End date must be after start date'
            }), 400
        
        # Create leave record
        leave_record = LeaveRecord(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            leave_type=body.leave_type,
            start_date=start_date,
            end_date=end_date,
            days_count=leave_days,
            status='approved',
            approved_by=current_user_id,
            doctor_note_url=body.doctor_note_url,
            comments=body.comments
        )
        
        # Create HR action record
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            action_type=f'leave_{body.leave_type}',
            action_date=datetime.now(),
            effective_date=start_date,
            performed_by=current_user_id,
            details={
                'leave_type': body.leave_type,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days_count': leave_days,
                'reason': body.reason,
                'emergency_contact': body.emergency_contact,
                'supporting_docs': body.supporting_docs or []
            },
            summary=f"{body.leave_type.title()} leave recorded for {leave_days} days",
            status='completed',
            comments=body.comments
        )
        
        leave_record.hr_action_id = hr_action.id
        
        db.session.add(leave_record)
        db.session.add(hr_action)
        db.session.commit()
        
        return jsonify({
            'status': 200,
            'data': {
                'hr_action': hr_action.to_dict(),
                'leave_record': {
                    'id': leave_record.id,
                    'leave_type': leave_record.leave_type,
                    'start_date': leave_record.start_date.isoformat(),
                    'end_date': leave_record.end_date.isoformat(),
                    'days_count': leave_record.days_count,
                    'status': leave_record.status
                }
            },
            'message': f'{body.leave_type.title()} leave recorded successfully for {leave_days} days'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to record employee leave'
        }), 500

# ---------------------- 6. COMMUTE LEAVE ---------------------- #
@hr_actions_bp.post('/leave/commute', tags=[hr_actions_tag])
@jwt_required()
def commute_employee_leave(body: CommuteLeaveSchema):
    """Commute annual leave to cash payment"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate employee exists
        employee = Employee.query.get(body.employee_id)
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Parse dates
        effective_date = datetime.strptime(body.effective_date, '%Y-%m-%d').date()
        payment_date = datetime.strptime(body.payment_date, '%Y-%m-%d').date() if body.payment_date else None
        
        # Calculate daily rate based on salary
        daily_rate = employee.salary / 30 if employee.salary else 0  # Approximate daily rate
        calculated_value = body.leave_days * daily_rate
        
        # Validate commute value
        if abs(body.total_value - calculated_value) > (calculated_value * 0.1):  # Allow 10% variance
            return jsonify({
                'status': 400,
                'error': 'Invalid commute value',
                'message': f'Commute value should be approximately {calculated_value:.2f} based on salary'
            }), 400
        
        # Create leave record for commutation
        leave_record = LeaveRecord(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            leave_type='commuted',
            start_date=effective_date,
            end_date=effective_date,  # Same day for commutation
            days_count=body.leave_days,
            status='approved',
            approved_by=current_user_id,
            commute_value=body.commute_value,
            total_commute_value=body.total_value,
            comments=body.comments
        )
        
        # Create HR action record
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            action_type='leave_commute',
            action_date=datetime.now(),
            effective_date=effective_date,
            performed_by=current_user_id,
            details={
                'leave_days_commuted': body.leave_days,
                'daily_commute_value': body.commute_value,
                'total_commute_value': body.total_value,
                'calculated_daily_rate': daily_rate,
                'calculated_total_value': calculated_value,
                'payment_date': payment_date.isoformat() if payment_date else None,
                'payroll_timing': 'Next payroll run' if not payment_date else f'Scheduled for {payment_date.strftime("%Y-%m-%d")}'
            },
            summary=f"Committed {body.leave_days} leave days for ZMW {body.total_value:.2f}",
            status='completed',
            comments=body.comments
        )
        
        leave_record.hr_action_id = hr_action.id
        
        db.session.add(leave_record)
        db.session.add(hr_action)
        db.session.commit()
        
        return jsonify({
            'status': 200,
            'data': {
                'hr_action': hr_action.to_dict(),
                'commutation_details': {
                    'leave_days': body.leave_days,
                    'daily_value': body.commute_value,
                    'total_value': body.total_value,
                    'payment_timing': hr_action.details['payroll_timing']
                }
            },
            'message': f'Successfully commuted {body.leave_days} leave days for ZMW {body.total_value:.2f}'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to commute employee leave'
        }), 500

# ---------------------- 7. UNAUTHORIZED ABSENCE ---------------------- #
@hr_actions_bp.post('/absence/unauthorized', tags=[hr_actions_tag])
@jwt_required()
def record_unauthorized_absence(body: UnauthorizedAbsenceSchema):
    """Record unauthorized absence with automatic deductions"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate employee exists
        employee = Employee.query.get(body.employee_id)
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Parse absence dates
        absence_dates = [datetime.strptime(date, '%Y-%m-%d').date() for date in body.absence_dates]
        absence_dates.sort()
        
        # Calculate absence duration
        absence_days = len(absence_dates)
        
        # Auto-calculate deductions if not provided
        deduction_amount = body.deduction_amount
        leave_days_deducted = body.leave_days_deducted
        
        if not deduction_amount and body.deduction_type in ['salary', 'both']:
            # Calculate salary deduction based on daily rate
            daily_rate = employee.salary / 30 if employee.salary else 0
            deduction_amount = absence_days * daily_rate
        
        if not leave_days_deducted and body.deduction_type in ['leave', 'both']:
            leave_days_deducted = absence_days
        
        # Create leave record for unauthorized absence
        leave_record = LeaveRecord(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            leave_type='unauthorized',
            start_date=absence_dates[0],
            end_date=absence_dates[-1],
            days_count=absence_days,
            status='recorded',
            approved_by=current_user_id,
            deduction_type=body.deduction_type,
            deduction_amount=deduction_amount,
            leave_days_deducted=leave_days_deducted,
            comments=body.comments
        )
        
        # Create HR action record
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            action_type='absence_unauthorized',
            action_date=datetime.now(),
            effective_date=absence_dates[0],
            performed_by=current_user_id,
            details={
                'absence_dates': [date.isoformat() for date in absence_dates],
                'absence_days': absence_days,
                'reason': body.reason,
                'deduction_type': body.deduction_type,
                'deduction_amount': deduction_amount,
                'leave_days_deducted': leave_days_deducted,
                'daily_salary_rate': employee.salary / 30 if employee.salary else 0,
                'supporting_docs': body.supporting_docs or []
            },
            summary=f"Unauthorized absence: {absence_days} days with {body.deduction_type} deductions",
            status='completed',
            comments=body.comments
        )
        
        leave_record.hr_action_id = hr_action.id
        
        db.session.add(leave_record)
        db.session.add(hr_action)
        db.session.commit()
        
        # Prepare deduction summary
        deduction_summary = []
        if deduction_amount:
            deduction_summary.append(f"Salary deduction: ZMW {deduction_amount:.2f}")
        if leave_days_deducted:
            deduction_summary.append(f"Leave days deducted: {leave_days_deducted}")
        
        return jsonify({
            'status': 200,
            'data': {
                'hr_action': hr_action.to_dict(),
                'absence_details': {
                    'dates': [date.isoformat() for date in absence_dates],
                    'total_days': absence_days,
                    'deductions': deduction_summary
                }
            },
            'message': f'Recorded {absence_days} days unauthorized absence with {body.deduction_type} deductions'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to record unauthorized absence'
        }), 500

# ---------------------- 8. DISCIPLINARY ACTION ---------------------- #
@hr_actions_bp.post('/disciplinary', tags=[hr_actions_tag])
@jwt_required()
def record_disciplinary_action(body: DisciplinaryActionSchema):
    """Record disciplinary actions with validity periods and consequences"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate employee exists
        employee = Employee.query.get(body.employee_id)
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Parse dates
        issued_date = datetime.strptime(body.issued_date, '%Y-%m-%d').date()
        valid_until = datetime.strptime(body.valid_until, '%Y-%m-%d').date()
        
        # Validate date range
        if valid_until <= issued_date:
            return jsonify({
                'status': 400,
                'error': 'Invalid validity period',
                'message': 'Valid until date must be after issued date'
            }), 400
        
        # Create disciplinary record
        disciplinary_record = DisciplinaryRecord(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            type=body.action_type,
            reason=body.reason,
            issued_date=issued_date,
            valid_until=valid_until,
            severity=body.severity,
            consequences=json.dumps(body.consequences),
            issued_by=current_user_id,
            requires_acknowledgement=body.requires_acknowledgement,
            document_url=json.dumps(body.document_urls) if body.document_urls else None,
            comments=body.comments
        )
        
        # Create HR action record
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            action_type='disciplinary_action',
            action_date=datetime.now(),
            effective_date=issued_date,
            performed_by=current_user_id,
            details={
                'action_type': body.action_type,
                'reason': body.reason,
                'severity': body.severity,
                'consequences': body.consequences,
                'validity_period': {
                    'issued_date': issued_date.isoformat(),
                    'valid_until': valid_until.isoformat(),
                    'duration_days': (valid_until - issued_date).days
                },
                'requires_employee_acknowledgement': body.requires_acknowledgement,
                'document_urls': body.document_urls or []
            },
            summary=f"Disciplinary action: {body.action_type} ({body.severity} severity)",
            status='completed',
            comments=body.comments
        )
        
        disciplinary_record.hr_action_id = hr_action.id
        
        # Update employee disciplinary flag
        employee.has_live_disciplinary = True
        employee.updated_at = datetime.now()
        
        db.session.add(disciplinary_record)
        db.session.add(hr_action)
        db.session.commit()
        
        return jsonify({
            'status': 200,
            'data': {
                'hr_action': hr_action.to_dict(),
                'disciplinary_record': {
                    'id': disciplinary_record.id,
                    'type': disciplinary_record.type,
                    'severity': disciplinary_record.severity,
                    'issued_date': disciplinary_record.issued_date.isoformat(),
                    'valid_until': disciplinary_record.valid_until.isoformat(),
                    'consequences': body.consequences,
                    'requires_acknowledgement': body.requires_acknowledgement
                }
            },
            'message': f'Disciplinary action recorded successfully. Valid until {valid_until.strftime("%Y-%m-%d")}'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to record disciplinary action'
        }), 500

# ---------------------- 9. EXIT PROCESS ---------------------- #
@hr_actions_bp.post('/exit', tags=[hr_actions_tag])
@jwt_required()
def process_employee_exit(body: ExitProcessSchema):
    """Process employee exit with final pay calculation and asset recovery"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate employee exists
        employee = Employee.query.get(body.employee_id)
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Parse exit date
        exit_date = datetime.strptime(body.exit_date, '%Y-%m-%d').date()
        
        # Calculate final settlement
        final_settlement = body.final_settlement
        if not final_settlement.get('calculated'):
            # Auto-calculate final settlement if not provided
            basic_salary = employee.salary or 0
            outstanding_leave = final_settlement.get('outstanding_leave_days', 0)
            leave_encashment = (basic_salary / 30) * outstanding_leave
            
            final_settlement.update({
                'calculated': True,
                'basic_salary': basic_salary,
                'outstanding_leave_days': outstanding_leave,
                'leave_encashment': leave_encashment,
                'final_pay': basic_salary + leave_encashment,
                'deductions': final_settlement.get('deductions', 0),
                'net_pay': basic_salary + leave_encashment - final_settlement.get('deductions', 0)
            })
        
        # Update employee status and end date
        previous_status = employee.employment_status
        employee.employment_status = 'Inactive'
        employee.end_date = exit_date
        employee.has_live_disciplinary = False  # Clear disciplinary flag on exit
        
        # Create HR action record
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=body.employee_id,
            action_type='exit_processing',
            action_date=datetime.now(),
            effective_date=exit_date,
            performed_by=current_user_id,
            details={
                'exit_type': body.exit_type,
                'reason': body.reason,
                'previous_status': previous_status,
                'notice_served': body.notice_served,
                'final_settlement': final_settlement,
                'assets_to_return': body.asset_return,
                'exit_interview': body.exit_interview or {},
                'completion_checklist': {
                    'final_pay_processed': False,
                    'assets_recovered': False,
                    'system_access_revoked': False,
                    'exit_interview_completed': body.exit_interview is not None
                }
            },
            summary=f"Exit process initiated: {body.exit_type}",
            status='in_progress',  # Exit process may have multiple steps
            comments=body.comments
        )
        
        # Create asset return records
        asset_records = []
        for asset in body.asset_return:
            asset_record = {
                'asset_type': asset.get('type'),
                'asset_description': asset.get('description'),
                'due_date': asset.get('due_date', exit_date.isoformat()),
                'status': 'pending',
                'responsible_person': asset.get('responsible_person')
            }
            asset_records.append(asset_record)
        
        hr_action.details['asset_return_records'] = asset_records
        
        db.session.add(hr_action)
        db.session.commit()
        
        # Prepare notifications
        notifications = []
        if body.asset_return:
            notifications.append("Asset recovery process initiated")
        if final_settlement.get('net_pay', 0) > 0:
            notifications.append("Final pay calculation completed")
        if body.exit_interview:
            notifications.append("Exit interview recorded")
        
        return jsonify({
            'status': 200,
            'data': {
                'hr_action': hr_action.to_dict(),
                'employee_status': {
                    'previous': previous_status,
                    'current': 'Inactive',
                    'exit_date': exit_date.isoformat()
                },
                'final_settlement': final_settlement,
                'asset_recovery': {
                    'total_assets': len(body.asset_return),
                    'assets': body.asset_return
                },
                'notifications': notifications
            },
            'message': f'Exit process initiated for employee. {len(notifications)} action items require attention.'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to process employee exit'
        }), 500

# ---------------------- ORIGINAL ENDPOINTS (UPDATED WITH AUTH) ---------------------- #
@hr_actions_bp.post('/', tags=[hr_actions_tag])
@jwt_required()
def create_hr_action():
    """Create a new HR action"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['employee_id', 'action_type', 'effective_date', 'summary']
        missing_fields = [field for field in required_fields if field not in data or not data[field]]
        if missing_fields:
            return jsonify({
                'status': 400,
                'error': f'Missing required fields: {", ".join(missing_fields)}',
                'message': 'All required fields must be provided'
            }), 400
        
        # Validate employee exists
        employee = Employee.query.get(data['employee_id'])
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Create HR action
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            action_type=data['action_type'],
            action_date=datetime.now(),
            effective_date=datetime.strptime(data['effective_date'], '%Y-%m-%d').date(),
            performed_by=current_user_id,
            details=data.get('details', {}),
            summary=data['summary'],
            status=data.get('status', 'completed'),
            requires_approval=data.get('requires_approval', False),
            comments=data.get('comments')
        )
        
        db.session.add(hr_action)
        
        # Handle specific action types
        if data['action_type'] == 'disciplinary_action' and data.get('disciplinary_data'):
            disciplinary_data = data['disciplinary_data']
            disciplinary_record = DisciplinaryRecord(
                id=str(uuid.uuid4()),
                employee_id=data['employee_id'],
                hr_action_id=hr_action.id,
                type=disciplinary_data['type'],
                reason=disciplinary_data['reason'],
                issued_date=datetime.strptime(disciplinary_data.get('issued_date', data['effective_date']), '%Y-%m-%d').date(),
                valid_until=datetime.strptime(disciplinary_data['valid_until'], '%Y-%m-%d').date(),
                issued_by=current_user_id,
                document_url=disciplinary_data.get('document_url'),
                comments=disciplinary_data.get('comments')
            )
            db.session.add(disciplinary_record)
            
            # Update employee disciplinary flag
            employee.has_live_disciplinary = True
        
        elif data['action_type'] in ['leave_maternity', 'leave_sick', 'leave_commute', 'leave_unauthorized'] and data.get('leave_data'):
            leave_data = data['leave_data']
            leave_record = LeaveRecord(
                id=str(uuid.uuid4()),
                employee_id=data['employee_id'],
                hr_action_id=hr_action.id,
                leave_type=data['action_type'].replace('leave_', ''),
                start_date=datetime.strptime(leave_data['start_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(leave_data['end_date'], '%Y-%m-%d').date(),
                days_count=leave_data['days_count'],
                status=leave_data.get('status', 'approved'),
                approved_by=current_user_id,
                doctor_note_url=leave_data.get('doctor_note_url'),
                commute_value=leave_data.get('commute_value'),
                deduction_type=leave_data.get('deduction_type'),
                deduction_amount=leave_data.get('deduction_amount'),
                return_to_work_date=datetime.strptime(leave_data['return_to_work_date'], '%Y-%m-%d').date() if leave_data.get('return_to_work_date') else None,
                reminder_date=datetime.strptime(leave_data['reminder_date'], '%Y-%m-%d').date() if leave_data.get('reminder_date') else None,
                comments=leave_data.get('comments')
            )
            db.session.add(leave_record)
        
        db.session.commit()
        
        return jsonify({
            'status': 201,
            'data': hr_action.to_dict(),
            'message': 'HR action created successfully'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to create HR action'
        }), 500

@hr_actions_bp.get('/employee/<string:employee_id>', tags=[hr_actions_tag])
@jwt_required()
def get_employee_hr_actions(employee_id):
    """Get HR actions history for an employee"""
    try:
        # Validate employee exists
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }), 404
        
        # Get query parameters
        action_type = request.args.get('action_type')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Build query
        query = HRAction.query.filter_by(employee_id=employee_id)
        
        if action_type:
            query = query.filter_by(action_type=action_type)
        
        # Order by action date descending
        query = query.order_by(HRAction.action_date.desc())
        
        # Pagination
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonify({
            'status': 200,
            'data': [action.to_dict() for action in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            },
            'message': 'Employee HR actions retrieved successfully'
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve employee HR actions'
        }), 500

@hr_actions_bp.get('/', tags=[hr_actions_tag])
@jwt_required()
def get_all_hr_actions():
    """Get all HR actions with filtering"""
    try:
        # Get query parameters
        action_type = request.args.get('action_type')
        status = request.args.get('status')
        company_id = request.args.get('company_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Build query
        query = HRAction.query.join(Employee)
        
        if action_type:
            query = query.filter(HRAction.action_type == action_type)
        
        if status:
            query = query.filter(HRAction.status == status)
        
        if company_id and company_id != 'all':
            query = query.filter(Employee.company_id == company_id)
        
        if start_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(HRAction.action_date >= start_date_obj)
        
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            query = query.filter(HRAction.action_date <= end_date_obj)
        
        # Order by action date descending
        query = query.order_by(HRAction.action_date.desc())
        
        # Pagination
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonify({
            'status': 200,
            'data': [action.to_dict() for action in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            },
            'message': 'HR actions retrieved successfully'
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve HR actions'
        }), 500

# ---------------------- UTILITY ENDPOINTS ---------------------- #
@hr_actions_bp.get('/pending-approvals', tags=[hr_actions_tag])
@jwt_required()
def get_pending_approvals():
    """Get HR actions pending approval"""
    try:
        # Get query parameters
        action_type = request.args.get('action_type')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Build query for pending approvals
        query = HRAction.query.filter_by(status='pending_approval')
        
        if action_type:
            query = query.filter_by(action_type=action_type)
        
        # Order by action date
        query = query.order_by(HRAction.action_date.desc())
        
        # Pagination
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonify({
            'status': 200,
            'data': [action.to_dict() for action in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            },
            'message': 'Pending approvals retrieved successfully'
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve pending approvals'
        }), 500

@hr_actions_bp.post('/<string:action_id>/approve', tags=[hr_actions_tag])
@jwt_required()
def approve_hr_action(action_id):
    """Approve a pending HR action"""
    try:
        current_user_id = get_jwt_identity()
        
        # Find HR action
        hr_action = HRAction.query.get(action_id)
        if not hr_action:
            return jsonify({
                'status': 404,
                'error': 'HR action not found',
                'message': 'The specified HR action does not exist'
            }), 404
        
        if hr_action.status != 'pending_approval':
            return jsonify({
                'status': 400,
                'error': 'Invalid action status',
                'message': 'Only actions with pending_approval status can be approved'
            }), 400
        
        # Update HR action status
        hr_action.status = 'completed'
        hr_action.comments = f"Approved by user {current_user_id} on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Execute the approved action
        if hr_action.action_type == 'salary_change':
            # Apply salary change
            employee = Employee.query.get(hr_action.employee_id)
            if employee:
                new_salary = hr_action.details.get('new_salary')
                if new_salary:
                    employee.salary = new_salary
                    employee.updated_at = datetime.now()
        
        db.session.commit()
        
        return jsonify({
            'status': 200,
            'data': hr_action.to_dict(),
            'message': 'HR action approved and executed successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e),
            'message': 'Failed to approve HR action'
        }), 500