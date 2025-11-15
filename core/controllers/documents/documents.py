# controllers/documents/documents.py
from flask import request
from flask_openapi3 import APIBlueprint, Tag
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from ...addons.extensions import db
from ...models import EmployeeDocument, Employee, HRAction
from ...addons.functions import jsonifyFormat

documents_bp = APIBlueprint('documents', __name__, url_prefix='/api/documents')
documents_tag = Tag(name="Documents", description="Employee documents management")

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

class DocumentUploadSchema(BaseModel):
    employee_id: int = Field(..., description="Employee ID", gt=0)
    document_type: str = Field(..., description="Document type")
    document_name: str = Field(..., description="Document name")
    file_url: str = Field(..., description="File URL or path")
    uploaded_by: int = Field(..., description="User ID who uploaded the document")
    expiry_date: Optional[str] = Field(None, description="Expiry date (YYYY-MM-DD)")
    is_verified: Optional[bool] = Field(False, description="Whether document is verified")
    verified_by: Optional[int] = Field(None, description="User ID who verified the document")
    comments: Optional[str] = Field(None, description="Additional comments")

class DocumentUpdateSchema(BaseModel):
    document_name: Optional[str] = Field(None, description="Document name")
    expiry_date: Optional[str] = Field(None, description="Expiry date (YYYY-MM-DD)")
    is_verified: Optional[bool] = Field(None, description="Whether document is verified")
    verified_by: Optional[int] = Field(None, description="User ID who verified the document")
    comments: Optional[str] = Field(None, description="Additional comments")

# ==================== ROUTES ====================

@documents_bp.post(
    '/', 
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
def upload_document(body: DocumentUploadSchema):
    """Upload a new employee document"""
    try:
        current_user_id = get_jwt_identity()
        data = body.model_dump()
        
        # Validate employee exists
        employee = Employee.query.get(data['employee_id'])
        if not employee:
            return jsonifyFormat({
                'status': 404,
                'error': 'Employee not found',
                'message': 'The specified employee does not exist'
            }, 404)

        # Create document record
        document = EmployeeDocument(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            document_type=data['document_type'],
            document_name=data['document_name'],
            file_url=data['file_url'],
            upload_date=datetime.now(),
            uploaded_by=data['uploaded_by'],
            expiry_date=datetime.strptime(data['expiry_date'], '%Y-%m-%d').date() if data.get('expiry_date') else None,
            is_verified=data.get('is_verified', False),
            verified_by=data.get('verified_by'),
            comments=data.get('comments')
        )
        
        # Create HR action log
        hr_action = HRAction(
            id=str(uuid.uuid4()),
            employee_id=data['employee_id'],
            action_type='compliance_update',
            action_date=datetime.now(),
            effective_date=datetime.now().date(),
            performed_by=data['uploaded_by'],
            details={
                'document_type': data['document_type'],
                'document_name': data['document_name'],
                'file_url': data['file_url'],
                'expiry_date': data.get('expiry_date'),
                'is_verified': data.get('is_verified', False)
            },
            summary=f"Document uploaded: {data['document_name']} ({data['document_type'].replace('_', ' ').title()})",
            status='completed'
        )
        
        db.session.add(document)
        db.session.add(hr_action)
        db.session.commit()
        
        return jsonifyFormat({
            'status': 201,
            'data': document.to_dict(),
            'message': 'Document uploaded successfully'
        }, 201)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to upload document'
        }, 500)

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

# ==================== ADDITIONAL DOCUMENT ROUTES ====================

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
            'bank_details', 'tax_form', 'pension_form', 'other'
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