from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from customers.models import Customer
from vehicles.models import Vehicle
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
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class InsuranceRecordDetailSerializer(serializers.ModelSerializer):
    customer = RecordCustomerSummarySerializer(read_only=True)
    vehicle = RecordVehicleSummarySerializer(read_only=True)
    insurance_company = RecordCompanySummarySerializer(read_only=True)
    documents = InsuranceDocumentSerializer(many=True, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_left = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)

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

    # Vehicle inputs (Support either existing ID or automatic create/find details)
    vehicle_id = serializers.IntegerField(required=False, write_only=True)
    vehicle_number = serializers.CharField(max_length=50, required=False, write_only=True)
    vehicle_type = serializers.CharField(max_length=50, required=False, allow_blank=True, write_only=True)

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
            "vehicle",
            "vehicle_id",
            "vehicle_number",
            "vehicle_type",
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
        # 1. Check direct customer_id
        customer_id = validated_data.pop("customer_id", None) or self.initial_data.get("customer_id")
        if not customer_id and isinstance(self.initial_data.get("customer"), int):
            customer_id = self.initial_data.get("customer")

        customer_name = (
            validated_data.pop("customer_name", "")
            or self.initial_data.get("customer_name")
            or self.initial_data.get("name", "")
        )
        customer_email = (
            validated_data.pop("customer_email", "")
            or self.initial_data.get("customer_email")
            or self.initial_data.get("email", "")
        )
        customer_address = (
            validated_data.pop("customer_address", "")
            or self.initial_data.get("customer_address")
            or self.initial_data.get("address", "")
        )
        customer_phone = (
            validated_data.pop("customer_phone", "")
            or self.initial_data.get("customer_phone")
            or self.initial_data.get("phone", "")
        )

        if customer_id:
            try:
                customer = Customer.objects.get(pk=customer_id)
                # Update empty fields if new values are provided
                dirty = False
                if customer_name and not customer.name:
                    customer.name = customer_name
                    dirty = True
                if customer_email and not customer.email:
                    customer.email = customer_email
                    dirty = True
                if customer_address and not customer.address:
                    customer.address = customer_address
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

            customer, created = Customer.get_or_create_by_phone(
                phone=normalized_phone,
                name=customer_name,
                email=customer_email,
                address=customer_address,
            )
            # If existed, update fields if provided
            if not created:
                dirty = False
                if customer_name and customer.name != customer_name:
                    customer.name = customer_name
                    dirty = True
                if customer_email and customer.email != customer_email:
                    customer.email = customer_email
                    dirty = True
                if customer_address and customer.address != customer_address:
                    customer.address = customer_address
                    dirty = True
                if dirty:
                    customer.save()
            return customer

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
        # Flow:
        # Create Record
        #       ↓
        # Customer Created/Found
        #       ↓
        # Vehicle Created/Found
        #       ↓
        # Insurance Record Created

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
