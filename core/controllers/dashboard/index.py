# controllers/dashboard/index.py
from flask import Blueprint, request, jsonify
from flask_openapi3 import APIBlueprint, Tag
from flask_jwt_extended import jwt_required
from core.addons.extensions import db
from ...models import Employee, Company, HRAction, LeaveRecord, DisciplinaryRecord
from ...addons.functions import jsonifyFormat
from datetime import datetime, timedelta
from sqlalchemy import func, and_

hr_bp = APIBlueprint('dashboard', __name__, url_prefix='/api/dashboard')

dashboard_tag = Tag(name="Dashboard", description="Dashboard statistics and analytics")

@hr_bp.get('/stats', tags=[dashboard_tag], security=[{"jwt": []}])
@jwt_required()
def get_dashboard_stats():
    """Get dashboard statistics"""
    try:
        company_id = request.args.get('company_id', 'all')
        period = request.args.get('period', 'month')  # month or quarter
        
        # Build base queries
        employee_query = Employee.query
        if company_id != 'all':
            employee_query = employee_query.filter_by(company_id=company_id)
        
        # Calculate statistics
        total_headcount = employee_query.filter(
            Employee.employment_status.in_(['Active', 'Probation'])
        ).count()
        
        active_employees = employee_query.filter_by(
            employment_status='Active'
        ).count()
        
        probation_employees = employee_query.filter_by(
            employment_status='Probation'
        ).count()
        
        # Calculate leavers
        current_period_start = datetime.now().replace(day=1)
        if period == 'quarter':
            # Get first month of current quarter
            current_quarter_month = ((datetime.now().month - 1) // 3) * 3 + 1
            current_period_start = current_period_start.replace(month=current_quarter_month)
        
        last_period_start = current_period_start - timedelta(days=30 if period == 'month' else 90)
        
        current_leavers = employee_query.filter(
            Employee.employment_status == 'Inactive',
            Employee.end_date >= current_period_start
        ).count()
        
        last_leavers = employee_query.filter(
            Employee.employment_status == 'Inactive',
            Employee.end_date >= last_period_start,
            Employee.end_date < current_period_start
        ).count()
        
        # Calculate average tenure
        tenure_query = employee_query.filter_by(employment_status='Active')
        if company_id != 'all':
            tenure_query = tenure_query.filter_by(company_id=company_id)
            
        active_employees_with_tenure = tenure_query.with_entities(
            func.datediff(func.now(), Employee.start_date).label('tenure_days')
        ).all()
        
        avg_tenure_days = sum(emp.tenure_days for emp in active_employees_with_tenure) / len(active_employees_with_tenure) if active_employees_with_tenure else 0
        avg_tenure_months = round(avg_tenure_days / 30.44, 1)
        
        live_disciplinaries = employee_query.filter_by(
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
        
        return jsonifyFormat({
            'status': 200,
            'data': stats,
            'message': 'Dashboard statistics retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve dashboard statistics'
        }, 500)

@hr_bp.get('/people-cost', tags=[dashboard_tag], security=[{"jwt": []}])
@jwt_required()
def get_people_cost():
    """Get people cost breakdown"""
    try:
        company_id = request.args.get('company_id', 'all')
        months = int(request.args.get('months', 6))
        
        # Calculate date range
        end_date = datetime.now().replace(day=1)
        start_date = (end_date - timedelta(days=months*30)).replace(day=1)
        
        # This is a simplified version - in production you'd want to join with payroll data
        employee_query = Employee.query.filter(
            Employee.employment_status.in_(['Active', 'Probation'])
        )
        
        if company_id != 'all':
            employee_query = employee_query.filter_by(company_id=company_id)
        
        # Get total salary cost for current month (simplified)
        total_salary = db.session.query(
            func.sum(Employee.salary)
        ).filter(
            Employee.employment_status.in_(['Active', 'Probation'])
        ).scalar() or 0
        
        # Generate mock data for chart (replace with actual payroll data)
        cost_data = []
        current_date = start_date
        while current_date <= end_date:
            # In production, this would query actual payroll data
            base_salaries = float(total_salary) * 0.8  # 80% of total
            statutory_payments = float(total_salary) * 0.15  # 15%
            overtime = float(total_salary) * 0.03  # 3%
            leave_commutation = float(total_salary) * 0.02  # 2%
            
            cost_data.append({
                'month': current_date.strftime('%Y-%m'),
                'base_salaries': base_salaries,
                'statutory_payments': statutory_payments,
                'overtime': overtime,
                'leave_commutation': leave_commutation,
                'total': base_salaries + statutory_payments + overtime + leave_commutation
            })
            
            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        return jsonifyFormat({
            'status': 200,
            'data': cost_data,
            'message': 'People cost breakdown retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve people cost breakdown'
        }, 500)

@hr_bp.get('/role-distribution', tags=[dashboard_tag], security=[{"jwt": []}])
@jwt_required()
def get_role_distribution():
    """Get role distribution data"""
    try:
        company_id = request.args.get('company_id', 'all')
        
        employee_query = Employee.query.filter(
            Employee.employment_status.in_(['Active', 'Probation'])
        )
        
        if company_id != 'all':
            employee_query = employee_query.filter_by(company_id=company_id)
        
        # Get role counts
        role_counts = db.session.query(
            Employee.position,
            func.count(Employee.id).label('count')
        ).filter(
            Employee.employment_status.in_(['Active', 'Probation'])
        )
        
        if company_id != 'all':
            role_counts = role_counts.filter(Employee.company_id == company_id)
            
        role_counts = role_counts.group_by(Employee.position).order_by(func.count(Employee.id).desc()).all()
        
        # Prepare data for chart
        top_roles = role_counts[:5]  # Top 5 roles
        other_count = sum(count for _, count in role_counts[5:])  # Sum of remaining roles
        
        distribution_data = [
            {'role': role, 'count': count} for role, count in top_roles
        ]
        
        if other_count > 0:
            distribution_data.append({'role': 'Others', 'count': other_count})
        
        return jsonifyFormat({
            'status': 200,
            'data': distribution_data,
            'message': 'Role distribution retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve role distribution'
        }, 500)

@hr_bp.get('/recent-activities', tags=[dashboard_tag], security=[{"jwt": []}])
@jwt_required()
def get_recent_activities():
    """Get recent activities feed"""
    try:
        company_id = request.args.get('company_id', 'all')
        limit = int(request.args.get('limit', 20))
        
        # Build query for recent HR actions (excluding annual leave)
        query = HRAction.query.join(Employee).filter(
            HRAction.action_type.in_([
                'disciplinary_action', 'leave_maternity', 'leave_sick', 
                'status_change', 'contract_update', 'salary_change',
                'exit_processing'
            ])
        )
        
        if company_id != 'all':
            query = query.filter(Employee.company_id == company_id)
        
        recent_activities = query.order_by(
            HRAction.action_date.desc()
        ).limit(limit).all()
        
        activities_data = []
        for activity in recent_activities:
            activities_data.append({
                'id': activity.id,
                'employee_name': f"{activity.employee.first_name} {activity.employee.last_name}",
                'action_type': activity.action_type,
                'action_date': activity.action_date.isoformat(),
                'summary': activity.summary,
                'icon': _get_action_icon(activity.action_type)
            })
        
        return jsonifyFormat({
            'status': 200,
            'data': activities_data,
            'message': 'Recent activities retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve recent activities'
        }, 500)

@hr_bp.get('/supervisors-on-leave', tags=[dashboard_tag], security=[{"jwt": []}])
@jwt_required()
def get_supervisors_on_leave():
    """Get supervisors currently on leave"""
    try:
        company_id = request.args.get('company_id', 'all')
        
        # Find supervisors/managers (simplified - look for titles containing supervisor/manager)
        supervisor_query = LeaveRecord.query.join(Employee).filter(
            and_(
                LeaveRecord.status.in_(['approved', 'completed']),
                LeaveRecord.start_date <= datetime.now().date(),
                LeaveRecord.end_date >= datetime.now().date(),
                db.or_(
                    Employee.position.ilike('%supervisor%'),
                    Employee.position.ilike('%manager%'),
                    Employee.position.ilike('%director%'),
                    Employee.position.ilike('%head%')
                )
            )
        )
        
        if company_id != 'all':
            supervisor_query = supervisor_query.filter(Employee.company_id == company_id)
        
        supervisors_on_leave = supervisor_query.all()
        
        supervisors_data = []
        for leave in supervisors_on_leave:
            supervisors_data.append({
                'id': leave.employee.id,
                'name': f"{leave.employee.first_name} {leave.employee.last_name}",
                'position': leave.employee.position,
                'leave_type': leave.leave_type,
                'start_date': leave.start_date.isoformat(),
                'end_date': leave.end_date.isoformat(),
                'return_date': leave.return_to_work_date.isoformat() if leave.return_to_work_date else leave.end_date.isoformat()
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

def _get_action_icon(action_type):
    """Get icon for action type"""
    icons = {
        'disciplinary_action': '⚖️',
        'leave_maternity': '👶',
        'leave_sick': '🏥',
        'status_change': '🔄',
        'contract_update': '📝',
        'salary_change': '💰',
        'exit_processing': '🚪'
    }
    return icons.get(action_type, '📋')