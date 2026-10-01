import time
from django.core.management.base import BaseCommand
from whatsapp_integration.renewals import enqueue_due, dispatch_one


class Command(BaseCommand):
    help = "Queue due renewal stages and dispatch safely outside web requests."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Run continuously under a process supervisor.")

    def handle(self, *args, **options):
        while True:
            count = enqueue_due()
            if count:
                self.stdout.write(f"Queued {count} renewal reminders")
            while dispatch_one():
                time.sleep(4)
            if not options["watch"]:
                break
            time.sleep(15)
