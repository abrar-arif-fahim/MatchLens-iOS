"""Private user workflows with simulated sessions and isolated local mutations."""

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from app_contracts import AccessError
from app_service import AppReadService, NotFoundError
from app_repository import RepositoryError
from preview_app_workflow import load_demo_repository
from user_data_service import (UserDataService, favorite_id, simulate_user_plan, validate_user_document)
from validate_match_schema import ValidationError


class UserDataServiceTests(unittest.TestCase):
    def setUp(self):
        for guard in (
            patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network allowed")),
            patch("firebase_admin.initialize_app", side_effect=AssertionError("No real Auth account allowed")),
            patch("firebase_admin.firestore.client", side_effect=AssertionError("No real database allowed")),
        ):
            guard.start()
            self.addCleanup(guard.stop)
        self.repo, self.catalog = load_demo_repository()
        self.app = AppReadService(self.repo, self.catalog, actor_uid="test-alice", demo_mode=True)
        self.users = UserDataService(self.repo, self.app.resolve_reference, actor_uid="test-alice")
        self.clock = datetime(2030, 1, 2, tzinfo=timezone.utc)
        self.match_id = next(iter(self.repo.documents["matches"]))
        self.highlight_id = next(iter(self.repo.documents["highlights"]))

    def apply(self, plan, *, actor_uid="test-alice", clock=None):
        original = copy.deepcopy(self.repo.documents)
        updated = simulate_user_plan(plan, self.repo.documents, actor_uid=actor_uid,
                                     server_time=clock or self.clock, resolve_reference=self.app.resolve_reference)
        self.assertEqual(self.repo.documents, original)
        self.repo.documents = updated
        return plan

    def test_missing_auth_is_rejected_before_private_reads(self):
        repository = Mock()
        with self.assertRaises(AccessError):
            UserDataService(repository, self.app.resolve_reference, actor_uid=None)
        repository.get.assert_not_called()

    def test_profile_provisioning_recovers_after_auth_succeeded_and_profile_was_missing(self):
        self.assertIsNone(self.users.profile())
        plan = self.users.plan_profile("Fictional Fan")
        self.assertEqual(plan["operation"], "CREATE")
        self.assertNotIn("createdAt", plan["data"])
        self.assertEqual(plan["serverTimestampFields"], ["createdAt", "updatedAt"])
        self.apply(plan)
        profile = self.users.profile()
        self.assertEqual(profile["uid"], "test-alice")
        self.assertEqual(profile["displayName"], "Fictional Fan")
        self.assertEqual(profile["createdAt"], profile["updatedAt"])
        self.assertNotIn("email", profile)
        self.assertNotIn("password", profile)

    def test_profile_repeated_provisioning_is_idempotent_and_name_update_preserves_created_at(self):
        self.apply(self.users.plan_profile("Fictional Fan"))
        created = self.users.profile()["createdAt"]
        self.assertEqual(self.users.plan_profile("Fictional Fan")["operation"], "NO CHANGE")
        self.apply(self.users.plan_profile("Updated Fan"), clock=self.clock + timedelta(hours=1))
        self.assertEqual(self.users.profile()["createdAt"], created)
        self.assertGreater(self.users.profile()["updatedAt"], created)

    def test_invalid_display_names_never_produce_a_plan(self):
        for name in ("", " leading", "trailing ", "a\nb", "x" * 81, None):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.users.plan_profile(name)

    def test_cross_user_reads_and_all_private_plans_fail_before_storage_access(self):
        with patch.object(self.repo, "get") as read, patch.object(self.repo, "private_page") as listing:
            methods = (
                lambda: self.users.profile(owner_uid="test-bob"),
                lambda: self.users.settings(owner_uid="test-bob"),
                lambda: self.users.plan_profile("Name", owner_uid="test-bob"),
                lambda: self.users.plan_settings({}, owner_uid="test-bob"),
                lambda: self.users.plan_favorite("player", "wikidata_Q615", owner_uid="test-bob"),
                lambda: self.users.plan_watchlist(self.match_id, owner_uid="test-bob"),
                lambda: self.users.saved_items(owner_uid="test-bob"),
            )
            for method in methods:
                with self.assertRaises(AccessError):
                    method()
            read.assert_not_called()
            listing.assert_not_called()

    def test_settings_defaults_are_explicitly_not_persisted(self):
        result = self.users.settings()
        self.assertFalse(result["persisted"])
        self.assertIsNone(result["values"]["updatedAt"])
        self.assertFalse(result["values"]["scoreNotifications"])
        self.assertFalse(result["values"]["highlightNotifications"])
        self.assertEqual(result["values"]["appearance"], "system")

    def test_settings_create_patch_and_no_change_do_not_fabricate_timestamps(self):
        plan = self.users.plan_settings({"appearance": "dark", "favoriteTeamId": "wikidata_Q7156"})
        self.assertEqual(plan["operation"], "CREATE")
        self.assertNotIn("updatedAt", plan["data"])
        self.apply(plan)
        self.assertTrue(self.users.settings()["persisted"])
        update = self.users.plan_settings({"scoreNotifications": True})
        self.assertEqual(update["data"], {"scoreNotifications": True})
        self.apply(update, clock=self.clock + timedelta(seconds=1))
        self.assertEqual(self.users.plan_settings({"scoreNotifications": True})["operation"], "NO CHANGE")

    def test_settings_reject_protected_unknown_or_wrongly_typed_fields(self):
        for change in ({"uid": "test-bob"}, {"role": "admin"}, {"email": "test@example.invalid"},
                       {"updatedAt": "2030-01-01T00:00:00Z"}, {"schemaVersion": 2},
                       {"appearance": "automatic"}, {"scoreNotifications": 1},
                       {"highlightNotifications": "yes"}, {"favoriteTeamId": "529"}, []):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.users.plan_settings(change)

    def test_settings_require_existing_team_and_allow_clearing_stale_team(self):
        with self.assertRaises(NotFoundError):
            self.users.plan_settings({"favoriteTeamId": "wikidata_Q999999"})
        self.apply(self.users.plan_settings({"favoriteTeamId": "wikidata_Q7156"}))
        del self.repo.documents["teams"]["wikidata_Q7156"]
        self.apply(self.users.plan_settings({"favoriteTeamId": None}))
        self.assertIsNone(self.users.settings()["values"]["favoriteTeamId"])

    def test_all_four_favorite_types_resolve_to_safe_read_contracts(self):
        for kind, identifier in (("player", "wikidata_Q615"), ("team", "wikidata_Q7156"),
                                 ("match", self.match_id), ("highlight", self.highlight_id)):
            self.apply(self.users.plan_favorite(kind, identifier))
        saved = self.users.saved_items()["items"]
        self.assertEqual(len(saved), 4)
        self.assertTrue(all(row["availability"] == "available" for row in saved))
        highlight = next(row for row in saved if row["saved"]["targetType"] == "highlight")
        self.assertFalse(highlight["target"]["playbackAvailable"])
        self.assertNotIn("mediaReference", highlight["target"])
        json.dumps(saved)  # In-memory serialization only.

    def test_favorite_ids_and_desired_saved_state_prevent_duplicate_toggles(self):
        plan = self.users.plan_favorite("player", "wikidata_Q615")
        self.assertEqual(plan["path"], "users/test-alice/favorites/player_wikidata_Q615")
        self.apply(plan)
        self.assertEqual(self.users.plan_favorite("player", "wikidata_Q615")["operation"], "NO CHANGE")
        self.assertEqual(len(self.users.saved_items()["items"]), 1)
        self.apply(self.users.plan_favorite("player", "wikidata_Q615", saved=False))
        self.assertEqual(self.users.plan_favorite("player", "wikidata_Q615", saved=False)["operation"], "NO CHANGE")

    def test_unknown_or_provider_specific_favorite_targets_are_rejected(self):
        for kind, identifier in (("team", "529"), ("player", "wikidata_Q999999"), ("user", "test-bob"),
                                 ("highlight", "demo_highlight_missing__one")):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                self.users.plan_favorite(kind, identifier)
        for value in ("YES", 1, None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.users.plan_favorite("player", "wikidata_Q615", saved=value)

    def test_watchlist_is_match_only_and_idempotent(self):
        self.apply(self.users.plan_watchlist(self.match_id))
        self.assertEqual(self.users.plan_watchlist(self.match_id)["operation"], "NO CHANGE")
        rows = self.users.saved_items("watchlist")["items"]
        self.assertEqual(rows[0]["saved"]["matchId"], self.match_id)
        with self.assertRaises(ValidationError):
            self.users.plan_watchlist("wikidata_Q7156")
        self.apply(self.users.plan_watchlist(self.match_id, saved=False))
        self.assertEqual(self.users.saved_items("watchlist")["items"], [])

    def test_deleted_reference_is_reported_missing_and_can_be_removed(self):
        self.apply(self.users.plan_favorite("player", "wikidata_Q615"))
        del self.repo.documents["players"]["wikidata_Q615"]
        item = self.users.saved_items()["items"][0]
        self.assertEqual(item["availability"], "missing")
        self.assertIsNone(item["target"])
        self.apply(self.users.plan_favorite("player", "wikidata_Q615", saved=False))
        self.assertEqual(self.users.saved_items()["items"], [])

    def test_reference_failure_is_review_required_but_connectivity_is_an_error(self):
        self.apply(self.users.plan_favorite("player", "wikidata_Q615"))
        self.repo.documents["players"]["wikidata_Q615"]["source"] = "unreviewed"
        self.assertEqual(self.users.saved_items()["items"][0]["availability"], "reviewRequired")
        with patch.object(self.users, "resolve_reference", side_effect=RepositoryError("Read failed")):
            with self.assertRaises(RepositoryError):
                self.users.saved_items()

    def test_private_list_pagination_never_crosses_users_or_loses_rows(self):
        for identifier in ("wikidata_Q615", "wikidata_Q11571", "wikidata_Q21621995"):
            self.apply(self.users.plan_favorite("player", identifier))
        rows, cursor = [], None
        while True:
            page = self.users.saved_items(page_size=1, cursor=cursor)
            rows.extend(page["items"])
            if not page["hasMore"]:
                break
            cursor = page["nextCursor"]
        self.assertEqual(len({row["documentId"] for row in rows}), 3)
        with self.assertRaises(ValidationError):
            self.users.saved_items(page_size=0)
        with self.assertRaises(ValidationError):
            self.users.saved_items(cursor="missing")

    def test_two_users_have_independent_profiles_settings_and_saved_items(self):
        self.apply(self.users.plan_profile("Alice"))
        self.apply(self.users.plan_favorite("player", "wikidata_Q615"))
        bob = UserDataService(self.repo, self.app.resolve_reference, actor_uid="test-bob")
        self.apply(bob.plan_profile("Bob"), actor_uid="test-bob")
        self.assertEqual(self.users.profile()["displayName"], "Alice")
        self.assertEqual(bob.profile()["displayName"], "Bob")
        self.assertEqual(bob.saved_items()["items"], [])
        with self.assertRaises(AccessError):
            bob.profile(owner_uid="test-alice")

    def test_private_documents_reject_roles_passwords_schema_spoofing_and_owner_mismatch(self):
        self.apply(self.users.plan_profile("Fan"))
        original = self.users.profile()
        for change in ({"role": "admin"}, {"password": "not-a-field"}, {"schemaVersion": True},
                       {"uid": "test-bob"}, {"createdAt": None}, {"updatedAt": "2020-02-30T00:00:00Z"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                validate_user_document("users/test-alice", dict(original, **change), "test-alice")

    def test_changed_private_state_conflicts_without_any_partial_mutation(self):
        self.apply(self.users.plan_profile("Fan"))
        stale = self.users.plan_profile("Stale proposed name")
        self.apply(self.users.plan_profile("Newer name"), clock=self.clock + timedelta(seconds=1))
        original = copy.deepcopy(self.repo.documents)
        with self.assertRaisesRegex(ValidationError, "Conflict"):
            self.apply(stale)
        self.assertEqual(self.repo.documents, original)

    def test_replayed_create_plan_conflicts_and_fresh_plan_is_no_change(self):
        plan = self.users.plan_profile("Fan")
        self.apply(plan)
        with self.assertRaisesRegex(ValidationError, "Conflict"):
            self.apply(plan)
        self.assertEqual(self.users.plan_profile("Fan")["operation"], "NO CHANGE")

    def test_apply_rechecks_reference_existence_after_preview(self):
        plan = self.users.plan_favorite("player", "wikidata_Q615")
        del self.repo.documents["players"]["wikidata_Q615"]
        original = copy.deepcopy(self.repo.documents)
        with self.assertRaises(NotFoundError):
            self.apply(plan)
        self.assertEqual(self.repo.documents, original)

    def test_apply_cannot_trust_forged_ownership_or_protected_fields(self):
        plan = self.users.plan_profile("Fan")
        with self.assertRaises(AccessError):
            self.apply(plan, actor_uid="test-bob")
        for changed in (dict(plan, path="teams/wikidata_Q7156"), dict(plan, operation="UNSUPPORTED"),
                        dict(plan, data=dict(plan["data"], role="admin")),
                        dict(plan, data=dict(plan["data"], createdAt="2030-01-01T00:00:00Z")),
                        dict(plan, serverTimestampFields=[])):
            with self.subTest(path=changed["path"]), self.assertRaises(ValidationError):
                self.apply(changed)

    def test_profile_deletion_and_immutable_favorite_update_are_not_supported(self):
        self.apply(self.users.plan_profile("Fan"))
        current = self.users.profile()
        removal = {"path": "users/test-alice", "operation": "DELETE", "data": None,
                   "serverTimestampFields": [], "expected": current}
        with self.assertRaises(AccessError):
            self.apply(removal)
        self.apply(self.users.plan_favorite("player", "wikidata_Q615"))
        plan = self.users.plan_favorite("player", "wikidata_Q615")
        plan.update(operation="UPDATE", data={"targetType": "player"}, serverTimestampFields=["createdAt"])
        with self.assertRaises(ValidationError):
            self.apply(plan)

    def test_user_contracts_do_not_initialize_auth_or_create_firebase_users(self):
        # Account creation/sign-in remain Firebase Swift SDK responsibilities.
        with patch("firebase_admin.auth.create_user", side_effect=AssertionError("No real account allowed")) as create:
            self.apply(self.users.plan_profile("Offline fan"))
            self.users.profile()
            create.assert_not_called()

    def test_malformed_plan_operation_and_no_change_data_are_rejected(self):
        plan = self.users.plan_profile("Fan")
        with self.assertRaises(ValidationError):
            self.apply(dict(plan, operation=[]))
        self.apply(plan)
        unchanged = self.users.plan_profile("Fan")
        with self.assertRaises(ValidationError):
            self.apply(dict(unchanged, data={"displayName": "Should not apply"}))


if __name__ == "__main__":
    unittest.main()
