# controllers/approvals/approvals.py
from flask import Blueprint, request, jsonify
from flask_openapi3 import APIBlueprint, Tag
from ...addons.extensions import db
from ...models import HRAction, User
from ...addons.functions import jsonifyFormat
import uuid
from datetime import datetime

approvals_bp = APIBlueprint('approvals', __name__, url_prefix='/api/approvals')

approvals_tag = Tag(name="Approvals", description="Approval workflow management")

@approvals_bp.post('/request', tags=[approvals_tag])
def request_approval():
    """Request approval for an HR action"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['hr_action_id', 'approver_id', 'requested_by']
        missing_fields = [field for field in required_fields if field not in data or not data[field]]
        if missing_fields:
            return jsonifyFormat({
                'status': 400,
                'error': f'Missing required fields: {", ".join(missing_fields)}',
                'message': 'All required fields must be provided'
            }, 400)
        
        # Validate HR action exists
        hr_action = HRAction.query.get(data['hr_action_id'])
        if not hr_action:
            return jsonifyFormat({
                'status': 404,
                'error': 'HR action not found',
                'message': 'The specified HR action does not exist'
            }, 404)
        
        # Validate approver exists
        approver = User.query.get(data['approver_id'])
        if not approver:
            return jsonifyFormat({
                'status': 404,
                'error': 'Approver not found',
                'message': 'The specified approver does not exist'
            }, 404)
        
        # Update HR action to require approval
        hr_action.requires_approval = True
        hr_action.status = 'pending'
        
        db.session.commit()
        
        # In production, you would send email/SMS notification to approver here
        
        return jsonifyFormat({
            'status': 200,
            'data': hr_action.to_dict(),
            'message': 'Approval requested successfully'
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to request approval'
        }, 500)

@approvals_bp.put('/<string:action_id>/approve', tags=[approvals_tag])
def approve_action(action_id):
    """Approve an HR action"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('approved_by'):
            return jsonifyFormat({
                'status': 400,
                'error': 'Approver ID is required',
                'message': 'Approver ID must be provided'
            }, 400)
        
        # Validate HR action exists
        hr_action = HRAction.query.get(action_id)
        if not hr_action:
            return jsonifyFormat({
                'status': 404,
                'error': 'HR action not found',
                'message': 'The specified HR action does not exist'
            }, 404)
        
        # Validate approver exists
        approver = User.query.get(data['approved_by'])
        if not approver:
            return jsonifyFormat({
                'status': 404,
                'error': 'Approver not found',
                'message': 'The specified approver does not exist'
            }, 404)
        
        # Update HR action with approval
        hr_action.approved_by = data['approved_by']
        hr_action.approval_date = datetime.now()
        hr_action.status = 'completed'
        hr_action.requires_approval = False
        
        db.session.commit()
        
        return jsonifyFormat({
            'status': 200,
            'data': hr_action.to_dict(),
            'message': 'HR action approved successfully'
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to approve HR action'
        }, 500)

@approvals_bp.put('/<string:action_id>/reject', tags=[approvals_tag])
def reject_action(action_id):
    """Reject an HR action"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('rejected_by'):
            return jsonifyFormat({
                'status': 400,
                'error': 'Rejecter ID is required',
                'message': 'Rejecter ID must be provided'
            }, 400)
        
        # Validate HR action exists
        hr_action = HRAction.query.get(action_id)
        if not hr_action:
            return jsonifyFormat({
                'status': 404,
                'error': 'HR action not found',
                'message': 'The specified HR action does not exist'
            }, 404)
        
        # Validate rejecter exists
        rejecter = User.query.get(data['rejected_by'])
        if not rejecter:
            return jsonifyFormat({
                'status': 404,
                'error': 'Rejecter not found',
                'message': 'The specified rejecter does not exist'
            }, 404)
        
        # Update HR action with rejection
        hr_action.status = 'cancelled'
        hr_action.requires_approval = False
        hr_action.comments = f"Rejected by {rejecter.full_name}. Reason: {data.get('reason', 'No reason provided')}"
        
        db.session.commit()
        
        return jsonifyFormat({
            'status': 200,
            'data': hr_action.to_dict(),
            'message': 'HR action rejected successfully'
        }, 200)
        
    except Exception as e:
        db.session.rollback()
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to reject HR action'
        }, 500)

@approvals_bp.get('/pending', tags=[approvals_tag])
def get_pending_approvals():
    """Get pending approvals"""
    try:
        # Get query parameters
        approver_id = request.args.get('approver_id')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Build query for pending approvals
        query = HRAction.query.filter(
            HRAction.requires_approval == True,
            HRAction.status == 'pending'
        )
        
        # If specific approver is provided (in production, you'd filter by approver roles/companies)
        if approver_id:
            # This is simplified - in production, you'd have a proper approver assignment system
            pass
        
        # Order by action date
        query = query.order_by(HRAction.action_date.desc())
        
        # Pagination
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonifyFormat({
            'status': 200,
            'data': [action.to_dict() for action in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            },
            'message': 'Pending approvals retrieved successfully'
        }, 200)
        
    except Exception as e:
        return jsonifyFormat({
            'status': 500,
            'error': str(e),
            'message': 'Failed to retrieve pending approvals'
        }, 500)