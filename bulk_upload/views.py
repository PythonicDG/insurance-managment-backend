import hashlib
import uuid

from django.core import signing
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UploadReceipt, UploadTemplate
from .services import configuration, fingerprint, parse_rows, process_rows, read_upload, sample_workbook

TOKEN_SALT = "bulk-upload-preview-v1"


class TemplateListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        templates = UploadTemplate.objects.filter(is_active=True).prefetch_related("columns")
        return Response([{
            "id": template.pk, "name": template.name, "target": template.target,
            "description": template.description,
            "columns": [{"name": column.column_name, "required": column.is_required, "default": column.default_value}
                        for column in template.columns.all() if column.is_active],
        } for template in templates])


class TemplateDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        template = get_object_or_404(UploadTemplate, pk=pk, is_active=True)
        response = HttpResponse(sample_workbook(template, configuration(template)),
                                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="bulk-upload-template-{template.pk}.xlsx"'
        return response


class UploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    preview = True

    def post(self, request):
        try:
            template_id = int(request.data.get("template_id", ""))
        except (ValueError, TypeError):
            raise ValidationError({"error": "Select an upload template."})
        raw = read_upload(request.FILES.get("file"))
        try:
            with transaction.atomic():
                template = get_object_or_404(UploadTemplate.objects.select_for_update(), pk=template_id, is_active=True)
                columns = configuration(template)
                digest = hashlib.sha256(raw).hexdigest()
                config_hash = fingerprint(template, columns)
                token_hash = None
                if not self.preview:
                    token = request.data.get("preview_token", "")
                    try:
                        payload = signing.loads(token, salt=TOKEN_SALT, max_age=1800)
                    except (signing.BadSignature, TypeError, ValueError):
                        raise ValidationError({"error": "Validate the file again. The preview is missing, invalid, or expired."})
                    if payload.get("user") != request.user.pk or payload.get("file") != digest or payload.get("config") != config_hash:
                        raise ValidationError({"error": "The file or template has changed. Validate it again before importing."})
                    token_hash = hashlib.sha256(token.encode()).hexdigest()
                    if UploadReceipt.all_objects.filter(token_hash=token_hash).exists():
                        raise ValidationError({"error": "This upload has already been imported."})
                    # Unique receipt also protects against concurrent replay requests.
                    receipt = UploadReceipt.objects.create(token_hash=token_hash, template=template, user=request.user)
                rows, warnings = parse_rows(raw, template, columns)
                result = process_rows(template.target, rows, columns, self.preview)
                result["warnings"] = warnings
                if not result["valid"]:
                    transaction.set_rollback(True)
                    return Response(result, status=400)
                if self.preview:
                    result["preview_token"] = signing.dumps({"user": request.user.pk, "file": digest,
                                                              "config": config_hash, "nonce": uuid.uuid4().hex}, salt=TOKEN_SALT)
                    result["message"] = "Validation passed. No data has been saved. Preview expires in 30 minutes."
                else:
                    receipt.created_count = result["created"]
                    receipt.skipped_count = result["skipped"]
                    receipt.save(update_fields=["created_count", "skipped_count"])
                    result["message"] = "Import completed successfully."
                return Response(result)
        except IntegrityError:
            raise ValidationError({"error": "A concurrent upload or conflicting record was detected. Validate the file again."})


class PreviewView(UploadView):
    pass


class ImportView(UploadView):
    preview = False
