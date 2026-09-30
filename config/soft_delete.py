"""Archival deletion for application records, including queryset/admin deletes."""
import uuid
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models, router, transaction
from django.db.models.deletion import CASCADE
from django.utils import timezone
from auditlog.context import audit_operation


class SoftDeleteQuerySet(models.QuerySet):
    @audit_operation
    def update(self, **kwargs):
        from auditlog.services import record_change, snapshot, tracked
        if not tracked(self.model):
            return super().update(**kwargs)
        if {self.model._meta.pk.name, self.model._meta.pk.attname} & kwargs.keys():
            raise ValueError("Primary keys cannot be changed by audited queryset updates.")
        with transaction.atomic(using=self.db):
            before = {row.pk: snapshot(row) for row in self.select_for_update()}
            # Restrict the write to captured rows: concurrent matching inserts
            # must not be changed without a corresponding before snapshot.
            count = models.QuerySet.update(self.filter(pk__in=before), **kwargs)
            # The update may change fields used by the original filter.
            for row in self.model.all_objects.using(self.db).filter(pk__in=before):
                record_change(row, before[row.pk], snapshot(row), self.db)
            return count

    @audit_operation
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False,
                    update_conflicts=False, update_fields=None, unique_fields=None):
        from auditlog.services import record_change, snapshot, tracked
        kwargs = dict(batch_size=batch_size, ignore_conflicts=ignore_conflicts,
                      update_conflicts=update_conflicts, update_fields=update_fields,
                      unique_fields=unique_fields)
        if not tracked(self.model):
            return super().bulk_create(objs, **kwargs)
        if ignore_conflicts or update_conflicts:
            raise ValueError("Audited bulk inserts cannot ignore or overwrite conflicts; use update_or_create.")
        with transaction.atomic(using=self.db):
            rows = super().bulk_create(objs, **kwargs)
            for row in rows:
                if row.pk is None:
                    raise ValueError("This database cannot return IDs for audited bulk inserts.")
                record_change(row, None, snapshot(row), self.db)
            return rows

    @audit_operation
    def bulk_update(self, objs, fields, batch_size=None):
        # Django implements this via our audited queryset.update(), per batch.
        return super().bulk_update(objs, fields, batch_size=batch_size)

    @audit_operation
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

    @audit_operation
    def save(self, *args, **kwargs):
        from auditlog.services import record_change, snapshot, tracked
        if not tracked(type(self)):
            return super().save(*args, **kwargs)
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            previous = None
            if self.pk is not None:
                previous = type(self).all_objects.using(using).select_for_update().filter(pk=self.pk).first()
            before = snapshot(previous) if previous is not None else None
            result = super().save(*args, **kwargs)
            # Read persisted values so update_fields/deferred fields are accurate.
            persisted = type(self).all_objects.using(using).get(pk=self.pk)
            record_change(persisted, before, snapshot(persisted), using)
            return result

    def delete(self, using=None, keep_parents=False):
        if self.pk is None:
            raise ValueError("Cannot delete an unsaved record.")
        using = using or router.db_for_write(type(self), instance=self)
        result = type(self).all_objects.using(using).filter(pk=self.pk).delete()
        self.refresh_from_db(using=using)
        return result

    @audit_operation
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
