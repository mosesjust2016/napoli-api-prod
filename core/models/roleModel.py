from ..addons.extensions import db, BaseModel

class Role(BaseModel):
    __tablename__ = 'roles'

    name = db.Column(db.String(50), unique=True, nullable=False)
    tier = db.Column(db.Integer, nullable=False, default=1)
    description = db.Column(db.Text)

    # Relationships
    users = db.relationship('User', secondary='user_roles', back_populates='roles')
    permissions = db.relationship('Permission', secondary='role_permissions', back_populates='roles')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'tier': self.tier,
            'description': self.description
        }

    def __repr__(self):
        return f"<Role {self.name}>"