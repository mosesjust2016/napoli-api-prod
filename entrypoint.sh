#!/bin/sh
echo "⏳ Waiting for MySQL to be ready..."
until nc -z "$DB_HOST" 3306; do
    sleep 1
done
echo "✅ MySQL is up - initializing database..."

python << 'END'
import os
import sys
from sqlalchemy import text

# Add app path
sys.path.insert(0, '/app')

from app import create_app
from core.addons.extensions import db

# Import all models
from core.models.users import User
from core.models.roleModel import Role
from core.models.permissionModel import Permission
from core.models.employees import Employee
from core.models.tokenBlacklistModel import TokenBlacklist
from core.models.passwordResetTokenModel import PasswordResetToken
from core.models.auditLogModel import AuditLog
from core.models.companies import Company  # Import Company model

app = create_app()

with app.app_context():
    print("🔍 Connecting to the database...")
    try:
        db.session.execute(text('SELECT 1'))
        print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)

    print("💣 Dropping all existing tables...")
    try:
        db.drop_all()
        db.session.commit()
        print("✅ All tables dropped successfully")
    except Exception as e:
        print(f"⚠️ Error dropping tables: {e}")
        db.session.rollback()

    print("📦 Creating all tables...")
    try:
        db.create_all()
        db.session.commit()
        print("✅ Tables recreated successfully")
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        db.session.rollback()
        sys.exit(1)

    print("🏢 Creating default company...")
    try:
        # Create Napoli Property Investments Limited as default company
        default_company = Company(
            name="Napoli Property Inv Ltd",
            code="NAP",
            employee_id_prefix="NAP",  # Add employee ID prefix
            registration_number="ZMW/REG-1005/25",
            employee_count=0,
            status="Active"
        )
        db.session.add(default_company)
        db.session.flush()  # Get the company ID without committing
        print("✅ Default company 'Napoli Property Inv Ltd' created successfully with employee_id_prefix: NAP")
    except Exception as e:
        print(f"⚠️ Error creating default company: {e}")
        db.session.rollback()
        sys.exit(1)

    print("🧩 Creating roles...")
    try:
        admin_role = Role.query.filter_by(name='admin').first()
        if not admin_role:
            admin_role = Role(name='admin', tier=1, description='Administrator')
            db.session.add(admin_role)
        
        hr_role = Role.query.filter_by(name='hr').first()
        if not hr_role:
            hr_role = Role(name='hr', tier=2, description='HR Admin')
            db.session.add(hr_role)
        
        payroll_role = Role.query.filter_by(name='payroll').first()
        if not payroll_role:
            payroll_role = Role(name='payroll', tier=3, description='Payroll User')
            db.session.add(payroll_role)
        
        db.session.flush()
        print("✅ Roles created successfully")
    except Exception as e:
        print(f"⚠️ Error creating roles: {e}")
        db.session.rollback()

    print("👤 Creating default users...")
    try:
        # Super Admin
        super_admin = User.query.filter_by(email='super.admin@hrgroup.co.zm').first()
        if not super_admin:
            super_admin = User(
                email='super.admin@hrgroup.co.zm',
                name='Super Administrator',
                is_active=True
            )
            super_admin.set_password('password123')
            super_admin.roles.append(admin_role)
            db.session.add(super_admin)
        
        # HR Admin
        hr_admin = User.query.filter_by(email='hr.admin@hrgroup.co.zm').first()
        if not hr_admin:
            hr_admin = User(
                email='hr.admin@hrgroup.co.zm',
                name='HR Administrator',
                is_active=True
            )
            hr_admin.set_password('password123')
            hr_admin.roles.append(hr_role)
            db.session.add(hr_admin)
        
        # HR Payroll
        hr_payroll = User.query.filter_by(email='hr.payroll@hrgroup.co.zm').first()
        if not hr_payroll:
            hr_payroll = User(
                email='hr.payroll@hrgroup.co.zm',
                name='HR Payroll User',
                is_active=True
            )
            hr_payroll.set_password('password123')
            hr_payroll.roles.append(payroll_role)
            db.session.add(hr_payroll)
        
        db.session.commit()
        print("✅ Default users created successfully!")
        
        # Display company details
        print(f"🏢 Company Details:")
        print(f"   - Name: {default_company.name}")
        print(f"   - Code: {default_company.code}")
        print(f"   - Employee ID Prefix: {default_company.employee_id_prefix}")
        print(f"   - Registration: {default_company.registration_number}")
        print(f"   - Status: {default_company.status}")
        
    except Exception as e:
        print(f"⚠️ Error creating default users: {e}")
        db.session.rollback()

print("✅ Database initialization complete!")
END

if [ $? -eq 0 ]; then
    echo "🚀 Starting Flask with debug mode..."
    flask run --host=0.0.0.0 --debug
else
    echo "❌ Database initialization failed. Exiting."
    exit 1
fi