from datetime import datetime, timezone
import re
import uuid
from unittest.mock import patch

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

    def complete_all_exercise_steps(self, program_id: str, exercise_id: str) -> None:
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

    def test_me_endpoints_return_overall_progress_and_update_after_step_completion(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        exercise_id = self.get_program_exercise_ids(program_id)[0]

        initial_auth_me_response = self.client.get(reverse("me"))
        initial_user_me_response = self.client.get(reverse("user-me"))

        self.assertEqual(initial_auth_me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(initial_user_me_response.status_code, status.HTTP_200_OK)
        self.assertIn("overall_progress", initial_auth_me_response.data)
        self.assertEqual(
            initial_auth_me_response.data["overall_progress"],
            initial_user_me_response.data["overall_progress"],
        )
        self.assertEqual(initial_auth_me_response.data["overall_progress"]["completed_steps_count"], 0)
        self.assertEqual(initial_auth_me_response.data["overall_progress"]["completed_exercises_count"], 0)
        self.assertEqual(initial_auth_me_response.data["overall_progress"]["completed_programs_count"], 0)
        self.assertFalse(initial_auth_me_response.data["overall_progress"]["is_finished"])

        completion_response = self.client.post(
            reverse(
                "exercise-step-complete",
                kwargs={"id": program_id, "exercise_id": exercise_id, "step_index": 0},
            ),
            format="json",
        )
        updated_auth_me_response = self.client.get(reverse("me"))
        updated_user_me_response = self.client.get(reverse("user-me"))

        self.assertEqual(completion_response.status_code, status.HTTP_200_OK)
        self.assertEqual(updated_auth_me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(updated_user_me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            updated_auth_me_response.data["overall_progress"],
            updated_user_me_response.data["overall_progress"],
        )
        self.assertEqual(updated_auth_me_response.data["overall_progress"]["completed_steps_count"], 1)
        self.assertEqual(updated_auth_me_response.data["overall_progress"]["completed_exercises_count"], 0)
        self.assertEqual(updated_auth_me_response.data["overall_progress"]["completed_programs_count"], 0)
        self.assertFalse(updated_auth_me_response.data["overall_progress"]["is_finished"])

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
        self.assertFalse(detail_response.data["is_completed"])
        self.assertFalse(detail_response.data["is_favorite"])
        self.assertIsNone(detail_response.data["suggested_days_per_week"])
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
        self.assertFalse(response.data[0]["is_completed"])
        self.assertFalse(response.data[0]["is_favorite"])

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
        self.assertTrue(final_exercise_detail_response.data["is_completed"])
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

    def test_user_can_favorite_and_unfavorite_exercise(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        exercise_id = self.get_program_exercise_ids(program_id)[0]

        favorite_response = self.client.post(
            reverse(
                "program-exercise-favorite-update",
                kwargs={"id": program_id, "exercise_id": exercise_id},
            ),
            {"is_favorite": True},
            format="json",
        )
        detail_response = self.client.get(
            reverse("program-exercise-detail", kwargs={"id": program_id, "exercise_id": exercise_id})
        )
        unfavorite_response = self.client.post(
            reverse(
                "program-exercise-favorite-update",
                kwargs={"id": program_id, "exercise_id": exercise_id},
            ),
            {"is_favorite": False},
            format="json",
        )
        calendar_response = self.client.get(
            reverse("favorite-exercise-calendar"),
            {"year": 2026, "month": 5},
        )

        self.assertEqual(favorite_response.status_code, status.HTTP_200_OK)
        self.assertTrue(favorite_response.data["is_favorite"])
        self.assertEqual(favorite_response.data["suggested_days_per_week"], 3)
        self.assertEqual(favorite_response.data["message"], "3 days a week is ok for this exercise.")
        self.assertNotIn("current_streak_days", favorite_response.data)
        self.assertNotIn("longest_streak_days", favorite_response.data)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertTrue(detail_response.data["is_favorite"])
        self.assertEqual(detail_response.data["suggested_days_per_week"], 3)
        self.assertEqual(unfavorite_response.status_code, status.HTTP_200_OK)
        self.assertFalse(unfavorite_response.data["is_favorite"])
        self.assertEqual(unfavorite_response.data["message"], "Exercise removed from favourites.")
        self.assertNotIn("current_streak_days", unfavorite_response.data)
        self.assertNotIn("longest_streak_days", unfavorite_response.data)
        self.assertEqual(calendar_response.status_code, status.HTTP_200_OK)
        self.assertEqual(calendar_response.data["days"][0]["exercises"], [])

    def test_favorite_calendar_returns_short_exercise_information(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        exercise_id = self.get_program_exercise_ids(program_id)[0]
        self.client.post(
            reverse(
                "program-exercise-favorite-update",
                kwargs={"id": program_id, "exercise_id": exercise_id},
            ),
            {"is_favorite": True},
            format="json",
        )

        response = self.client.get(
            reverse("favorite-exercise-calendar"),
            {"year": 2026, "month": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["year"], 2026)
        self.assertEqual(response.data["month"], 5)
        self.assertEqual(len(response.data["days"]), 31)
        self.assertEqual(response.data["days"][0]["date"], "2026-05-01")
        self.assertEqual(len(response.data["days"][0]["exercises"]), 1)
        exercise_entry = response.data["days"][0]["exercises"][0]
        self.assertEqual(exercise_entry["exercise_id"], exercise_id)
        self.assertIn("title", exercise_entry)
        self.assertIn("body_area", exercise_entry)
        self.assertIn("duration_sec", exercise_entry)
        self.assertIn("image", exercise_entry)
        self.assertEqual(exercise_entry["suggested_days_per_week"], 3)
        self.assertEqual(len(exercise_entry["program_items"]), 1)
        self.assertEqual(exercise_entry["program_items"][0]["program_id"], program_id)

    def test_completion_response_sets_is_completed_and_updates_favorite_streak(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        exercise_id = self.get_program_exercise_ids(program_id)[0]
        self.client.post(
            reverse(
                "program-exercise-favorite-update",
                kwargs={"id": program_id, "exercise_id": exercise_id},
            ),
            {"is_favorite": True},
            format="json",
        )

        with patch("apps.core.programs.services.timezone.now") as mocked_now:
            mocked_now.return_value = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
            self.complete_all_exercise_steps(program_id, exercise_id)

        with patch("apps.core.programs.services.timezone.now") as mocked_now:
            mocked_now.return_value = datetime(2026, 5, 1, 18, 0, tzinfo=timezone.utc)
            same_day_response = self.client.post(
                reverse(
                    "exercise-step-complete",
                    kwargs={"id": program_id, "exercise_id": exercise_id, "step_index": 2},
                ),
                format="json",
            )

        with patch("apps.core.programs.services.timezone.now") as mocked_now:
            mocked_now.return_value = datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc)
            next_day_response = self.client.post(
                reverse(
                    "exercise-step-complete",
                    kwargs={"id": program_id, "exercise_id": exercise_id, "step_index": 2},
                ),
                format="json",
            )

        with patch("apps.core.programs.services.timezone.now") as mocked_now:
            mocked_now.return_value = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
            skipped_day_response = self.client.post(
                reverse(
                    "exercise-step-complete",
                    kwargs={"id": program_id, "exercise_id": exercise_id, "step_index": 2},
                ),
                format="json",
            )

        self.assertEqual(same_day_response.status_code, status.HTTP_200_OK)
        self.assertTrue(same_day_response.data["is_completed"])
        self.assertTrue(same_day_response.data["is_favorite"])
        self.assertEqual(same_day_response.data["current_streak_days"], 1)
        self.assertEqual(next_day_response.status_code, status.HTTP_200_OK)
        self.assertEqual(next_day_response.data["current_streak_days"], 2)
        self.assertEqual(next_day_response.data["longest_streak_days"], 2)
        self.assertEqual(skipped_day_response.status_code, status.HTTP_200_OK)
        self.assertEqual(skipped_day_response.data["current_streak_days"], 1)
        self.assertEqual(skipped_day_response.data["longest_streak_days"], 2)

    def test_program_exercise_etags_change_when_favorite_state_changes(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        exercise_id = self.get_program_exercise_ids(program_id)[0]
        list_url = reverse("program-exercise-list", kwargs={"id": program_id})
        detail_url = reverse("program-exercise-detail", kwargs={"id": program_id, "exercise_id": exercise_id})

        first_list_response = self.client.get(list_url)
        first_detail_response = self.client.get(detail_url)

        self.client.post(
            reverse(
                "program-exercise-favorite-update",
                kwargs={"id": program_id, "exercise_id": exercise_id},
            ),
            {"is_favorite": True},
            format="json",
        )

        second_list_response = self.client.get(list_url, HTTP_IF_NONE_MATCH=first_list_response.headers.get("ETag"))
        second_detail_response = self.client.get(detail_url, HTTP_IF_NONE_MATCH=first_detail_response.headers.get("ETag"))

        self.assertEqual(first_list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_detail_response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(first_list_response.headers.get("ETag"), second_list_response.headers.get("ETag"))
        self.assertNotEqual(first_detail_response.headers.get("ETag"), second_detail_response.headers.get("ETag"))

    def test_favorite_calendar_returns_etag_and_supports_not_modified(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        url = reverse("favorite-exercise-calendar")

        first_response = self.client.get(url, {"year": 2026, "month": 5})
        etag = first_response.headers.get("ETag")
        second_response = self.client.get(
            url,
            {"year": 2026, "month": 5},
            HTTP_IF_NONE_MATCH=etag,
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(etag)
        self.assertEqual(second_response.status_code, status.HTTP_304_NOT_MODIFIED)
        self.assertEqual(second_response.headers.get("ETag"), etag)

    def test_favorite_calendar_etag_changes_when_favorite_state_changes(self) -> None:
        upsert_seed_programs()
        access_token, _ = self.signup_and_verify_user()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        program_id = self.get_neck_program_id()
        exercise_id = self.get_program_exercise_ids(program_id)[0]
        url = reverse("favorite-exercise-calendar")

        first_response = self.client.get(url, {"year": 2026, "month": 5})

        self.client.post(
            reverse(
                "program-exercise-favorite-update",
                kwargs={"id": program_id, "exercise_id": exercise_id},
            ),
            {"is_favorite": True},
            format="json",
        )

        second_response = self.client.get(
            url,
            {"year": 2026, "month": 5},
            HTTP_IF_NONE_MATCH=first_response.headers.get("ETag"),
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(first_response.headers.get("ETag"), second_response.headers.get("ETag"))

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
