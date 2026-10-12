"""Repair templates created after the original optional mapping migration."""
from importlib import import_module

from django.db import migrations


def repair_net_premium_mapping(apps, schema_editor):
    migration = import_module("bulk_upload.migrations.0006_recover_archived_imports")
    migration.add_net_premium_mapping(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [("bulk_upload", "0006_recover_archived_imports")]
    operations = [migrations.RunPython(repair_net_premium_mapping, migrations.RunPython.noop)]
