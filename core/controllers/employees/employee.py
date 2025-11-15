from flask_openapi3 import APIBlueprint, Tag
from flask import jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy import func, desc, and_, or_
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
from typing import List, Optional, Dict, Any, Union
import os
import secrets
import base64
import uuid
from docx import Document
from num2words import num2words
from werkzeug.utils import secure_filename

# Fixed imports
from core.addons.extensions import db
from core.models.employees import Employee
from core.models.companies import Company
from core.models.hr_actions import HRAction
from core.models.employee_documents import EmployeeDocument
from core.models.users import User
from core.models.auditLogModel import AuditLog

employee_tag = Tag(name="Employees", description="Employee management operations")
employee_bp = APIBlueprint(
    'employee', __name__, url_prefix='/api/employees', abp_tags=[employee_tag]
)

# ---------------------- EMPLOYEE ID GENERATION ---------------------- #
def generate_employee_id(company_id: int) -> str:
    """
    Generate employee ID in format: {COMPANY_PREFIX}{SEQUENCE_NUMBER}
    Example: AMA001, AMA002, NAP001, etc.
    """
    try:
        # Get company prefix from database
        company = Company.query.get(company_id)
        if not company:
            raise ValueError(f"Company with ID {company_id} not found")
        
        # Get company prefix - use custom prefix if available, otherwise generate from name
        if hasattr(company, 'employee_id_prefix') and company.employee_id_prefix:
            prefix = company.employee_id_prefix.upper()
        else:
            # Generate prefix from company name (first 3 characters uppercase)
            prefix = company.name[:3].upper().replace(' ', '')
            # Ensure we have at least 3 characters
            if len(prefix) < 3:
                prefix = prefix.ljust(3, 'X')
        
        # Get the last employee ID for this company
        last_employee = Employee.query.filter(
            Employee.company_id == company_id,
            Employee.employee_id.like(f"{prefix}%")
        ).order_by(Employee.id.desc()).first()
        
        if last_employee and last_employee.employee_id:
            # Extract the numeric part and increment
            last_id = last_employee.employee_id
            # Remove prefix and get numeric part
            numeric_part = last_id.replace(prefix, "")
            try:
                next_number = int(numeric_part) + 1
            except ValueError:
                next_number = 1
        else:
            # First employee for this company
            next_number = 1
        
        # Format with leading zeros (AMA001, AMA002, etc.)
        return f"{prefix}{next_number:03d}"
        
    except Exception as e:
        print(f"Error generating employee ID: {str(e)}")
        # Fallback: use timestamp-based ID
        return f"EMP{int(datetime.now().timestamp())}"

# ---------------------- DOCUMENT HANDLING FUNCTIONS ---------------------- #
def create_documents_directory(employee_id: int) -> str:
    """Create directory structure for employee documents"""
    try:
        # Base documents directory - using Napoli HR Folders structure
        base_dir = "/app/Napoli HR Folders"
        os.makedirs(base_dir, exist_ok=True)
        
        # Employee-specific directory
        employee_dir = os.path.join(base_dir, f"Employee_{employee_id}")
        os.makedirs(employee_dir, exist_ok=True)
            
        return employee_dir
        
    except Exception as e:
        print(f"Error creating documents directory: {str(e)}")
        return "/app/Napoli HR Folders"

def handle_employee_documents(employee_id: int, documents_data: Dict[str, Any], uploaded_by: int) -> List[EmployeeDocument]:
    """Handle saving uploaded documents to file system and database"""
    saved_documents = []
    
    # Create employee documents directory
    employee_dir = create_documents_directory(employee_id)
    
    # Document type mapping - using your EmployeeDocument ENUM values
    document_type_mapping = {
        'profilePhoto': 'id_card',  # Maps to 'id_card' in your ENUM
        'nrcCopy': 'id_card',       # Maps to 'id_card' in your ENUM  
        'cv': 'resume',             # Maps to 'resume' in your ENUM
        'offerLetter': 'contract',  # Maps to 'contract' in your ENUM
        'certificates': 'certificate' # Maps to 'certificate' in your ENUM
    }
    
    for doc_key, doc_data in documents_data.items():
        try:
            # Handle single documents
            if doc_key in ['profilePhoto', 'nrcCopy', 'cv', 'offerLetter'] and doc_data:
                saved_doc = save_base64_document(
                    employee_id=employee_id,
                    base64_data=doc_data,
                    document_type=document_type_mapping[doc_key],
                    document_name=f"{document_type_mapping[doc_key].replace('_', ' ').title()}",
                    uploaded_by=uploaded_by,
                    employee_dir=employee_dir,
                    doc_key=doc_key
                )
                if saved_doc:
                    saved_documents.append(saved_doc)
            
            # Handle certificates array
            elif doc_key == 'certificates' and doc_data:
                for i, cert_data in enumerate(doc_data):
                    if cert_data:
                        saved_cert = save_base64_document(
                            employee_id=employee_id,
                            base64_data=cert_data,
                            document_type='certificate',
                            document_name=f"Certificate {i+1}",
                            uploaded_by=uploaded_by,
                            employee_dir=employee_dir,
                            doc_key=f"certificate_{i+1}"
                        )
                        if saved_cert:
                            saved_documents.append(saved_cert)
                            
        except Exception as e:
            print(f"Error processing document {doc_key}: {str(e)}")
            continue
    
    return saved_documents

def save_base64_document(employee_id: int, base64_data: str, document_type: str, 
                        document_name: str, uploaded_by: int, employee_dir: str, doc_key: str) -> Optional[EmployeeDocument]:
    """Save base64 document to file system and database"""
    try:
        # Extract file extension from base64 data
        if base64_data.startswith('data:'):
            # data:image/png;base64,iVBORw0KGgoAAA...
            header = base64_data.split(';')[0]
            mime_type = header.split(':')[1] if ':' in header else header
            
            # Map MIME types to file extensions
            mime_to_extension = {
                'image/png': 'png',
                'image/jpeg': 'jpg',
                'image/jpg': 'jpg',
                'application/pdf': 'pdf',
                'application/msword': 'doc',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx'
            }
            
            file_extension = mime_to_extension.get(mime_type, 'bin')
            
            # Extract the actual base64 data
            base64_data = base64_data.split(',')[1]
        else:
            file_extension = 'bin'
        
        # Fix base64 padding issues
        # Add padding if necessary
        padding = len(base64_data) % 4
        if padding:
            base64_data += '=' * (4 - padding)
        
        # Decode base64 data
        file_data = base64.b64decode(base64_data)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{doc_key}_{employee_id}_{timestamp}.{file_extension}"
        file_path = os.path.join(employee_dir, filename)
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
        # Save to database using your EmployeeDocument model
        document = EmployeeDocument(
            employee_id=employee_id,
            document_type=document_type,
            document_name=document_name,
            file_url=file_path,  # Store the file path
            upload_date=datetime.now(),
            uploaded_by=uploaded_by,
            is_verified=True,  # Auto-verify uploaded documents during creation
            verified_by=uploaded_by,
            comments=f"Uploaded during employee creation: {document_name}",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        db.session.add(document)
        db.session.flush()
        
        print(f"DEBUG: Saved document {document_name} to {file_path}")
        return document
        
    except Exception as e:
        print(f"Error saving base64 document {document_name}: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return None

def save_document_to_database(employee_id: int, document_type: str, file_path: str, uploaded_by: int, document_name: str, comments: str = None, expiry_date: datetime = None) -> Optional[EmployeeDocument]:
    """Save document record to database with proper ENUM values matching the table structure"""
    try:
        # Map document types to database ENUM values - using your EmployeeDocument ENUM
        document_type_mapping = {
            'new_joiner_form': 'other',  # Maps to 'other' in your ENUM
            'employment_contract': 'contract'  # Maps to 'contract' in your ENUM
        }
        
        db_document_type = document_type_mapping.get(document_type, 'other')
        
        document = EmployeeDocument(
            employee_id=employee_id,
            document_type=db_document_type,
            document_name=document_name,
            file_url=file_path,  # Store the actual file path
            upload_date=datetime.now(),
            uploaded_by=uploaded_by,
            expiry_date=expiry_date,
            is_verified=True,  # Auto-verify system-generated documents
            verified_by=uploaded_by,
            comments=comments or f"Automatically generated {document_name}",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        db.session.add(document)
        db.session.flush()
        print(f"DEBUG: Document saved to database: {document_name} with type: {db_document_type}")
        return document
        
    except Exception as e:
        print(f"Error saving document to database: {str(e)}")
        db.session.rollback()
        return None

def generate_documents_from_templates(employee: Employee, company: Company, documents_data: Dict[str, Any] = None) -> Dict[str, str]:
    """Generate documents using template files and save to employee folder"""
    documents_data = documents_data or {}
    
    # Create employee folder structure
    employee_dir = create_documents_directory(employee.id)
    generated_docs = {
        'new_joiner_form': None,
        'employment_contract': None,
        'documents_folder': employee_dir
    }
    
    # Updated template paths to be relative to the project root
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    new_joiner_template_path = os.path.join(base_dir, "templates", "NEW JOINER FORM 2025.pdf")
    contract_template_path = os.path.join(base_dir, "templates", "Contract Template.pdf")
    
    # Generate New Joiner Form from template
    try:
        # Check if template exists
        if os.path.exists(new_joiner_template_path):
            new_joiner_doc = Document(new_joiner_template_path)
            
            # Prepare replacements for new joiner form
            new_joiner_replacements = {
                'Employee Name:': f'Employee Name: {employee.first_name} {employee.middle_name or ""} {employee.last_name}'.strip(),
                'Date of birth\n(dd/mm/yyyy):': f'Date of birth\n(dd/mm/yyyy): {employee.date_of_birth.strftime("%d/%m/%Y") if employee.date_of_birth else ""}',
                'NRC Number:': f'NRC Number: {employee.national_id or ""}',
                'Employing Company:': f'Employing Company: {company.name}',
                'Hire Date:': f'Hire Date: {employee.start_date.strftime("%d/%m/%Y") if employee.start_date else ""}',
                'Job Title:': f'Job Title: {employee.position or ""}',
                'NAPSA:': f'NAPSA: {employee.pension_number or ""}',
                'NHIMA:': f'NHIMA: {documents_data.get("nhima_number", "")}',
                'TPIN:': f'TPIN: {employee.tax_id or ""}',
                'Bank Name:': f'Bank Name: {employee.bank_name or ""}',
                'Branch:': f'Branch: {documents_data.get("bank_branch", "")}',
                'Account\nNumber:': f'Account\nNumber: {employee.bank_account or ""}',
                'Sort\nCode:': f'Sort\nCode: {documents_data.get("sort_code", "")}',
                'Gender (M/F):': f'Gender (M/F): {employee.gender[0] if employee.gender else ""}',
                'Phone:': f'Phone: {employee.phone or ""}',
                'Home Address:': f'Home Address: {employee.address or ""}',
                'Marital\nStatus\n(Single /\nMarried /\nDivorced):': f'Marital\nStatus\n(Single /\nMarried /\nDivorced): {employee.marital_status or ""}',
                'Spouse\nName:': f'Spouse\nName: {documents_data.get("spouse_name", "")}',
                'Next of Kin:': f'Next of Kin: {employee.emergency_contact_name or ""}',
                'Children\nNames & DOB:': f'Children\nNames & DOB: {documents_data.get("children", "")}'
            }
            
            # Replace text in paragraphs
            for paragraph in new_joiner_doc.paragraphs:
                for old_text, new_text in new_joiner_replacements.items():
                    if old_text in paragraph.text:
                        paragraph.text = paragraph.text.replace(old_text, str(new_text))
            
            # Save the document directly to employee folder
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"New_Joiner_Form_{employee.id}_{timestamp}.docx"
            new_joiner_filepath = os.path.join(employee_dir, filename)
            new_joiner_doc.save(new_joiner_filepath)
            generated_docs['new_joiner_form'] = new_joiner_filepath
            
            print(f"DEBUG: New Joiner Form saved to: {new_joiner_filepath}")
        else:
            print(f"Warning: New Joiner template not found at {new_joiner_template_path}")
        
    except Exception as e:
        print(f"Error generating New Joiner Form: {str(e)}")
    
    # Generate Employment Contract from template
    try:
        # Check if template exists
        if os.path.exists(contract_template_path):
            contract_doc = Document(contract_template_path)
            
            # Calculate salary components
            basic_salary = float(employee.salary) if employee.salary else 0
            housing_allowance = documents_data.get("housing_allowance", 0) or 0
            transport_allowance = documents_data.get("transport_allowance", 0) or 0
            lunch_allowance = documents_data.get("lunch_allowance", 0) or 0
            fuel_allowance = documents_data.get("fuel_allowance", 0) or 0
            phone_allowance = documents_data.get("phone_allowance", 0) or 0
            
            total_salary = basic_salary + housing_allowance + transport_allowance + lunch_allowance + fuel_allowance + phone_allowance
            amount_words = num2words(total_salary, lang="en").title() if total_salary > 0 else "Zero"
            
            # Prepare replacements for contract
            contract_replacements = {
                '[Company]': company.name,
                '[Employee]': f'{employee.first_name} {employee.last_name}',
                '[X]': datetime.now().strftime('%d'),
                '[month year]': datetime.now().strftime('%B %Y'),
                '[Job Title]': employee.position or '[Job Title]',
                '[XX date]': employee.start_date.strftime('%Y-%m-%d') if employee.start_date else '[Start Date]',
                '[Amount]': f'{total_salary:.2f}' if total_salary > 0 else '[Amount]',
                '[Write Amount Out in Full]': f'{amount_words} Kwacha',
                'Basic Salary ZMW [Amount]': f'Basic Salary ZMW {basic_salary:.2f}' if basic_salary > 0 else 'Basic Salary ZMW [Amount]',
                'Housing Allowance ZMW [Amount]': f'Housing Allowance ZMW {housing_allowance:.2f}' if housing_allowance > 0 else 'Housing Allowance ZMW [Amount]',
                'Transport Allowance ZMW [Amount]': f'Transport Allowance ZMW {transport_allowance:.2f}' if transport_allowance > 0 else 'Transport Allowance ZMW [Amount]',
                'Lunch Allowance ZMW [Amount]': f'Lunch Allowance ZMW {lunch_allowance:.2f}' if lunch_allowance > 0 else 'Lunch Allowance ZMW [Amount]',
                '[Fuel Allowance]': f'Fuel Allowance ZMW {fuel_allowance:.2f}' if fuel_allowance > 0 else '',
                '[Phone Allowance]': f'Phone Allowance ZMW {phone_allowance:.2f}' if phone_allowance > 0 else '',
                '[Company Vehicle]': documents_data.get("company_vehicle", '') if documents_data.get("company_vehicle") else '',
                '[Company Phone]': documents_data.get("company_phone", '') if documents_data.get("company_phone") else '',
                '[Company-Provided Accommodation (include address)]': documents_data.get("company_accommodation", '') if documents_data.get("company_accommodation") else '',
                '[Monday to Friday, from 08:00 to 17:00 and Saturday, from 08:00 to 13:00.]': documents_data.get("working_hours", "Monday to Friday, from 08:00 to 17:00 and Saturday, from 08:00 to 13:00."),
                '«Currency»': employee.salary_currency,
                '«Lunch_Allowance_Figure»': str(lunch_allowance) if lunch_allowance > 0 else '[Amount]',
                '[add the below manually, as not standard offering]:': '',
                '[[OR]]': '',
                '[OR]': ''
            }
            
            # Replace text in paragraphs
            for paragraph in contract_doc.paragraphs:
                for old_text, new_text in contract_replacements.items():
                    if old_text in paragraph.text:
                        paragraph.text = paragraph.text.replace(old_text, str(new_text))
            
            # Remove optional sections if not applicable
            if not fuel_allowance:
                for paragraph in contract_doc.paragraphs:
                    if 'Fuel Allowance' in paragraph.text and not fuel_allowance:
                        paragraph.clear()
            
            if not phone_allowance:
                for paragraph in contract_doc.paragraphs:
                    if 'Phone Allowance' in paragraph.text and not phone_allowance:
                        paragraph.clear()
            
            # Save the document directly to employee folder
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"Employment_Contract_{employee.id}_{timestamp}.docx"
            contract_filepath = os.path.join(employee_dir, filename)
            contract_doc.save(contract_filepath)
            generated_docs['employment_contract'] = contract_filepath
            
            print(f"DEBUG: Employment Contract saved to: {contract_filepath}")
        else:
            print(f"Warning: Contract template not found at {contract_template_path}")
        
    except Exception as e:
        print(f"Error generating Employment Contract: {str(e)}")
    
    return generated_docs

# ---------------------- SCHEMAS ---------------------- #
class EmployeeResponseSchema(BaseModel):
    employee_id: str = Field(..., description="Employee ID (e.g., AMA001)")
    id: int = Field(..., description="Employee ID")
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    email: str = Field(..., description="Email")
    phone: str = Field(..., description="Phone")
    personal_email: Optional[str] = Field(None, description="Personal email")
    date_of_birth: str = Field(..., description="Date of birth")
    national_id: Optional[str] = Field(None, description="National ID")
    work_permit_number: Optional[str] = Field(None, description="Work Permit Number")
    identity_type: str = Field(..., description="Identity Type (NRC or Work Permit)")
    work_permit_valid_from: Optional[str] = Field(None, description="Work permit valid from date")
    work_permit_valid_to: Optional[str] = Field(None, description="Work permit valid to date")
    work_permit_expiry_notified: bool = Field(False, description="Whether work permit expiry notification was sent")
    identity_document_is_expired: bool = Field(False, description="Whether work permit is expired")
    identity_document_expires_soon: bool = Field(False, description="Whether work permit expires soon")
    primary_identity_number: Optional[str] = Field(None, description="Primary identity number based on type")
    requires_work_permit_renewal: bool = Field(False, description="Whether work permit requires renewal")
    gender: str = Field(..., description="Gender")
    marital_status: Optional[str] = Field(None, description="Marital status")
    address: Optional[str] = Field(None, description="Address")
    emergency_contact_name: str = Field(..., description="Emergency contact name")
    emergency_contact_phone: str = Field(..., description="Emergency contact phone")
    emergency_contact_relationship: str = Field(..., description="Emergency contact relationship")
    company_id: int = Field(..., description="Company ID")
    department: str = Field(..., description="Department")
    position: str = Field(..., description="Position")
    employment_type: str = Field(..., description="Employment type")
    employment_status: str = Field(..., description="Employment status")
    start_date: str = Field(..., description="Start date")
    end_date: Optional[str] = Field(None, description="End date")
    probation_end_date: Optional[str] = Field(None, description="Probation end date")
    contract_end_date: Optional[str] = Field(None, description="Contract end date")
    supervisor_id: Optional[int] = Field(None, description="Supervisor ID")
    work_location: Optional[str] = Field(None, description="Work location")
    salary: float = Field(..., description="Salary")
    salary_currency: str = Field(..., description="Salary currency")
    payment_frequency: str = Field(..., description="Payment frequency")
    bank_name: Optional[str] = Field(None, description="Bank name")
    bank_account: Optional[str] = Field(None, description="Bank account")
    tax_id: Optional[str] = Field(None, description="Tax ID")
    pension_number: Optional[str] = Field(None, description="Pension number")
    has_live_disciplinary: bool = Field(..., description="Has live disciplinary")
    created_by: int = Field(..., description="Created by")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Update timestamp")
    company_name: Optional[str] = Field(None, description="Company name")

class EmployeeCreateSchema(BaseModel):
    first_name: str = Field(..., min_length=1, description="First name")
    last_name: str = Field(..., min_length=1, description="Last name")
    date_of_birth: str = Field(..., description="Date of birth")
    
    # Identity Document Fields
    identity_type: str = Field("NRC", description="Identity Type (NRC or Work Permit)")
    national_id: Optional[str] = Field(None, min_length=1, description="National ID - required if identity_type is NRC")
    work_permit_number: Optional[str] = Field(None, description="Work Permit Number - required if identity_type is Work Permit")
    work_permit_valid_from: Optional[str] = Field(None, description="Work permit valid from date - required if identity_type is Work Permit")
    work_permit_valid_to: Optional[str] = Field(None, description="Work permit valid to date - required if identity_type is Work Permit")
    
    gender: str = Field(..., description="Gender")
    phone: Optional[Union[str, int]] = Field(None, description="Phone")
    personal_email: Optional[EmailStr] = Field(None, description="Personal email")
    address: Optional[str] = Field(None, description="Address")
    marital_status: Optional[str] = Field(None, description="Marital status")
    company_id: int = Field(..., description="Company ID")
    position: str = Field(..., min_length=1, description="Position")
    department: str = Field(..., description="Department")
    employment_type: str = Field(..., description="Employment type")
    employment_status: str = Field("Active", description="Employment status")
    start_date: str = Field(..., description="Start date")
    end_date: Optional[str] = Field(None, description="End date")
    probation_end_date: Optional[str] = Field(None, description="Probation end date")
    contract_end_date: Optional[str] = Field(None, description="Contract end date")
    supervisor_id: Optional[int] = Field(None, description="Supervisor ID")
    work_location: Optional[str] = Field(None, description="Work location")
    salary: Optional[float] = Field(None, ge=0, description="Salary")
    salary_currency: str = Field("ZMW", description="Salary currency")
    payment_frequency: str = Field("Monthly", description="Payment frequency")
    bank_name: Optional[str] = Field(None, description="Bank name")
    bank_account: Optional[Union[str, int]] = Field(None, description="Bank account")
    tax_id: Optional[str] = Field(None, description="Tax ID")
    pension_number: Optional[str] = Field(None, description="Pension number")
    generate_documents: Optional[bool] = Field(True, description="Generate onboarding documents")

    # Emergency contact fields
    emergency_contact_name: Optional[str] = Field("Not Provided", description="Emergency contact name")
    emergency_contact_phone: Optional[Union[str, int]] = Field("Not Provided", description="Emergency contact phone")
    emergency_contact_relationship: Optional[str] = Field("Not Provided", description="Emergency contact relationship")
    
    # Email is now optional and will be generated if not provided
    email: Optional[EmailStr] = Field(None, description="Email")

    # Additional fields for document generation
    middle_name: Optional[str] = Field(None, description="Middle name")
    napsa_number: Optional[str] = Field(None, description="NAPSA number")
    nhima_number: Optional[str] = Field(None, description="NHIMA number")
    tpin: Optional[str] = Field(None, description="TPIN number")
    account_number: Optional[Union[str, int]] = Field(None, description="Bank account number")
    sort_code: Optional[Union[str, int]] = Field(None, description="Bank sort code")
    next_of_kin: Optional[str] = Field(None, description="Next of kin")
    physical_address: Optional[str] = Field(None, description="Physical address")

    # Document generation fields
    housing_allowance: Optional[float] = Field(0, description="Housing allowance")
    transport_allowance: Optional[float] = Field(0, description="Transport allowance")
    lunch_allowance: Optional[float] = Field(0, description="Lunch allowance")
    fuel_allowance: Optional[float] = Field(0, description="Fuel allowance")
    phone_allowance: Optional[float] = Field(0, description="Phone allowance")
    company_vehicle: Optional[str] = Field(None, description="Company vehicle details")
    company_phone: Optional[str] = Field(None, description="Company phone details")
    company_accommodation: Optional[str] = Field(None, description="Company accommodation details")
    working_hours: Optional[str] = Field("Monday to Friday, from 08:00 to 17:00 and Saturday, from 08:00 to 13:00.", description="Working hours")
    bank_branch: Optional[str] = Field(None, description="Bank branch")
    spouse_name: Optional[str] = Field(None, description="Spouse name")
    children: Optional[str] = Field(None, description="Children details")

    # Documents field - NEW: Added for document handling
    documents: Optional[Dict[str, Any]] = Field(None, description="Employee documents")

    # Validators to convert integers to strings for phone and account fields
    @field_validator('phone', 'emergency_contact_phone', 'bank_account', 'account_number', 'sort_code', mode='before')
    @classmethod
    def convert_to_string(cls, v):
        if v is None:
            return v
        return str(v)

    @field_validator('email')
    @classmethod
    def email_to_lowercase(cls, v):
        if v:
            return v.strip().lower()
        return v

    @field_validator('personal_email')
    @classmethod
    def personal_email_to_lowercase(cls, v):
        if v:
            return v.strip().lower()
        return v

    @field_validator('identity_type')
    @classmethod
    def validate_identity_type(cls, v):
        valid_types = ['NRC', 'Work Permit', 'nrc', 'work permit', 'work_permit']
        if v not in valid_types:
            raise ValueError(f'Identity type must be one of: NRC, Work Permit')
        # Normalize to standard format
        if v.lower() in ['work permit', 'work_permit']:
            return 'Work Permit'
        return 'NRC'

    @field_validator('work_permit_valid_from', 'work_permit_valid_to')
    @classmethod
    def validate_work_permit_dates_required(cls, v, info):
        """Validate that work permit dates are provided for work permit type"""
        data = info.data
        field_name = info.field_name
        
        if data.get('identity_type') == 'Work Permit':
            if not v:
                raise ValueError(f'Work permit {field_name.split("_")[-1]} date is required when identity type is Work Permit')
        return v

    @field_validator('work_permit_valid_to')
    @classmethod
    def validate_work_permit_dates(cls, v, info):
        """Validate that work_permit_valid_to is after work_permit_valid_from"""
        data = info.data
        valid_from = data.get('work_permit_valid_from')
        valid_to = v
        
        if data.get('identity_type') == 'Work Permit' and valid_from and valid_to:
            try:
                valid_from_date = datetime.strptime(valid_from, '%Y-%m-%d').date()
                valid_to_date = datetime.strptime(valid_to, '%Y-%m-%d').date()
                if valid_to_date <= valid_from_date:
                    raise ValueError('Work permit valid to date must be after valid from date')
            except ValueError:
                # Let the date format validation handle invalid formats
                pass
        return v

    @field_validator('employment_type')
    @classmethod
    def validate_employment_type(cls, v):
        valid_types = ['FULL-TIME', 'PART-TIME', 'CONTRACT', 'PERMANENT', 'Full-time', 'Part-time', 'Contract', 'Permanent']
        if v not in valid_types:
            raise ValueError(f'Employment type must be one of: {", ".join(valid_types)}')
        # Normalize to standard format
        if v.upper() == 'PERMANENT':
            return 'Full-time'
        return v

    @field_validator('employment_status')
    @classmethod
    def validate_employment_status(cls, v):
        valid_statuses = ['Active', 'Probation', 'Inactive', 'Expired Contract']
        if v not in valid_statuses:
            raise ValueError(f'Employment status must be one of: {", ".join(valid_statuses)}')
        return v

    @field_validator('gender')
    @classmethod
    def validate_gender(cls, v):
        valid_genders = ['Male', 'Female', 'Other', 'male', 'female', 'other']
        if v not in valid_genders:
            raise ValueError(f'Gender must be one of: Male, Female, Other')
        # Normalize to title case
        return v.title()

    @field_validator('payment_frequency')
    @classmethod
    def validate_payment_frequency(cls, v):
        valid_frequencies = ['Monthly', 'Bi-weekly', 'Weekly', 'monthly', 'bi-weekly', 'weekly']
        if v not in valid_frequencies:
            raise ValueError(f'Payment frequency must be one of: Monthly, Bi-weekly, Weekly')
        # Normalize to title case
        return v.title()

    @field_validator('marital_status')
    @classmethod
    def validate_marital_status(cls, v):
        if v is None:
            return v
        valid_statuses = ['Single', 'Married', 'Divorced', 'Widowed', 'single', 'married', 'divorced', 'widowed']
        if v not in valid_statuses:
            raise ValueError(f'Marital status must be one of: Single, Married, Divorced, Widowed')
        # Normalize to title case
        return v.title()

    @model_validator(mode='before')
    @classmethod
    def validate_dates(cls, data):
        """Validate all date fields with flexible format handling including Excel serial numbers"""
        if not isinstance(data, dict):
            return data
            
        date_fields = ['date_of_birth', 'start_date', 'end_date', 'probation_end_date', 'contract_end_date', 'work_permit_valid_from', 'work_permit_valid_to']
        date_formats = [
            '%Y-%m-%d',  # 2024-01-15
            '%m/%d/%Y',  # 01/15/2024
            '%d/%m/%Y',  # 15/01/2024
            '%d-%m-%Y',  # 15-01-2024
            '%m-%d-%Y',  # 01-15-2024
            '%Y/%m/%d',  # 2024/01/15
        ]
        
        for field in date_fields:
            if field in data and data[field]:
                date_value = data[field]
                
                # Convert to string if it's not already
                if not isinstance(date_value, str):
                    date_value = str(date_value)
                
                parsed = False
                
                # First try to parse as Excel serial number
                try:
                    # Excel serial numbers are days since 1900-01-01
                    # But Excel incorrectly treats 1900 as a leap year, so we need to adjust
                    excel_serial = float(date_value)
                    if 0 <= excel_serial <= 100000:  # Reasonable range for dates
                        # Excel base date is 1900-01-01, but it has a bug treating 1900 as leap year
                        # So we use 1899-12-30 as base to match Excel's behavior
                        base_date = datetime(1899, 12, 30)
                        parsed_date = base_date + timedelta(days=excel_serial)
                        
                        # Convert to standard date string and update the data
                        data[field] = parsed_date.strftime('%Y-%m-%d')
                        parsed = True
                        print(f"DEBUG: Converted Excel serial {excel_serial} to {data[field]}")
                except (ValueError, TypeError):
                    pass
                
                # If not an Excel serial, try standard date formats
                if not parsed:
                    for date_format in date_formats:
                        try:
                            datetime.strptime(date_value, date_format)
                            parsed = True
                            break
                        except ValueError:
                            continue
                
                if not parsed:
                    raise ValueError(f'{field} must be in a valid date format (YYYY-MM-DD, MM/DD/YYYY, etc.) or Excel serial number. Received: {date_value}')
        
        return data

    @model_validator(mode='after')
    def validate_identity_documents(self):
        """Validate identity document requirements"""
        if self.identity_type == 'NRC':
            if not self.national_id:
                raise ValueError('National ID is required when identity type is NRC')
            # Clear work permit fields for NRC
            self.work_permit_number = None
            self.work_permit_valid_from = None
            self.work_permit_valid_to = None
        elif self.identity_type == 'Work Permit':
            if not self.work_permit_number:
                raise ValueError('Work Permit Number is required when identity type is Work Permit')
            if not self.work_permit_valid_from:
                raise ValueError('Work Permit valid from date is required when identity type is Work Permit')
            if not self.work_permit_valid_to:
                raise ValueError('Work Permit valid to date is required when identity type is Work Permit')
            # Clear national_id for Work Permit
            self.national_id = None
        
        return self

    @model_validator(mode='after')
    def set_defaults(self):
        """Set default values for required fields that might be missing"""
        # Generate email if not provided
        if not self.email:
            email_username = f"{self.first_name.lower().replace(' ', '.')}.{self.last_name.lower()}"
            self.email = f"{email_username}@company.com"
        
        # Set default department if not provided
        if not self.department:
            self.department = "General"
            
        return self

class EmployeeUpdateSchema(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, description="First name")
    last_name: Optional[str] = Field(None, min_length=1, description="Last name")
    email: Optional[EmailStr] = Field(None, description="Email")
    phone: Optional[Union[str, int]] = Field(None, description="Phone")
    personal_email: Optional[EmailStr] = Field(None, description="Personal email")
    date_of_birth: Optional[str] = Field(None, description="Date of birth")
    national_id: Optional[str] = Field(None, min_length=1, description="National ID")
    work_permit_number: Optional[str] = Field(None, description="Work Permit Number")
    identity_type: Optional[str] = Field(None, description="Identity Type (NRC or Work Permit)")
    work_permit_valid_from: Optional[str] = Field(None, description="Work permit valid from date")
    work_permit_valid_to: Optional[str] = Field(None, description="Work permit valid to date")
    work_permit_expiry_notified: Optional[bool] = Field(None, description="Whether work permit expiry notification was sent")
    gender: Optional[str] = Field(None, description="Gender")
    marital_status: Optional[str] = Field(None, description="Marital status")
    address: Optional[str] = Field(None, description="Address")
    emergency_contact_name: Optional[str] = Field(None, description="Emergency contact name")
    emergency_contact_phone: Optional[Union[str, int]] = Field(None, description="Emergency contact phone")
    emergency_contact_relationship: Optional[str] = Field(None, description="Emergency contact relationship")
    company_id: Optional[int] = Field(None, description="Company ID")
    department: Optional[str] = Field(None, description="Department")
    position: Optional[str] = Field(None, min_length=1, description="Position")
    employment_type: Optional[str] = Field(None, description="Employment type")
    employment_status: Optional[str] = Field(None, description="Employment status")
    start_date: Optional[str] = Field(None, description="Start date")
    end_date: Optional[str] = Field(None, description="End date")
    probation_end_date: Optional[str] = Field(None, description="Probation end date")
    contract_end_date: Optional[str] = Field(None, description="Contract end date")
    supervisor_id: Optional[int] = Field(None, description="Supervisor ID")
    work_location: Optional[str] = Field(None, description="Work location")
    salary: Optional[float] = Field(None, ge=0, description="Salary")
    salary_currency: Optional[str] = Field(None, description="Salary currency")
    payment_frequency: Optional[str] = Field(None, description="Payment frequency")
    bank_name: Optional[str] = Field(None, description="Bank name")
    bank_account: Optional[Union[str, int]] = Field(None, description="Bank account")
    tax_id: Optional[str] = Field(None, description="Tax ID")
    pension_number: Optional[str] = Field(None, description="Pension number")
    force_update: Optional[bool] = Field(False, description="Force update")

    # Validators to convert integers to strings for phone and account fields
    @field_validator('phone', 'emergency_contact_phone', 'bank_account', mode='before')
    @classmethod
    def convert_to_string(cls, v):
        if v is None:
            return v
        return str(v)

class DocumentGenerationResponse(BaseModel):
    employee_id: int = Field(..., description="Employee ID")
    new_joiner_form_url: Optional[str] = Field(None, description="New Joiner Form URL")
    contract_url: Optional[str] = Field(None, description="Employment Contract URL")
    message: str = Field(..., description="Response message")

class EmployeeListResponseSchema(BaseModel):
    employees: List[EmployeeResponseSchema] = Field(..., description="List of employees")
    pagination: Dict[str, Any] = Field(..., description="Pagination information")

class EmployeeFullResponseSchema(BaseModel):
    employee: EmployeeResponseSchema = Field(..., description="Employee information")
    hr_actions: List[Dict[str, Any]] = Field(..., description="HR actions")
    disciplinary_records: List[Dict[str, Any]] = Field(..., description="Disciplinary records")
    leave_records: List[Dict[str, Any]] = Field(..., description="Leave records")
    documents: List[Dict[str, Any]] = Field(..., description="Documents")

class WorkPermitExpiryResponse(BaseModel):
    expired_work_permits: List[Dict[str, Any]] = Field(..., description="List of employees with expired work permits")
    expiring_soon_work_permits: List[Dict[str, Any]] = Field(..., description="List of employees with work permits expiring soon")
    expired_count: int = Field(..., description="Count of expired work permits")
    expiring_soon_count: int = Field(..., description="Count of expiring soon work permits")
    check_date: str = Field(..., description="Date when the check was performed")

class ErrorResponse(BaseModel):
    status: int = Field(..., description="HTTP status code")
    isError: bool = Field(True, description="Indicates if the response is an error")
    message: str = Field(..., description="Error message")

class SuccessResponse(BaseModel):
    message: str = Field(..., description="Success message")
    status: int = Field(200, description="HTTP status code")
    isError: bool = Field(False, description="Indicates if the response is an error")

# ---------------------- BULK UPLOAD SCHEMAS ---------------------- #
class BulkEmployeeCreateSchema(BaseModel):
    employees: List[EmployeeCreateSchema] = Field(..., description="List of employees to create")
    skip_errors: bool = Field(False, description="Skip employees with errors and continue processing")
    send_notifications: bool = Field(False, description="Send email notifications to new employees")

class BulkEmployeeResponseSchema(BaseModel):
    total_processed: int = Field(..., description="Total employees processed")
    successful: int = Field(..., description="Number of successfully created employees")
    failed: int = Field(..., description="Number of failed creations")
    errors: List[Dict[str, Any]] = Field(..., description="List of errors for failed creations")
    successful_employees: List[Dict[str, Any]] = Field(..., description="List of successfully created employees")

# Path parameter schemas
class EmployeeIdPath(BaseModel):
    employee_id: int = Field(..., description="Employee ID")

# ---------------------- DATE PARSING HELPER ---------------------- #
def parse_date(date_str):
    """Parse date from string or Excel serial number"""
    if not date_str:
        return None
    
    # Handle Excel serial numbers
    try:
        excel_serial = float(date_str)
        if 0 <= excel_serial <= 100000:  # Reasonable range for dates
            base_date = datetime(1899, 12, 30)
            parsed_date = base_date + timedelta(days=excel_serial)
            return parsed_date.date()
    except (ValueError, TypeError):
        pass
    
    # Handle standard date formats
    date_formats = [
        '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%d-%m-%Y', '%m-%d-%Y', '%Y/%m/%d'
    ]
    
    for date_format in date_formats:
        try:
            return datetime.strptime(date_str, date_format).date()
        except ValueError:
            continue
    
    raise ValueError(f"Invalid date format: {date_str}")

# ---------------------- ROUTES ---------------------- #
@employee_bp.get('/', responses={"200": EmployeeListResponseSchema, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_employees():
    """Get paginated list of employees with filtering and sorting"""
    try:
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        # Base query
        query = Employee.query

        # Filtering
        status = request.args.get('status', 'all')
        company_id = request.args.get('company_id')
        search = request.args.get('search', '')
        identity_type = request.args.get('identity_type', 'all')
        work_permit_status = request.args.get('work_permit_status', 'all')

        # Status filter
        if status == 'active':
            query = query.filter(Employee.employment_status.in_(['Active', 'Probation']))
        elif status in ['Active', 'Probation', 'Inactive', 'Expired Contract']:
            query = query.filter_by(employment_status=status)

        # Company filter
        if company_id and company_id != 'all':
            query = query.filter_by(company_id=company_id)

        # Identity type filter
        if identity_type and identity_type != 'all':
            query = query.filter_by(identity_type=identity_type)

        # Work permit status filter
        if work_permit_status != 'all':
            today = datetime.now().date()
            if work_permit_status == 'expired':
                query = query.filter(
                    Employee.identity_type == 'Work Permit',
                    Employee.work_permit_valid_to < today
                )
            elif work_permit_status == 'expiring_soon':
                thirty_days_from_now = today + timedelta(days=30)
                query = query.filter(
                    Employee.identity_type == 'Work Permit',
                    Employee.work_permit_valid_to >= today,
                    Employee.work_permit_valid_to <= thirty_days_from_now
                )
            elif work_permit_status == 'valid':
                query = query.filter(
                    Employee.identity_type == 'Work Permit',
                    Employee.work_permit_valid_to > today + timedelta(days=30)
                )

        # Search filter
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Employee.first_name.ilike(search_term),
                    Employee.last_name.ilike(search_term),
                    Employee.email.ilike(search_term),
                    Employee.phone.ilike(search_term),
                    Employee.national_id.ilike(search_term),
                    Employee.work_permit_number.ilike(search_term),
                    Employee.position.ilike(search_term),
                    Employee.employee_id.ilike(search_term)  # ADDED: Search by employee_id
                )
            )

        # Sorting
        sort_by = request.args.get('sort_by', 'first_name')
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

        employees = pagination.items

        # Add disciplinary flag for display
        employees_data = []
        for employee in employees:
            emp_data = employee.to_dict()
            emp_data['has_live_disciplinary_flag'] = '🔴' if employee.has_live_disciplinary else ''
            employees_data.append(emp_data)

        return jsonify({
            "employees": employees_data,
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
            "message": f"Error fetching employees: {str(e)}"
        }), 500

@employee_bp.post(
    '/create',
    responses={"201": EmployeeResponseSchema, "400": ErrorResponse, "403": ErrorResponse, "409": ErrorResponse, "500": ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def create_employee(body: EmployeeCreateSchema):
    """Create a new employee with template-based document generation"""
    try:
        current_user_id = get_jwt_identity()
        
        # Check HR admin access
        jwt_data = get_jwt()
        roles = jwt_data.get('roles', [])
        
        if 'hr_admin' not in roles and 'admin' not in roles:
            return jsonify({
                "status": 403,
                "isError": True,
                "message": "HR admin or Super Admin access required"
            }), 403

        # Validate company exists
        company = Company.query.get(body.company_id)
        if not company:
            return jsonify({
                "status": 404,
                "isError": True,
                "message": "Company not found"
            }), 404

        # Validate supervisor exists if provided
        if body.supervisor_id:
            supervisor = Employee.query.get(body.supervisor_id)
            if not supervisor:
                return jsonify({
                    "status": 400,
                    "isError": True,
                    "message": f"Supervisor with ID {body.supervisor_id} not found. Please create the supervisor first or set supervisor_id to null."
                }), 400

        # Generate employee ID
        employee_id = generate_employee_id(body.company_id)

        # Check if generated employee ID already exists
        existing_employee = Employee.query.filter_by(employee_id=employee_id).first()
        if existing_employee:
            employee_id = f"EMP{int(datetime.now().timestamp())}"

        # Check if email already exists
        if body.email:
            existing_employee = Employee.query.filter_by(email=body.email).first()
            if existing_employee:
                return jsonify({
                    "status": 409,
                    "isError": True,
                    "message": "An employee with this email already exists"
                }), 409
        
        # Check identity document uniqueness
        if body.identity_type == 'NRC' and body.national_id:
            existing_national_id = Employee.query.filter_by(national_id=body.national_id).first()
            if existing_national_id:
                return jsonify({
                    "status": 409,
                    "isError": True,
                    "message": "An employee with this National ID already exists"
                }), 409
        elif body.identity_type == 'Work Permit' and body.work_permit_number:
            existing_work_permit = Employee.query.filter_by(work_permit_number=body.work_permit_number).first()
            if existing_work_permit:
                return jsonify({
                    "status": 409,
                    "isError": True,
                    "message": "An employee with this Work Permit Number already exists"
                }), 409

        # Parse dates using the updated parse_date function
        date_of_birth = parse_date(body.date_of_birth)
        start_date = parse_date(body.start_date)
        end_date = parse_date(body.end_date) if body.end_date else None
        probation_end_date = parse_date(body.probation_end_date) if body.probation_end_date else None
        contract_end_date = parse_date(body.contract_end_date) if body.contract_end_date else None
        
        # Parse work permit dates
        work_permit_valid_from = None
        work_permit_valid_to = None
        if body.identity_type == 'Work Permit':
            work_permit_valid_from = parse_date(body.work_permit_valid_from) if body.work_permit_valid_from else None
            work_permit_valid_to = parse_date(body.work_permit_valid_to) if body.work_permit_valid_to else None

        # Handle null salary
        salary = body.salary if body.salary is not None else 0.0

        # Create employee
        employee = Employee(
            employee_id=employee_id,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            phone=body.phone or "Not Provided",
            personal_email=body.personal_email,
            date_of_birth=date_of_birth,
            
            # Identity fields
            national_id=body.national_id,
            work_permit_number=body.work_permit_number,
            identity_type=body.identity_type,
            work_permit_valid_from=work_permit_valid_from,
            work_permit_valid_to=work_permit_valid_to,
            work_permit_expiry_notified=False,
            
            # Additional fields
            middle_name=body.middle_name,
            napsa_number=body.napsa_number,
            nhima_number=body.nhima_number,
            tpin=body.tax_id,
            account_number=body.bank_account,
            sort_code=body.sort_code,
            next_of_kin=body.next_of_kin,
            physical_address=body.physical_address,
            
            gender=body.gender,
            marital_status=body.marital_status,
            address=body.address,
            emergency_contact_name=body.emergency_contact_name or "Not Provided",
            emergency_contact_phone=body.emergency_contact_phone or "Not Provided",
            emergency_contact_relationship=body.emergency_contact_relationship or "Not Provided",
            company_id=body.company_id,
            department=body.department,
            position=body.position,
            employment_type=body.employment_type,
            employment_status=body.employment_status,
            start_date=start_date,
            end_date=end_date,
            probation_end_date=probation_end_date,
            contract_end_date=contract_end_date,
            supervisor_id=body.supervisor_id,  # Now validated above
            work_location=body.work_location,
            salary=salary,
            salary_currency=body.salary_currency,
            payment_frequency=body.payment_frequency,
            bank_name=body.bank_name,
            bank_account=body.bank_account,
            tax_id=body.tax_id,
            pension_number=body.pension_number,
            created_by=int(current_user_id)
        )
        
        db.session.add(employee)
        db.session.flush()  # This gets the employee ID without committing
        
        # ========== NEW: HANDLE UPLOADED DOCUMENTS ==========
        if body.documents:
            try:
                saved_documents = handle_employee_documents(
                    employee_id=employee.id,
                    documents_data=body.documents,
                    uploaded_by=current_user_id
                )
                print(f"DEBUG: Saved {len(saved_documents)} documents for employee {employee.id}")
            except Exception as doc_error:
                print(f"Warning: Document processing failed but employee created: {str(doc_error)}")
                import traceback
                print(f"Document error traceback: {traceback.format_exc()}")
        # ========== END DOCUMENTS HANDLING ==========
        
        # Generate template documents if requested
        if body.generate_documents:
            try:
                documents_data = {
                    "nhima_number": body.nhima_number,
                    "bank_branch": body.bank_branch,
                    "sort_code": body.sort_code,
                    "spouse_name": body.spouse_name,
                    "children": body.children,
                    "housing_allowance": body.housing_allowance or 0,
                    "transport_allowance": body.transport_allowance or 0,
                    "lunch_allowance": body.lunch_allowance or 0,
                    "fuel_allowance": body.fuel_allowance or 0,
                    "phone_allowance": body.phone_allowance or 0,
                    "company_vehicle": body.company_vehicle,
                    "company_phone": body.company_phone,
                    "company_accommodation": body.company_accommodation,
                    "working_hours": body.working_hours
                }
                
                generated_docs = generate_documents_from_templates(employee, company, documents_data)
                
                # Save documents to database
                if generated_docs.get('new_joiner_form'):
                    save_document_to_database(
                        employee_id=employee.id,
                        document_type='new_joiner_form',
                        file_path=generated_docs['new_joiner_form'],
                        uploaded_by=current_user_id,
                        document_name=f"New Joiner Form - {employee.first_name} {employee.last_name}",
                        comments="Employee onboarding form with personal and employment details"
                    )
                
                if generated_docs.get('employment_contract'):
                    expiry_date = None
                    if employee.contract_end_date:
                        expiry_date = employee.contract_end_date
                    elif employee.start_date:
                        expiry_date = employee.start_date + timedelta(days=365)
                    
                    save_document_to_database(
                        employee_id=employee.id,
                        document_type='employment_contract',
                        file_path=generated_docs['employment_contract'],
                        uploaded_by=current_user_id,
                        document_name=f"Employment Contract - {employee.first_name} {employee.last_name}",
                        comments="Formal employment agreement with terms and conditions",
                        expiry_date=expiry_date
                    )
                    
            except Exception as doc_error:
                print(f"Template document generation failed but employee created: {str(doc_error)}")
        
        # Update company employee count
        company.employee_count = Employee.query.filter_by(
            company_id=body.company_id
        ).filter(
            Employee.employment_status.in_(['Active', 'Probation'])
        ).count()
        
        db.session.commit()
        
        # Create audit log
        audit = AuditLog(
            employee_id=employee.id,
            action="CREATE",
            performed_by=current_user_id,
            details=f"Employee {employee.employee_id} created successfully with identity type: {employee.identity_type}"
        )
        db.session.add(audit)
        db.session.commit()
        
        employee_data = employee.to_dict()
        if 'company_name' not in employee_data or not employee_data['company_name']:
            employee_data['company_name'] = company.name
            
        return jsonify(employee_data), 201

    except Exception as e:
        db.session.rollback()
        print(f"Error in create_employee: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            "status": 500,
            "isError": True,
            "message": f"Error creating employee: {str(e)}"
        }), 500

@employee_bp.get('/documents/<path:filename>')
@jwt_required()
def serve_document(filename):
    """Serve generated documents from Napoli HR Folders"""
    try:
        documents_base = "/app/Napoli HR Folders"
        file_path = os.path.join(documents_base, filename)
        
        # If filename doesn't include full path, try to find it in employee folders
        if not os.path.exists(file_path):
            # Look for file in any employee folder
            for folder in os.listdir(documents_base):
                folder_path = os.path.join(documents_base, folder)
                if os.path.isdir(folder_path) and folder.startswith('Employee_'):
                    potential_path = os.path.join(folder_path, filename)
                    if os.path.exists(potential_path):
                        file_path = potential_path
                        break
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_file(file_path, as_attachment=False)
        else:
            return jsonify({
                "status": 404,
                "isError": True,
                "message": "Document not found"
            }), 404
            
    except Exception as e:
        return jsonify({
            "status": 500,
            "isError": True,
            "message": f"Error serving document: {str(e)}"
        }), 500

@employee_bp.get('/<int:employee_id>', responses={"200": EmployeeResponseSchema, "404": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_employee(path: EmployeeIdPath):
    """Get employee by ID"""
    try:
        employee = Employee.query.get(path.employee_id)
        if not employee:
            return jsonify({
                "status": 404,
                "isError": True,
                "message": "Employee not found"
            }), 404
        
        employee_data = employee.to_dict()
        
        # Add company name if not already included
        if 'company_name' not in employee_data or not employee_data['company_name']:
            company = Company.query.get(employee.company_id)
            if company:
                employee_data['company_name'] = company.name
        
        return jsonify(employee_data), 200
        
    except Exception as e:
        return jsonify({
            "status": 500,
            "isError": True,
            "message": f"Error fetching employee: {str(e)}"
        }), 500

@employee_bp.put('/<int:employee_id>', responses={"200": EmployeeResponseSchema, "404": ErrorResponse, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def update_employee(path: EmployeeIdPath, body: EmployeeUpdateSchema):
    """Update employee details"""
    try:
        employee = Employee.query.get(path.employee_id)
        if not employee:
            return jsonify({
                "status": 404,
                "isError": True,
                "message": "Employee not found"
            }), 404

        # Update fields if provided
        update_data = body.model_dump(exclude_unset=True, exclude_none=True)
        
        # Remove force_update from update data as it's not an employee field
        update_data.pop('force_update', None)
        
        # Parse date fields if provided
        date_fields = ['date_of_birth', 'start_date', 'end_date', 'probation_end_date', 'contract_end_date', 'work_permit_valid_from', 'work_permit_valid_to']
        for field in date_fields:
            if field in update_data and update_data[field]:
                try:
                    update_data[field] = parse_date(update_data[field])
                except ValueError as e:
                    return jsonify({
                        "status": 400,
                        "isError": True,
                        "message": f"Invalid date format for {field}: {str(e)}"
                    }), 400

        # Handle identity type changes and validation
        if 'identity_type' in update_data:
            new_identity_type = update_data['identity_type']
            if new_identity_type == 'NRC':
                # Clear work permit fields when switching to NRC
                update_data['work_permit_number'] = None
                update_data['work_permit_valid_from'] = None
                update_data['work_permit_valid_to'] = None
                update_data['work_permit_expiry_notified'] = False
                if not update_data.get('national_id'):
                    return jsonify({
                        "status": 400,
                        "isError": True,
                        "message": "National ID is required when identity type is NRC"
                    }), 400
            elif new_identity_type == 'Work Permit':
                # Clear national_id when switching to Work Permit
                update_data['national_id'] = None
                if not update_data.get('work_permit_number'):
                    return jsonify({
                        "status": 400,
                        "isError": True,
                        "message": "Work Permit Number is required when identity type is Work Permit"
                    }), 400
                if not update_data.get('work_permit_valid_from'):
                    return jsonify({
                        "status": 400,
                        "isError": True,
                        "message": "Work Permit valid from date is required when identity type is Work Permit"
                    }), 400
                if not update_data.get('work_permit_valid_to'):
                    return jsonify({
                        "status": 400,
                        "isError": True,
                        "message": "Work Permit valid to date is required when identity type is Work Permit"
                    }), 400

        # Update employee fields
        for key, value in update_data.items():
            if hasattr(employee, key):
                setattr(employee, key, value)

        employee.updated_at = datetime.now()
        db.session.commit()

        # Return updated employee
        employee_data = employee.to_dict()
        company = Company.query.get(employee.company_id)
        if company:
            employee_data['company_name'] = company.name

        return jsonify(employee_data), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": 500,
            "isError": True,
            "message": f"Error updating employee: {str(e)}"
        }), 500

@employee_bp.delete('/<int:employee_id>', responses={"200": SuccessResponse, "404": ErrorResponse, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def delete_employee(path: EmployeeIdPath):
    """Delete employee"""
    try:
        employee = Employee.query.get(path.employee_id)
        if not employee:
            return jsonify({
                "status": 404,
                "isError": True,
                "message": "Employee not found"
            }), 404

        db.session.delete(employee)
        db.session.commit()

        return jsonify({
            "message": "Employee deleted successfully",
            "status": 200,
            "isError": False
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": 500,
            "isError": True,
            "message": f"Error deleting employee: {str(e)}"
        }), 500

@employee_bp.post('/<int:employee_id>/generate-documents', responses={"200": DocumentGenerationResponse, "404": ErrorResponse, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def generate_employee_documents(path: EmployeeIdPath):
    """Generate onboarding documents for an existing employee"""
    try:
        employee = Employee.query.get(path.employee_id)
        if not employee:
            return jsonify({
                "status": 404,
                "isError": True,
                "message": "Employee not found"
            }), 404

        company = Company.query.get(employee.company_id)
        if not company:
            return jsonify({
                "status": 404,
                "isError": True,
                "message": "Company not found"
            }), 404

        current_user_id = get_jwt_identity()
        
        # Generate documents
        generated_docs = generate_documents_from_templates(employee, company)
        
        # Save document records to database
        new_joiner_url = None
        contract_url = None
        
        if generated_docs.get('new_joiner_form'):
            new_joiner_doc = save_document_to_database(
                employee_id=employee.id,
                document_type='new_joiner_form',
                file_path=generated_docs['new_joiner_form'],
                uploaded_by=current_user_id,
                document_name=f"New Joiner Form - {employee.first_name} {employee.last_name}",
                comments="Employee onboarding form with personal and employment details"
            )
            if new_joiner_doc:
                new_joiner_url = new_joiner_doc.file_url
        
        if generated_docs.get('employment_contract'):
            # Calculate contract expiry date
            expiry_date = None
            if employee.contract_end_date:
                expiry_date = employee.contract_end_date
            elif employee.start_date:
                # Default 1-year contract if no end date specified
                expiry_date = employee.start_date + timedelta(days=365)
            
            contract_doc = save_document_to_database(
                employee_id=employee.id,
                document_type='employment_contract',
                file_path=generated_docs['employment_contract'],
                uploaded_by=current_user_id,
                document_name=f"Employment Contract - {employee.first_name} {employee.last_name}",
                comments="Formal employment agreement with terms and conditions",
                expiry_date=expiry_date
            )
            if contract_doc:
                contract_url = contract_doc.file_url

        return jsonify({
            "employee_id": employee.id,
            "message": "Documents generated successfully",
            "new_joiner_form_url": new_joiner_url,
            "contract_url": contract_url
        }), 200

    except Exception as e:
        return jsonify({
            "status": 500,
            "isError": True,
            "message": f"Error generating documents: {str(e)}"
        }), 500

# ---------------------- BULK UPLOAD ROUTES ---------------------- #
@employee_bp.post(
    '/bulk-upload',
    responses={"200": BulkEmployeeResponseSchema, "400": ErrorResponse, "403": ErrorResponse, "500": ErrorResponse},
    security=[{"jwt": []}]
)
@jwt_required()
def bulk_create_employees(body: BulkEmployeeCreateSchema):
    """Bulk create multiple employees with optional document handling"""
    try:
        current_user_id = get_jwt_identity()
        
        # Check HR admin access
        jwt_data = get_jwt()
        roles = jwt_data.get('roles', [])
        
        if 'hr_admin' not in roles and 'admin' not in roles:
            return jsonify({
                "status": 403,
                "isError": True,
                "message": "HR admin or Super Admin access required for bulk operations"
            }), 403

        if not body.employees:
            return jsonify({
                "status": 400,
                "isError": True,
                "message": "No employees provided for bulk upload"
            }), 400

        # Limit bulk upload size
        if len(body.employees) > 100:
            return jsonify({
                "status": 400,
                "isError": True,
                "message": "Bulk upload limited to 100 employees at a time"
            }), 400

        results = {
            "total_processed": len(body.employees),
            "successful": 0,
            "failed": 0,
            "errors": [],
            "successful_employees": []
        }

        # Process each employee
        for index, employee_data in enumerate(body.employees):
            try:
                # Validate company exists
                company = Company.query.get(employee_data.company_id)
                if not company:
                    error_msg = f"Company with ID {employee_data.company_id} not found"
                    if not body.skip_errors:
                        raise ValueError(error_msg)
                    results["errors"].append({
                        "index": index,
                        "employee_name": f"{employee_data.first_name} {employee_data.last_name}",
                        "error": error_msg
                    })
                    results["failed"] += 1
                    continue

                # Validate supervisor exists if provided
                if employee_data.supervisor_id:
                    supervisor = Employee.query.get(employee_data.supervisor_id)
                    if not supervisor:
                        error_msg = f"Supervisor with ID {employee_data.supervisor_id} not found"
                        if not body.skip_errors:
                            raise ValueError(error_msg)
                        results["errors"].append({
                            "index": index,
                            "employee_name": f"{employee_data.first_name} {employee_data.last_name}",
                            "error": error_msg
                        })
                        results["failed"] += 1
                        continue

                # Generate employee ID
                employee_id = generate_employee_id(employee_data.company_id)

                # Check if generated employee ID already exists
                existing_employee = Employee.query.filter_by(employee_id=employee_id).first()
                if existing_employee:
                    employee_id = f"EMP{int(datetime.now().timestamp())}_{index}"

                # Check if email already exists
                if employee_data.email:
                    existing_employee = Employee.query.filter_by(email=employee_data.email).first()
                    if existing_employee:
                        error_msg = f"An employee with email {employee_data.email} already exists"
                        if not body.skip_errors:
                            raise ValueError(error_msg)
                        results["errors"].append({
                            "index": index,
                            "employee_name": f"{employee_data.first_name} {employee_data.last_name}",
                            "error": error_msg
                        })
                        results["failed"] += 1
                        continue

                # Check identity document uniqueness
                if employee_data.identity_type == 'NRC' and employee_data.national_id:
                    existing_national_id = Employee.query.filter_by(national_id=employee_data.national_id).first()
                    if existing_national_id:
                        error_msg = f"An employee with National ID {employee_data.national_id} already exists"
                        if not body.skip_errors:
                            raise ValueError(error_msg)
                        results["errors"].append({
                            "index": index,
                            "employee_name": f"{employee_data.first_name} {employee_data.last_name}",
                            "error": error_msg
                        })
                        results["failed"] += 1
                        continue
                elif employee_data.identity_type == 'Work Permit' and employee_data.work_permit_number:
                    existing_work_permit = Employee.query.filter_by(work_permit_number=employee_data.work_permit_number).first()
                    if existing_work_permit:
                        error_msg = f"An employee with Work Permit Number {employee_data.work_permit_number} already exists"
                        if not body.skip_errors:
                            raise ValueError(error_msg)
                        results["errors"].append({
                            "index": index,
                            "employee_name": f"{employee_data.first_name} {employee_data.last_name}",
                            "error": error_msg
                        })
                        results["failed"] += 1
                        continue

                # Parse dates using the updated parse_date function
                date_of_birth = parse_date(employee_data.date_of_birth)
                start_date = parse_date(employee_data.start_date)
                end_date = parse_date(employee_data.end_date) if employee_data.end_date else None
                probation_end_date = parse_date(employee_data.probation_end_date) if employee_data.probation_end_date else None
                contract_end_date = parse_date(employee_data.contract_end_date) if employee_data.contract_end_date else None
                
                # Parse work permit dates
                work_permit_valid_from = None
                work_permit_valid_to = None
                if employee_data.identity_type == 'Work Permit':
                    work_permit_valid_from = parse_date(employee_data.work_permit_valid_from) if employee_data.work_permit_valid_from else None
                    work_permit_valid_to = parse_date(employee_data.work_permit_valid_to) if employee_data.work_permit_valid_to else None

                # Handle null salary
                salary = employee_data.salary if employee_data.salary is not None else 0.0

                # Create employee
                employee = Employee(
                    employee_id=employee_id,
                    first_name=employee_data.first_name,
                    last_name=employee_data.last_name,
                    email=employee_data.email,
                    phone=employee_data.phone or "Not Provided",
                    personal_email=employee_data.personal_email,
                    date_of_birth=date_of_birth,
                    
                    # Identity fields
                    national_id=employee_data.national_id,
                    work_permit_number=employee_data.work_permit_number,
                    identity_type=employee_data.identity_type,
                    work_permit_valid_from=work_permit_valid_from,
                    work_permit_valid_to=work_permit_valid_to,
                    work_permit_expiry_notified=False,
                    
                    # Additional fields
                    middle_name=employee_data.middle_name,
                    napsa_number=employee_data.napsa_number,
                    nhima_number=employee_data.nhima_number,
                    tpin=employee_data.tax_id,
                    account_number=employee_data.bank_account,
                    sort_code=employee_data.sort_code,
                    next_of_kin=employee_data.next_of_kin,
                    physical_address=employee_data.physical_address,
                    
                    gender=employee_data.gender,
                    marital_status=employee_data.marital_status,
                    address=employee_data.address,
                    emergency_contact_name=employee_data.emergency_contact_name or "Not Provided",
                    emergency_contact_phone=employee_data.emergency_contact_phone or "Not Provided",
                    emergency_contact_relationship=employee_data.emergency_contact_relationship or "Not Provided",
                    company_id=employee_data.company_id,
                    department=employee_data.department,
                    position=employee_data.position,
                    employment_type=employee_data.employment_type,
                    employment_status=employee_data.employment_status,
                    start_date=start_date,
                    end_date=end_date,
                    probation_end_date=probation_end_date,
                    contract_end_date=contract_end_date,
                    supervisor_id=employee_data.supervisor_id,
                    work_location=employee_data.work_location,
                    salary=salary,
                    salary_currency=employee_data.salary_currency,
                    payment_frequency=employee_data.payment_frequency,
                    bank_name=employee_data.bank_name,
                    bank_account=employee_data.bank_account,
                    tax_id=employee_data.tax_id,
                    pension_number=employee_data.pension_number,
                    created_by=int(current_user_id)
                )
                
                db.session.add(employee)
                db.session.flush()  # Get the employee ID without committing
                
                # Handle uploaded documents if provided
                if employee_data.documents:
                    try:
                        saved_documents = handle_employee_documents(
                            employee_id=employee.id,
                            documents_data=employee_data.documents,
                            uploaded_by=current_user_id
                        )
                        print(f"DEBUG: Saved {len(saved_documents)} documents for employee {employee.id}")
                    except Exception as doc_error:
                        print(f"Warning: Document processing failed but employee created: {str(doc_error)}")
                        # Continue with employee creation even if documents fail
                
                # Generate template documents if requested
                if employee_data.generate_documents:
                    try:
                        documents_data = {
                            "nhima_number": employee_data.nhima_number,
                            "bank_branch": employee_data.bank_branch,
                            "sort_code": employee_data.sort_code,
                            "spouse_name": employee_data.spouse_name,
                            "children": employee_data.children,
                            "housing_allowance": employee_data.housing_allowance or 0,
                            "transport_allowance": employee_data.transport_allowance or 0,
                            "lunch_allowance": employee_data.lunch_allowance or 0,
                            "fuel_allowance": employee_data.fuel_allowance or 0,
                            "phone_allowance": employee_data.phone_allowance or 0,
                            "company_vehicle": employee_data.company_vehicle,
                            "company_phone": employee_data.company_phone,
                            "company_accommodation": employee_data.company_accommodation,
                            "working_hours": employee_data.working_hours
                        }
                        
                        generated_docs = generate_documents_from_templates(employee, company, documents_data)
                        
                        # Save documents to database
                        if generated_docs.get('new_joiner_form'):
                            save_document_to_database(
                                employee_id=employee.id,
                                document_type='new_joiner_form',
                                file_path=generated_docs['new_joiner_form'],
                                uploaded_by=current_user_id,
                                document_name=f"New Joiner Form - {employee.first_name} {employee.last_name}",
                                comments="Employee onboarding form with personal and employment details"
                            )
                        
                        if generated_docs.get('employment_contract'):
                            expiry_date = None
                            if employee.contract_end_date:
                                expiry_date = employee.contract_end_date
                            elif employee.start_date:
                                expiry_date = employee.start_date + timedelta(days=365)
                            
                            save_document_to_database(
                                employee_id=employee.id,
                                document_type='employment_contract',
                                file_path=generated_docs['employment_contract'],
                                uploaded_by=current_user_id,
                                document_name=f"Employment Contract - {employee.first_name} {employee.last_name}",
                                comments="Formal employment agreement with terms and conditions",
                                expiry_date=expiry_date
                            )
                            
                    except Exception as doc_error:
                        print(f"Template document generation failed but employee created: {str(doc_error)}")
                
                # Update company employee count
                company.employee_count = Employee.query.filter_by(
                    company_id=employee_data.company_id
                ).filter(
                    Employee.employment_status.in_(['Active', 'Probation'])
                ).count()
                
                # Create audit log
                audit = AuditLog(
                    employee_id=employee.id,
                    action="CREATE",
                    performed_by=current_user_id,
                    details=f"Employee {employee.employee_id} created via bulk upload with identity type: {employee.identity_type}"
                )
                db.session.add(audit)
                
                # Add to successful results
                employee_dict = employee.to_dict()
                if 'company_name' not in employee_dict or not employee_dict['company_name']:
                    employee_dict['company_name'] = company.name
                
                results["successful_employees"].append({
                    "index": index,
                    "employee_id": employee.employee_id,
                    "employee_db_id": employee.id,
                    "name": f"{employee.first_name} {employee.last_name}",
                    "email": employee.email,
                    "position": employee.position,
                    "department": employee.department
                })
                results["successful"] += 1
                
                print(f"Successfully created employee {index + 1}/{len(body.employees)}: {employee.employee_id}")

            except Exception as e:
                db.session.rollback()
                error_msg = f"Error creating employee {employee_data.first_name} {employee_data.last_name}: {str(e)}"
                print(f"Bulk upload error at index {index}: {error_msg}")
                
                results["errors"].append({
                    "index": index,
                    "employee_name": f"{employee_data.first_name} {employee_data.last_name}",
                    "error": error_msg
                })
                results["failed"] += 1
                
                if not body.skip_errors:
                    # If not skipping errors, stop processing
                    return jsonify({
                        "status": 500,
                        "isError": True,
                        "message": f"Bulk upload failed at employee {index + 1}: {error_msg}",
                        "partial_results": results
                    }), 500
        
        # Commit all successful creations
        if results["successful"] > 0:
            db.session.commit()
        
        # Final response
        message = f"Bulk upload completed: {results['successful']} successful, {results['failed']} failed"
        if results["failed"] > 0 and body.skip_errors:
            message += " (errors were skipped)"
        
        response_data = {
            "message": message,
            "status": 200,
            "isError": False,
            **results
        }
        
        return jsonify(response_data), 200

    except Exception as e:
        db.session.rollback()
        print(f"Error in bulk_create_employees: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            "status": 500,
            "isError": True,
            "message": f"Error in bulk upload: {str(e)}"
        }), 500

# Also add this helper endpoint for bulk upload template
@employee_bp.get('/bulk-upload-template', responses={"200": None}, security=[{"jwt": []}])
@jwt_required()
def get_bulk_upload_template():
    """Get template for bulk employee upload"""
    template = {
        "employees": [
            {
                "first_name": "Moses",
                "middle_name": "K.",
                "last_name": "Jasi",
                "email": "moses.jasi@example.com",
                "phone": "+260971234567",
                "personal_email": "mjasi.personal@example.com",
                "gender": "Male",
                "marital_status": "Single",
                "date_of_birth": "1992-06-15",
                "address": "Plot 12, Lusaka",
                "physical_address": "Lusaka, Zambia",
                
                "identity_type": "NRC",
                "national_id": "123456/12/1",
                "work_permit_number": None,
                "work_permit_valid_from": None,
                "work_permit_valid_to": None,
                
                "company_id": 1,
                "department": "IT Department",
                "position": "Software Engineer",
                "employment_type": "Full-time",
                "employment_status": "Active",
                "start_date": "2025-11-01",
                "end_date": None,
                "probation_end_date": None,
                "contract_end_date": None,
                "supervisor_id": None,
                "work_location": "Head Office",
                "salary": 12000.0,
                "salary_currency": "ZMW",
                "payment_frequency": "Monthly",
                
                "bank_name": "Stanbic Bank",
                "bank_branch": "Cairo Road",
                "bank_account": "1234567890",
                "sort_code": "090009",
                "account_number": "1234567890",
                
                "tax_id": "TPIN123456",
                "pension_number": "NAPSA98765",
                "nhima_number": "NHIMA55555",
                "napsa_number": "NAPSA98765",
                
                "next_of_kin": "Emmanuel Chanda",
                "emergency_contact_name": "Emmanuel Chanda",
                "emergency_contact_relationship": "Brother",
                "emergency_contact_phone": "+260977000999",
                
                "generate_documents": True,
                
                "documents": {
                    "profilePhoto": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgA...",  # Optional
                    "nrcCopy": "data:application/pdf;base64,JVBERi0xLjQKJeLjz9M...",  # Optional
                    "cv": "data:application/pdf;base64,JVBERi0xLjQKJeLjz9M...",  # Optional
                    "offerLetter": "data:application/pdf;base64,JVBERi0xLjQKJeLjz9M...",  # Optional
                    "certificates": [  # Optional
                        "data:application/pdf;base64,JVBERi0xLjQKJeLjz9M...",
                        "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD..."
                    ]
                }
            }
        ],
        "skip_errors": False,
        "send_notifications": False
    }
    
    return jsonify({
        "template": template,
        "instructions": {
            "required_fields": ["first_name", "last_name", "date_of_birth", "gender", "company_id", "position", "department", "employment_type", "start_date"],
            "optional_fields": "All other fields are optional including documents",
            "identity_documents": "Provide either national_id (for NRC) or work_permit_number with dates (for Work Permit)",
            "documents": "All document fields are optional. Supported formats: PNG, JPG, JPEG, PDF",
            "max_file_size": "10MB per document",
            "max_employees": "100 per bulk upload"
        }
    }), 200

# ---------------------- WORK PERMIT EXPIRY NOTIFICATION ROUTES ---------------------- #
@employee_bp.get('/work-permit-expiry-notifications', responses={"200": WorkPermitExpiryResponse, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def get_expiring_work_permits():
    """Get employees with expiring or expired work permits"""
    try:
        today = datetime.now().date()
        thirty_days_from_now = today + timedelta(days=30)
        
        # Employees with expired work permits
        expired_employees = Employee.query.filter(
            Employee.identity_type == 'Work Permit',
            Employee.work_permit_valid_to < today,
            Employee.work_permit_expiry_notified == False,
            Employee.employment_status.in_(['Active', 'Probation'])
        ).all()
        
        # Employees with work permits expiring within 30 days
        expiring_soon_employees = Employee.query.filter(
            Employee.identity_type == 'Work Permit',
            Employee.work_permit_valid_to >= today,
            Employee.work_permit_valid_to <= thirty_days_from_now,
            Employee.work_permit_expiry_notified == False,
            Employee.employment_status.in_(['Active', 'Probation'])
        ).all()
        
        expired_data = [emp.to_dict() for emp in expired_employees]
        expiring_soon_data = [emp.to_dict() for emp in expiring_soon_employees]
        
        return jsonify({
            "expired_work_permits": expired_data,
            "expiring_soon_work_permits": expiring_soon_data,
            "expired_count": len(expired_data),
            "expiring_soon_count": len(expiring_soon_data),
            "check_date": today.isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": 500,
            "isError": True,
            "message": f"Error checking expiring work permits: {str(e)}"
        }), 500

@employee_bp.post('/<int:employee_id>/mark-work-permit-notified', responses={"200": SuccessResponse, "404": ErrorResponse, "500": ErrorResponse}, security=[{"jwt": []}])
@jwt_required()
def mark_work_permit_expiry_notified(path: EmployeeIdPath):
    """Mark work permit expiry as notified"""
    try:
        employee = Employee.query.get(path.employee_id)
        if not employee:
            return jsonify({
                "status": 404,
                "isError": True,
                "message": "Employee not found"
            }), 404

        if employee.identity_type != 'Work Permit':
            return jsonify({
                "status": 400,
                "isError": True,
                "message": "Employee does not have a work permit"
            }), 400

        employee.work_permit_expiry_notified = True
        employee.updated_at = datetime.now()
        db.session.commit()

        return jsonify({
            "message": "Work permit expiry notification marked as sent",
            "status": 200,
            "isError": False
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": 500,
            "isError": True,
            "message": f"Error updating work permit notification status: {str(e)}"
        }), 500