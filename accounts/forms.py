from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError


class OperatorAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "not_operator": "This account does not have operator access.",
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError(
                self.error_messages["not_operator"],
                code="not_operator",
            )
