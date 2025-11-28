import json
from sqlalchemy import event
from flask_jwt_extended import get_jwt_identity
from core.addons.extensions import db
from .payroll import PayrollPeriod, PayrollRecord
from .payroll_audit import PayrollAudit

def _serialize_model(instance):
    """Return a plain dict of a model's column->value pairs."""
    d = {}
    for c in instance.__table__.columns:
        val = getattr(instance, c.name)
        try:
            json.dumps(val)
            d[c.name] = val
        except TypeError:
            d[c.name] = str(val) if val is not None else None
    return d

def log_audit(entity_type, entity_id, action, before, after, performed_by=None, comment=None):
    a = PayrollAudit(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        performed_by=performed_by,
        before_data=json.dumps(before) if before is not None else None,
        after_data=json.dumps(after) if after is not None else None,
        comment=comment
    )
    db.session.add(a)
    # commit is deferred to outer transaction (recommended).
    # If you want immediate commit, call db.session.commit() here.

# PayrollPeriod listeners
@event.listens_for(PayrollPeriod, 'after_insert')
def after_insert_period(mapper, connection, target):
    before = None
    after = _serialize_model(target)
    # Try to get user id from Flask context (best-effort; might be None)
    try:
        performed_by = get_jwt_identity()
    except Exception:
        performed_by = None
    # use a new session bound to connection
    session = db.session.object_session(target) or db.session
    session.add(PayrollAudit(
        entity_type='PayrollPeriod',
        entity_id=target.id,
        action='created',
        performed_by=performed_by,
        before_data=None,
        after_data=json.dumps(after)
    ))

@event.listens_for(PayrollPeriod, 'after_update')
def after_update_period(mapper, connection, target):
    # get history via target.__dict__ is not always reliable; do best-effort
    before = None
    after = _serialize_model(target)
    try:
        performed_by = get_jwt_identity()
    except Exception:
        performed_by = None
    session = db.session.object_session(target) or db.session
    session.add(PayrollAudit(
        entity_type='PayrollPeriod',
        entity_id=target.id,
        action='updated',
        performed_by=performed_by,
        before_data=None,
        after_data=json.dumps(after)
    ))

@event.listens_for(PayrollPeriod, 'after_delete')
def after_delete_period(mapper, connection, target):
    before = _serialize_model(target)
    try:
        performed_by = get_jwt_identity()
    except Exception:
        performed_by = None
    session = db.session.object_session(target) or db.session
    session.add(PayrollAudit(
        entity_type='PayrollPeriod',
        entity_id=target.id,
        action='deleted',
        performed_by=performed_by,
        before_data=json.dumps(before),
        after_data=None
    ))

# PayrollRecord listeners (same pattern)
@event.listens_for(PayrollRecord, 'after_insert')
def after_insert_record(mapper, connection, target):
    after = _serialize_model(target)
    try:
        performed_by = get_jwt_identity()
    except Exception:
        performed_by = None
    session = db.session.object_session(target) or db.session
    session.add(PayrollAudit(
        entity_type='PayrollRecord',
        entity_id=target.id,
        action='created',
        performed_by=performed_by,
        before_data=None,
        after_data=json.dumps(after)
    ))

@event.listens_for(PayrollRecord, 'after_update')
def after_update_record(mapper, connection, target):
    after = _serialize_model(target)
    try:
        performed_by = get_jwt_identity()
    except Exception:
        performed_by = None
    session = db.session.object_session(target) or db.session
    session.add(PayrollAudit(
        entity_type='PayrollRecord',
        entity_id=target.id,
        action='updated',
        performed_by=performed_by,
        before_data=None,
        after_data=json.dumps(after)
    ))

@event.listens_for(PayrollRecord, 'after_delete')
def after_delete_record(mapper, connection, target):
    before = _serialize_model(target)
    try:
        performed_by = get_jwt_identity()
    except Exception:
        performed_by = None
    session = db.session.object_session(target) or db.session
    session.add(PayrollAudit(
        entity_type='PayrollRecord',
        entity_id=target.id,
        action='deleted',
        performed_by=performed_by,
        before_data=json.dumps(before),
        after_data=None
    ))
