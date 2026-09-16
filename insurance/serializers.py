from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from customers.models import Customer
from vehicles.models import Vehicle
from payments.serializers import PaymentSerializer
from .models import InsuranceCompany, InsuranceDocument, InsuranceRecord


class InsuranceCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceCompany
        fields = [
            "id",
            "name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Company name cannot be empty.")

        instance = getattr(self, "instance", None)
        qs = InsuranceCompany.objects.filter(name__iexact=trimmed)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An insurance company with this name already exists.")

        return trimmed


class InsuranceDocumentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = InsuranceDocument
        fields = [
            "id",
            "record",
            "file",
            "file_url",
            "document_name",
            "file_size",
            "uploaded_at",
        ]
        read_only_fields = ["id", "file_url", "file_size", "uploaded_at"]
        extra_kwargs = {
            "record": {"required": False},
        }

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class RecordCustomerSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "email", "address"]


class RecordVehicleSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ["id", "vehicle_type", "vehicle_number"]


class RecordCompanySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceCompany
        fields = ["id", "name", "is_active"]


class InsuranceRecordListSerializer(serializers.ModelSerializer):
    customer = RecordCustomerSummarySerializer(read_only=True)
    vehicle = RecordVehicleSummarySerializer(read_only=True)
    insurance_company = RecordCompanySummarySerializer(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_left = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    documents_count = serializers.IntegerField(source="documents.count", read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    transactions = PaymentSerializer(source="payments", many=True, read_only=True)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    payment_status = serializers.CharField(read_only=True)
    paid_amount = serializers.DecimalField(source="total_paid", max_digits=12, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(source="outstanding", max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InsuranceRecord
        fields = [
            "id",
            "policy_number",
            "entry_date",
            "policy_start_date",
            "policy_expiry_date",
            "total_premium",
            "remarks",
            "customer",
            "vehicle",
            "insurance_company",
            "is_expired",
            "days_left",
            "status",
            "documents_count",
            "payments",
            "transactions",
            "total_paid",
            "outstanding",
            "payment_status",
            "paid_amount",
            "balance",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class InsuranceRecordDetailSerializer(serializers.ModelSerializer):
    customer = RecordCustomerSummarySerializer(read_only=True)
    vehicle = RecordVehicleSummarySerializer(read_only=True)
    insurance_company = RecordCompanySummarySerializer(read_only=True)
    documents = InsuranceDocumentSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    transactions = PaymentSerializer(source="payments", many=True, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_left = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    payment_status = serializers.CharField(read_only=True)
    paid_amount = serializers.DecimalField(source="total_paid", max_digits=12, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(source="outstanding", max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InsuranceRecord
        fields = [
            "id",
            "policy_number",
            "entry_date",
            "policy_start_date",
            "policy_expiry_date",
            "total_premium",
            "remarks",
            "customer",
            "vehicle",
            "insurance_company",
            "documents",
            "payments",
            "transactions",
            "total_paid",
            "outstanding",
            "payment_status",
            "paid_amount",
            "balance",
            "is_expired",
            "days_left",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class InsuranceRecordCreateUpdateSerializer(serializers.ModelSerializer):
    # Insurance company link
    insurance_company_id = serializers.PrimaryKeyRelatedField(
        queryset=InsuranceCompany.objects.all(),
        source="insurance_company",
        write_only=True,
        required=False,
    )

    # Customer inputs (Support either existing ID or automatic create/find details)
    customer_id = serializers.IntegerField(required=False, write_only=True)
    customer_phone = serializers.CharField(max_length=20, required=False, write_only=True)
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True, write_only=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True, write_only=True)
    customer_address = serializers.CharField(required=False, allow_blank=True, write_only=True)
    create_new_customer = serializers.BooleanField(required=False, default=False, write_only=True)

    # Vehicle inputs (Support either existing ID or automatic create/find details)
    vehicle_id = serializers.IntegerField(required=False, write_only=True)
    vehicle_number = serializers.CharField(max_length=50, required=False, write_only=True)
    vehicle_type = serializers.CharField(max_length=50, required=False, allow_blank=True, write_only=True)

    # Initial Payment inputs (optional on record creation)
    initial_payment = serializers.JSONField(required=False, write_only=True)
    paid_amount = serializers.JSONField(required=False, write_only=True)
    initial_payment_method = serializers.CharField(required=False, allow_blank=True, write_only=True)
    initial_payment_date = serializers.DateField(required=False, write_only=True)
    initial_payment_notes = serializers.CharField(required=False, allow_blank=True, write_only=True)
    payment_method = serializers.CharField(required=False, allow_blank=True, write_only=True)
    payment_mode = serializers.CharField(required=False, allow_blank=True, write_only=True)
    payment_date = serializers.DateField(required=False, write_only=True)
    payment_notes = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = InsuranceRecord
        fields = [
            "id",
            "policy_number",
            "entry_date",
            "policy_start_date",
            "policy_expiry_date",
            "total_premium",
            "remarks",
            "insurance_company",
            "insurance_company_id",
            "customer",
            "customer_id",
            "customer_phone",
            "customer_name",
            "customer_email",
            "customer_address",
            "create_new_customer",
            "vehicle",
            "vehicle_id",
            "vehicle_number",
            "vehicle_type",
            "initial_payment",
            "paid_amount",
            "initial_payment_method",
            "initial_payment_date",
            "initial_payment_notes",
            "payment_method",
            "payment_mode",
            "payment_date",
            "payment_notes",
        ]
        read_only_fields = ["id", "customer", "vehicle"]
        extra_kwargs = {
            "policy_number": {"validators": []},
            "insurance_company": {"required": False},
            "entry_date": {"required": False},
            "remarks": {"required": False, "allow_blank": True},
        }

    def validate_policy_number(self, value):
        if not value:
            raise serializers.ValidationError("Policy number cannot be empty.")
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Policy number cannot be empty.")

        queryset = InsuranceRecord.objects.select_related("customer", "vehicle").filter(
            policy_number__iexact=trimmed
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            existing = queryset.first()
            cust_name = (
                existing.customer.name
                if existing and existing.customer and existing.customer.name
                else existing.customer.phone if existing and existing.customer else "another customer"
            )
            veh_num = existing.vehicle.vehicle_number if existing and existing.vehicle else ""
            veh_info = f" (Vehicle: {veh_num})" if veh_num else ""
            raise serializers.ValidationError(
                f"Policy number '{trimmed}' is already registered to {cust_name}{veh_info}. Policy numbers must be unique."
            )

        return trimmed

    def validate(self, attrs):
        # Fallback support for insurance_company / insurance_company_id
        insurance_company = attrs.get("insurance_company")
        if not insurance_company and not self.instance:
            raise serializers.ValidationError(
                {"insurance_company_id": "Insurance company is required."}
            )

        # Dates validation
        start_date = attrs.get("policy_start_date") or (
            self.instance.policy_start_date if self.instance else None
        )
        expiry_date = attrs.get("policy_expiry_date") or (
            self.instance.policy_expiry_date if self.instance else None
        )
        if start_date and expiry_date and expiry_date < start_date:
            raise serializers.ValidationError(
                {"policy_expiry_date": "Policy expiry date cannot be earlier than policy start date."}
            )

        # Premium validation
        premium = attrs.get("total_premium")
        if premium is not None and premium < 0:
            raise serializers.ValidationError(
                {"total_premium": "Total premium cannot be negative."}
            )

        # On creation: Validate customer and vehicle specification
        if not self.instance:
            has_customer = (
                attrs.get("customer_id")
                or attrs.get("customer_phone")
                or self.initial_data.get("phone")
                or self.initial_data.get("customer")
            )
            if not has_customer:
                raise serializers.ValidationError(
                    {"customer": "Either customer_id or customer_phone is required."}
                )

            has_vehicle = (
                attrs.get("vehicle_id")
                or attrs.get("vehicle_number")
                or self.initial_data.get("vehicle")
            )
            if not has_vehicle:
                raise serializers.ValidationError(
                    {"vehicle": "Either vehicle_id or vehicle_number is required."}
                )

        return attrs

    def _resolve_customer(self, validated_data):
        create_new_customer = validated_data.pop("create_new_customer", False)
        if create_new_customer is None:
            create_new_customer = self.initial_data.get("create_new_customer", False)
        if isinstance(create_new_customer, str):
            create_new_customer = create_new_customer.lower() in ("true", "1", "yes")

        # 1. Check direct customer_id (only if NOT explicitly creating a new customer)
        customer_id = None
        if not create_new_customer:
            customer_id = validated_data.pop("customer_id", None) or self.initial_data.get("customer_id")
            if not customer_id and isinstance(self.initial_data.get("customer"), int):
                customer_id = self.initial_data.get("customer")
            if not customer_id and getattr(self, "instance", None) and self.instance.customer_id:
                customer_id = self.instance.customer_id
        else:
            validated_data.pop("customer_id", None)

        customer_name = (
            validated_data.pop("customer_name", "")
            or self.initial_data.get("customer_name")
            or self.initial_data.get("name", "")
        )
        if customer_name:
            customer_name = customer_name.strip()

        customer_email = (
            validated_data.pop("customer_email", "")
            or self.initial_data.get("customer_email")
            or self.initial_data.get("email", "")
        )
        if customer_email:
            customer_email = customer_email.strip()

        customer_address = (
            validated_data.pop("customer_address", "")
            or self.initial_data.get("customer_address")
            or self.initial_data.get("address", "")
        )
        if customer_address:
            customer_address = customer_address.strip()

        customer_phone = (
            validated_data.pop("customer_phone", "")
            or self.initial_data.get("customer_phone")
            or self.initial_data.get("phone", "")
        )

        # If existing customer_id is specified: Update existing customer in place (no duplicate)
        if customer_id:
            try:
                customer = Customer.objects.get(pk=customer_id)
                dirty = False
                if customer_name and customer.name != customer_name:
                    customer.name = customer_name
                    dirty = True
                if customer_address is not None and customer_address != "" and customer.address != customer_address:
                    customer.address = customer_address
                    dirty = True
                if customer_email is not None and customer_email != "" and customer.email != customer_email:
                    customer.email = customer_email
                    dirty = True
                if customer_phone:
                    norm_phone = Customer.normalize_phone(customer_phone)
                    if norm_phone and customer.phone != norm_phone:
                        customer.phone = norm_phone
                        dirty = True
                if dirty:
                    customer.save()
                return customer
            except Customer.DoesNotExist:
                raise serializers.ValidationError(
                    {"customer_id": f"Customer with id {customer_id} does not exist."}
                )

        # 2. Automatically find or create customer by phone
        if customer_phone:
            normalized_phone = Customer.normalize_phone(customer_phone)
            if not normalized_phone:
                raise serializers.ValidationError({"customer_phone": "Valid phone number is required."})

            if create_new_customer:
                # Explicitly create new customer record with its own unique customer_id
                return Customer.objects.create(
                    phone=normalized_phone,
                    name=customer_name or "",
                    email=customer_email or "",
                    address=customer_address or "",
                )

            # Check if customer already exists
            existing_qs = Customer.objects.filter(phone=normalized_phone)
            if customer_name:
                named_match = existing_qs.filter(name__iexact=customer_name).first()
                if named_match:
                    dirty = False
                    if customer_address and named_match.address != customer_address:
                        named_match.address = customer_address
                        dirty = True
                    if customer_email and named_match.email != customer_email:
                        named_match.email = customer_email
                        dirty = True
                    if dirty:
                        named_match.save()
                    return named_match

            # If no name given and existing customer exists with this phone
            first_match = existing_qs.order_by("created_at").first()
            if first_match and not customer_name:
                return first_match

            # Otherwise create a new customer
            return Customer.objects.create(
                phone=normalized_phone,
                name=customer_name or "",
                email=customer_email or "",
                address=customer_address or "",
            )

        return None

    def _resolve_vehicle(self, customer, validated_data):
        # 1. Check direct vehicle_id
        vehicle_id = validated_data.pop("vehicle_id", None) or self.initial_data.get("vehicle_id")
        if not vehicle_id and isinstance(self.initial_data.get("vehicle"), int):
            vehicle_id = self.initial_data.get("vehicle")

        vehicle_number = (
            validated_data.pop("vehicle_number", "")
            or self.initial_data.get("vehicle_number", "")
        )
        vehicle_type = (
            validated_data.pop("vehicle_type", "")
            or self.initial_data.get("vehicle_type", "")
        )

        if vehicle_id:
            try:
                vehicle = Vehicle.objects.get(pk=vehicle_id)
                # If vehicle exists and vehicle_type provided, update if empty
                if vehicle_type and not vehicle.vehicle_type:
                    vehicle.vehicle_type = vehicle_type
                    vehicle.save(update_fields=["vehicle_type"])
                return vehicle
            except Vehicle.DoesNotExist:
                raise serializers.ValidationError(
                    {"vehicle_id": f"Vehicle with id {vehicle_id} does not exist."}
                )

        # 2. Automatically find or create vehicle by vehicle number
        if vehicle_number:
            normalized_number = Vehicle.normalize_vehicle_number(vehicle_number)
            if not normalized_number:
                raise serializers.ValidationError({"vehicle_number": "Valid vehicle number is required."})

            vehicle, created = Vehicle.get_or_create_vehicle(
                customer=customer,
                vehicle_number=normalized_number,
                vehicle_type=vehicle_type or "General",
            )
            if not created and vehicle_type and vehicle.vehicle_type != vehicle_type:
                vehicle.vehicle_type = vehicle_type
                vehicle.save(update_fields=["vehicle_type", "updated_at"])
            return vehicle

        return None

    @transaction.atomic
    def create(self, validated_data):
        # Extract initial payment info before creating record
        raw_init_pay = (
            validated_data.pop("initial_payment", None)
            or validated_data.pop("paid_amount", None)
            or self.initial_data.get("initial_payment")
            or self.initial_data.get("paid_amount")
        )
        pay_method = (
            validated_data.pop("initial_payment_method", None)
            or validated_data.pop("payment_method", None)
            or validated_data.pop("payment_mode", None)
            or self.initial_data.get("initial_payment_method")
            or self.initial_data.get("payment_method")
            or self.initial_data.get("payment_mode")
            or "Cash"
        )
        pay_date = (
            validated_data.pop("initial_payment_date", None)
            or validated_data.pop("payment_date", None)
            or self.initial_data.get("initial_payment_date")
            or self.initial_data.get("payment_date")
            or None
        )
        pay_notes = (
            validated_data.pop("initial_payment_notes", None)
            or validated_data.pop("payment_notes", None)
            or validated_data.pop("payment_remark", None)
            or self.initial_data.get("initial_payment_notes")
            or self.initial_data.get("payment_notes")
            or "Initial payment"
        )
        for k in [
            "initial_payment",
            "paid_amount",
            "initial_payment_method",
            "initial_payment_date",
            "initial_payment_notes",
            "payment_method",
            "payment_mode",
            "payment_date",
            "payment_notes",
        ]:
            validated_data.pop(k, None)

        # 1. Customer Created/Found
        customer = self._resolve_customer(validated_data)
        if not customer:
            raise serializers.ValidationError({"customer": "Could not identify or create customer."})

        # 2. Vehicle Created/Found
        vehicle = self._resolve_vehicle(customer, validated_data)
        if not vehicle:
            raise serializers.ValidationError({"vehicle": "Could not identify or create vehicle."})

        # Fallback entry_date if not specified
        if "entry_date" not in validated_data or not validated_data.get("entry_date"):
            validated_data["entry_date"] = timezone.localdate()

        validated_data["customer"] = customer
        validated_data["vehicle"] = vehicle

        # 3. Insurance Record Created
        record = super().create(validated_data)

        # 4. Handle initial payment if provided
        init_amount = None
        if isinstance(raw_init_pay, dict):
            init_amount = raw_init_pay.get("amount")
            pay_method = raw_init_pay.get("payment_method") or raw_init_pay.get("payment_mode") or pay_method
            pay_date = raw_init_pay.get("payment_date") or raw_init_pay.get("date") or pay_date
            pay_notes = raw_init_pay.get("notes") or raw_init_pay.get("note") or pay_notes
        elif raw_init_pay is not None and str(raw_init_pay).strip() != "":
            try:
                init_amount = Decimal(str(raw_init_pay).strip())
            except Exception:
                init_amount = None

        if init_amount is not None:
            try:
                dec_amount = Decimal(str(init_amount))
                if dec_amount > Decimal("0.00"):
                    from payments.models import Payment
                    Payment.objects.create(
                        insurance_record=record,
                        amount=dec_amount,
                        payment_method=str(pay_method).strip() or "Cash",
                        payment_date=pay_date or record.policy_start_date or record.entry_date or timezone.localdate(),
                        notes=str(pay_notes).strip(),
                    )
            except Exception:
                pass

        # Optional: Handle file uploads included in the multipart request
        request = self.context.get("request")
        if request and hasattr(request, "FILES") and request.FILES:
            files = request.FILES.getlist("documents") or request.FILES.getlist("files")
            if not files:
                single = request.FILES.get("file") or request.FILES.get("document")
                if single:
                    files = [single]

            for uploaded_file in files:
                InsuranceDocument.objects.create(
                    record=record,
                    file=uploaded_file,
                    document_name=uploaded_file.name,
                )

        return record

    @transaction.atomic
    def update(self, instance, validated_data):
        for k in [
            "initial_payment",
            "paid_amount",
            "initial_payment_method",
            "initial_payment_date",
            "initial_payment_notes",
            "payment_method",
            "payment_mode",
            "payment_date",
            "payment_notes",
        ]:
            validated_data.pop(k, None)

        # Update customer if provided
        new_customer = self._resolve_customer(validated_data)
        if new_customer:
            instance.customer = new_customer

        # Update vehicle if provided
        current_customer = instance.customer
        new_vehicle = self._resolve_vehicle(current_customer, validated_data)
        if new_vehicle:
            instance.vehicle = new_vehicle

        # Handle other fields
        return super().update(instance, validated_data)
