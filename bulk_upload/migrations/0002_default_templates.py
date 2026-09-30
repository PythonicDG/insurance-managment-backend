from django.db import migrations


def create_templates(apps, schema_editor):
    Template = apps.get_model("bulk_upload", "UploadTemplate")
    Column = apps.get_model("bulk_upload", "UploadColumn")
    db = schema_editor.connection.alias
    customer_columns = [
        ("Customer Name", "name", "Name\nClient Name\nInsured Name", False),
        ("Mobile Number", "phone", "Phone\nContact No\nPhone Number", True),
        ("Alternative Mobile Number", "alternative_mobile_number", "Alternate Phone", False),
        ("Email", "email", "Email Address", False),
        ("Address", "address", "Customer Address", False),
    ]
    insurance_columns = [
        ("Customer Name", "customer_name", "Name\nClient Name\nInsured Name", False),
        ("Mobile Number", "customer_phone", "Phone\nContact No\nPhone Number", True),
        ("Alternative Mobile Number", "customer_alternative_mobile_number", "Alternate Phone", False),
        ("Email", "customer_email", "Email Address", False),
        ("Address", "customer_address", "Customer Address", False),
        ("Vehicle Number", "vehicle_number", "Registration Number\nRegistration No", True),
        ("Vehicle Type", "vehicle_type", "Vehicle Category", False),
        ("Insurance Company", "insurance_company_name", "Insurer\nCompany", True),
        ("Policy Number", "policy_number", "Policy No", True),
        ("Entry Date", "entry_date", "", False),
        ("Policy Start Date", "policy_start_date", "Start Date", True),
        ("Policy Expiry Date", "policy_expiry_date", "Expiry Date\nEnd Date", True),
        ("Total Premium", "total_premium", "Premium", True),
        ("Discount", "discount", "", False),
        ("Remarks", "remarks", "Notes", False),
    ]
    for name, target, columns in [("Standard Customers", "customers", customer_columns),
                                   ("Standard Insurance Records", "insurance", insurance_columns)]:
        template = Template.objects.using(db).create(name=name, target=target)
        for position, (header, field, aliases, required) in enumerate(columns):
            Column.objects.using(db).create(template=template, column_name=header, field_name=field,
                                            aliases=aliases, is_required=required, position=position)


class Migration(migrations.Migration):
    dependencies = [("bulk_upload", "0001_initial")]
    operations = [migrations.RunPython(create_templates, migrations.RunPython.noop)]
