from flask import Flask, jsonify, request
from flask_openapi3 import OpenAPI, Info, APIBlueprint, Tag
from flask_cors import CORS
from decouple import config
from datetime import timedelta
import urllib.parse
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv
import logging, os

# Import extensions ONLY (not models at module level)
from core.addons.extensions import db, jwt, bcrypt
from core.addons.functions import jsonifyFormat

# Import controllers
from core.controllers.dashboard.index import hr_bp
from core.controllers.auth.authentication import auth_bp
from core.controllers.companies.company import company_bp
from core.controllers.employees.employee import employee_bp
from core.controllers.hr_actions.hr_actions import hr_actions_bp
from core.controllers.disciplinary.disciplinary_records import disciplinary_bp
from core.controllers.leave.leave_records import leave_bp
from core.controllers.documents.documents import documents_bp
from core.controllers.reports.reports import reports_bp
from core.controllers.approvals.approvals import approvals_bp
from core.controllers.notifications.notifications import notifications_bp
from core.controllers.attendance.attendance_payroll import attendance_bp


def create_app():
    """
    Application factory for creating and configuring the Flask app
    """
    # Load environment variables FIRST
    load_dotenv()
    
    # CRITICAL: Import ALL models HERE at the start of create_app()
    # This ensures they're registered with SQLAlchemy before db.init_app()
    print("📦 Importing all models...")
    from core.models.users import User
    from core.models.roleModel import Role
    from core.models.permissionModel import Permission
    from core.models.employees import Employee
    from core.models.tokenBlacklistModel import TokenBlacklist
    from core.models.passwordResetTokenModel import PasswordResetToken
    from core.models.auditLogModel import AuditLog
    from core.models.companies import Company
    from core.models.disciplinary_records import DisciplinaryRecord
    from core.models.employee_documents import EmployeeDocument
    from core.models.hr_actions import HRAction
    from core.models.leave_records import LeaveRecord
    print("✅ All models imported")

    # Define the Info object for OpenAPI
    info = Info(
        title="Napoli HR Management System API",
        version="1.0.0",
        description="A comprehensive HR management system for Napoli Property Investment Limited"
    )

    # JWT Bearer Sample
    jwt_scheme = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    security_schemes = {
        "jwt": jwt_scheme,
    }

    # Create OpenAPI app instance
    app = OpenAPI(
        __name__,
        info=info,
        security_schemes=security_schemes,
    )

    # Enable CORS
    cors = CORS(app)
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Configure detailed logging
    log_file = "app.log"
    log_format = "%(asctime)s %(levelname)s: %(message)s"
    log_level = logging.DEBUG
    logging.basicConfig(
        filename=log_file, 
        level=log_level, 
        format=log_format,
        force=True  # Override any existing config
    )

    # Database configuration
    db_environment = config('ENVIRONMENT', default='Development')
    db_password = config('DB_PASSWORD', default='password')
    db_user = config('DB_USERNAME', default='root')
    db_host = config('DB_HOST', default='localhost')
    db_name = config('DB_NAME', default='napoli_hr')
    db_port = config('DB_PORT', default='3306')

    # Build database URI
    encoded_password = urllib.parse.quote_plus(db_password)
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f'mysql+pymysql://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}'
    )
    
    # SQLAlchemy configuration
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_POOL_RECYCLE'] = 3600
    app.config['SQLALCHEMY_POOL_SIZE'] = 10
    app.config['SQLALCHEMY_MAX_OVERFLOW'] = 20
    app.config['SQLALCHEMY_POOL_PRE_PING'] = True  # Verify connections before using
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
    }
    
    # Initialize extensions with app
    print("🔧 Initializing extensions...")
    db.init_app(app)
    bcrypt.init_app(app)
    
    # JWT Configuration
    app.secret_key = config("SECRET_KEY", default="your-secret-key-here-change-in-production")
    app.config["JWT_TOKEN_LOCATION"] = ["headers", "query_string"]
    app.config["JWT_BLACKLIST_ENABLED"] = True
    app.config["JWT_BLACKLIST_TOKEN_CHECKS"] = ["access", "refresh"] 
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=30)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=7)
    app.config["JWT_ALGORITHM"] = "HS256"
    app.config["JWT_HEADER_NAME"] = "Authorization"
    app.config["JWT_HEADER_TYPE"] = "Bearer"

    # Initialize the JWTManager
    jwt_manager = JWTManager(app)

    # Set up the token blacklist check after JWT initialization
    @jwt_manager.token_in_blocklist_loader
    def check_if_token_in_blacklist(jwt_header, jwt_payload):
        """Check if a JWT token is in the blacklist"""
        try:
            jti = jwt_payload.get("jti")
            if not jti:
                logger.warning("Token does not have a 'jti' field")
                return False

            # Import here to avoid circular imports
            from core.models.tokenBlacklistModel import TokenBlacklist
            token = TokenBlacklist.query.filter_by(token=jti).first()
            
            if token is not None:
                logger.info(f"Token with jti {jti} is blacklisted")
                return True
            else:
                logger.debug(f"Token with jti {jti} is valid")
                return False
        except Exception as e:
            logger.error(f"Error checking token in blacklist: {e}")
            return False

    # Request/Response logging middleware
    @app.before_request
    def log_request():
        """Log all incoming requests"""
        log_message = f"Method: {request.method}\n"
        log_message += f"Path: {request.path}\n"
        log_message += f"Headers: {dict(request.headers)}\n"
        
        # Log form data if it exists
        if request.form:
            log_message += f"Form Data: {dict(request.form)}\n"

        # Log file data if it exists (file names only)
        if request.files:
            file_names = [f.filename for f in request.files.values()]
            log_message += f"Files: {file_names}\n"

        logger.debug(log_message)

    @app.after_request
    def log_response(response):
        """Log all outgoing responses"""
        try:
            # Check if response is in direct passthrough mode
            if not response.direct_passthrough:
                log_message = f"Response: {response.status_code}\n"
                log_message += f"Headers: {response.headers}\n"
                
                # Only log response data for non-binary responses
                if response.content_type and 'application/json' in response.content_type:
                    try:
                        log_message += f"Data: {response.get_data(as_text=True)[:500]}"  # Limit to 500 chars
                    except:
                        log_message += "Data: [Unable to decode]"
                
                logger.debug(log_message)
        except RuntimeError as e:
            logger.warning("Failed to log response data. Response is in passthrough mode.")
        return response
    
    # Enable SQLAlchemy query logging (optional - can be verbose)
    if db_environment == "Development":
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

    # Error handlers
    @app.errorhandler(429)
    def too_many_requests(error):
        """Handle rate limiting errors"""
        resp = jsonify({
            "status": 429,
            "isError": True,
            "message": "Too many requests. Please try again later.",
        })
        return jsonifyFormat(resp, 429)

    @app.errorhandler(405)
    def method_not_allowed(error):
        """Handle method not allowed errors"""
        resp = jsonify({
            "status": 405,
            "isError": True,
            "message": "The method is not allowed for this request",
        })
        return jsonifyFormat(resp, 405)

    @app.errorhandler(404)
    def not_found(error):
        """Handle not found errors"""
        resp = jsonify({
            "status": 404,
            "isError": True,
            "message": "The requested resource was not found",
        })
        return jsonifyFormat(resp, 404)

    @app.errorhandler(500)
    def internal_server_error(error):
        """Handle internal server errors"""
        logger.error(f"Internal server error: {error}")
        resp = jsonify({
            "status": 500,
            "isError": True,
            "message": "An internal server error occurred",
        })
        return jsonifyFormat(resp, 500)

    # Register all blueprints
    print("📋 Registering blueprints...")
    app.register_api(hr_bp)
    app.register_api(auth_bp)
    app.register_api(company_bp)  
    app.register_api(employee_bp)
    app.register_api(hr_actions_bp)
    app.register_api(disciplinary_bp)
    app.register_api(leave_bp)
    app.register_api(documents_bp)
    app.register_api(reports_bp)
    app.register_api(approvals_bp)
    app.register_api(notifications_bp)
    app.register_api(attendance_bp)
    print("✅ All blueprints registered")

    # Default route
    @app.route("/", methods=["GET"])
    def home():
        """API home route with available endpoints"""
        return jsonify({
            "message": "Welcome to Napoli HR Management System API!",
            "version": "1.0.0",
            "status": "online",
            "endpoints": {
                "dashboard": "/api/dashboard/stats",
                "companies": "/api/companies",
                "employees": "/api/employees", 
                "hr_actions": "/api/hr-actions",
                "disciplinary": "/api/disciplinary-records",
                "leave": "/api/leave-records",
                "documents": "/api/documents",
                "reports": "/api/reports",
                "approvals": "/api/approvals",
                "notifications": "/api/notifications",
                "authentication": "/api/auth"
            }
        })

    # Health check endpoint
    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint for monitoring"""
        try:
            # Try to query the database
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            db_status = "healthy"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            db_status = "unhealthy"
        
        return jsonify({
            "status": "online",
            "database": db_status,
            "environment": db_environment
        })

    # Create database tables WITH proper error handling
    with app.app_context():
        try:
            print("\n" + "="*50)
            print("🔍 CHECKING DATABASE CONFIGURATION")
            print("="*50)
            print(f"Environment: {db_environment}")
            print(f"Database: {db_name}")
            print(f"Host: {db_host}:{db_port}")
            print(f"User: {db_user}")
            
            # Test database connection
            from sqlalchemy import text
            print("\n🔌 Testing database connection...")
            db.session.execute(text('SELECT 1'))
            db.session.commit()
            print("✅ Database connection successful")
            
            # Check registered models
            print("\n📋 Checking registered models...")
            print(f"Tables in metadata: {list(db.metadata.tables.keys())}")
            
            if not db.metadata.tables:
                raise Exception(
                    "❌ CRITICAL ERROR: No tables found in metadata! "
                    "Models are not being imported correctly."
                )
            
            print(f"✅ Found {len(db.metadata.tables)} tables in metadata")
            
            # Check existing tables in database
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            print(f"\n📊 Existing tables in database: {existing_tables}")
            
            # Find missing tables
            expected_tables = list(db.metadata.tables.keys())
            missing_tables = [table for table in expected_tables if table not in existing_tables]
            
            # Only drop/create if explicitly requested or in development with no tables
            recreate_db = config('RECREATE_DB', default='false').lower() == 'true'
            
            if recreate_db or (db_environment == "Development" and not existing_tables):
                print("\n🗑️  Dropping all existing tables...")
                db.drop_all()
                db.session.commit()
                print("✅ Tables dropped successfully")
                
                print("\n📦 Creating all tables...")
                db.create_all()
                db.session.commit()
                print("✅ Database tables created!")
                
                # Verify creation
                inspector = inspect(db.engine)
                tables_created = inspector.get_table_names()
                print(f"\n📊 Tables in database after creation: {tables_created}")
                
                if not tables_created:
                    raise Exception("❌ No tables were created in the database!")
                
                print(f"✅ Successfully created {len(tables_created)} tables")
            elif missing_tables:
                # CREATE MISSING TABLES ONLY - This is the key fix!
                print(f"\n📦 Creating {len(missing_tables)} missing tables: {missing_tables}")
                
                for table_name in missing_tables:
                    try:
                        table = db.metadata.tables[table_name]
                        table.create(db.engine)
                        print(f"✅ Created table: {table_name}")
                    except Exception as e:
                        print(f"❌ Failed to create table {table_name}: {e}")
                        # Continue with other tables even if one fails
                
                print("✅ Missing tables creation completed")
                
                # Verify all tables now exist
                inspector = inspect(db.engine)
                final_tables = inspector.get_table_names()
                still_missing = [table for table in expected_tables if table not in final_tables]
                
                if still_missing:
                    print(f"⚠️  Still missing tables after creation attempt: {still_missing}")
                else:
                    print("✅ All expected tables now exist in database")
            else:
                print("\nℹ️  All tables exist - skipping table creation")
                print("ℹ️  Set RECREATE_DB=true to force recreation")
                print("ℹ️  Use Flask-Migrate for schema changes in production")
            
            # Create initial data if needed
            try:
                print("\n👤 Checking for initial data...")
                
                # Import models here to avoid circular imports
                from core.models.users import User
                from core.models.roleModel import Role
                from core.models.companies import Company
                
                # Check if data already exists
                existing_roles = Role.query.count()
                existing_users = User.query.count()
                existing_companies = Company.query.count()
                
                if existing_roles > 0 and existing_users > 0 and existing_companies > 0:
                    print(f"ℹ️  Data already exists ({existing_users} users, {existing_roles} roles, {existing_companies} companies). Skipping initial data creation.")
                else:
                    print("📝 Creating initial data...")
                    
                    # Create default company if it doesn't exist
                    default_company = Company.query.filter_by(code='NAP').first()
                    if not default_company:
                        default_company = Company(
                            name="Napoli Property Inv Ltd",
                            code="NAP",
                            employee_id_prefix="NAP",
                            registration_number="ZMW/REG-1005/25",
                            employee_count=0,
                            status="Active"
                        )
                        db.session.add(default_company)
                        db.session.flush()  # Get ID without commit
                        print("✅ Created default company 'Napoli Property Inv Ltd'")
                    
                    # Create default roles if they don't exist
                    admin_role = Role.query.filter_by(name='admin').first()
                    if not admin_role:
                        admin_role = Role(name='admin', tier=1, description='Administrator')
                        db.session.add(admin_role)
                        print("✅ Created admin role")
                    
                    user_role = Role.query.filter_by(name='user').first()
                    if not user_role:
                        user_role = Role(name='user', tier=2, description='Regular User')
                        db.session.add(user_role)
                        print("✅ Created user role")
                    
                    db.session.flush()
                    
                    # Create super admin user if it doesn't exist
                    super_admin = User.query.filter_by(email='super.admin@hrgroup.co.zm').first()
                    if not super_admin:
                        super_admin = User(
                            email='super.admin@hrgroup.co.zm',
                            name='Super Administrator',
                            is_active=True,
                        )
                        super_admin.set_password('password123')
                        super_admin.roles.append(admin_role)
                        db.session.add(super_admin)
                        print("✅ Created super admin user associated with Napoli Property Inv Ltd")
                    
                    db.session.commit()
                    print("✅ Initial data created successfully")
                
                # Final verification
                user_count = User.query.count()
                role_count = Role.query.count()
                company_count = Company.query.count()
                print(f"📊 Final state: {user_count} users, {role_count} roles, {company_count} companies in database")
                
                # Display company details
                default_company = Company.query.filter_by(code='NAP').first()
                if default_company:
                    print(f"🏢 Default Company Details:")
                    print(f"   - Name: {default_company.name}")
                    print(f"   - Code: {default_company.code}")
                    print(f"   - Employee ID Prefix: {default_company.employee_id_prefix}")
                    print(f"   - Registration: {default_company.registration_number}")
                    print(f"   - Status: {default_company.status}")
                    
            except Exception as e:
                print(f"❌ Error checking/creating initial data: {e}")
                import traceback
                traceback.print_exc()
                db.session.rollback()
                # Don't exit here - the app might still work without initial data
            
            print("\n" + "="*50)
            print("✅ DATABASE SETUP COMPLETE")
            print("="*50 + "\n")
            
        except Exception as e:
            print("\n" + "="*50)
            print("❌ FATAL ERROR DURING DATABASE SETUP")
            print("="*50)
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            print("="*50 + "\n")
            raise
    
    return app