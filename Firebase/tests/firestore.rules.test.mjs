// Optional emulator tests. Never connect this test file to a real project.
import { readFile } from "node:fs/promises";
import { after, before, beforeEach, test } from "node:test";
import { initializeTestEnvironment, assertFails, assertSucceeds } from "@firebase/rules-unit-testing";
import {
  collection, collectionGroup, deleteDoc, doc, getDoc, getDocs, limit, query,
  serverTimestamp, setDoc, Timestamp, updateDoc, where,
} from "firebase/firestore";

const endpoint = process.env.FIRESTORE_EMULATOR_HOST ?? "";
if (!/^(127\.0\.0\.1|localhost):[0-9]+$/.test(endpoint)) {
  throw new Error("Tests require a loopback FIRESTORE_EMULATOR_HOST; all other destinations are forbidden.");
}
const [host, port] = endpoint.split(":");
let environment;
const alice = () => environment.authenticatedContext("test-alice").firestore();
const bob = () => environment.authenticatedContext("test-bob").firestore();
const guest = () => environment.unauthenticatedContext().firestore();
const profile = (uid = "test-alice") => ({
  uid, displayName: "Fictional Fan", schemaVersion: 1,
  createdAt: serverTimestamp(), updatedAt: serverTimestamp(),
});
const favorite = (targetType = "team", targetId = "wikidata_Q900001") => ({
  targetType, targetId, schemaVersion: 1, createdAt: serverTimestamp(),
});
const settings = () => ({
  favoriteTeamId: null, appearance: "system", scoreNotifications: false,
  highlightNotifications: false, schemaVersion: 1, updatedAt: serverTimestamp(),
});

before(async () => {
  environment = await initializeTestEnvironment({
    projectId: "demo-matchlens",
    firestore: { host, port: Number(port), rules: await readFile(new URL("../firestore.rules", import.meta.url), "utf8") },
  });
});
beforeEach(async () => {
  await environment.clearFirestore();
  await environment.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    // All records in this file are synthetic rule-test data, never provider data.
    await setDoc(doc(db, "teams/wikidata_Q900001"), { teamId: "wikidata_Q900001", name: "Fictional team" });
    await setDoc(doc(db, "players/wikidata_Q900001"), { wikidataId: "Q900001", name: "Fictional player" });
    await setDoc(doc(db, "matches/demo_rule_test"), { matchId: "demo_rule_test", isDemo: true });
    await setDoc(doc(db, "highlights/demo_highlight_rule_test__one"), {
      highlightId: "demo_highlight_rule_test__one", rightsStatus: "unconfirmed", mediaReference: null,
    });
    await setDoc(doc(db, "highlights/demo_highlight_rule_test__blocked"), {
      highlightId: "demo_highlight_rule_test__blocked", rightsStatus: "authorized",
      mediaReference: "fictional_nonexistent_clip.mp4",
    });
  });
});
after(async () => { await environment?.cleanup(); });

test("catalog requires authentication, bounded lists and no client writes", async () => {
  await assertFails(getDoc(doc(guest(), "teams/wikidata_Q900001")));
  await assertSucceeds(getDoc(doc(alice(), "teams/wikidata_Q900001")));
  await assertFails(getDocs(collection(alice(), "players")));
  await assertSucceeds(getDocs(query(collection(alice(), "players"), limit(20))));
  await assertFails(getDocs(query(collection(alice(), "players"), limit(52))));
  for (const name of ["players", "teams", "competitions", "matches", "matchEvents", "highlights"]) {
    await assertFails(setDoc(doc(alice(), name, "forbidden"), { arbitrary: true }));
  }
});
test("profile provision and display-name edit use server timestamps", async () => {
  const reference = doc(alice(), "users/test-alice");
  await assertSucceeds(setDoc(reference, profile()));
  await assertSucceeds(updateDoc(reference, { displayName: "Updated fictional fan", updatedAt: serverTimestamp() }));
  await assertSucceeds(getDoc(reference));
});
test("profile ownership, UID and private-list access cannot be spoofed", async () => {
  await assertFails(setDoc(doc(alice(), "users/test-bob"), profile("test-bob")));
  await assertFails(setDoc(doc(alice(), "users/test-alice"), profile("test-bob")));
  await assertFails(getDoc(doc(bob(), "users/test-alice")));
  await assertFails(getDocs(query(collection(alice(), "users"), limit(20))));
  await assertFails(getDoc(doc(guest(), "users/test-alice")));
});
test("profile rejects protected fields, client clocks and deletion", async () => {
  const reference = doc(alice(), "users/test-alice");
  for (const extra of [{ role: "admin" }, { password: "fictional-invalid-field" }, { email: "test@example.invalid" }]) {
    await assertFails(setDoc(reference, { ...profile(), ...extra }));
  }
  await assertFails(setDoc(reference, { ...profile(), createdAt: Timestamp.fromMillis(0) }));
  await assertSucceeds(setDoc(reference, profile()));
  await assertFails(updateDoc(reference, { uid: "test-bob", updatedAt: serverTimestamp() }));
  await assertFails(updateDoc(reference, { createdAt: Timestamp.fromMillis(0), updatedAt: serverTimestamp() }));
  await assertFails(deleteDoc(reference));
});
test("settings validate types, allow existing team and remain owner-only", async () => {
  const reference = doc(alice(), "users/test-alice/settings/preferences");
  await assertSucceeds(setDoc(reference, settings()));
  await assertSucceeds(updateDoc(reference, { favoriteTeamId: "wikidata_Q900001", updatedAt: serverTimestamp() }));
  for (const change of [{ scoreNotifications: 1 }, { appearance: "automatic" }, { role: "admin" },
                        { favoriteTeamId: "wikidata_Q999999" }]) {
    await assertFails(updateDoc(reference, { ...change, updatedAt: serverTimestamp() }));
  }
  await assertFails(getDoc(doc(bob(), "users/test-alice/settings/preferences")));
  await assertFails(setDoc(doc(alice(), "users/test-alice/settings/other"), settings()));
});
test("favorites use deterministic IDs and require existing canonical targets", async () => {
  const reference = doc(alice(), "users/test-alice/favorites/team_wikidata_Q900001");
  await assertSucceeds(setDoc(reference, favorite()));
  await assertSucceeds(getDoc(reference));
  await assertFails(setDoc(doc(alice(), "users/test-alice/favorites/wrong"), favorite()));
  await assertFails(setDoc(doc(alice(), "users/test-alice/favorites/team_wikidata_Q999999"),
                          favorite("team", "wikidata_Q999999")));
  await assertFails(setDoc(doc(alice(), "users/test-alice/favorites/team_529"), favorite("team", "529")));
  await assertFails(updateDoc(reference, { targetId: "wikidata_Q999999" }));
});
test("favorites cannot be read, listed or mutated by another user", async () => {
  await assertSucceeds(setDoc(doc(alice(), "users/test-alice/favorites/team_wikidata_Q900001"), favorite()));
  const foreign = doc(bob(), "users/test-alice/favorites/team_wikidata_Q900001");
  await assertFails(getDoc(foreign));
  await assertFails(deleteDoc(foreign));
  await assertFails(getDocs(query(collection(bob(), "users/test-alice/favorites"), limit(20))));
  await assertFails(getDocs(query(collectionGroup(alice(), "favorites"), limit(20))));
});
test("stale favorites can be removed, and private lists require limits", async () => {
  const db = alice();
  const reference = doc(db, "users/test-alice/favorites/team_wikidata_Q900001");
  await assertSucceeds(setDoc(reference, favorite()));
  await environment.withSecurityRulesDisabled(async (context) => {
    await deleteDoc(doc(context.firestore(), "teams/wikidata_Q900001"));
  });
  await assertSucceeds(getDocs(query(collection(db, "users/test-alice/favorites"), limit(20))));
  await assertFails(getDocs(collection(db, "users/test-alice/favorites")));
  await assertSucceeds(deleteDoc(reference));
});
test("watchlist is match-only, immutable and scoped to its owner", async () => {
  const value = { matchId: "demo_rule_test", schemaVersion: 1, createdAt: serverTimestamp() };
  const reference = doc(alice(), "users/test-alice/watchlist/demo_rule_test");
  await assertSucceeds(setDoc(reference, value));
  await assertFails(setDoc(doc(alice(), "users/test-alice/watchlist/wrong"), value));
  await assertFails(updateDoc(reference, { matchId: "demo_missing" }));
  await assertFails(getDoc(doc(bob(), "users/test-alice/watchlist/demo_rule_test")));
  await assertSucceeds(deleteDoc(reference));
});
test("media stays blocked; metadata-only highlight queries need matching constraints", async () => {
  await assertSucceeds(getDoc(doc(alice(), "highlights/demo_highlight_rule_test__one")));
  await assertFails(getDoc(doc(alice(), "highlights/demo_highlight_rule_test__blocked")));
  await assertFails(getDocs(query(collection(alice(), "highlights"), limit(20))));
  await assertSucceeds(getDocs(query(collection(alice(), "highlights"),
    where("rightsStatus", "==", "unconfirmed"), where("mediaReference", "==", null), limit(20))));
  await assertSucceeds(setDoc(doc(alice(), "users/test-alice/favorites/highlight_demo_highlight_rule_test__one"),
                             favorite("highlight", "demo_highlight_rule_test__one")));
  await assertFails(setDoc(doc(alice(), "users/test-alice/favorites/highlight_demo_highlight_rule_test__blocked"),
                          favorite("highlight", "demo_highlight_rule_test__blocked")));
});
test("unknown collections and private descendants are denied", async () => {
  await assertFails(getDoc(doc(alice(), "credentials/anything")));
  await assertFails(setDoc(doc(alice(), "users/test-alice/private/anything"), { value: true }));
  await assertFails(getDoc(doc(alice(), "users/test-alice/private/anything")));
});
