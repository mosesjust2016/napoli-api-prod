# controllers/documents/documents.py
from flask import request, current_app
from flask_openapi3 import APIBlueprint, Tag
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import os
from werkzeug.utils import secure_filename

from ...addons.extensions import db
from ...models import EmployeeDocument, Employee, HRAction
from ...addons.functions import jsonifyFormat

documents_bp = APIBlueprint('documents', __name__, url_prefix='/api/documents')
documents_tag = Tag(name="Documents", description="Employee documents management")

# ==================== CONSTANTS ====================

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'txt'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==================== RESPONSE SCHEMAS ====================

class DocumentResponseSchema(BaseModel):
    id: str = Field(..., description="Document ID")
    employee_id: int = Field(..., description="Employee ID")
    document_type: str = Field(..., description="Document type")
    document_name: str = Field(..., description="Document name")
    file_url: str = Field(..., description="File URL or path")
    upload_date: str = Field(..., description="Upload date")
    uploaded_by: int = Field(..., description="User ID who uploaded")
    expiry_date: Optional[str] = Field(None, description="Expiry date")
    is_verified: bool = Field(..., description="Whether verified")
    verified_by: Optional[int] = Field(None, description="User ID who verified")
    comments: Optional[str] = Field(None, description="Comments")
    employee_name: Optional[str] = Field(None, description="Employee name")

class DocumentListResponseSchema(BaseModel):
    status: int = Field(..., description="HTTP status code")
    data: List[DocumentResponseSchema] = Field(..., description="List of documents")
    pagination: Dict[str, Any] = Field(..., description="Pagination info")
    message: str = Field(..., description="Response message")

class DocumentSingleResponseSchema(BaseModel):
    status: int = Field(..., description="HTTP status code")
    data: DocumentResponseSchema = Field(..., description="Document data")
    message: str = Field(..., description="Response message")

class DocumentTypesResponseSchema(BaseModel):
    status: int = Field(..., description="HTTP status code")
    data: List[str] = Field(..., description="List of document types")
    message: str = Field(..., description="Response message")

class SuccessResponseSchema(BaseModel):
    status: int = Field(..., description="HTTP status code")
    message: str = Field(..., description="Response message")

class ErrorResponseSchema(BaseModel):
    status: int = Field(..., description="HTTP status code")
    error: str = Field(..., description="Error message")
    message: str = Field(..., description="User-friendly message")

# ==================== PATH PARAMETER SCHEMAS ====================

class EmployeeIdPath(BaseModel):
    employee_id: int = Field(..., description="Employee ID", gt=0)

class DocumentIdPath(BaseModel):
    document_id: str = Field(..., description="Document ID (UUID)")

# ==================== REQUEST SCHEMAS ====================

class DocumentUpdateSchema(BaseModel):
    document_name: Optional[str] = Field(None, description="Document name")
    expiry_date: Optional[str] = Field(None, description="Expiry date (YYYY-MM-DD)")
    is_verified: Optional[bool] = Field(None, description="Whether document is verified")
    verified_by: Optional[int] = Field(None, description="User ID who verified the document")
    comments: Optional[str] = Field(None, description="Additional comments")

# ==================== SINGLE UPLOAD ENDPOINT ====================

@documents_bp.post(
    '/upload',
    tags=[documents_tag],
    responses={
        "201": DocumentSingleResponseSchema,
        "400": ErrorResponseSchema,
        "404": ErrorResponseSchema,
        "500": ErrorResponseSchema
    },
    security=[{"jwt": []}]
)
@jwt_required()
def upload_document():
    """
    Upload a document with file and metadata in one request
    Uses multipart/form-data with both file and form fields
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Check if file is present
        if 'file' not in request.files:
            return jsonifyFormat({
                'status': 400,
                'error': 'No file provided',
                'message': 'Please select a file to upload'
            }, 400)
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonifyFormat({
                'status': 400,
                'error': 'No file selected',
                'message': 'Please select a valid file'
            }, 400)
        
        # Get and validate form data
        employee_id = request.form.get('employee_id', type=int)
        document_type = request.form.get('document_type')
        document_name = request.form.get('document_name') or secure_filename(file.filename)
        expiry_date = request.form.get('expiry_date')
        comments = request.form.get('comments')
        
        # Validate required fields
        if not employee_id:
            return jsonifyFormat({
                'status': 400,
                'error': 'Missing employee_id',
                'message': 'Employee ID is required'
            }, 400)
        
        if not document_type:
            return jsonifyFormat({
                'status': 400,
                'error': 'Missing document_type',
                'message': 'Document type is required'
            }, 400)
        
        # Validate employee exists
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonifyFormat({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }, 404)
        
        # Check file type
        if not allowed_file(file.filename):
            return jsonifyFormat({
                'status': 400,
                'error': 'Invalid file type',
                'message': f'Allowed file types: {", ".join(ALLOWED_EXTENSIONS)}'
            }, 400)
        
        # Check file size
        file.seek(0, 2)  # Seek to end to get size
        file_size = file.tell()
        file.seek(0)  # Reset file pointer
        
        if file_size > MAX_FILE_SIZE:
            return jsonifyFormat({
                'status': 400,
                'error': 'File too large',
                'message': f'File size must be less than {MAX_FILE_SIZE // (1024*1024)}MB'
            }, 400)
        
        # Generate unique filename
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        
        # Create uploads directory if it doesn't exist
        upload_folder = current_app.config.get('UPLOAD_FOLDER', '/app/uploads')
        os.makedirs(upload_folder, exist_ok=True)
        
        # Save file
        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)
        
        # Create file URL for the document record
        file_url = f"/api/documents/files/{unique_filename}"
        
        # Parse expiry date if provided
        expiry_date_obj = None
        if expiry_date:
            try:
                expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
            except ValueError:
                return jsonifyFormat({
                    'status': 400,
                    'error': 'Invalid expiry date format',
                    'message': 'Expiry date must be in YYYY-MM-DD format'
                }, 400)
        
        # Create document record
        document = EmployeeDocument(
            id=str(uuid.uuid4()),
            employee_id=employee_id,
            document_type=document_type,
            document_name=document_name,
            file_url=file_url,
            upload_date=datetime.now(),
            uploaded_by=current_user_id,
            expiry_date=expiry_date_obj,
            is_verified=False,  # Default to not verified
            verified_by=None,
            comments=comments
        )
        
        # Create HR action log
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=employee_id,
            action_type='document_upload',
            action_date=datetime.now(),
            effective_date=datetime.now().date(),
            performed_by=current_user_id,
            details={
                'document_type': document_type,
                'document_name': document_name,
                'file_url': file_url,
                'expiry_date': expiry_date,
                'file_size': file_size,
                'original_filename': original_filename
            },
            summary=f"Document uploaded: {document_name} ({document_type.replace('_', ' ').title()})",
            status='completed'
        )
        
        db.session.add(document)
        db.session.add(hr_action)
        db.session.commit()
        
        # Get employee name for response
        employee_name = f"{employee.first_name} {employee.last_name}"
        
        document_data = document.to_dict()
        document_data['employee_name'] = employee_name
        
        return jsonifyFormat({
            'status': 201,
            'data': document_data,
            'message': 'Document uploaded successfully'
        }, 201)
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Document upload error: {str(e)}")
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to upload document'
        }, 500)

# ==================== OTHER DOCUMENT ENDPOINTS ====================

@documents_bp.get(
    '/employee/<int:employee_id>', 
    tags=[documents_tag],
    responses={
        "200": DocumentListResponseSchema, 
        "404": ErrorResponseSchema, 
        "500": ErrorResponseSchema
    },
    security=[{"jwt": []}]
)
@jwt_required()
def get_employee_documents(path: EmployeeIdPath):
    """Get documents for an employee"""
    try:
        employee_id = path.employee_id
        
        # Validate employee exists
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonifyFormat({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }, 404)
        
        # Get query parameters
        document_type = request.args.get('document_type')
        is_verified = request.args.get('is_verified')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Build query
        query = EmployeeDocument.query.filter_by(employee_id=employee_id)
        
        if document_type:
            query = query.filter_by(document_type=document_type)
        
        if is_verified:
            is_verified_bool = is_verified.lower() == 'true'
            query = query.filter_by(is_verified=is_verified_bool)
        
        # Order by upload date descending
        query = query.order_by(EmployeeDocument.upload_date.desc())
        
        # Pagination
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonifyFormat({
            'status': 200,
            'data': [doc.to_dict() for doc in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            },
            'message': 'Employee documents retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve employee documents'
        }, 500)

@documents_bp.put(
    '/<string:document_id>', 
    tags=[documents_tag],
    responses={
        "200": DocumentSingleResponseSchema, 
        "404": ErrorResponseSchema, 
        "500": ErrorResponseSchema
    },
    security=[{"jwt": []}]
)
@jwt_required()
def update_document(path: DocumentIdPath, body: DocumentUpdateSchema):
    """Update document metadata"""
    try:
        document_id = path.document_id
        data = body.model_dump(exclude_unset=True)
        
        document = EmployeeDocument.query.get(document_id)
        if not document:
            return jsonifyFormat({
                'status': 404,
                'error': 'Document not found',
                'message': 'The specified document does not exist'
            }, 404)
        
        # Update allowed fields
        allowed_fields = ['document_name', 'expiry_date', 'is_verified', 'verified_by', 'comments']
        
        for field in allowed_fields:
            if field in data:
                if field == 'expiry_date' and data[field]:
                    setattr(document, field, datetime.strptime(data[field], '%Y-%m-%d').date())
                else:
                    setattr(document, field, data[field])

        document.updated_at = datetime.now()
        db.session.commit()
        
        return jsonifyFormat({
            'status': 200,
            'data': document.to_dict(),
            'message': 'Document updated successfully'
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to update document'
        }, 500)

@documents_bp.delete(
    '/<string:document_id>', 
    tags=[documents_tag],
    responses={
        "200": SuccessResponseSchema, 
        "404": ErrorResponseSchema, 
        "500": ErrorResponseSchema
    },
    security=[{"jwt": []}]
)
@jwt_required()
def delete_document(path: DocumentIdPath):
    """Delete a document"""
    try:
        document_id = path.document_id
        document = EmployeeDocument.query.get(document_id)
        
        if not document:
            return jsonifyFormat({
                'status': 404,
                'error': 'Document not found',
                'message': 'The specified document does not exist'
            }, 404)
        
        # In production, you would also delete the actual file from storage
        # For now, just delete the database record
        
        db.session.delete(document)
        db.session.commit()
        
        return jsonifyFormat({
            'status': 200,
            'message': 'Document deleted successfully'
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to delete document'
        }, 500)

@documents_bp.get(
    '/files/<filename>',
    tags=[documents_tag],
    security=[{"jwt": []}]
)
@jwt_required()
def get_uploaded_file(filename):
    """Serve uploaded files"""
    try:
        upload_folder = current_app.config.get('UPLOAD_FOLDER', '/app/uploads')
        file_path = os.path.join(upload_folder, secure_filename(filename))
        
        if not os.path.exists(file_path):
            return jsonifyFormat({
                'status': 404,
                'error': 'File not found',
                'message': 'The requested file does not exist'
            }, 404)
        
        from flask import send_file
        return send_file(file_path)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve file'
        }, 500)

@documents_bp.get(
    '/<string:document_id>', 
    tags=[documents_tag],
    responses={
        "200": DocumentSingleResponseSchema, 
        "404": ErrorResponseSchema, 
        "500": ErrorResponseSchema
    },
    security=[{"jwt": []}]
)
@jwt_required()
def get_document(path: DocumentIdPath):
    """Get a specific document by ID"""
    try:
        document_id = path.document_id
        document = EmployeeDocument.query.get(document_id)
        
        if not document:
            return jsonifyFormat({
                'status': 404,
                'error': 'Document not found',
                'message': 'The specified document does not exist'
            }, 404)
        
        return jsonifyFormat({
            'status': 200,
            'data': document.to_dict(),
            'message': 'Document retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve document'
        }, 500)

@documents_bp.get(
    '/types', 
    tags=[documents_tag],
    responses={
        "200": DocumentTypesResponseSchema, 
        "500": ErrorResponseSchema
    },
    security=[{"jwt": []}]
)
@jwt_required()
def get_document_types():
    """Get available document types"""
    try:
        # This would typically come from your ENUM definition
        document_types = [
            'id_card', 'contract', 'certificate', 'degree', 'resume',
            'bank_details', 'tax_form', 'pension_form', 'napsa_card', 
            'nhima_card', 'work_permit', 'passport', 'driving_license', 'other'
        ]
        
        return jsonifyFormat({
            'status': 200,
            'data': document_types,
            'message': 'Document types retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve document types'
        }, 500)