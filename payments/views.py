from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from insurance.models import InsuranceRecord
from .models import Payment
from .serializers import PaymentSerializer


class PaymentViewSet(viewsets.ModelViewSet):
    """
    Payment Transactions API:
    - GET    /api/payments/?insurance_record_id=<id> -> List payments for a record
    - POST   /api/payments/                         -> Create a payment
    - GET    /api/payments/<id>/                    -> Retrieve payment
    - PUT    /api/payments/<id>/                    -> Update payment
    - PATCH  /api/payments/<id>/                    -> Partial update payment
    - DELETE /api/payments/<id>/                    -> Delete payment
    - GET    /api/payments/history/?insurance_record_id=<id> -> Detailed payment history & summary
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        # Requirement: Payment history must always be fetched using insurance_record_id, never customer phone/customer_id.
        params = self.request.query_params
        customer_phone = params.get("customer_phone") or params.get("phone")
        customer_id = params.get("customer_id") or params.get("customer")

        record_id = (
            params.get("insurance_record_id")
            or params.get("insurance_record")
            or params.get("record_id")
            or params.get("record")
        )

        if customer_phone or customer_id:
            if not record_id:
                raise ValidationError(
                    {"insurance_record_id": "Payment history must always be fetched using insurance_record_id, never customer phone/customer_id."}
                )

        queryset = Payment.objects.select_related("insurance_record").all()
        if record_id:
            queryset = queryset.filter(insurance_record_id=record_id)
        return queryset.order_by("-payment_date", "-created_at")

    def create(self, request, *args, **kwargs):
        record_id = (
            request.data.get("insurance_record_id")
            or request.data.get("insurance_record")
            or request.data.get("record_id")
            or request.data.get("record")
        )
        if not record_id:
            raise ValidationError({"insurance_record_id": "insurance_record_id is required."})

        record = get_object_or_404(InsuranceRecord, pk=record_id)
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        data["insurance_record_id"] = record.id

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(insurance_record=record)
        record.refresh_from_db()

        return Response(
            {
                "message": "Payment recorded successfully.",
                "data": serializer.data,
                "total_paid": f"{record.total_paid:.2f}",
                "outstanding": f"{record.outstanding:.2f}",
                "payment_status": record.payment_status,
                "status": record.payment_status,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="history")
    def history(self, request):
        """
        GET /api/payments/history/?insurance_record_id=<id>
        """
        record_id = (
            request.query_params.get("insurance_record_id")
            or request.query_params.get("insurance_record")
            or request.query_params.get("record_id")
            or request.query_params.get("record")
        )
        if not record_id:
            raise ValidationError(
                {"insurance_record_id": "insurance_record_id is required to fetch payment history."}
            )

        record = get_object_or_404(InsuranceRecord, pk=record_id)
        payments = record.payments.all().order_by("-payment_date", "-created_at")
        serializer = self.get_serializer(payments, many=True)

        return Response(
            {
                "insurance_record_id": record.id,
                "total_premium": f"{record.total_premium:.2f}",
                "total_paid": f"{record.total_paid:.2f}",
                "outstanding": f"{record.outstanding:.2f}",
                "status": record.payment_status,
                "payment_status": record.payment_status,
                "payments": serializer.data,
                "transactions": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
