# models/attendanceModel.py
from datetime import datetime
from ..addons.extensions import db

class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    check_in = db.Column(db.DateTime, nullable=True)
    check_out = db.Column(db.DateTime, nullable=True)
    hours_worked = db.Column(db.Float, default=0.0)

    status = db.Column(
        db.Enum("Present", "Absent", "Late", name="attendance_status_enum"),
        default="Present",
        nullable=False
    )

    employee = db.relationship("Employee", backref="attendance_records")

    def to_dict(self):
        """Convert model to dictionary for JSON responses."""
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "date": self.date.isoformat(),
            "check_in": self.check_in.isoformat() if self.check_in else None,
            "check_out": self.check_out.isoformat() if self.check_out else None,
            "hours_worked": self.hours_worked,
            "status": self.status,
        }

    @classmethod
    def get_attendance_by_company_and_date(cls, company_id, date):
        """Get attendance records for a company and date."""
        return (
            cls.query
            .join(Employee, Employee.id == cls.employee_id)
            .filter(Employee.company_id == company_id)
            .filter(cls.date == date)
            .all()
        )

    @classmethod
    def get_employee_hours_for_period(cls, employee_id, period):
        """Get total hours worked by an employee for a specific period."""
        total_hours = (
            db.session.query(db.func.sum(cls.hours_worked))
            .filter(cls.employee_id == employee_id)
            .filter(cls.date.like(f"{period}-%"))
            .scalar()
        )
        return total_hours or 0

    @classmethod
    def find_existing_record(cls, employee_id, date):
        """Find existing attendance record for employee and date."""
        return cls.query.filter_by(employee_id=employee_id, date=date).first()