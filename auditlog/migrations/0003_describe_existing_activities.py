from django.db import migrations


def describe_existing(apps, schema_editor):
    # Historical identity only: do not substitute today's customer names into
    # yesterday's events. Missing history remains an ID rather than a guess.
    from auditlog.presentation import describe, IDENTITY_FIELDS

    model = apps.get_model("auditlog", "ActivityLog")
    using = schema_editor.connection.alias
    identities = {}
    pending = []
    fields = ("summary", "object_label", "customer_name", "customer_phone", "policy_number", "vehicle_number", "search_text", "device")

    def resolve(label, pk):
        return identities.get((label, str(pk)), {})

    for entry in model.objects.using(using).order_by("occurred_at", "pk").iterator(chunk_size=500):
        state = identities.setdefault((entry.object_type, entry.object_id), {})
        for name, values in entry.changes.items():
            if name in IDENTITY_FIELDS:
                state[name] = values.get("after")
        if entry.object_type == "auth.user":
            state["username"] = entry.actor_username
        metadata = describe(entry.object_type, entry.object_id, state, resolve, entry.action, entry.changes)
        for name, value in metadata.items():
            setattr(entry, name, value)
        entry.device = "Not recorded (older activity)" if entry.source == "request" else "Automatic / server task"
        pending.append(entry)
        if len(pending) == 500:
            model.objects.using(using).bulk_update(pending, fields, batch_size=500)
            pending.clear()
    if pending:
        model.objects.using(using).bulk_update(pending, fields, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("auditlog", "0002_alter_activitylog_options_activitylog_customer_name_and_more")]
    operations = [migrations.RunPython(describe_existing, migrations.RunPython.noop)]
