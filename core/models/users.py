from ..addons.extensions import BaseModel, db, bcrypt

class User(BaseModel):
    __tablename__ = 'users'


    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    roles = db.relationship('Role', secondary='user_roles', back_populates='users')

    def set_password(self, password):
        """Hashes and sets the user's password."""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Verifies a password against the stored hash."""
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'is_active': self.is_active,
            'roles': [role.name for role in self.roles]
        }

    def __repr__(self):
        return f"<User {self.email}>"