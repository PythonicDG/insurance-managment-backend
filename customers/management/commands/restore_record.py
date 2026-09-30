from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from config.soft_delete import SoftDeleteModel


class Command(BaseCommand):
    help = "Restore an archived application record and its deletion batch."

    def add_arguments(self, parser):
        parser.add_argument("model", help="Model label, e.g. customers.Customer")
        parser.add_argument("pk", type=int)

    def handle(self, *args, **options):
        try:
            model = apps.get_model(options["model"])
        except (LookupError, ValueError) as exc:
            raise CommandError("Unknown model label.") from exc
        if not issubclass(model, SoftDeleteModel):
            raise CommandError("This model does not support soft deletion.")
        try:
            record = model.all_objects.get(pk=options["pk"])
            count = record.restore()
        except model.DoesNotExist as exc:
            raise CommandError("Record does not exist.") from exc
        except (ValidationError, IntegrityError) as exc:
            raise CommandError(f"Restore failed; no records were changed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Restored {count} record(s)."))
