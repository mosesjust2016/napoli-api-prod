# controllers/attendance_controller.py
from flask_openapi3 import APIBlueprint, Tag
from flask import request, jsonify
from flask_jwt_extended import jwt_required
from datetime import datetime
import csv
from io import TextIOWrapper
from pydantic import BaseModel, Field
from typing import List, Optional

# Fix import paths - use absolute imports from the root
from core.addons.extensions import db
from core.models.employees import Employee
from core.models.attendanceModel import Attendance

# Create blueprint with OpenAPI documentation
attendance_tag = Tag(name="Attendance & Payroll", description="Attendance tracking and payroll processing")
attendance_bp = APIBlueprint(
    'attendance_payroll', __name__, url_prefix='/api', abp_tags=[attendance_tag]
)

# ======================================================
#                   SCHEMAS
# ======================================================

class _AttendanceRecordResponse(BaseModel):
    id: int = Field(..., description="Attendance record ID")
    employee_id: int = Field(..., description="Employee ID")
    date: str = Field(..., description="Date of attendance (YYYY-MM-DD)")
    check_in: Optional[str] = Field(None, description="Check-in time")
    check_out: Optional[str] = Field(None, description="Check-out time")
    hours_worked: float = Field(..., description="Hours worked")
    status: str = Field(..., description="Attendance status")

class _MarkAttendanceRequest(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    check_in: Optional[str] = Field(None, description="Check-in time (ISO format)")
    check_out: Optional[str] = Field(None, description="Check-out time (ISO format)")
    status: str = Field("Present", description="Attendance status")

class _MarkAttendanceResponse(BaseModel):
    message: str = Field(..., description="Status message")

class _BulkAttendanceResponse(BaseModel):
    message: str = Field(..., description="Status message")
    records_processed: int = Field(..., description="Number of records successfully processed")
    records_failed: int = Field(..., description="Number of records that failed")

class _PayrollEmployeeResponse(BaseModel):
    employee_id: str = Field(..., description="Employee ID")
    name: str = Field(..., description="Employee name")
    position: str = Field(..., description="Employee position")
    salary: float = Field(..., description="Basic salary")
    payment_frequency: str = Field(..., description="Payment frequency")
    hours_worked: float = Field(..., description="Total hours worked")

class _ProcessPayrollRequest(BaseModel):
    company_id: int = Field(..., description="Company ID")
    period: str = Field(..., description="Payroll period (YYYY-MM)")

class _PayrollRecordResponse(BaseModel):
    employee_id: str = Field(..., description="Employee ID")
    name: str = Field(..., description="Employee name")
    basic_salary: float = Field(..., description="Basic salary")
    hours_worked: float = Field(..., description="Hours worked")
    gross_pay: float = Field(..., description="Gross pay")

class _ErrorResponse(BaseModel):
    status: int = Field(..., description="HTTP status code")
    isError: bool = Field(True, description="Indicates if the response is an error")
    message: str = Field(..., description="Error message")

class _CompanyIdPath(BaseModel):
    company_id: int = Field(..., description="Company ID")

class _AttendanceQuery(BaseModel):
    company_id: int = Field(..., description="Company ID")
    date: str = Field(..., description="Date (YYYY-MM-DD)")

class _PayrollEmployeesQuery(BaseModel):
    company_id: int = Field(..., description="Company ID")
    period: str = Field(..., description="Payroll period (YYYY-MM)")

# ======================================================
#                   UTILITY FUNCTIONS
# ======================================================

def calculate_hours_worked(check_in, check_out):
    """Calculate hours worked from check-in and check-out times."""
    if check_in and check_out:
        return (check_out - check_in).total_seconds() / 3600
    return 0.0

def validate_csv_row(row):
    """Validate and parse CSV row data."""
    try:
        if not row.get('employee_id') or not row.get('date'):
            return None
        
        employee_id = int(row['employee_id'])
        date_str = row['date']
        check_in_str = row.get('check_in', '').strip() or None
        check_out_str = row.get('check_out', '').strip() or None
        status = row.get('status', 'Present')

        # Parse dates
        date = datetime.fromisoformat(date_str).date()
        check_in = datetime.fromisoformat(check_in_str) if check_in_str else None
        check_out = datetime.fromisoformat(check_out_str) if check_out_str else None

        return {
            'employee_id': employee_id,
            'date': date,
            'check_in': check_in,
            'check_out': check_out,
            'status': status
        }
    except Exception:
        return None

# ======================================================
#                   CONTROLLER ENDPOINTS
# ======================================================

@attendance_bp.get(
    "/companies/<int:company_id>/employees",
    responses={"200": None, "400": _ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def get_employees_by_company(path: _CompanyIdPath):
    """Get all employees for a company
    Returns a list of employees belonging to the specified company.
    """
    try:
        company_id = path.company_id
        employees = Employee.query.filter_by(company_id=company_id).all()
        return jsonify([emp.to_dict() for emp in employees]), 200
    except Exception as e:
        return jsonify({"status": 500, "isError": True, "message": f"Error retrieving employees: {str(e)}"}), 500

@attendance_bp.get(
    "/attendance",
    responses={"200": None, "400": _ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def get_attendance(query: _AttendanceQuery):
    """Get attendance records for a company and date
    Returns attendance records filtered by company and specific date.
    """
    try:
        company_id = query.company_id
        date = query.date

        if not company_id or not date:
            return jsonify({"status": 400, "isError": True, "message": "company_id and date are required"}), 400

        attendance_records = Attendance.get_attendance_by_company_and_date(company_id, date)
        return jsonify([rec.to_dict() for rec in attendance_records]), 200

    except Exception as e:
        return jsonify({"status": 500, "isError": True, "message": f"Error retrieving attendance: {str(e)}"}), 500

@attendance_bp.post(
    "/attendance/mark",
    responses={"200": _MarkAttendanceResponse, "400": _ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def mark_attendance(body: _MarkAttendanceRequest):
    """Mark attendance for an employee
    Creates or updates an attendance record for a specific employee and date.
    """
    try:
        employee_id = body.employee_id
        date = body.date
        check_in = body.check_in
        check_out = body.check_out
        status = body.status

        # Check if employee exists
        employee = Employee.query.filter_by(id=employee_id).first()
        if not employee:
            return jsonify({"status": 404, "isError": True, "message": "Employee not found"}), 404

        # Check if attendance record already exists
        existing_attendance = Attendance.find_existing_record(
            employee_id, 
            datetime.fromisoformat(date).date()
        )
        
        if existing_attendance:
            # Update existing record
            if check_in:
                existing_attendance.check_in = datetime.fromisoformat(check_in) if check_in else None
            if check_out:
                existing_attendance.check_out = datetime.fromisoformat(check_out) if check_out else None
            if status:
                existing_attendance.status = status
            
            # Recalculate hours worked
            existing_attendance.hours_worked = calculate_hours_worked(
                existing_attendance.check_in, 
                existing_attendance.check_out
            )
            
            attendance = existing_attendance
        else:
            # Create new record
            attendance = Attendance(
                employee_id=employee_id,
                date=datetime.fromisoformat(date).date(),
                check_in=datetime.fromisoformat(check_in) if check_in else None,
                check_out=datetime.fromisoformat(check_out) if check_out else None,
                status=status
            )

            # Calculate hours worked
            attendance.hours_worked = calculate_hours_worked(
                attendance.check_in, 
                attendance.check_out
            )

        db.session.add(attendance)
        db.session.commit()

        return jsonify({"message": "Attendance recorded successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": 500, "isError": True, "message": f"Error recording attendance: {str(e)}"}), 500

@attendance_bp.post(
    "/attendance/bulk",
    responses={"200": _BulkAttendanceResponse, "400": _ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def upload_bulk_attendance():
    """Bulk upload attendance records
    Processes a CSV file containing multiple attendance records.
    Expected CSV columns: employee_id, date, check_in, check_out, status
    """
    try:
        if 'file' not in request.files:
            return jsonify({"status": 400, "isError": True, "message": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == '':
            return jsonify({"status": 400, "isError": True, "message": "No file selected"}), 400

        if not file.filename.lower().endswith('.csv'):
            return jsonify({"status": 400, "isError": True, "message": "Only CSV files are supported"}), 400

        # Read and process CSV file
        csv_file = TextIOWrapper(file.stream, encoding='utf-8')
        csv_reader = csv.DictReader(csv_file)
        
        records_processed = 0
        records_failed = 0
        
        for row_num, row in enumerate(csv_reader, start=2):
            try:
                # Validate and parse row data
                row_data = validate_csv_row(row)
                if not row_data:
                    records_failed += 1
                    continue
                
                # Check if employee exists
                employee = Employee.query.filter_by(id=row_data['employee_id']).first()
                if not employee:
                    records_failed += 1
                    continue

                # Calculate hours worked
                hours_worked = calculate_hours_worked(
                    row_data['check_in'], 
                    row_data['check_out']
                )

                # Check for existing record
                existing_record = Attendance.find_existing_record(
                    row_data['employee_id'], 
                    row_data['date']
                )

                if existing_record:
                    # Update existing record
                    existing_record.check_in = row_data['check_in']
                    existing_record.check_out = row_data['check_out']
                    existing_record.hours_worked = hours_worked
                    existing_record.status = row_data['status']
                else:
                    # Create new record
                    attendance = Attendance(
                        employee_id=row_data['employee_id'],
                        date=row_data['date'],
                        check_in=row_data['check_in'],
                        check_out=row_data['check_out'],
                        hours_worked=hours_worked,
                        status=row_data['status']
                    )
                    db.session.add(attendance)

                records_processed += 1

            except Exception as row_error:
                records_failed += 1
                print(f"Error processing row {row_num}: {row_error}")
                continue

        db.session.commit()
        
        return jsonify({
            "message": "Bulk attendance processing completed",
            "records_processed": records_processed,
            "records_failed": records_failed
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": 500, "isError": True, "message": f"Error processing bulk attendance: {str(e)}"}), 500

@attendance_bp.get(
    "/payroll/employees",
    responses={"200": None, "400": _ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def payroll_employees(query: _PayrollEmployeesQuery):
    """Get payroll employee list with hours worked
    Returns employees with their total hours worked for a specific period.
    """
    try:
        company_id = query.company_id
        period = query.period

        if not company_id or not period:
            return jsonify({"status": 400, "isError": True, "message": "company_id and period are required"}), 400

        employees = Employee.query.filter_by(company_id=company_id).all()
        results = []

        for emp in employees:
            total_hours = Attendance.get_employee_hours_for_period(emp.id, period)

            results.append({
                "employee_id": emp.employee_id,
                "name": f"{emp.first_name} {emp.last_name}",
                "position": emp.position,
                "salary": float(emp.salary),
                "payment_frequency": emp.payment_frequency,
                "hours_worked": round(total_hours, 2)
            })

        return jsonify(results), 200

    except Exception as e:
        return jsonify({"status": 500, "isError": True, "message": f"Error retrieving payroll data: {str(e)}"}), 500

@attendance_bp.post(
    "/payroll/process",
    responses={"200": None, "400": _ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def process_payroll(body: _ProcessPayrollRequest):
    """Process payroll for a company and period
    Calculates payroll for all employees in a company for the specified period.
    """
    try:
        company_id = body.company_id
        period = body.period

        employees = Employee.query.filter_by(company_id=company_id).all()
        payroll_output = []

        for emp in employees:
            hours = Attendance.get_employee_hours_for_period(emp.id, period)

            payroll_output.append({
                "employee_id": emp.employee_id,
                "name": f"{emp.first_name} {emp.last_name}",
                "basic_salary": float(emp.salary),
                "hours_worked": float(hours),
                "gross_pay": float(emp.salary),  # Basic implementation - can be enhanced with calculations
            })

        return jsonify(payroll_output), 200

    except Exception as e:
        return jsonify({"status": 500, "isError": True, "message": f"Error processing payroll: {str(e)}"}), 500