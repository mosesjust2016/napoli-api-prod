from flask_openapi3 import APIBlueprint, Tag
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ...addons.functions import jsonifyFormat
from ...models.payroll_audit import PayrollAudit
from core.addons.extensions import db

payroll_tag = Tag(name="Payroll", description="Payroll management & auditing")

@payroll_bp.get('/period/<int:period_id>/history', tags=[payroll_tag], security=[{"jwt": []}])
@jwt_required()
def get_period_history(period_id):
    """Return audit history for a payroll period"""
    try:
        audits = PayrollAudit.query.filter_by(entity_type='PayrollPeriod', entity_id=period_id).order_by(PayrollAudit.timestamp.desc()).all()
        data = [a.to_dict() for a in audits]
        return jsonifyFormat({"status": 200, "data": data}, 200)
    except Exception as e:
        return jsonifyFormat({"status": 500, "error": str(e)}, 500)

@payroll_bp.get('/record/<int:record_id>/history', tags=[payroll_tag], security=[{"jwt": []}])
@jwt_required()
def get_record_history(record_id):
    """Return audit history for a payroll record"""
    try:
        audits = PayrollAudit.query.filter_by(entity_type='PayrollRecord', entity_id=record_id).order_by(PayrollAudit.timestamp.desc()).all()
        data = [a.to_dict() for a in audits]
        return jsonifyFormat({"status": 200, "data": data}, 200)
    except Exception as e:
        return jsonifyFormat({"status": 500, "error": str(e)}, 500)
