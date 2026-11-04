"""Crée le compte super admin d'un site neuf (sans les comptes de démonstration)."""

import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.users.models import User
from apps.users.roles import Role


class Command(BaseCommand):
    help = "Crée un super admin de la plateforme. Le mot de passe est demandé au clavier (jamais affiché)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--first-name", required=True)
        parser.add_argument("--last-name", required=True)
        parser.add_argument("--password", help="À éviter : il resterait dans l'historique du terminal. Sinon il est demandé.")
        parser.add_argument("--if-missing", action="store_true", help="Ne fait rien (sans erreur) si le compte existe déjà.")
        parser.add_argument("--skip-validation", action="store_true", help="Accepte un mot de passe court ou simple (démonstration seulement).")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            if options["if_missing"]:
                self.stdout.write(f"Le compte {email} existe déjà.")
                return
            raise CommandError(f"Un compte existe déjà avec {email}.")
        password = options["password"]
        if not password:
            password = getpass.getpass("Mot de passe : ")
            if password != getpass.getpass("Confirmez le mot de passe : "):
                raise CommandError("Les deux mots de passe ne sont pas identiques.")
        if not options["skip_validation"]:
            try:
                validate_password(password)
            except ValidationError as exc:
                raise CommandError(" ".join(exc.messages)) from exc
        User.objects.create_user(
            email=email,
            password=password,
            first_name=options["first_name"],
            last_name=options["last_name"],
            role=Role.PLATFORM_ADMIN,
            is_staff=True,
        )
        self.stdout.write(self.style.SUCCESS(f"Super admin créé : {email}"))
