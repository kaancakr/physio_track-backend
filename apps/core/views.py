from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="health_check",
        summary="Health check",
        description="Return a simple status response for service monitoring.",
        responses={200: OpenApiResponse(description="Service is healthy.")},
    )
    def get(self, request):
        return Response({"status": "ok"})
