from marshmallow import Schema, fields, validate


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=1, max=128))


class ChangePasswordSchema(Schema):
    current_password = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(max=128))


class ForgotPasswordSchema(Schema):
    email = fields.Email(required=True)


class ResetPasswordSchema(Schema):
    token = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(max=128))


class CreateUserSchema(Schema):
    role = fields.String(required=True, validate=validate.OneOf(["admin", "domain_lead", "mentor", "student"]))
    name = fields.String(required=True, validate=validate.Length(min=2, max=150))
    email = fields.Email(required=True)
    phone = fields.String(load_default=None, validate=validate.Length(max=30))
    password = fields.String(required=True, validate=validate.Length(max=128))


def user_to_dict(u):
    return {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role_name,
            "is_active": u.is_active, "must_change_password": u.must_change_password,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat()}
