# controllers/reports/reports.py
from flask import Blueprint, request, jsonify
from flask_openapi3 import APIBlueprint, Tag
from ...addons.extensions import db
from ...models import Employee, Company, LeaveRecord, DisciplinaryRecord, HRAction
from ...addons.functions import jsonifyFormat
from datetime import datetime, timedelta
from sqlalchemy import and_, or_, func
import csv
from io import StringIO

reports_bp = APIBlueprint('reports', __name__, url_prefix='/api/reports')

reports_tag = Tag(name="Reports", description="Reporting and analytics")

@reports_bp.get('/employees', tags=[reports_tag])
def get_employee_report():
    """Generate employee report"""
    try:
        # Get query parameters
        company_id = request.args.get('company_id')
        department = request.args.get('department')
        status = request.args.get('status')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        export_format = request.args.get('format', 'json')  # json, csv
        
        # Build query
        query = Employee.query
        
        if company_id and company_id != 'all':
            query = query.filter_by(company_id=company_id)
        
        if department:
            query = query.filter_by(department=department)
        
        if status and status != 'all':
            if status == 'active':
                query = query.filter(Employee.employment_status.in_(['Active', 'Probation']))
            else:
                query = query.filter_by(employment_status=status)
        
        if start_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(Employee.start_date >= start_date_obj)
        
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(Employee.start_date <= end_date_obj)
        
        employees = query.all()
        
        # Prepare report data
        report_data = []
        for employee in employees:
            # Calculate tenure in months
            tenure_days = (datetime.now().date() - employee.start_date).days
            tenure_months = round(tenure_days / 30.44, 1)
            
            employee_data = employee.to_dict()
            employee_data.update({
                'tenure_months': tenure_months,
                'company_name': employee.company.name if employee.company else None
            })
            report_data.append(employee_data)
        
        # Export to CSV if requested
        if export_format == 'csv':
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header
            headers = ['Employee ID', 'Name', 'Email', 'Phone', 'Company', 'Department', 
                      'Position', 'Employment Type', 'Employment Status', 'Start Date', 
                      'Tenure (Months)', 'Salary', 'Currency', 'Live Disciplinary']
            writer.writerow(headers)
            
            # Write data
            for employee in report_data:
                writer.writerow([
                    employee['id'],
                    f"{employee['first_name']} {employee['last_name']}",
                    employee['email'],
                    employee['phone'],
                    employee['company_name'],
                    employee['department'],
                    employee['position'],
                    employee['employment_type'],
                    employee['employment_status'],
                    employee['start_date'],
                    employee['tenure_months'],
                    employee['salary'],
                    employee['salary_currency'],
                    'Yes' if employee['has_live_disciplinary'] else 'No'
                ])
            
            return jsonifyFormat({
                'status': 200,
                'data': output.getvalue(),
                'format': 'csv',
                'message': 'Employee report generated successfully'
            }, 200)
        
        return jsonifyFormat({
            'status': 200,
            'data': report_data,
            'total_count': len(report_data),
            'message': 'Employee report generated successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to generate employee report'
        }, 500)

@reports_bp.get('/payroll', tags=[reports_tag])
def get_payroll_report():
    """Generate payroll report"""
    try:
        # Get query parameters
        company_id = request.args.get('company_id')
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        export_format = request.args.get('format', 'json')
        
        # This is a simplified version - in production, you'd join with actual payroll data
        query = Employee.query.filter(
            Employee.employment_status.in_(['Active', 'Probation'])
        )
        
        if company_id and company_id != 'all':
            query = query.filter_by(company_id=company_id)
        
        employees = query.all()
        
        # Prepare payroll data
        payroll_data = []
        total_base_salary = 0
        total_net_pay = 0
        
        for employee in employees:
            base_salary = float(employee.salary)
            allowances = base_salary * 0.1  # Simplified: 10% allowances
            deductions = base_salary * 0.15  # Simplified: 15% deductions (tax, pension, etc.)
            overtime = base_salary * 0.05  # Simplified: 5% overtime
            net_pay = base_salary + allowances + overtime - deductions
            
            payroll_data.append({
                'employee_id': employee.id,
                'employee_name': f"{employee.first_name} {employee.last_name}",
                'company': employee.company.name if employee.company else None,
                'department': employee.department,
                'position': employee.position,
                'base_salary': base_salary,
                'allowances': allowances,
                'deductions': deductions,
                'overtime': overtime,
                'net_pay': net_pay,
                'currency': employee.salary_currency,
                'payment_status': 'Pending'  # Simplified status
            })
            
            total_base_salary += base_salary
            total_net_pay += net_pay
        
        # Export to CSV if requested
        if export_format == 'csv':
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header
            headers = ['Employee ID', 'Name', 'Company', 'Department', 'Position', 
                      'Base Salary', 'Allowances', 'Deductions', 'Overtime', 
                      'Net Pay', 'Currency', 'Payment Status']
            writer.writerow(headers)
            
            # Write data
            for payroll in payroll_data:
                writer.writerow([
                    payroll['employee_id'],
                    payroll['employee_name'],
                    payroll['company'],
                    payroll['department'],
                    payroll['position'],
                    payroll['base_salary'],
                    payroll['allowances'],
                    payroll['deductions'],
                    payroll['overtime'],
                    payroll['net_pay'],
                    payroll['currency'],
                    payroll['payment_status']
                ])
            
            return jsonifyFormat({
                'status': 200,
                'data': output.getvalue(),
                'format': 'csv',
                'message': 'Payroll report generated successfully'
            }, 200)
        
        return jsonifyFormat({
            'status': 200,
            'data': payroll_data,
            'summary': {
                'total_employees': len(payroll_data),
                'total_base_salary': total_base_salary,
                'total_net_pay': total_net_pay,
                'report_period': month
            },
            'message': 'Payroll report generated successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to generate payroll report'
        }, 500)

@reports_bp.get('/leave', tags=[reports_tag])
def get_leave_report():
    """Generate leave report"""
    try:
        # Get query parameters
        company_id = request.args.get('company_id')
        leave_type = request.args.get('leave_type')
        status = request.args.get('status')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        export_format = request.args.get('format', 'json')
        
        # Build query
        query = LeaveRecord.query.join(Employee)
        
        if company_id and company_id != 'all':
            query = query.filter(Employee.company_id == company_id)
        
        if leave_type:
            query = query.filter(LeaveRecord.leave_type == leave_type)
        
        if status:
            query = query.filter(LeaveRecord.status == status)
        
        if start_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(LeaveRecord.start_date >= start_date_obj)
        
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(LeaveRecord.end_date <= end_date_obj)
        
        leave_records = query.all()
        
        # Prepare report data
        report_data = []
        for leave in leave_records:
            report_data.append({
                'id': leave.id,
                'employee_name': f"{leave.employee.first_name} {leave.employee.last_name}",
                'company': leave.employee.company.name if leave.employee.company else None,
                'department': leave.employee.department,
                'leave_type': leave.leave_type,
                'start_date': leave.start_date.isoformat(),
                'end_date': leave.end_date.isoformat(),
                'days_count': leave.days_count,
                'status': leave.status,
                'approved_by': leave.approved_by,
                'return_to_work_date': leave.return_to_work_date.isoformat() if leave.return_to_work_date else None,
                'comments': leave.comments
            })
        
        # Export to CSV if requested
        if export_format == 'csv':
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header
            headers = ['Employee Name', 'Company', 'Department', 'Leave Type', 
                      'Start Date', 'End Date', 'Days Count', 'Status', 
                      'Return to Work Date', 'Comments']
            writer.writerow(headers)
            
            # Write data
            for leave in report_data:
                writer.writerow([
                    leave['employee_name'],
                    leave['company'],
                    leave['department'],
                    leave['leave_type'],
                    leave['start_date'],
                    leave['end_date'],
                    leave['days_count'],
                    leave['status'],
                    leave['return_to_work_date'],
                    leave['comments'] or ''
                ])
            
            return jsonifyFormat({
                'status': 200,
                'data': output.getvalue(),
                'format': 'csv',
                'message': 'Leave report generated successfully'
            }, 200)
        
        return jsonifyFormat({
            'status': 200,
            'data': report_data,
            'total_count': len(report_data),
            'message': 'Leave report generated successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to generate leave report'
        }, 500)

@reports_bp.get('/disciplinary', tags=[reports_tag])
def get_disciplinary_report():
    """Generate disciplinary report"""
    try:
        # Get query parameters
        company_id = request.args.get('company_id')
        disciplinary_type = request.args.get('type')
        status = request.args.get('status')  # active, expired
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        export_format = request.args.get('format', 'json')
        
        # Build query
        query = DisciplinaryRecord.query.join(Employee)
        
        if company_id and company_id != 'all':
            query = query.filter(Employee.company_id == company_id)
        
        if disciplinary_type:
            query = query.filter(DisciplinaryRecord.type == disciplinary_type)
        
        if status == 'active':
            query = query.filter(DisciplinaryRecord.is_active == True)
        elif status == 'expired':
            query = query.filter(DisciplinaryRecord.is_active == False)
        
        if start_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(DisciplinaryRecord.issued_date >= start_date_obj)
        
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(DisciplinaryRecord.issued_date <= end_date_obj)
        
        disciplinary_records = query.all()
        
        # Prepare report data
        report_data = []
        for record in disciplinary_records:
            report_data.append({
                'id': record.id,
                'employee_name': f"{record.employee.first_name} {record.employee.last_name}",
                'company': record.employee.company.name if record.employee.company else None,
                'department': record.employee.department,
                'type': record.type,
                'reason': record.reason,
                'issued_date': record.issued_date.isoformat(),
                'valid_until': record.valid_until.isoformat(),
                'is_active': record.is_active,
                'issued_by': record.issued_by,
                'document_uploaded': bool(record.document_url),
                'comments': record.comments
            })
        
        # Export to CSV if requested
        if export_format == 'csv':
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header
            headers = ['Employee Name', 'Company', 'Department', 'Type', 'Reason', 
                      'Issued Date', 'Valid Until', 'Status', 'Issued By', 
                      'Document Uploaded', 'Comments']
            writer.writerow(headers)
            
            # Write data
            for record in report_data:
                writer.writerow([
                    record['employee_name'],
                    record['company'],
                    record['department'],
                    record['type'].replace('_', ' ').title(),
                    record['reason'],
                    record['issued_date'],
                    record['valid_until'],
                    'Active' if record['is_active'] else 'Expired',
                    record['issued_by'],
                    'Yes' if record['document_uploaded'] else 'No',
                    record['comments'] or ''
                ])
            
            return jsonifyFormat({
                'status': 200,
                'data': output.getvalue(),
                'format': 'csv',
                'message': 'Disciplinary report generated successfully'
            }, 200)
        
        return jsonifyFormat({
            'status': 200,
            'data': report_data,
            'total_count': len(report_data),
            'message': 'Disciplinary report generated successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to generate disciplinary report'
        }, 500)