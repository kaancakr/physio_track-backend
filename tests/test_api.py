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
            "gender": "female",
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

    def get_neck_program_id(self) -> str:
        list_response = self.client.get(reverse("program-list"))
        matching_programs = [program for program in list_response.data["results"] if program["focus_area"] == "neck"]

        self.assertEqual(len(matching_programs), 1)

        return str(matching_programs[0]["id"])

    def get_program_exercise_ids(self, program_id: str) -> list[str]:
        exercises_response = self.client.get(reverse("program-exercise-list", kwargs={"id": program_id}))

        self.assertEqual(exercises_response.status_code, status.HTTP_200_OK)

        return [str(exercise["id"]) for exercise in exercises_response.data]

    def test_signup_creates_unverified_user_and_sends_email(self) -> None:
        response = self.client.post(reverse("signup"), self.signup_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=self.signup_payload["email"])

        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertEqual(user.profile.full_name, self.signup_payload["full_name"])
        self.assertEqual(user.profile.gender, self.signup_payload["gender"])
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
        self.assertEqual(response.data["user"]["profile"]["gender"], self.signup_payload["gender"])

    def test_signup_rejects_unknown_gender_choice(self) -> None:
        response = self.client.post(
            reverse("signup"),
            {
                **self.signup_payload,
                "gender": "invalid-choice",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("gender", response.data)

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

    def test_refresh_returns_new_access_and_refresh_tokens(self) -> None:
        _, refresh_token = self.signup_and_verify_user()

        response = self.client.post(
            reverse("token-refresh"),
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotEqual(response.data["refresh"], refresh_token)

    def test_logout_revokes_access_and_refresh_tokens(self) -> None:
        access_token, refresh_token = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        logout_response = self.client.post(
            reverse("logout"),
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)

        me_response = self.client.get(reverse("me"))
        self.assertEqual(me_response.status_code, status.HTTP_401_UNAUTHORIZED)

        refresh_response = self.client.post(
            reverse("token-refresh"),
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

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

    def test_user_me_endpoint_allows_clearing_gender(self) -> None:
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.patch(
            reverse("user-me"),
            {
                "gender": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["profile"]["gender"], "")

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
        program_id = self.get_neck_program_id()
        matching_program = [program for program in list_response.data["results"] if str(program["id"]) == program_id][0]
        exercises_response = self.client.get(reverse("program-exercise-list", kwargs={"id": program_id}))
        first_exercise_id = exercises_response.data[0]["id"]
        detail_response = self.client.get(
            reverse(
                "program-exercise-detail",
                kwargs={"id": program_id, "exercise_id": first_exercise_id},
            )
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(exercises_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["count"], 4)
        self.assertEqual(len(list_response.data["results"]), 4)
        self.assertIsInstance(uuid.UUID(detail_response.data["id"]), uuid.UUID)
        self.assertEqual(matching_program["difficulty"], "beginner")
        self.assertEqual(exercises_response.data[0]["exercise_order"], 1)
        self.assertEqual(len(exercises_response.data), 13)
        self.assertFalse(detail_response.data["is_finished"])
        self.assertEqual(detail_response.data["completed_step_indexes"], [])
        self.assertIn("steps", detail_response.data)
        self.assertIn("instruction_steps", detail_response.data)
        self.assertIn("timing", detail_response.data)
        self.assertIn("instruction_step_images", detail_response.data)
        self.assertEqual(
            matching_program["cover_image"],
            {
                "url": "",
                "thumbnail_url": "",
                "width": None,
                "height": None,
                "alt": "Cover image for the neck pain relief stretching program.",
                "blurhash": "",
            },
        )
        self.assertEqual(
            detail_response.data["image"],
            {
                "url": "",
                "thumbnail_url": "",
                "width": None,
                "height": None,
                "alt": "Person performing a neck glide exercise.",
            },
        )
        self.assertEqual(
            detail_response.data["steps"][0],
            {
                "step_index": 0,
                "title": "Step 1",
                "instruction": "Sit or stand upright with the head in a neutral position.",
                "image": {
                    "url": "",
                    "thumbnail_url": "",
                    "width": None,
                    "height": None,
                    "alt": "Sit or stand upright with the head in a neutral position.",
                },
            },
        )
        self.assertEqual(
            detail_response.data["instruction_step_images"][0],
            {
                "url": "",
                "thumbnail_url": "",
                "width": None,
                "height": None,
                "alt": "Sit or stand upright with the head in a neutral position.",
            },
        )
        self.assertEqual(detail_response.data["exercise_order"], 1)
        self.assertEqual(detail_response.data["steps_count"], 3)
        self.assertEqual(detail_response.data["completed_steps_count"], 0)
        self.assertEqual(detail_response.data["next_step_index"], 0)
        self.assertGreater(len(detail_response.data["instruction_steps"]), 0)

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
        self.assertIsInstance(uuid.UUID(response.data["results"][0]["id"]), uuid.UUID)
        self.assertEqual(response.data["results"][0]["difficulty"], "beginner")
        self.assertEqual(response.data["results"][0]["exercises_count"], 13)
        self.assertEqual(response.data["results"][0]["completed_exercises_count"], 0)
        self.assertFalse(response.data["results"][0]["is_finished"])

    def test_program_exercise_list_returns_progress_summary(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()

        response = self.client.get(reverse("program-exercise-list", kwargs={"id": program_id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 13)
        self.assertEqual(response.data[0]["steps_count"], 3)
        self.assertEqual(response.data[0]["completed_steps_count"], 0)
        self.assertEqual(response.data[0]["next_step_index"], 0)
        self.assertFalse(response.data[0]["is_finished"])

    def test_user_cannot_complete_step_out_of_order(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        exercise_id = self.get_program_exercise_ids(program_id)[0]

        response = self.client.post(
            reverse(
                "exercise-step-complete",
                kwargs={"id": program_id, "exercise_id": exercise_id, "step_index": 1},
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("step_index", response.data)

    def test_user_cannot_complete_the_same_step_twice(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        exercise_id = self.get_program_exercise_ids(program_id)[0]

        first_response = self.client.post(
            reverse(
                "exercise-step-complete",
                kwargs={"id": program_id, "exercise_id": exercise_id, "step_index": 0},
            ),
            format="json",
        )
        second_response = self.client.post(
            reverse(
                "exercise-step-complete",
                kwargs={"id": program_id, "exercise_id": exercise_id, "step_index": 0},
            ),
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("step_index", second_response.data)

    def test_completing_all_steps_marks_exercise_and_program_progress_for_current_user(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        exercise_ids = self.get_program_exercise_ids(program_id)

        for exercise_id in exercise_ids:
            detail_response = self.client.get(
                reverse("program-exercise-detail", kwargs={"id": program_id, "exercise_id": exercise_id})
            )
            self.assertEqual(detail_response.status_code, status.HTTP_200_OK)

            for step_index in range(detail_response.data["steps_count"]):
                completion_response = self.client.post(
                    reverse(
                        "exercise-step-complete",
                        kwargs={"id": program_id, "exercise_id": exercise_id, "step_index": step_index},
                    ),
                    format="json",
                )
                self.assertEqual(completion_response.status_code, status.HTTP_200_OK)

        final_exercise_detail_response = self.client.get(
            reverse("program-exercise-detail", kwargs={"id": program_id, "exercise_id": exercise_ids[-1]})
        )
        final_program_list_response = self.client.get(reverse("program-list"))
        matching_programs = [
            program for program in final_program_list_response.data["results"] if str(program["id"]) == program_id
        ]

        self.assertEqual(final_exercise_detail_response.data["next_step_index"], None)
        self.assertTrue(final_exercise_detail_response.data["is_finished"])
        self.assertEqual(final_exercise_detail_response.data["completed_steps_count"], final_exercise_detail_response.data["steps_count"])
        self.assertEqual(len(matching_programs), 1)
        self.assertEqual(matching_programs[0]["completed_exercises_count"], matching_programs[0]["exercises_count"])
        self.assertTrue(matching_programs[0]["is_finished"])

    def test_progress_is_isolated_per_user(self) -> None:
        upsert_seed_programs()
        first_access_token, _ = self.signup_and_verify_user()
        program_id = None
        exercise_id = None

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {first_access_token}")
        program_id = self.get_neck_program_id()
        exercise_id = self.get_program_exercise_ids(program_id)[0]
        completion_response = self.client.post(
            reverse(
                "exercise-step-complete",
                kwargs={"id": program_id, "exercise_id": exercise_id, "step_index": 0},
            ),
            format="json",
        )
        self.assertEqual(completion_response.status_code, status.HTTP_200_OK)

        second_signup_payload = {
            "email": "second-patient@example.com",
            "password": "StrongPass123",
            "full_name": "Second Patient",
            "focus_area": "neck",
            "weekly_goal": 3,
            "age_range": "30-44",
            "gender": "female",
            "daily_step_goal": 5000,
        }
        self.client.credentials()
        self.client.post(reverse("signup"), second_signup_payload, format="json")
        second_verification_code = self.extract_code_from_last_email()
        second_verify_response = self.client.post(
            reverse("verify-signup-code"),
            {"email": second_signup_payload["email"], "code": second_verification_code},
            format="json",
        )
        second_access_token = second_verify_response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {second_access_token}")

        detail_response = self.client.get(
            reverse("program-exercise-detail", kwargs={"id": program_id, "exercise_id": exercise_id})
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["completed_step_indexes"], [])
        self.assertEqual(detail_response.data["completed_steps_count"], 0)
        self.assertEqual(detail_response.data["next_step_index"], 0)

    def test_request_fails_if_exercise_does_not_belong_to_program(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        programs_response = self.client.get(reverse("program-list"))
        self.assertEqual(programs_response.status_code, status.HTTP_200_OK)

        neck_program_id = str([program for program in programs_response.data["results"] if program["focus_area"] == "neck"][0]["id"])
        shoulder_program_id = str(
            [program for program in programs_response.data["results"] if program["focus_area"] == "shoulder"][0]["id"]
        )
        shoulder_exercise_id = self.get_program_exercise_ids(shoulder_program_id)[0]

        detail_response = self.client.get(
            reverse(
                "program-exercise-detail",
                kwargs={"id": neck_program_id, "exercise_id": shoulder_exercise_id},
            )
        )
        completion_response = self.client.post(
            reverse(
                "exercise-step-complete",
                kwargs={"id": neck_program_id, "exercise_id": shoulder_exercise_id, "step_index": 0},
            ),
            format="json",
        )

        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(completion_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_old_program_complete_flow_is_rejected(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()

        response = self.client.post(
            f"/api/programs/{program_id}/complete/",
            {"finished_at": "2026-05-03T10:15:00Z"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_program_list_returns_etag_and_supports_not_modified(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        first_response = self.client.get(reverse("program-list"))
        etag = first_response.headers.get("ETag")
        second_response = self.client.get(
            reverse("program-list"),
            HTTP_IF_NONE_MATCH=etag,
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(etag)
        self.assertEqual(second_response.status_code, status.HTTP_304_NOT_MODIFIED)
        self.assertEqual(second_response.headers.get("ETag"), etag)

    def test_program_exercise_list_returns_etag_and_supports_not_modified(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        url = reverse("program-exercise-list", kwargs={"id": program_id})

        first_response = self.client.get(url)
        etag = first_response.headers.get("ETag")
        second_response = self.client.get(
            url,
            HTTP_IF_NONE_MATCH=etag,
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(etag)
        self.assertEqual(second_response.status_code, status.HTTP_304_NOT_MODIFIED)
        self.assertEqual(second_response.headers.get("ETag"), etag)

    def test_program_exercise_detail_returns_etag_and_supports_not_modified(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        exercise_id = self.get_program_exercise_ids(program_id)[0]
        url = reverse("program-exercise-detail", kwargs={"id": program_id, "exercise_id": exercise_id})

        first_response = self.client.get(url)
        etag = first_response.headers.get("ETag")
        second_response = self.client.get(
            url,
            HTTP_IF_NONE_MATCH=etag,
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(etag)
        self.assertEqual(second_response.status_code, status.HTTP_304_NOT_MODIFIED)
        self.assertEqual(second_response.headers.get("ETag"), etag)

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
        self.assertIn("404", schema_response.data["paths"]["/api/programs/{id}/exercises/{exercise_id}/"]["get"]["responses"])
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
