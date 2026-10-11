from django.core.management.base import BaseCommand

from ...site_setup import get_site, reset


class Command(BaseCommand):
    help = "Reset the synthetic site: no scans, fixes or releases"

    def handle(self, *args, **options) -> None:
        reset(get_site())
        self.stdout.write("Reset done")
