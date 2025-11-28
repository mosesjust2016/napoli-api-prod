# controllers/payroll/payroll_management.py
from flask_openapi3 import APIBlueprint, Tag
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

from ...addons.extensions import db
from ...addons.functions import jsonifyFormat
from ...models import PayrollRecord, PayrollBatch, Employee, Company, User
from ...addons.payroll_calculator import PayrollCalculator

# Define blueprint
payroll_bp = APIBlueprint('payroll', __name__, url_prefix='/api/payroll')

payroll_tag = Tag(name="Payroll", description="Payroll management & processing")

# ---------------------- REQUEST SCHEMAS ---------------------- #
class PayrollRecordsQuery(BaseModel):
    period: Optional[str] = Field(None, description="Format: YYYY-MM")
    periodType: str = Field(..., description="monthly or ytd")
    department: Optional[str] = Field(None, description="Department filter")
    employeeId: Optional[str] = Field(None, description="Employee ID filter")
    status: Optional[str] = Field(None, description="Pending, Processed, or Paid")
    companyId: Optional[str] = Field(None, description="Company ID filter")

class ComparisonQuery(BaseModel):
    startPeriod: str = Field(..., description="Format: YYYY-MM")
    endPeriod: str = Field(..., description="Format: YYYY-MM")
    companyId: Optional[str] = Field(None, description="Company ID filter")

class ProcessPayrollSchema(BaseModel):
    period: str = Field(..., description="Format: YYYY-MM")
    companyId: str = Field(..., description="Company ID")
    employeeIds: List[str] = Field([], description="List of employee IDs")
    processDate: str = Field(..., description="Process date")
    notes: Optional[str] = Field(None, description="Processing notes")

class GeneratePayslipSchema(BaseModel):
    employeeId: str = Field(..., description="Employee ID")
    period: str = Field(..., description="Format: YYYY-MM")
    format: str = Field("pdf", description="pdf or json")

class ExportPayrollSchema(BaseModel):
    period: str = Field(..., description="Format: YYYY-MM")
    periodType: str = Field("monthly", description="monthly or ytd")
    format: str = Field("csv", description="csv, xlsx, or pdf")
    includeFields: List[str] = Field([], description="Fields to include")
    department: Optional[str] = Field(None, description="Department filter")
    companyId: Optional[str] = Field(None, description="Company ID")

class MarkPaidSchema(BaseModel):
    period: str = Field(..., description="Format: YYYY-MM")
    employeeIds: List[str] = Field([], description="List of employee IDs")
    paymentDate: str = Field(..., description="Payment date")
    paymentReference: str = Field(..., description="Payment reference")
    bankTransactionId: Optional[str] = Field(None, description="Bank transaction ID")
    companyId: str = Field(..., description="Company ID")

class StatisticsQuery(BaseModel):
    startPeriod: str = Field(..., description="Format: YYYY-MM")
    endPeriod: str = Field(..., description="Format: YYYY-MM")
    companyId: Optional[str] = Field(None, description="Company ID filter")

class TaxComplianceQuery(BaseModel):
    period: str = Field(..., description="Format: YYYY-MM")
    companyId: str = Field(..., description="Company ID")

# ---------------------- RESPONSE SCHEMAS ---------------------- #
class SuccessResponse(BaseModel):
    success: bool = Field(True, description="Success status")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    message: Optional[str] = Field(None, description="Response message")

class ErrorResponse(BaseModel):
    success: bool = Field(False, description="Success status")
    error: str = Field(..., description="Error description")
    message: str = Field(..., description="Error message")
    details: Optional[Any] = Field(None, description="Error details")

# ---------------------- ENDPOINTS ---------------------- #

@payroll_bp.get('/records', tags=[payroll_tag], responses={200: SuccessResponse, 500: ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_payroll_records(query: PayrollRecordsQuery):
    """Get payroll records with filtering"""
    try:
        # Build query
        db_query = PayrollRecord.query.join(Employee)
        
        if query.period:
            db_query = db_query.filter(PayrollRecord.period == query.period)
        
        if query.periodType:
            db_query = db_query.filter(PayrollRecord.period_type == query.periodType)
        
        if query.department:
            db_query = db_query.filter(Employee.department.has(name=query.department))
        
        if query.employeeId:
            db_query = db_query.filter(PayrollRecord.employee_id == query.employeeId)
        
        if query.status:
            db_query = db_query.filter(PayrollRecord.status == query.status)
        
        if query.companyId:
            db_query = db_query.filter(PayrollRecord.company_id == query.companyId)
        
        records = db_query.all()
        
        # Calculate summary
        summary = {
            'totalGrossPay': sum(float(record.gross_pay) for record in records),
            'totalNetPay': sum(float(record.net_salary) for record in records),
            'companyNapsa': sum(float(record.company_contributions.get('napsa', 0)) for record in records),
            'companyNhima': sum(float(record.company_contributions.get('nhima', 0)) for record in records),
            'companySaturnia': sum(float(record.company_contributions.get('saturnia', 0)) for record in records),
            'totalCompanyCost': sum(float(record.gross_pay) + 
                                  float(record.company_contributions.get('napsa', 0)) +
                                  float(record.company_contributions.get('nhima', 0)) +
                                  float(record.company_contributions.get('saturnia', 0)) for record in records)
        }
        
        return jsonifyFormat({
            "success": True,
            "data": {
                "records": [record.to_dict() for record in records],
                "summary": summary
            }
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            "success": False,
            "error": "Failed to retrieve payroll records",
            "message": str(e)
        }, 500)

@payroll_bp.get('/comparison', tags=[payroll_tag], responses={200: SuccessResponse, 500: ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_comparison(query: ComparisonQuery):
    """Get month-on-month payroll comparison"""
    try:
        # This would typically query aggregated data from the database
        # For now, returning mock data structure
        comparison_data = [
            {
                "period": "2023-08",
                "grossPay": 435000,
                "netPay": 326250,
                "companyNapsa": 21750,
                "companyNhima": 4350,
                "companySaturnia": 10875,
                "totalCompanyCost": 472975,
                "employeeCount": 45,
                "changePercentage": 3.2
            },
            {
                "period": "2023-09",
                "grossPay": 448000,
                "netPay": 336000,
                "companyNapsa": 22400,
                "companyNhima": 4480,
                "companySaturnia": 11200,
                "totalCompanyCost": 486080,
                "employeeCount": 46,
                "changePercentage": 2.8
            }
        ]
        
        return jsonifyFormat({
            "success": True,
            "data": comparison_data
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            "success": False,
            "error": "Failed to retrieve comparison data",
            "message": str(e)
        }, 500)

@payroll_bp.post('/process', tags=[payroll_tag], responses={200: SuccessResponse, 400: ErrorResponse, 500: ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def process_payroll(body: ProcessPayrollSchema):
    """Process payroll for a specific period"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate period format
        try:
            datetime.strptime(body.period, '%Y-%m')
        except ValueError:
            return jsonifyFormat({
                "success": False,
                "error": "Invalid period format",
                "message": "Period must be in YYYY-MM format"
            }, 400)
        
        # Check if payroll already processed for this period
        existing = PayrollRecord.query.filter_by(
            period=body.period,
            company_id=body.companyId
        ).first()
        
        if existing and existing.status in ['Processed', 'Paid']:
            return jsonifyFormat({
                "success": False,
                "error": "Payroll already processed",
                "message": f"Payroll for period {body.period} has already been processed"
            }, 422)
        
        # Get employees to process
        employees_query = Employee.query.filter_by(company_id=body.companyId, is_active=True)
        if body.employeeIds:
            employees_query = employees_query.filter(Employee.employee_code.in_(body.employeeIds))
        
        employees = employees_query.all()
        
        # Validate employees have complete information
        invalid_employees = []
        for emp in employees:
            if not emp.bank_account_number or not emp.bank_name:
                invalid_employees.append(emp.employee_code)
        
        if invalid_employees:
            return jsonifyFormat({
                "success": False,
                "error": "Incomplete employee information",
                "message": "Some employees have incomplete banking information",
                "details": invalid_employees
            }, 422)
        
        # Process payroll for each employee
        processed_count = 0
        total_gross_pay = 0
        total_net_pay = 0
        total_company_contributions = 0
        
        for employee in employees:
            # Calculate payroll
            allowances = {
                'housing': float(employee.housing_allowance or 0),
                'transport': float(employee.transport_allowance or 0),
                'lunch': float(employee.lunch_allowance or 0)
            }
            
            payroll_data = PayrollCalculator.calculate_payroll(
                employee, 
                float(employee.basic_salary or 0),
                allowances
            )
            
            # Create payroll record
            payroll_record = PayrollRecord(
                employee_id=employee.employee_code,
                period=body.period,
                period_type='monthly',
                basic_salary=payroll_data['basic_salary'],
                allowances=payroll_data['allowances'],
                total_allowances=payroll_data['total_allowances'],
                gross_pay=payroll_data['gross_pay'],
                deductions=payroll_data['deductions'],
                total_deductions=payroll_data['total_deductions'],
                net_salary=payroll_data['net_salary'],
                company_contributions=payroll_data['company_contributions'],
                status='Processed',
                processed_date=datetime.utcnow(),
                company_id=body.companyId
            )
            
            db.session.add(payroll_record)
            
            # Update totals
            processed_count += 1
            total_gross_pay += payroll_data['gross_pay']
            total_net_pay += payroll_data['net_salary']
            total_company_contributions += (
                payroll_data['company_contributions']['napsa'] +
                payroll_data['company_contributions']['nhima'] +
                payroll_data['company_contributions']['saturnia']
            )
        
        # Create payroll batch record
        payroll_batch = PayrollBatch(
            period=body.period,
            company_id=body.companyId,
            processed_by=current_user_id,
            processed_count=processed_count,
            total_gross_pay=total_gross_pay,
            total_net_pay=total_net_pay,
            total_company_contributions=total_company_contributions,
            notes=body.notes,
            processed_at=datetime.utcnow()
        )
        
        db.session.add(payroll_batch)
        db.session.commit()
        
        # TODO: Send email notifications
        
        return jsonifyFormat({
            "success": True,
            "data": {
                "batchId": payroll_batch.id,
                "period": body.period,
                "processedCount": processed_count,
                "totalGrossPay": total_gross_pay,
                "totalNetPay": total_net_pay,
                "totalCompanyContributions": total_company_contributions,
                "processedAt": datetime.utcnow().isoformat()
            }
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            "success": False,
            "error": "Failed to process payroll",
            "message": str(e)
        }, 500)

@payroll_bp.post('/payslip/generate', tags=[payroll_tag], responses={200: SuccessResponse, 500: ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def generate_payslip(body: GeneratePayslipSchema):
    """Generate payslip for an employee"""
    try:
        # Get payroll record
        payroll_record = PayrollRecord.query.filter_by(
            employee_id=body.employeeId,
            period=body.period
        ).first()
        
        if not payroll_record:
            return jsonifyFormat({
                "success": False,
                "error": "Payroll record not found",
                "message": f"No payroll record found for employee {body.employeeId} in period {body.period}"
            }, 404)
        
        # Get employee details
        employee = payroll_record.employee
        
        payslip_data = {
            "employee": {
                "id": employee.employee_code,
                "name": f"{employee.first_name} {employee.last_name}",
                "department": employee.department.name if employee.department else "",
                "position": employee.position,
                "napsaNumber": employee.napsa_number,
                "nhimaNumber": employee.nhima_number,
                "bankAccount": employee.bank_account_number
            },
            "period": payroll_record.period,
            "earnings": {
                "basicSalary": float(payroll_record.basic_salary),
                "housingAllowance": payroll_record.allowances.get('housing', 0),
                "transportAllowance": payroll_record.allowances.get('transport', 0),
                "lunchAllowance": payroll_record.allowances.get('lunch', 0),
                "grossPay": float(payroll_record.gross_pay)
            },
            "deductions": {
                "paye": payroll_record.deductions.get('paye', 0),
                "napsa": payroll_record.deductions.get('employee_napsa', 0),
                "nhima": payroll_record.deductions.get('employee_nhima', 0),
                "saturnia": payroll_record.deductions.get('employee_saturnia', 0),
                "totalDeductions": float(payroll_record.total_deductions)
            },
            "netPay": float(payroll_record.net_salary),
            "companyContributions": payroll_record.company_contributions
        }
        
        if body.format == "pdf":
            # TODO: Generate PDF and return URL
            payslip_url = f"https://storage.example.com/payslips/{body.employeeId}_{body.period}.pdf"
            return jsonifyFormat({
                "success": True,
                "data": {
                    "payslipUrl": payslip_url,
                    "payslipData": payslip_data
                }
            }, 200)
        else:
            return jsonifyFormat({
                "success": True,
                "data": {
                    "payslipData": payslip_data
                }
            }, 200)
            
    except Exception as e:
        return jsonifyFormat({
            "success": False,
            "error": "Failed to generate payslip",
            "message": str(e)
        }, 500)

@payroll_bp.post('/mark-paid', tags=[payroll_tag], responses={200: SuccessResponse, 500: ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def mark_payroll_paid(body: MarkPaidSchema):
    """Mark payroll records as paid"""
    try:
        # Get payroll records
        query = PayrollRecord.query.filter_by(
            period=body.period,
            company_id=body.companyId,
            status='Processed'
        )
        
        if body.employeeIds:
            query = query.filter(PayrollRecord.employee_id.in_(body.employeeIds))
        
        records = query.all()
        
        if not records:
            return jsonifyFormat({
                "success": False,
                "error": "No records found",
                "message": f"No processed payroll records found for period {body.period}"
            }, 404)
        
        # Update records
        updated_count = 0
        total_amount_paid = 0
        
        for record in records:
            record.status = 'Paid'
            record.paid_date = datetime.strptime(body.paymentDate, '%Y-%m-%d')
            record.payment_reference = body.paymentReference
            record.bank_transaction_id = body.bankTransactionId
            total_amount_paid += float(record.net_salary)
            updated_count += 1
        
        db.session.commit()
        
        return jsonifyFormat({
            "success": True,
            "data": {
                "updatedCount": updated_count,
                "period": body.period,
                "paymentDate": body.paymentDate,
                "totalAmountPaid": total_amount_paid
            }
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            "success": False,
            "error": "Failed to mark payroll as paid",
            "message": str(e)
        }, 500)

# Additional endpoints (statistics, compliance, export) would follow similar patterns...

@payroll_bp.get('/statistics', tags=[payroll_tag], responses={200: SuccessResponse, 500: ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_payroll_statistics(query: StatisticsQuery):
    """Get payroll statistics"""
    try:
        # Implementation for statistics endpoint
        return jsonifyFormat({
            "success": True,
            "data": {
                "totalPeriods": 6,
                "averageGrossPay": 468333,
                "averageNetPay": 351250,
                "averageCompanyContributions": 40083,
                "growthRate": 8.2
            }
        }, 200)
    except Exception as e:
        return jsonifyFormat({
            "success": False,
            "error": "Failed to retrieve statistics",
            "message": str(e)
        }, 500)

@payroll_bp.get('/compliance/tax', tags=[payroll_tag], responses={200: SuccessResponse, 500: ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_tax_compliance_report(query: TaxComplianceQuery):
    """Get tax compliance report"""
    try:
        # Implementation for tax compliance report
        return jsonifyFormat({
            "success": True,
            "data": {
                "period": query.period,
                "payeSummary": {
                    "totalEmployees": 45,
                    "totalGrossIncome": 506000,
                    "totalPayeDeducted": 78000
                }
            }
        }, 200)
    except Exception as e:
        return jsonifyFormat({
            "success": False,
            "error": "Failed to generate compliance report",
            "message": str(e)
        }, 500)