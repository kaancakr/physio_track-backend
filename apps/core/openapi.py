from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, inline_serializer
from rest_framework import serializers


ErrorDetailViewModel = inline_serializer(
    name="ErrorDetailViewModel",
    fields={
        "detail": serializers.CharField(),
    },
)

ThrottledErrorViewModel = inline_serializer(
    name="ThrottledErrorViewModel",
    fields={
        "detail": serializers.CharField(),
    },
)

BAD_REQUEST_RESPONSE = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Validation error. The response body contains field-specific errors or non-field errors.",
    examples=[
        OpenApiExample(
            "Field validation error",
            value={
                "email": ["An account with this email already exists."],
            },
            response_only=True,
            status_codes=["400"],
        ),
        OpenApiExample(
            "Verification code error",
            value={
                "code": ["Invalid or expired verification code."],
            },
            response_only=True,
            status_codes=["400"],
        ),
        OpenApiExample(
            "Non-field validation error",
            value={
                "non_field_errors": ["At least one profile field must be provided."],
            },
            response_only=True,
            status_codes=["400"],
        ),
    ],
)

UNAUTHORIZED_RESPONSE = OpenApiResponse(
    response=ErrorDetailViewModel,
    description="Authentication failed or credentials were not provided.",
    examples=[
        OpenApiExample(
            "Authentication required",
            value={"detail": "Authentication credentials were not provided."},
            response_only=True,
            status_codes=["401"],
        ),
        OpenApiExample(
            "Invalid credentials",
            value={"detail": "Invalid email or password."},
            response_only=True,
            status_codes=["401"],
        ),
    ],
)

FORBIDDEN_RESPONSE = OpenApiResponse(
    response=ErrorDetailViewModel,
    description="The authenticated client does not have permission to access this endpoint.",
    examples=[
        OpenApiExample(
            "Permission denied",
            value={"detail": "You do not have permission to perform this action."},
            response_only=True,
            status_codes=["403"],
        ),
    ],
)

NOT_FOUND_RESPONSE = OpenApiResponse(
    response=ErrorDetailViewModel,
    description="The requested resource was not found.",
    examples=[
        OpenApiExample(
            "Not found",
            value={"detail": "Not found."},
            response_only=True,
            status_codes=["404"],
        ),
    ],
)

THROTTLED_RESPONSE = OpenApiResponse(
    response=ThrottledErrorViewModel,
    description="The client exceeded the allowed request rate.",
    examples=[
        OpenApiExample(
            "Rate limited",
            value={"detail": "Request was throttled. Expected available in 60 seconds."},
            response_only=True,
            status_codes=["429"],
        ),
    ],
)

UUID_PATH_PARAMETER = OpenApiParameter(
    name="user_id",
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.PATH,
    description="Public UUID of the user.",
)

PROGRAM_ID_PATH_PARAMETER = OpenApiParameter(
    name="id",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Program slug identifier.",
)
