from django.contrib import admin, messages
from django.contrib.admin.utils import NestedObjects
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import CASCADE, ProtectedError

from .soft_delete import SoftDeleteModel


class DeletionStatusFilter(admin.SimpleListFilter):
    title = "deletion status"
    parameter_name = "deletion_status"

    def lookups(self, request, model_admin):
        return [("active", "Active"), ("deleted", "Deleted"), ("all", "All")]

    def queryset(self, request, queryset):
        if self.value() == "all":
            return queryset
        return queryset.filter(deleted_at__isnull=self.value() != "deleted")

    def choices(self, changelist):
        # Default to Active rather than Django's usual unfiltered All option.
        for value, label in self.lookup_choices:
            yield {
                "selected": (self.value() or "active") == value,
                "query_string": changelist.get_query_string({self.parameter_name: value}),
                "display": label,
            }


class SoftDeleteAdmin(admin.ModelAdmin):
    """Archive active records and permanently delete already archived records."""

    actions = ["restore_selected"]

    def get_queryset(self, request):
        queryset = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        return queryset.order_by(*ordering) if ordering else queryset

    def get_list_filter(self, request):
        return (DeletionStatusFilter, *super().get_list_filter(request))

    def get_list_display(self, request):
        return (*super().get_list_display(request), "is_deleted", "deleted_at")

    @admin.display(boolean=True, description="Deleted")
    def is_deleted(self, obj):
        return obj.deleted_at is not None

    def get_readonly_fields(self, request, obj=None):
        return (*super().get_readonly_fields(request, obj), "deleted_at", "deletion_batch")

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.deleted_at is not None:
            return False
        return super().has_change_permission(request, obj)

    def _purge_collector(self, queryset):
        collector = NestedObjects(using=queryset.db)
        collector.collect(queryset)
        # An archived parent can acquire live children after archival. Never
        # physically cascade into those records, even from the All filter.
        active = [obj for model, rows in collector.data.items()
                  if issubclass(model, SoftDeleteModel)
                  for obj in rows if obj.deleted_at is None]
        return collector, active

    def delete_queryset(self, request, queryset):
        with transaction.atomic(using=queryset.db):
            rows = list(queryset.select_for_update())
            archived_ids = [obj.pk for obj in rows if obj.deleted_at is not None]
            active_ids = [obj.pk for obj in rows if obj.deleted_at is None]
            archived = self.model.all_objects.using(queryset.db).filter(pk__in=archived_ids)
            collector, active = self._purge_collector(archived)
            if collector.protected or active:
                raise ProtectedError("Cannot permanently delete protected or active related records.",
                                     set(collector.protected) | set(active))
            # Collect before archival so a mixed selection cannot purge rows
            # that were active when the action started.
            collector.delete()
            self.model.all_objects.using(queryset.db).filter(pk__in=active_ids).delete()

    def delete_model(self, request, obj):
        self.delete_queryset(request, self.model.all_objects.using(obj._state.db).filter(pk=obj.pk))

    def has_restore_permission(self, request):
        # A batch can contain models beyond this changelist's permissions.
        return request.user.is_active and request.user.is_superuser

    @admin.action(description="Restore selected deleted records", permissions=["restore"])
    def restore_selected(self, request, queryset):
        if not self.has_restore_permission(request):
            self.message_user(request, "Only superusers can restore deletion batches.", messages.ERROR)
            return
        count = 0
        for obj in queryset.filter(deleted_at__isnull=False):
            try:
                restored = obj.restore()
            except ValidationError as exc:
                self.message_user(request, f"Could not restore {obj}: {'; '.join(exc.messages)}", messages.ERROR)
            except IntegrityError:
                self.message_user(
                    request, f"Could not restore {obj}: conflicts with existing records. No records in this batch were restored.",
                    messages.ERROR,
                )
            else:
                if restored:
                    count += restored
                    self.log_change(request, obj, "Restored archived record and its deletion batch.")
        self.message_user(request, f"Restored {count} record(s), including related records.", messages.SUCCESS if count else messages.INFO)

    def get_deleted_objects(self, objs, request):
        objs = list(objs)
        descriptions, counts, permissions, seen = [], {}, set(), set()
        archived = [obj for obj in objs if obj.deleted_at is not None]
        protected = []
        if archived:
            descriptions, counts, permissions, protected = super().get_deleted_objects(archived, request)
            descriptions.insert(0, "PERMANENT deletion of archived records below. These cannot be restored.")
            queryset = self.model.all_objects.using(archived[0]._state.db).filter(
                pk__in=[obj.pk for obj in archived]
            )
            _, active = self._purge_collector(queryset)
            protected.extend(f"Active {obj._meta.verbose_name}: {obj}" for obj in active)

        def collect(obj):
            key = (obj._meta.label, obj.pk)
            if key in seen or obj.deleted_at is not None:
                return
            seen.add(key)
            descriptions.append(f"Archive {obj._meta.verbose_name}: {obj}")
            name = str(obj._meta.verbose_name_plural)
            counts[name] = counts.get(name, 0) + 1
            registered = self.admin_site._registry.get(type(obj))
            if registered and not registered.has_delete_permission(request, obj):
                permissions.add(str(obj._meta.verbose_name))
            for relation in obj._meta.related_objects:
                child = relation.related_model
                if relation.on_delete is CASCADE:
                    if issubclass(child, SoftDeleteModel):
                        for row in child.objects.using(obj._state.db).filter(
                            **{relation.field.name: obj.pk}
                        ):
                            collect(row)

        for obj in objs:
            collect(obj)
        return descriptions, counts, permissions, protected
