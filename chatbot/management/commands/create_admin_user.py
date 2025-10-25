from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings


class Command(BaseCommand):
    help = 'Create an initial admin user for ZRA staff'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Admin username', default='zra_admin')
        parser.add_argument('--password', type=str, help='Admin password', default='zra_secret123')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']

        # Check if user already exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f'User "{username}" already exists')
            )
            return

        # Create the admin user
        user = User.objects.create_user(
            username=username,
            password=password,
            is_staff=True,  # Allow access to admin panel
            is_superuser=False  # Don't give full superuser access
        )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created admin user "{username}"')
        )