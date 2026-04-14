from http import HTTPStatus


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "application_error",
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class ValidationAppError(AppError):
    def __init__(self, message: str, *, code: str = "validation_error") -> None:
        super().__init__(message, code=code, status_code=HTTPStatus.BAD_REQUEST)


class UnprocessableAppError(AppError):
    def __init__(self, message: str, *, code: str = "unprocessable_entity") -> None:
        super().__init__(
            message,
            code=code,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )


class NotFoundAppError(AppError):
    def __init__(self, message: str, *, code: str = "not_found") -> None:
        super().__init__(message, code=code, status_code=HTTPStatus.NOT_FOUND)


class ConflictAppError(AppError):
    def __init__(self, message: str, *, code: str = "conflict") -> None:
        super().__init__(message, code=code, status_code=HTTPStatus.CONFLICT)


class DependencyAppError(AppError):
    def __init__(self, message: str, *, code: str = "dependency_error") -> None:
        super().__init__(
            message,
            code=code,
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )
