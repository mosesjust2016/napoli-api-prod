from ..addons.extensions import db, BaseModel

class Permission(BaseModel):
    __tablename__ = 'permissions'


    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)

    # Relationships
    roles = db.relationship('Role', secondary='role_permissions', back_populates='permissions')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description
        }

    def __repr__(self):
        return f"<Permission {self.name}>"