# controllers/disciplinary/disciplinary_records.py
from flask import Blueprint, request, jsonify
from flask_openapi3 import APIBlueprint, Tag
from ...addons.extensions import db
from ...models import DisciplinaryRecord, Employee, HRAction
from ...addons.functions import jsonifyFormat
import uuid
from datetime import datetime, timedelta
from sqlalchemy import and_

disciplinary_bp = APIBlueprint('disciplinary', __name__, url_prefix='/api/disciplinary-records')

disciplinary_tag = Tag(name="Disciplinary Records", description="Disciplinary actions management")

@disciplinary_bp.post('/', tags=[disciplinary_tag])
def create_disciplinary_record():
    """Create a new disciplinary record"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['employee_id', 'type', 'reason', 'issued_date', 'valid_until', 'issued_by']
        missing_fields = [field for field in required_fields if field not in data or not data[field]]
        if missing_fields:
            return jsonifyFormat({
                'status': 400,
                'error': f'Missing required fields: {", ".join(missing_fields)}',
                'message': 'All required fields must be provided'
            }, 400)
        
        # Validate employee exists
        employee = Employee.query.get(data['employee_id'])
        if not employee:
            return jsonifyFormat({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }, 404)
        
        # Check if final warning can be issued (should have prior written warning)
        if data['type'] == 'final_warning':
            prior_warnings = DisciplinaryRecord.query.filter_by(
                employee_id=data['employee_id'],
                type='written_warning',
                is_active=True
            ).count()
            
            if prior_warnings == 0:
                return jsonifyFormat({
                    'status': 400,
                'error': 'Cannot issue final warning without prior written warning',
                    'message': 'Employee must have an active written warning before issuing final warning'
                }, 400)
        
        # Create disciplinary record
        disciplinary_record = DisciplinaryRecord(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            type=data['type'],
            reason=data['reason'],
            issued_date=datetime.strptime(data['issued_date'], '%Y-%m-%d').date(),
            valid_until=datetime.strptime(data['valid_until'], '%Y-%m-%d').date(),
            is_active=True,
            issued_by=data['issued_by'],
            document_url=data.get('document_url'),
            comments=data.get('comments')
        )
        
        # Create HR action log
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            action_type='disciplinary_action',
            action_date=datetime.now(),
            effective_date=datetime.strptime(data['issued_date'], '%Y-%m-%d').date(),
            performed_by=data['issued_by'],
            details={
                'type': data['type'],
                'reason': data['reason'],
                'valid_until': data['valid_until'],
                'document_uploaded': bool(data.get('document_url')),
                'comments': data.get('comments')
            },
            summary=f"Disciplinary action issued: {data['type'].replace('_', ' ').title()} - {data['reason']}",
            status='completed'
        )
        
        db.session.add(disciplinary_record)
        db.session.add(hr_action)
        
        # Update employee disciplinary flag
        employee.has_live_disciplinary = True
        
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

@disciplinary_bp.get('/employee/<string:employee_id>', tags=[disciplinary_tag])
def get_employee_disciplinary_records(employee_id):
    """Get disciplinary records for an employee"""
    try:
        # Validate employee exists
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonifyFormat({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }, 404)
        
        # Get query parameters
        status = request.args.get('status', 'all')  # all, active, expired
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Build query
        query = DisciplinaryRecord.query.filter_by(employee_id=employee_id)
        
        if status == 'active':
            query = query.filter_by(is_active=True)
        elif status == 'expired':
            query = query.filter_by(is_active=False)
        
        # Order by issued date descending
        query = query.order_by(DisciplinaryRecord.issued_date.desc())
        
        # Pagination
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonifyFormat({
            'status': 200,
            'data': [record.to_dict() for record in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
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

@disciplinary_bp.get('/active', tags=[disciplinary_tag])
def get_active_disciplinary_records():
    """Get all active disciplinary records"""
    try:
        # Get query parameters
        company_id = request.args.get('company_id')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Build query
        query = DisciplinaryRecord.query.join(Employee).filter(
            DisciplinaryRecord.is_active == True
        )
        
        if company_id and company_id != 'all':
            query = query.filter(Employee.company_id == company_id)
        
        # Order by issued date descending
        query = query.order_by(DisciplinaryRecord.issued_date.desc())
        
        # Pagination
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonifyFormat({
            'status': 200,
            'data': [record.to_dict() for record in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
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

@disciplinary_bp.put('/<string:record_id>', tags=[disciplinary_tag])
def update_disciplinary_record(record_id):
    """Update a disciplinary record"""
    try:
        data = request.get_json()
        record = DisciplinaryRecord.query.get(record_id)
        
        if not record:
            return jsonifyFormat({
                'status': 404,
                'error': 'Disciplinary record not found',
                'message': 'The specified disciplinary record does not exist'
            }, 404)
        
        # Update allowed fields
        allowed_fields = ['reason', 'valid_until', 'document_url', 'comments', 'is_active']
        for field in allowed_fields:
            if field in data:
                if field == 'valid_until':
                    setattr(record, field, datetime.strptime(data[field], '%Y-%m-%d').date())
                else:
                    setattr(record, field, data[field])
        
        # Update employee disciplinary flag if is_active changed
        if 'is_active' in data:
            employee = Employee.query.get(record.employee_id)
            if employee:
                # Check if employee has any other active disciplinaries
                active_records = DisciplinaryRecord.query.filter_by(
                    employee_id=record.employee_id,
                    is_active=True
                ).count()
                employee.has_live_disciplinary = active_records > 0
        
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