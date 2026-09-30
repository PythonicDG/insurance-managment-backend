"""Archival deletion for application records, including queryset/admin deletes."""
import uuid
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models, router, transaction
from django.db.models.deletion import CASCADE
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        if self.query.is_sliced:
            raise TypeError("Cannot delete a sliced queryset.")
        using = self.db
        batch = uuid.uuid4()
        timestamp = timezone.now()
        counts = {}

        def archive(queryset):
            model = queryset.model
            ids = list(queryset.select_for_update().filter(deleted_at__isnull=True).values_list("pk", flat=True))
            if not ids:
                return
            rows = model.all_objects.using(using).filter(pk__in=ids)
            rows.update(deleted_at=timestamp, deletion_batch=batch)
            counts[model._meta.label] = counts.get(model._meta.label, 0) + len(ids)
            # SET_NULL links are deliberately retained, especially audit logs
            # and renewal lineage. Only owned CASCADE children are archived.
            for relation in model._meta.related_objects:
                child = relation.related_model
                if relation.on_delete is CASCADE:
                    if not issubclass(child, SoftDeleteModel):
                        raise ValidationError("Cannot archive an unsupported dependent model.")
                    archive(child.all_objects.using(using).filter(
                        **{f"{relation.field.name}__in": ids}
                    ))
            if model._meta.label_lower == "payments.payment":
                _adjust_discounts(rows, using, restoring=False)

        with transaction.atomic(using=using):
            archive(self)
        self._result_cache = None
        return sum(counts.values()), counts


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


def _adjust_discounts(payments, using, restoring):
    """Reverse/reapply transaction discounts only on a live parent policy."""
    record_model = apps.get_model("insurance", "InsuranceRecord")
    for payment in payments:
        record = record_model.objects.using(using).select_for_update().filter(
            pk=payment.insurance_record_id
        ).first()
        if record and payment.discount:
            delta = payment.discount if restoring else -payment.discount
            record_model.all_objects.using(using).filter(pk=record.pk).update(
                discount=max(Decimal("0.00"), record.discount + delta)
            )


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True, editable=False)
    deletion_batch = models.UUIDField(null=True, blank=True, db_index=True, editable=False)

    objects = SoftDeleteManager()
    all_objects = models.Manager.from_queryset(SoftDeleteQuerySet)()

    class Meta:
        abstract = True
        default_manager_name = "objects"
        base_manager_name = "all_objects"

    def delete(self, using=None, keep_parents=False):
        if self.pk is None:
            raise ValueError("Cannot delete an unsaved record.")
        using = using or router.db_for_write(type(self), instance=self)
        result = type(self).all_objects.using(using).filter(pk=self.pk).delete()
        self.refresh_from_db(using=using)
        return result

    def restore(self, using=None):
        """Restore this deletion batch atomically, without reviving earlier deletes."""
        using = using or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            self.refresh_from_db(using=using)
            if self.deleted_at is None:
                return 0
            batch = self.deletion_batch
            groups = []
            for model in apps.get_models():
                if issubclass(model, SoftDeleteModel):
                    rows = list(model.all_objects.using(using).select_for_update().filter(
                        deletion_batch=batch, deleted_at__isnull=False
                    ))
                    if rows:
                        groups.append((model, rows))
            for model, rows in groups:
                for row in rows:
                    for field in model._meta.fields:
                        parent = field.related_model if field.is_relation else None
                        parent_id = getattr(row, field.attname)
                        if parent_id and parent and issubclass(parent, SoftDeleteModel):
                            if parent.all_objects.using(using).filter(pk=parent_id).exclude(
                                deleted_at__isnull=True
                            ).exclude(deletion_batch=batch).exists():
                                raise ValidationError("Restore the archived parent record first.")
            # Database constraints reject conflicts and roll back the entire batch.
            for model, rows in groups:
                model.all_objects.using(using).filter(pk__in=[r.pk for r in rows]).update(
                    deleted_at=None, deletion_batch=None
                )
            for model, rows in groups:
                if model._meta.label_lower == "payments.payment":
                    standalone = [r for r in rows if not any(
                        m._meta.label_lower == "insurance.insurancerecord"
                        and any(record.pk == r.insurance_record_id for record in records)
                        for m, records in groups
                    )]
                    _adjust_discounts(standalone, using, restoring=True)
                    for payment in standalone:
                        payment.clean()
            self.refresh_from_db(using=using)
            return sum(len(rows) for _, rows in groups)
