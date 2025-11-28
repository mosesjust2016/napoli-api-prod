# controllers/disciplinary/disciplinary_records.py
from flask import Blueprint, request, jsonify
from flask_openapi3 import APIBlueprint, Tag
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json  # Add this import

from ...addons.extensions import db
from ...models import DisciplinaryRecord, Employee, HRAction
from ...addons.functions import jsonifyFormat
from sqlalchemy import and_

disciplinary_bp = APIBlueprint('disciplinary', __name__, url_prefix='/api/disciplinary-records')
disciplinary_tag = Tag(name="Disciplinary Records", description="Disciplinary actions management")

# ---------------------- REQUEST SCHEMAS ---------------------- #
class CreateDisciplinarySchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    type: str = Field(..., description="Type of disciplinary action")
    reason: str = Field(..., description="Reason for disciplinary action")
    issued_date: str = Field(..., description="Date action was issued")
    valid_until: str = Field(..., description="Date action is valid until")
    severity: str = Field(..., description="Severity level: low, medium, high")
    consequences: List[str] = Field(..., description="Consequences of the action")
    requires_acknowledgement: bool = Field(True, description="Whether employee acknowledgement is required")
    document_urls: Optional[List[str]] = Field(None, description="Supporting documents")
    comments: Optional[str] = Field(None, description="Additional comments")

class UpdateDisciplinarySchema(BaseModel):
    reason: Optional[str] = Field(None, description="Reason for disciplinary action")
    valid_until: Optional[str] = Field(None, description="Date action is valid until")
    severity: Optional[str] = Field(None, description="Severity level: low, medium, high")
    consequences: Optional[List[str]] = Field(None, description="Consequences of the action")
    is_active: Optional[bool] = Field(None, description="Whether the record is active")
    document_urls: Optional[List[str]] = Field(None, description="Supporting documents")
    comments: Optional[str] = Field(None, description="Additional comments")

# ---------------------- PATH PARAMETER SCHEMAS ---------------------- #
class EmployeeIdPath(BaseModel):
    employee_id: int = Field(..., description="Employee ID")

class RecordIdPath(BaseModel):
    record_id: str = Field(..., description="Disciplinary Record ID")

# ---------------------- QUERY PARAMETER SCHEMAS ---------------------- #
class DisciplinaryQuery(BaseModel):
    status: Optional[str] = Field('all', description="Filter by status: all, active, expired")
    company_id: Optional[str] = Field(None, description="Filter by company ID")
    type: Optional[str] = Field(None, description="Filter by disciplinary type")
    severity: Optional[str] = Field(None, description="Filter by severity")
    page: int = Field(1, description="Page number")
    per_page: int = Field(20, description="Items per page")

# ---------------------- RESPONSE SCHEMAS ---------------------- #
class SuccessResponse(BaseModel):
    status: int = Field(200, description="HTTP status code")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    message: str = Field(..., description="Response message")

class ErrorResponse(BaseModel):
    status: int = Field(..., description="HTTP status code")
    error: str = Field(..., description="Error description")
    message: str = Field(..., description="Error message")

class DisciplinaryListResponse(BaseModel):
    status: int = Field(200, description="HTTP status code")
    data: List[Dict[str, Any]] = Field(..., description="List of disciplinary records")
    pagination: Dict[str, Any] = Field(..., description="Pagination information")
    message: str = Field(..., description="Response message")

# ---------------------- CRUD ENDPOINTS ---------------------- #

@disciplinary_bp.post(
    '/',
    tags=[disciplinary_tag],
    responses={201: SuccessResponse, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def create_disciplinary_record(body: CreateDisciplinarySchema):
    """Create a new disciplinary record"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate employee exists
        employee = Employee.query.get(body.employee_id)
        if not employee:
            return jsonifyFormat({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }, 404)
        
        # Parse dates
        issued_date = datetime.strptime(body.issued_date, '%Y-%m-%d').date()
        valid_until = datetime.strptime(body.valid_until, '%Y-%m-%d').date()
        
        # Validate date range
        if valid_until <= issued_date:
            return jsonifyFormat({
                'status': 400,
                'error': 'Invalid validity period',
                'message': 'Valid until date must be after issued date'
            }, 400)
        
        # Check if final warning can be issued (should have prior written warning)
        if body.type == 'final_warning':
            prior_warnings = DisciplinaryRecord.query.filter_by(
                employee_id=body.employee_id,
                type='written_warning',
                is_active=True
            ).count()
            
            if prior_warnings == 0:
                return jsonifyFormat({
                    'status': 400,
                    'error': 'Cannot issue final warning without prior written warning',
                    'message': 'Employee must have an active written warning before issuing final warning'
                }, 400)
        
        # Create disciplinary record - FIXED: Convert lists to JSON strings
        disciplinary_record = DisciplinaryRecord(
            employee_id=body.employee_id,
            type=body.type,
            reason=body.reason,
            issued_date=issued_date,
            valid_until=valid_until,
            severity=body.severity,
            consequences=json.dumps(body.consequences) if body.consequences else None,
            is_active=True,
            issued_by=current_user_id,
            requires_acknowledgement=body.requires_acknowledgement,
            document_urls=json.dumps(body.document_urls) if body.document_urls else None,
            comments=body.comments
        )
        
        # Create HR action log
        hr_action = HRAction(
            employee_id=body.employee_id,
            action_type='disciplinary_action',
            action_date=datetime.now(),
            effective_date=issued_date,
            performed_by=current_user_id,
            details={
                'action_type': body.type,
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
            summary=f"Disciplinary action: {body.type} ({body.severity} severity)",
            status='completed',
            comments=body.comments
        )
        
        db.session.add(disciplinary_record)
        db.session.add(hr_action)
        
        # Update employee disciplinary flag
        employee.has_live_disciplinary = True
        employee.updated_at = datetime.now()
        
        db.session.commit()
        
        return jsonifyFormat({
            'status': 201,
            'data': disciplinary_record.to_dict(),
            'message': 'Disciplinary record created successfully'
        }, 201)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to create disciplinary record'
        }, 500)

@disciplinary_bp.get(
    '/employee/<int:employee_id>',
    tags=[disciplinary_tag],
    responses={200: DisciplinaryListResponse, 404: ErrorResponse, 500: ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def get_employee_disciplinary_records(path: EmployeeIdPath, query: DisciplinaryQuery):
    """Get disciplinary records for an employee"""
    try:
        # Validate employee exists
        employee = Employee.query.get(path.employee_id)
        if not employee:
            return jsonifyFormat({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }, 404)
        
        # Build query
        db_query = DisciplinaryRecord.query.filter_by(employee_id=path.employee_id)
        
        if query.status == 'active':
            db_query = db_query.filter_by(is_active=True)
        elif query.status == 'expired':
            db_query = db_query.filter_by(is_active=False)
        
        if query.type:
            db_query = db_query.filter_by(type=query.type)
            
        if query.severity:
            db_query = db_query.filter_by(severity=query.severity)
        
        # Order by issued date descending
        db_query = db_query.order_by(DisciplinaryRecord.issued_date.desc())
        
        # Pagination
        pagination = db_query.paginate(
            page=query.page, 
            per_page=query.per_page, 
            error_out=False
        )
        
        return jsonifyFormat({
            'status': 200,
            'data': [record.to_dict() for record in pagination.items],
            'pagination': {
                'page': query.page,
                'per_page': query.per_page,
                'total': pagination.total,
                'pages': pagination.pages
            },
            'message': 'Employee disciplinary records retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve employee disciplinary records'
        }, 500)

@disciplinary_bp.get(
    '/active',
    tags=[disciplinary_tag],
    responses={200: DisciplinaryListResponse, 500: ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def get_active_disciplinary_records(query: DisciplinaryQuery):
    """Get all active disciplinary records"""
    try:
        # Build query
        db_query = DisciplinaryRecord.query.join(Employee).filter(
            DisciplinaryRecord.is_active == True
        )
        
        if query.company_id and query.company_id != 'all':
            db_query = db_query.filter(Employee.company_id == query.company_id)
        
        if query.type:
            db_query = db_query.filter(DisciplinaryRecord.type == query.type)
            
        if query.severity:
            db_query = db_query.filter(DisciplinaryRecord.severity == query.severity)
        
        # Order by issued date descending
        db_query = db_query.order_by(DisciplinaryRecord.issued_date.desc())
        
        # Pagination
        pagination = db_query.paginate(
            page=query.page, 
            per_page=query.per_page, 
            error_out=False
        )
        
        return jsonifyFormat({
            'status': 200,
            'data': [record.to_dict() for record in pagination.items],
            'pagination': {
                'page': query.page,
                'per_page': query.per_page,
                'total': pagination.total,
                'pages': pagination.pages
            },
            'message': 'Active disciplinary records retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve active disciplinary records'
        }, 500)

@disciplinary_bp.get(
    '/',
    tags=[disciplinary_tag],
    responses={200: DisciplinaryListResponse, 500: ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def get_all_disciplinary_records(query: DisciplinaryQuery):
    """Get all disciplinary records with filtering"""
    try:
        # Build query
        db_query = DisciplinaryRecord.query.join(Employee)
        
        if query.status == 'active':
            db_query = db_query.filter(DisciplinaryRecord.is_active == True)
        elif query.status == 'expired':
            db_query = db_query.filter(DisciplinaryRecord.is_active == False)
        
        if query.company_id and query.company_id != 'all':
            db_query = db_query.filter(Employee.company_id == query.company_id)
        
        if query.type:
            db_query = db_query.filter(DisciplinaryRecord.type == query.type)
            
        if query.severity:
            db_query = db_query.filter(DisciplinaryRecord.severity == query.severity)
        
        # Order by issued date descending
        db_query = db_query.order_by(DisciplinaryRecord.issued_date.desc())
        
        # Pagination
        pagination = db_query.paginate(
            page=query.page, 
            per_page=query.per_page, 
            error_out=False
        )
        
        return jsonifyFormat({
            'status': 200,
            'data': [record.to_dict() for record in pagination.items],
            'pagination': {
                'page': query.page,
                'per_page': query.per_page,
                'total': pagination.total,
                'pages': pagination.pages
            },
            'message': 'Disciplinary records retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve disciplinary records'
        }, 500)

@disciplinary_bp.get(
    '/<string:record_id>',
    tags=[disciplinary_tag],
    responses={200: SuccessResponse, 404: ErrorResponse, 500: ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def get_disciplinary_record(path: RecordIdPath):
    """Get a specific disciplinary record by ID"""
    try:
        record = DisciplinaryRecord.query.get(path.record_id)
        
        if not record:
            return jsonifyFormat({
                'status': 404,
                'error': 'Disciplinary record not found',
                'message': 'The specified disciplinary record does not exist'
            }, 404)
        
        return jsonifyFormat({
            'status': 200,
            'data': record.to_dict(),
            'message': 'Disciplinary record retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve disciplinary record'
        }, 500)

@disciplinary_bp.put(
    '/<string:record_id>',
    tags=[disciplinary_tag],
    responses={200: SuccessResponse, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def update_disciplinary_record(path: RecordIdPath, body: UpdateDisciplinarySchema):
    """Update a disciplinary record"""
    try:
        current_user_id = get_jwt_identity()
        record = DisciplinaryRecord.query.get(path.record_id)
        
        if not record:
            return jsonifyFormat({
                'status': 404,
                'error': 'Disciplinary record not found',
                'message': 'The specified disciplinary record does not exist'
            }, 404)
        
        # Update allowed fields
        if body.reason is not None:
            record.reason = body.reason
            
        if body.valid_until is not None:
            valid_until = datetime.strptime(body.valid_until, '%Y-%m-%d').date()
            if valid_until <= record.issued_date:
                return jsonifyFormat({
                    'status': 400,
                    'error': 'Invalid validity period',
                    'message': 'Valid until date must be after issued date'
                }, 400)
            record.valid_until = valid_until
            
        if body.severity is not None:
            record.severity = body.severity
            
        if body.consequences is not None:
            record.consequences = json.dumps(body.consequences) if body.consequences else None
            
        if body.is_active is not None:
            record.is_active = body.is_active
            
        if body.document_urls is not None:
            record.document_urls = json.dumps(body.document_urls) if body.document_urls else None
            
        if body.comments is not None:
            record.comments = body.comments
        
        record.updated_at = datetime.now()
        
        # Update employee disciplinary flag if is_active changed
        if body.is_active is not None:
            employee = Employee.query.get(record.employee_id)
            if employee:
                # Check if employee has any other active disciplinaries
                active_records = DisciplinaryRecord.query.filter_by(
                    employee_id=record.employee_id,
                    is_active=True
                ).count()
                employee.has_live_disciplinary = active_records > 0
                employee.updated_at = datetime.now()
        
        # Create HR action log for update
        hr_action = HRAction(
            employee_id=record.employee_id,
            action_type='disciplinary_update',
            action_date=datetime.now(),
            effective_date=datetime.now().date(),
            performed_by=current_user_id,
            details={
                'record_id': path.record_id,
                'updates': body.dict(exclude_unset=True)
            },
            summary=f"Disciplinary record updated: {record.type}",
            status='completed',
            comments=f"Record updated by user {current_user_id}"
        )
        
        db.session.add(hr_action)
        db.session.commit()
        
        return jsonifyFormat({
            'status': 200,
            'data': record.to_dict(),
            'message': 'Disciplinary record updated successfully'
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to update disciplinary record'
        }, 500)

@disciplinary_bp.delete(
    '/<string:record_id>',
    tags=[disciplinary_tag],
    responses={200: SuccessResponse, 404: ErrorResponse, 500: ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def delete_disciplinary_record(path: RecordIdPath):
    """Delete a disciplinary record (soft delete)"""
    try:
        current_user_id = get_jwt_identity()
        record = DisciplinaryRecord.query.get(path.record_id)
        
        if not record:
            return jsonifyFormat({
                'status': 404,
                'error': 'Disciplinary record not found',
                'message': 'The specified disciplinary record does not exist'
            }, 404)
        
        # Store record data for HR action before deletion
        record_data = record.to_dict()
        
        # Soft delete by setting is_active to False
        record.is_active = False
        record.updated_at = datetime.now()
        
        # Update employee disciplinary flag
        employee = Employee.query.get(record.employee_id)
        if employee:
            # Check if employee has any other active disciplinaries
            active_records = DisciplinaryRecord.query.filter_by(
                employee_id=record.employee_id,
                is_active=True
            ).count()
            employee.has_live_disciplinary = active_records > 0
            employee.updated_at = datetime.now()
        
        # Create HR action log for deletion
        hr_action = HRAction(
            employee_id=record.employee_id,
            action_type='disciplinary_deletion',
            action_date=datetime.now(),
            effective_date=datetime.now().date(),
            performed_by=current_user_id,
            details={
                'deleted_record': record_data,
                'deletion_reason': 'Manual deletion by user'
            },
            summary=f"Disciplinary record deleted: {record.type}",
            status='completed',
            comments=f"Record deleted by user {current_user_id}"
        )
        
        db.session.add(hr_action)
        db.session.commit()
        
        return jsonifyFormat({
            'status': 200,
            'data': None,
            'message': 'Disciplinary record deleted successfully'
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to delete disciplinary record'
        }, 500)

# ---------------------- UTILITY ENDPOINTS ---------------------- #

@disciplinary_bp.get(
    '/stats/summary',
    tags=[disciplinary_tag],
    responses={200: SuccessResponse, 500: ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def get_disciplinary_stats():
    """Get disciplinary statistics summary"""
    try:
        # Get query parameters
        company_id = request.args.get('company_id')
        
        # Build base query
        query = DisciplinaryRecord.query.join(Employee)
        
        if company_id and company_id != 'all':
            query = query.filter(Employee.company_id == company_id)
        
        # Calculate statistics
        total_records = query.count()
        active_records = query.filter(DisciplinaryRecord.is_active == True).count()
        expired_records = query.filter(DisciplinaryRecord.is_active == False).count()
        
        # Count by type
        written_warnings = query.filter(DisciplinaryRecord.type == 'written_warning').count()
        final_warnings = query.filter(DisciplinaryRecord.type == 'final_warning').count()
        suspensions = query.filter(DisciplinaryRecord.type == 'suspension').count()
        
        # Count by severity
        low_severity = query.filter(DisciplinaryRecord.severity == 'low').count()
        medium_severity = query.filter(DisciplinaryRecord.severity == 'medium').count()
        high_severity = query.filter(DisciplinaryRecord.severity == 'high').count()
        
        stats = {
            'total_records': total_records,
            'active_records': active_records,
            'expired_records': expired_records,
            'by_type': {
                'written_warning': written_warnings,
                'final_warning': final_warnings,
                'suspension': suspensions
            },
            'by_severity': {
                'low': low_severity,
                'medium': medium_severity,
                'high': high_severity
            }
        }
        
        return jsonifyFormat({
            'status': 200,
            'data': stats,
            'message': 'Disciplinary statistics retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve disciplinary statistics'
        }, 500)

@disciplinary_bp.post(
    '/<string:record_id>/acknowledge',
    tags=[disciplinary_tag],
    responses={200: SuccessResponse, 404: ErrorResponse, 500: ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def acknowledge_disciplinary_record(path: RecordIdPath):
    """Mark a disciplinary record as acknowledged by employee"""
    try:
        current_user_id = get_jwt_identity()
        record = DisciplinaryRecord.query.get(path.record_id)
        
        if not record:
            return jsonifyFormat({
                'status': 404,
                'error': 'Disciplinary record not found',
                'message': 'The specified disciplinary record does not exist'
            }, 404)
        
        if not getattr(record, 'requires_acknowledgement', True):
            return jsonifyFormat({
                'status': 400,
                'error': 'Acknowledgement not required',
                'message': 'This disciplinary record does not require employee acknowledgement'
            }, 400)
        
        # Update record
        record.acknowledged_by_employee = True
        record.acknowledgement_date = datetime.now()
        record.updated_at = datetime.now()
        
        # Create HR action log for acknowledgement
        hr_action = HRAction(
            employee_id=record.employee_id,
            action_type='disciplinary_acknowledgement',
            action_date=datetime.now(),
            effective_date=datetime.now().date(),
            performed_by=current_user_id,
            details={
                'record_id': path.record_id,
                'acknowledgement_date': datetime.now().isoformat()
            },
            summary=f"Disciplinary record acknowledged: {record.type}",
            status='completed',
            comments=f"Record acknowledged by employee via user {current_user_id}"
        )
        
        db.session.add(hr_action)
        db.session.commit()
        
        return jsonifyFormat({
            'status': 200,
            'data': record.to_dict(),
            'message': 'Disciplinary record acknowledged successfully'
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to acknowledge disciplinary record'
        }, 500)