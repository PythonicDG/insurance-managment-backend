import hashlib
import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from rest_framework.exceptions import ValidationError

from customers.models import Customer
from customers.serializers import CustomerSerializer
from insurance.models import InsuranceCompany
from insurance.serializers import InsuranceRecordCreateUpdateSerializer
from .schema import FIELDS, normalize_header, validate_columns

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ROWS = 2000
MAX_COLUMNS = 100


def configuration(template):
    columns = list(template.columns.all())
    try:
        validate_columns(template.target, columns)
    except DjangoValidationError as exc:
        raise ValidationError({"error": "Template configuration is invalid. Contact your administrator.", "details": exc.messages})
    return [c for c in columns if c.is_active]


def fingerprint(template, columns):
    payload = [template.pk, template.target, template.is_active, [
        [c.pk, c.column_name, c.field_name, c.aliases, c.is_required, c.default_value, c.position]
        for c in columns
    ]]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def convert(value, kind):
    if kind == "text":
        if isinstance(value, bool):
            raise ValueError("Enter text, not a Boolean value.")
        if isinstance(value, (int, float, Decimal)):
            number = Decimal(str(value))
            if not number.is_finite():
                raise ValueError("Enter a finite value.")
            value = format(number, "f")
            if "." in value:
                value = value.rstrip("0").rstrip(".")
        return str(value).strip()
    if kind == "date":
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(str(value).strip(), fmt).date().isoformat()
            except ValueError:
                continue
        raise ValueError("Use an Excel date, YYYY-MM-DD, or DD/MM/YYYY.")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError("Enter a valid number without currency symbols or commas.")
    if not number.is_finite():
        raise ValueError("Enter a finite number.")
    return str(number)


def read_upload(upload):
    if not upload or not upload.name.lower().endswith(".xlsx"):
        raise ValidationError({"error": "Please upload an .xlsx Excel file."})
    if upload.size > MAX_FILE_BYTES:
        raise ValidationError({"error": "File exceeds the 10 MB limit."})
    raw = upload.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValidationError({"error": "File exceeds the 10 MB limit."})
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise ValidationError({"error": "Excel file expands beyond the supported size."})
    except BadZipFile:
        raise ValidationError({"error": "The file is not a valid .xlsx workbook."})
    return raw


def parse_rows(raw, template, columns):
    workbook = None
    try:
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False)
        sheet = workbook.worksheets[0]
        # Do not trust dimensions supplied by third-party Excel generators.
        sheet.reset_dimensions()
        iterator = sheet.iter_rows()
        header = next(iterator, ())
        if not header or len(header) > MAX_COLUMNS:
            raise ValidationError({"error": "Provide a header row with at most 100 columns on the first worksheet."})
        headers = [normalize_header(cell.value) for cell in header]
        nonempty = [name for name in headers if name]
        if len(nonempty) != len(set(nonempty)):
            raise ValidationError({"error": "The Excel file contains duplicate column headers."})
        positions, recognized = {}, set()
        for column in columns:
            names = {normalize_header(column.column_name), *[normalize_header(a) for a in column.aliases.splitlines() if a.strip()]}
            matches = [i for i, name in enumerate(headers) if name and name in names]
            if len(matches) > 1:
                raise ValidationError({"error": f"More than one header matches '{column.column_name}'. Keep only one."})
            if not matches and column.is_required and not column.default_value.strip():
                raise ValidationError({"error": f"Required column '{column.column_name}' is missing."})
            positions[column.pk] = matches[0] if matches else None
            recognized.update(matches)
        warnings = [f"Ignored column: {cell.value}" for i, cell in enumerate(header) if headers[i] and i not in recognized]
        rows = []
        for number, cells in enumerate(iterator, start=2):
            if number > MAX_ROWS + 1:
                raise ValidationError({"error": f"Use at most {MAX_ROWS} data rows per file, including blank rows."})
            if len(cells) > MAX_COLUMNS:
                raise ValidationError({"error": "Use at most 100 columns per file."})
            if all(cell.value in (None, "") for cell in cells):
                continue
            data, errors = {}, {}
            for column in columns:
                index = positions[column.pk]
                cell = cells[index] if index is not None and index < len(cells) else None
                value = cell.value if cell else None
                if cell and cell.data_type in ("f", "e"):
                    errors[column.column_name] = "Replace formulas or Excel errors with a plain value."
                    continue
                if value is None or (isinstance(value, str) and not value.strip()):
                    value = column.default_value.strip() or None
                if value is None:
                    if column.is_required:
                        errors[column.column_name] = "This value is required."
                    continue
                try:
                    data[column.field_name] = convert(value, FIELDS[template.target][column.field_name][1])
                except (ValueError, TypeError) as exc:
                    errors[column.column_name] = str(exc)
            rows.append((number, data, errors))
        if not rows:
            raise ValidationError({"error": "The first worksheet has no data rows."})
        return rows, warnings
    except ValidationError:
        raise
    except Exception:
        raise ValidationError({"error": "The workbook could not be read. Save it as a valid .xlsx file and try again."})
    finally:
        if workbook:
            workbook.close()


def import_row(target, data):
    if target == "customers":
        serializer = CustomerSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        existing = Customer.objects.filter(phone=values["phone"])
        if values.get("name"):
            existing = existing.filter(name__iexact=values["name"])
        if existing.exists():
            return "skipped"
        serializer.save()
        return "created"
    data = data.copy()
    company_name = data.pop("insurance_company_name", "")
    companies = list(InsuranceCompany.objects.filter(name__iexact=company_name, is_active=True)[:2])
    if len(companies) != 1:
        raise ValidationError({"insurance_company_name": "Enter the exact name of one existing active insurance company."})
    data["insurance_company_id"] = companies[0].pk
    serializer = InsuranceRecordCreateUpdateSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    record = serializer.save()
    if record.vehicle.customer_id != record.customer_id:
        raise ValidationError({"vehicle_number": "This vehicle belongs to a different customer. Review the customer details."})
    return "created"


def process_rows(target, rows, columns, preview):
    """Exercise the existing creation rules, rolling back previews and failed files."""
    errors, sample = [], []
    counts = {"created": 0, "skipped": 0}
    names = {c.field_name: c.column_name for c in columns}
    with transaction.atomic():
        for number, data, cell_errors in rows:
            try:
                with transaction.atomic():
                    if cell_errors:
                        raise ValidationError(cell_errors)
                    result = import_row(target, data)
                    counts[result] += 1
                    if len(sample) < 10:
                        sample.append({"row": number, "status": result, "values": {names.get(k, k): v for k, v in data.items()}})
            except (ValidationError, DjangoValidationError, IntegrityError) as exc:
                if isinstance(exc, ValidationError):
                    detail = exc.detail
                elif isinstance(exc, DjangoValidationError):
                    detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
                else:
                    detail = {"record": "A duplicate or conflicting record was detected. Review this row."}
                if isinstance(detail, dict):
                    detail = {names.get(k, k): v for k, v in detail.items()}
                errors.append({"row": number, "errors": detail})
        if preview or errors:
            transaction.set_rollback(True)
    return {"valid": not errors, "total_rows": len(rows), "created": counts["created"] if not errors or preview else 0,
            "skipped": counts["skipped"], "errors": errors, "sample": sample}


def sample_workbook(template, columns):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Upload"
    sheet.append([c.column_name for c in columns])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for index, column in enumerate(columns, 1):
        cell = sheet.cell(1, index)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2563EB")
        sheet.column_dimensions[cell.column_letter].width = max(20, min(45, len(column.column_name) + 5))
        # Preformat text fields to preserve leading zeros in phone/policy numbers.
        for row in range(2, 102):
            sheet.cell(row, index).number_format = "yyyy-mm-dd" if FIELDS[template.target][column.field_name][1] == "date" else "@" if FIELDS[template.target][column.field_name][1] == "text" else "0.00"
    help_sheet = workbook.create_sheet("Instructions")
    help_sheet.append(["Upload template", template.name])
    help_sheet.append(["Instructions", "Fill the first worksheet. Headers are on row 1. Maximum 2,000 data rows / 10 MB. No formulas."])
    help_sheet.append(["Dates", "Excel dates, YYYY-MM-DD, or DD/MM/YYYY (day first)."])
    help_sheet.append(["Duplicates", "Existing customers (same phone/name) are skipped. Duplicate policies are rejected."])
    help_sheet.append(["Insurance company", "Use the exact name of an existing active company from Settings."])
    help_sheet.append(["Column", "Required", "Type", "Default", "Accepted alternative headers"])
    for column in columns:
        help_sheet.append([column.column_name, "Yes" if column.is_required else "No", FIELDS[template.target][column.field_name][1], column.default_value, column.aliases.replace("\n", ", ")])
    # Force configurable strings to be text, even when they start with '='.
    for worksheet in workbook:
        for row in worksheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
    help_sheet.column_dimensions["A"].width = 30
    help_sheet.column_dimensions["B"].width = 100
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
