from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def mark_future_policies_scheduled(apps, schema_editor):
    InsuranceRecord = apps.get_model("insurance", "InsuranceRecord")
    InsuranceRecord.objects.filter(
        policy_start_date__gt=timezone.localdate(),
        is_active=True,
    ).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("insurance", "0006_insurancerecord_discount"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancerecord",
            name="previous_policy",
            field=models.OneToOneField(
                blank=True,
                help_text="The policy record that this policy renewed.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="renewed_policy",
                to="insurance.insurancerecord",
            ),
        ),
        migrations.RunPython(mark_future_policies_scheduled, migrations.RunPython.noop),
    ]
