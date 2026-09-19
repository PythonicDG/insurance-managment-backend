import django.utils.timezone
from django.db import migrations, models


def clean_duplicate_active_records(apps, schema_editor):
    InsuranceRecord = apps.get_model("insurance", "InsuranceRecord")
    today = django.utils.timezone.localdate()

    # 1. Any record already expired by date must be is_active=False
    InsuranceRecord.objects.filter(policy_expiry_date__lt=today).update(is_active=False)

    # 2. For each vehicle, ensure at most one active record
    from django.db.models import Count

    vehicles_with_active = (
        InsuranceRecord.objects.filter(is_active=True)
        .values("vehicle_id")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
    )

    for item in vehicles_with_active:
        v_id = item["vehicle_id"]
        active_records = list(
            InsuranceRecord.objects.filter(vehicle_id=v_id, is_active=True).order_by(
                "-policy_expiry_date", "-id"
            )
        )
        # Keep the latest one active, set all others to False
        for rec in active_records[1:]:
            rec.is_active = False
            rec.save(update_fields=["is_active"])


class Migration(migrations.Migration):

    dependencies = [
        ("insurance", "0003_alter_insurancerecord_policy_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancerecord",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.RunPython(clean_duplicate_active_records, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="insurancerecord",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=("vehicle",),
                name="unique_active_insurance_per_vehicle",
            ),
        ),
    ]
