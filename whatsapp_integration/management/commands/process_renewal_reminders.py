import time
from django.core.management.base import BaseCommand
from whatsapp_integration.models import WhatsAppConfig
from whatsapp_integration.renewals import enqueue_due, dispatch_one, readiness_issues


class Command(BaseCommand):
    help = "Queue due renewal stages and dispatch safely outside web requests."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Run continuously under a process supervisor.")
        parser.add_argument("--check", action="store_true", help="Show local setup blockers without queueing or sending.")

    def handle(self, *args, **options):
        if options["check"]:
            config = WhatsAppConfig.get_config()
            issues = readiness_issues(config)
            if issues:
                for issue in issues:
                    self.stdout.write(self.style.WARNING(issue))
            else:
                self.stdout.write(self.style.SUCCESS("Local renewal configuration is ready. Verify the worker and Meta template approvals separately."))
            return
        while True:
            count = enqueue_due()
            if count:
                self.stdout.write(f"Queued {count} renewal reminders")
            while dispatch_one():
                time.sleep(4)
            if not options["watch"]:
                break
            time.sleep(15)
