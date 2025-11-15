# controllers/leave/leave_records.py
from flask import Blueprint, request, jsonify
from flask_openapi3 import APIBlueprint, Tag
from ...addons.extensions import db
from ...models import LeaveRecord, Employee, HRAction
from ...addons.functions import jsonifyFormat
import uuid
from datetime import datetime, timedelta
from sqlalchemy import and_, or_

leave_bp = APIBlueprint('leave', __name__, url_prefix='/api/leave-records')

leave_tag = Tag(name="Leave Records", description="Leave management operations")

@leave_bp.post('/', tags=[leave_tag])
def create_leave_record():
    """Create a new leave record"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['employee_id', 'leave_type', 'start_date', 'end_date', 'days_count']
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
        
        # Validate leave type specific requirements
        if data['leave_type'] in ['maternity', 'sick'] and not data.get('doctor_note_url'):
            return jsonifyFormat({
                'status': 400,
                'error': 'Doctor note required',
                'message': f'Doctor note is required for {data["leave_type"]} leave'
            }, 400)
        
        # Create leave record
        leave_record = LeaveRecord(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            leave_type=data['leave_type'],
            start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(data['end_date'], '%Y-%m-%d').date(),
            days_count=data['days_count'],
            status=data.get('status', 'approved'),
            approved_by=data.get('approved_by'),
            doctor_note_url=data.get('doctor_note_url'),
            commute_value=data.get('commute_value'),
            deduction_type=data.get('deduction_type'),
            deduction_amount=data.get('deduction_amount'),
            return_to_work_date=datetime.strptime(data['return_to_work_date'], '%Y-%m-%d').date() if data.get('return_to_work_date') else None,
            reminder_date=datetime.strptime(data['reminder_date'], '%Y-%m-%d').date() if data.get('reminder_date') else None,
            comments=data.get('comments')
        )
        
        # Create HR action log
        action_type = f"leave_{data['leave_type']}"
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            action_type=action_type,
            action_date=datetime.now(),
            effective_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
            performed_by=data.get('approved_by', data.get('created_by', 'system')),
            details={
                'start_date': data['start_date'],
                'end_date': data['end_date'],
                'days_count': data['days_count'],
                'leave_type': data['leave_type'],
                'doctor_note_uploaded': bool(data.get('doctor_note_url')),
                'commute_value': data.get('commute_value'),
                'deduction_type': data.get('deduction_type'),
                'deduction_amount': data.get('deduction_amount')
            },
            summary=f"{data['leave_type'].title()} leave: {data['days_count']} days from {data['start_date']} to {data['end_date']}",
            status='completed'
        )
        
        db.session.add(leave_record)
        db.session.add(hr_action)
        
        # Link HR action to leave record
        leave_record.hr_action_id = hr_action.id
        
        db.session.commit()
        
        return jsonifyFormat({
            'status': 201,
            'data': leave_record.to_dict(),
            'message': 'Leave record created successfully'
        }, 201)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to create leave record'
        }, 500)

@leave_bp.post('/maternity', tags=[leave_tag])
def create_maternity_leave():
    """Create maternity leave with auto-calculation"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['employee_id', 'start_date', 'doctor_note_url', 'approved_by']
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
        
        # Auto-calculate end date (90 days from start)
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = start_date + timedelta(days=90)
        
        # Auto-set reminder date (30 days before end)
        reminder_date = end_date - timedelta(days=30)
        
        # Create maternity leave record
        leave_record = LeaveRecord(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            leave_type='maternity',
            start_date=start_date,
            end_date=end_date,
            days_count=90,
            status='approved',
            approved_by=data['approved_by'],
            doctor_note_url=data['doctor_note_url'],
            return_to_work_date=end_date,
            reminder_date=reminder_date,
            comments=data.get('comments', 'Maternity leave - 90 days')
        )
        
        # Create HR action log
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            action_type='leave_maternity',
            action_date=datetime.now(),
            effective_date=start_date,
            performed_by=data['approved_by'],
            details={
                'start_date': data['start_date'],
                'expected_end_date': end_date.isoformat(),
                'doctor_note_uploaded': True,
                'reminder_set': reminder_date.isoformat(),
                'comments': data.get('comments')
            },
            summary=f"Maternity leave: 90 days from {start_date} to {end_date}",
            status='completed'
        )
        
        db.session.add(leave_record)
        db.session.add(hr_action)
        leave_record.hr_action_id = hr_action.id
        
        db.session.commit()
        
        return jsonifyFormat({
            'status': 201,
            'data': leave_record.to_dict(),
            'message': 'Maternity leave created successfully'
        }, 201)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to create maternity leave'
        }, 500)

@leave_bp.post('/sick', tags=[leave_tag])
def create_sick_leave():
    """Create sick leave with validation"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['employee_id', 'start_date', 'days_count', 'approved_by']
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
        
        # Require doctor note for sick leave > 3 days
        if data['days_count'] > 3 and not data.get('doctor_note_url'):
            return jsonifyFormat({
                'status': 400,
                'error': 'Doctor note required',
                'message': 'Doctor note is required for sick leave longer than 3 days'
            }, 400)
        
        # Calculate end date
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = start_date + timedelta(days=data['days_count'] - 1)  # -1 because start date counts as day 1
        
        # Create sick leave record
        leave_record = LeaveRecord(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            leave_type='sick',
            start_date=start_date,
            end_date=end_date,
            days_count=data['days_count'],
            status='approved',
            approved_by=data['approved_by'],
            doctor_note_url=data.get('doctor_note_url'),
            comments=data.get('comments', 'Sick leave')
        )
        
        # Create HR action log
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            action_type='leave_sick',
            action_date=datetime.now(),
            effective_date=start_date,
            performed_by=data['approved_by'],
            details={
                'start_date': data['start_date'],
                'end_date': end_date.isoformat(),
                'days_count': data['days_count'],
                'doctor_note_uploaded': bool(data.get('doctor_note_url')),
                'comments': data.get('comments')
            },
            summary=f"Sick leave: {data['days_count']} days from {start_date} to {end_date}",
            status='completed'
        )
        
        db.session.add(leave_record)
        db.session.add(hr_action)
        leave_record.hr_action_id = hr_action.id
        
        db.session.commit()
        
        return jsonifyFormat({
            'status': 201,
            'data': leave_record.to_dict(),
            'message': 'Sick leave created successfully'
        }, 201)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to create sick leave'
        }, 500)

@leave_bp.post('/commute', tags=[leave_tag])
def create_leave_commutation():
    """Create leave commutation (cash out)"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['employee_id', 'days_to_commute', 'daily_rate', 'approved_by']
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
        
        # Calculate monetary value
        commute_value = float(data['days_to_commute']) * float(data['daily_rate'])
        
        # Create leave commutation record
        leave_record = LeaveRecord(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            leave_type='commute',
            start_date=datetime.now().date(),
            end_date=datetime.now().date(),
            days_count=data['days_to_commute'],
            status='approved',
            approved_by=data['approved_by'],
            commute_value=commute_value,
            comments=data.get('comments', 'Leave commutation')
        )
        
        # Create HR action log
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            action_type='leave_commute',
            action_date=datetime.now(),
            effective_date=datetime.now().date(),
            performed_by=data['approved_by'],
            details={
                'days_to_commute': data['days_to_commute'],
                'daily_rate': data['daily_rate'],
                'commute_value': commute_value,
                'payroll_cutoff_warning': data.get('payroll_cutoff_warning', False),
                'comments': data.get('comments')
            },
            summary=f"Leave commutation: {data['days_to_commute']} days = {commute_value} {employee.salary_currency}",
            status='completed'
        )
        
        db.session.add(leave_record)
        db.session.add(hr_action)
        leave_record.hr_action_id = hr_action.id
        
        db.session.commit()
        
        return jsonifyFormat({
            'status': 201,
            'data': leave_record.to_dict(),
            'message': 'Leave commutation created successfully'
        }, 201)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to create leave commutation'
        }, 500)

@leave_bp.post('/unauthorized', tags=[leave_tag])
def create_unauthorized_absence():
    """Create unauthorized absence record"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['employee_id', 'start_date', 'end_date', 'deduction_type', 'approved_by']
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
        
        # Calculate days count
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        days_count = (end_date - start_date).days + 1
        
        # Calculate deduction amount
        if data['deduction_type'] == 'pay_deduction':
            # Calculate based on daily rate
            daily_rate = float(employee.salary) / 30  # Simplified daily rate
            deduction_amount = days_count * daily_rate
        else:  # leave_deduction
            deduction_amount = days_count
        
        # Create unauthorized absence record
        leave_record = LeaveRecord(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            leave_type='unauthorized',
            start_date=start_date,
            end_date=end_date,
            days_count=days_count,
            status='approved',
            approved_by=data['approved_by'],
            deduction_type=data['deduction_type'],
            deduction_amount=deduction_amount,
            comments=data.get('comments', 'Unauthorized absence')
        )
        
        # Create HR action log
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            action_type='leave_unauthorized',
            action_date=datetime.now(),
            effective_date=start_date,
            performed_by=data['approved_by'],
            details={
                'start_date': data['start_date'],
                'end_date': data['end_date'],
                'days_count': days_count,
                'deduction_type': data['deduction_type'],
                'deduction_amount': deduction_amount,
                'comments': data.get('comments')
            },
            summary=f"Unauthorized absence: {days_count} days from {start_date} to {end_date} - {data['deduction_type'].replace('_', ' ').title()}",
            status='completed'
        )
        
        db.session.add(leave_record)
        db.session.add(hr_action)
        leave_record.hr_action_id = hr_action.id
        
        db.session.commit()
        
        return jsonifyFormat({
            'status': 201,
            'data': leave_record.to_dict(),
            'message': 'Unauthorized absence recorded successfully'
        }, 201)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to record unauthorized absence'
        }, 500)

@leave_bp.get('/employee/<string:employee_id>', tags=[leave_tag])
def get_employee_leave_records(employee_id):
    """Get leave records for an employee"""
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
        leave_type = request.args.get('leave_type')
        status = request.args.get('status')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Build query
        query = LeaveRecord.query.filter_by(employee_id=employee_id)
        
        if leave_type:
            query = query.filter_by(leave_type=leave_type)
        
        if status:
            query = query.filter_by(status=status)
        
        if start_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(LeaveRecord.start_date >= start_date_obj)
        
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(LeaveRecord.end_date <= end_date_obj)
        
        # Order by start date descending
        query = query.order_by(LeaveRecord.start_date.desc())
        
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
            'message': 'Employee leave records retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve employee leave records'
        }, 500)

@leave_bp.get('/active', tags=[leave_tag])
def get_active_leave_records():
    """Get currently active leaves"""
    try:
        # Get query parameters
        company_id = request.args.get('company_id')
        leave_type = request.args.get('leave_type')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        today = datetime.now().date()
        
        # Build query for active leaves (current date between start and end date)
        query = LeaveRecord.query.join(Employee).filter(
            and_(
                LeaveRecord.start_date <= today,
                LeaveRecord.end_date >= today,
                LeaveRecord.status.in_(['approved', 'completed'])
            )
        )
        
        if company_id and company_id != 'all':
            query = query.filter(Employee.company_id == company_id)
        
        if leave_type:
            query = query.filter(LeaveRecord.leave_type == leave_type)
        
        # Order by start date
        query = query.order_by(LeaveRecord.start_date.asc())
        
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
            'message': 'Active leave records retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve active leave records'
        }, 500)

@leave_bp.get('/supervisors-on-leave', tags=[leave_tag])
def get_supervisors_on_leave():
    """Get supervisors currently on leave"""
    try:
        company_id = request.args.get('company_id', 'all')
        
        today = datetime.now().date()
        
        # Build query for supervisors on leave
        query = LeaveRecord.query.join(Employee).filter(
            and_(
                LeaveRecord.start_date <= today,
                LeaveRecord.end_date >= today,
                LeaveRecord.status.in_(['approved', 'completed']),
                or_(
                    Employee.position.ilike('%supervisor%'),
                    Employee.position.ilike('%manager%'),
                    Employee.position.ilike('%director%'),
                    Employee.position.ilike('%head%')
                )
            )
        )
        
        if company_id and company_id != 'all':
            query = query.filter(Employee.company_id == company_id)
        
        supervisors_on_leave = query.all()
        
        supervisors_data = []
        for leave in supervisors_on_leave:
            supervisors_data.append({
                'id': leave.employee.id,
                'name': f"{leave.employee.first_name} {leave.employee.last_name}",
                'position': leave.employee.position,
                'leave_type': leave.leave_type,
                'start_date': leave.start_date.isoformat(),
                'end_date': leave.end_date.isoformat(),
                'return_date': leave.return_to_work_date.isoformat() if leave.return_to_work_date else leave.end_date.isoformat(),
                'company': leave.employee.company.name if leave.employee.company else None
            })
        
        return jsonifyFormat({
            'status': 200,
            'data': supervisors_data,
            'message': 'Supervisors on leave retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve supervisors on leave'
        }, 500)

@leave_bp.put('/<string:leave_id>', tags=[leave_tag])
def update_leave_record(leave_id):
    """Update a leave record"""
    try:
        data = request.get_json()
        leave_record = LeaveRecord.query.get(leave_id)
        
        if not leave_record:
            return jsonifyFormat({
                'status': 404,
                'error': 'Leave record not found',
                'message': 'The specified leave record does not exist'
            }, 404)
        
        # Update allowed fields
        allowed_fields = ['status', 'approved_by', 'doctor_note_url', 'commute_value', 
                         'deduction_type', 'deduction_amount', 'return_to_work_date', 
                         'reminder_date', 'comments']
        
        for field in allowed_fields:
            if field in data:
                if field in ['return_to_work_date', 'reminder_date'] and data[field]:
                    setattr(leave_record, field, datetime.strptime(data[field], '%Y-%m-%d').date())
                else:
                    setattr(leave_record, field, data[field])
        
        db.session.commit()
        
        return jsonifyFormat({
            'status': 200,
            'data': leave_record.to_dict(),
            'message': 'Leave record updated successfully'
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to update leave record'
        }, 500)