import json
import ipaddress
from uuid import uuid4

from django.core.serializers.json import DjangoJSONEncoder
from django.apps import apps
from django.conf import settings
from django.db.models.fields.files import FieldFile

from .context import current_request, operation_id
from .models import ActivityLog
from .presentation import describe, device_description, IDENTITY_FIELDS


EXCLUDED_MODELS = {"accounts.usersessionactivity"}
IGNORED_FIELDS = {"created_at", "updated_at", "uploaded_at", "deletion_batch"}
SENSITIVE_FRAGMENTS = ("password", "token", "secret", "pin", "otp", "payload", "parameters", "error_message")


def tracked(model):
    # Historical migration models must never generate runtime audit entries.
    return model.__module__ != "__fake__" and model._meta.label_lower not in EXCLUDED_MODELS


def snapshot(instance):
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in IGNORED_FIELDS:
            continue
        value = getattr(instance, field.attname)
        values[field.attname] = value.name if isinstance(value, FieldFile) else value
    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


def record_change(instance, before, after, using):
    changes = {}
    for name in (before or {}).keys() | (after or {}).keys():
        old, new = (before or {}).get(name), (after or {}).get(name)
        if old != new:
            secret = any(fragment in name.lower() for fragment in SENSITIVE_FRAGMENTS)
            changes[name] = {"before": "[REDACTED]" if secret else old,
                             "after": "[REDACTED]" if secret else new}
    if not changes:
        return
    if before is None:
        action = ActivityLog.Action.CREATE
    elif before.get("deleted_at") is None and after.get("deleted_at") is not None:
        action = ActivityLog.Action.DELETE
    elif before.get("deleted_at") is not None and after.get("deleted_at") is None:
        action = ActivityLog.Action.RESTORE
    else:
        action = ActivityLog.Action.UPDATE
    record_event(action, instance, changes=changes, using=using)


def record_event(action, instance, *, actor=None, changes=None, using="default"):
    request = current_request.get()
    user = actor if actor is not None else getattr(request, "user", None)
    authenticated = user is not None and user.is_authenticated
    def resolve(label, pk):
        model = apps.get_model(label)
        fields = [field.attname for field in model._meta.concrete_fields if field.attname in IDENTITY_FIELDS]
        return model._base_manager.using(using).filter(pk=pk).values(*fields).first() or {}
    state = {field.attname: getattr(instance, field.attname) for field in instance._meta.concrete_fields
             if field.attname in IDENTITY_FIELDS}
    metadata = describe(instance._meta.label_lower, instance.pk, state, resolve, action, changes or {})
    user_agent = getattr(request, "META", {}).get("HTTP_USER_AGENT", "")[:512]
    return ActivityLog.objects.using(using).create(
        actor_id=str(user.pk) if authenticated else "",
        actor_username=user.get_username() if authenticated else "",
        source="request" if request is not None else "system",
        action=action, object_type=instance._meta.label_lower, object_id=str(instance.pk),
        changes=changes or {}, request_id=operation_id.get() or uuid4(),
        request_method=getattr(request, "method", "")[:10],
        request_path=getattr(request, "path", "")[:512],
        device=device_description(user_agent) if request is not None else "Automatic / server task",
        user_agent=user_agent, ip_address=client_ip(request), **metadata,
    )


def client_ip(request):
    """Trust forwarding headers only when the direct peer is an approved proxy."""
    meta = getattr(request, "META", {})
    try:
        peer = str(ipaddress.ip_address(meta.get("REMOTE_ADDR", "")))
    except ValueError:
        return None
    trusted = getattr(settings, "AUDIT_TRUSTED_PROXY_IPS", [])
    if peer not in trusted:
        return peer
    try:
        hops = [str(ipaddress.ip_address(value.strip())) for value in
                meta.get("HTTP_X_FORWARDED_FOR", "").split(",")]
    except ValueError:
        return peer
    for address in reversed(hops):
        if address not in trusted:
            return address
    return hops[0] if hops else peer
