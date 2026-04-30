import re
import uuid

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.programs.services import upsert_seed_programs

User = get_user_model()


class ApiIntegrationTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        mail.outbox.clear()
        self.client = APIClient()
        self.signup_payload = {
            "email": "patient@example.com",
            "password": "StrongPass123",
            "full_name": "Patient Example",
            "focus_area": "neck",
            "weekly_goal": 3,
            "age_range": "30-44",
            "daily_step_goal": 5000,
        }

    def extract_code_from_last_email(self) -> str:
        last_email = mail.outbox[-1]
        match = re.search(r"(\d{6})", last_email.body)

        if match is None:
            raise AssertionError("Expected a 6-digit verification code in the email body.")

        return match.group(1)

    def signup_and_verify_user(self) -> tuple[str, str]:
        signup_response = self.client.post(reverse("signup"), self.signup_payload, format="json")
        self.assertEqual(signup_response.status_code, status.HTTP_201_CREATED)
        verification_code = self.extract_code_from_last_email()

        verify_response = self.client.post(
            reverse("verify-signup-code"),
            {"email": self.signup_payload["email"], "code": verification_code},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)

        return verify_response.data["access"], verify_response.data["refresh"]

    def test_signup_creates_unverified_user_and_sends_email(self) -> None:
        response = self.client.post(reverse("signup"), self.signup_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=self.signup_payload["email"])

        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertEqual(user.profile.full_name, self.signup_payload["full_name"])
        self.assertEqual(len(mail.outbox), 1)

    def test_verify_signup_code_activates_user_and_returns_tokens(self) -> None:
        self.client.post(reverse("signup"), self.signup_payload, format="json")
        verification_code = self.extract_code_from_last_email()

        response = self.client.post(
            reverse("verify-signup-code"),
            {"email": self.signup_payload["email"], "code": verification_code},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(email=self.signup_payload["email"])
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["id"], str(user.public_id))

    def test_login_rejects_unverified_accounts(self) -> None:
        self.client.post(reverse("signup"), self.signup_payload, format="json")

        response = self.client.post(
            reverse("login"),
            {
                "email": self.signup_payload["email"],
                "password": self.signup_payload["password"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["detail"], "Email verification is required before login.")

    def test_login_accepts_verified_accounts(self) -> None:
        self.signup_and_verify_user()

        response = self.client.post(
            reverse("login"),
            {
                "email": self.signup_payload["email"],
                "password": self.signup_payload["password"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIsInstance(uuid.UUID(response.data["user"]["id"]), uuid.UUID)

    def test_resend_and_verify_endpoints_enforce_rate_limits(self) -> None:
        self.client.post(reverse("signup"), self.signup_payload, format="json")
        resend_url = reverse("send-signup-code")
        verify_url = reverse("verify-signup-code")

        first_resend = self.client.post(
            resend_url,
            {"email": self.signup_payload["email"]},
            format="json",
        )
        second_resend = self.client.post(
            resend_url,
            {"email": self.signup_payload["email"]},
            format="json",
        )

        self.assertEqual(first_resend.status_code, status.HTTP_200_OK)
        self.assertEqual(second_resend.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        verification_code = self.extract_code_from_last_email()
        first_verify = self.client.post(
            verify_url,
            {"email": self.signup_payload["email"], "code": verification_code},
            format="json",
        )
        second_verify = self.client.post(
            verify_url,
            {"email": self.signup_payload["email"], "code": verification_code},
            format="json",
        )

        self.assertEqual(first_verify.status_code, status.HTTP_200_OK)
        self.assertEqual(second_verify.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_me_requires_authentication(self) -> None:
        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_uuid_user_id(self) -> None:
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(uuid.UUID(response.data["id"]), uuid.UUID)

    def test_user_me_endpoint_returns_current_user(self) -> None:
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.get(reverse("user-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.signup_payload["email"])

    def test_user_me_endpoint_updates_profile(self) -> None:
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.patch(
            reverse("user-me"),
            {
                "full_name": "Updated Patient",
                "weekly_goal": 5,
                "metadata": {"preferredLanguage": "en"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["profile"]["full_name"], "Updated Patient")
        self.assertEqual(response.data["profile"]["weekly_goal"], 5)
        self.assertEqual(response.data["profile"]["metadata"]["preferredLanguage"], "en")

    def test_admin_can_list_all_users(self) -> None:
        self.signup_and_verify_user()
        admin_user = User.objects.create_superuser(
            email="admin-users@example.com",
            password="StrongPass123",
        )
        self.client.force_authenticate(user=admin_user)

        response = self.client.get(reverse("user-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 2)
        self.assertIn("results", response.data)
        self.client.force_authenticate(user=None)

    def test_non_admin_cannot_list_all_users(self) -> None:
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.get(reverse("user-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_all_programs(self) -> None:
        upsert_seed_programs()
        admin_user = User.objects.create_superuser(
            email="admin-programs@example.com",
            password="StrongPass123",
        )
        self.client.force_authenticate(user=admin_user)

        response = self.client.get(reverse("program-admin-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 4)
        self.assertEqual(len(response.data["results"]), 4)
        self.client.force_authenticate(user=None)

    def test_non_admin_cannot_list_all_programs(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.get(reverse("program-admin-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_programs_require_authentication_and_return_seeded_data(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        list_response = self.client.get(reverse("program-list"))
        detail_response = self.client.get(reverse("program-detail", kwargs={"id": "neck-release-flow"}))

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["count"], 4)
        self.assertEqual(len(list_response.data["results"]), 4)
        self.assertEqual(detail_response.data["id"], "neck-release-flow")
        self.assertEqual(len(detail_response.data["steps"]), 3)

    def test_program_list_supports_pagination_and_query_filters(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.get(
            reverse("program-list"),
            {"page_size": 2, "focus_area": "neck", "search": "Neck"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], "neck-release-flow")

    def test_user_list_supports_pagination_and_query_filters(self) -> None:
        self.signup_and_verify_user()
        User.objects.create_superuser(
            email="admin-filter@example.com",
            password="StrongPass123",
        )
        admin_user = User.objects.create_superuser(
            email="admin-users@example.com",
            password="StrongPass123",
        )
        self.client.force_authenticate(user=admin_user)

        response = self.client.get(
            reverse("user-list"),
            {"page_size": 1, "is_staff": "true", "search": "admin"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertTrue(response.data["results"][0]["is_staff"])
        self.client.force_authenticate(user=None)

    def test_swagger_and_openapi_schema_endpoints_are_available(self) -> None:
        schema_response = self.client.get(reverse("schema"))
        swagger_response = self.client.get(reverse("swagger-ui"))

        self.assertEqual(schema_response.status_code, status.HTTP_200_OK)
        self.assertEqual(swagger_response.status_code, status.HTTP_200_OK)
        self.assertIn("/api/auth/signup", schema_response.data["paths"])
        self.assertIn("/api/programs/", schema_response.data["paths"])
        self.assertIn("400", schema_response.data["paths"]["/api/auth/signup"]["post"]["responses"])
        self.assertIn("429", schema_response.data["paths"]["/api/auth/signup"]["post"]["responses"])
        self.assertIn("401", schema_response.data["paths"]["/api/auth/login"]["post"]["responses"])
        self.assertIn("404", schema_response.data["paths"]["/api/programs/{id}/"]["get"]["responses"])
        self.assertIn("404", schema_response.data["paths"]["/api/users/{user_id}/"]["get"]["responses"])

    def test_admin_can_manage_programs(self) -> None:
        admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPass123",
        )
        logged_in = self.client.login(email=admin_user.email, password="StrongPass123")

        self.assertTrue(logged_in)

        response = self.client.get("/admin/programs/exerciseprogram/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
