"""State shared between requests.

Three kinds of records:

- threads: one Slack thread is one conversation with Duo. Holds the Duo
  session ID and the issue draft.
- tracks: one issue the bot reports on, with what has already been reported.
- claims and locks: guards against handling the same thing twice.

Firestore is used in Cloud Run. The in-memory store is for tests and local runs.
"""

import threading
import time


class MemoryStore:
    def __init__(self):
        self._docs = {}
        self._guard = threading.Lock()

    def claim(self, kind: str, key: str) -> bool:
        """True the first time a key is seen, False afterwards."""
        with self._guard:
            if (kind, key) in self._docs:
                return False
            self._docs[(kind, key)] = {}
            return True

    def get(self, kind: str, key: str):
        with self._guard:
            doc = self._docs.get((kind, key))
            return dict(doc) if doc is not None else None

    def save(self, kind: str, key: str, data: dict) -> None:
        with self._guard:
            self._docs.setdefault((kind, key), {}).update(data)

    def active_tracks(self) -> list:
        with self._guard:
            return [
                dict(doc) for (kind, _), doc in self._docs.items() if kind == "tracks" and doc.get("active")
            ]

    def owner(self, candidate: str) -> str:
        """Return the bot's owner, making the candidate the owner if there is none."""
        with self._guard:
            doc = self._docs.setdefault(("config", "owner"), {"user": candidate})
            return doc["user"]

    def acquire_lock(self, name: str, ttl: int) -> bool:
        now = time.time()
        with self._guard:
            doc = self._docs.get(("locks", name))
            if doc and doc["until"] > now:
                return False
            self._docs[("locks", name)] = {"until": now + ttl}
            return True

    def release_lock(self, name: str) -> None:
        with self._guard:
            self._docs.pop(("locks", name), None)


class FirestoreStore:
    def __init__(self):
        from google.cloud import firestore

        self._firestore = firestore
        self._db = firestore.Client()

    def _ref(self, kind: str, key: str):
        return self._db.collection(kind).document(key)

    def claim(self, kind: str, key: str) -> bool:
        from google.api_core.exceptions import AlreadyExists, Conflict

        try:
            self._ref(kind, key).create({"at": self._firestore.SERVER_TIMESTAMP})
            return True
        except (AlreadyExists, Conflict):
            return False

    def get(self, kind: str, key: str):
        snapshot = self._ref(kind, key).get()
        return snapshot.to_dict() if snapshot.exists else None

    def save(self, kind: str, key: str, data: dict) -> None:
        self._ref(kind, key).set(data, merge=True)

    def active_tracks(self) -> list:
        query = self._db.collection("tracks").where(filter=self._firestore.FieldFilter("active", "==", True))
        return [snapshot.to_dict() for snapshot in query.stream()]

    def owner(self, candidate: str) -> str:
        ref = self._ref("config", "owner")
        if self.claim("config", "owner"):
            ref.set({"user": candidate}, merge=True)
            return candidate
        return (ref.get().to_dict() or {}).get("user") or candidate

    def acquire_lock(self, name: str, ttl: int) -> bool:
        ref = self._ref("locks", name)
        transaction = self._db.transaction()

        @self._firestore.transactional
        def attempt(transaction):
            snapshot = ref.get(transaction=transaction)
            now = time.time()
            if snapshot.exists and (snapshot.to_dict() or {}).get("until", 0) > now:
                return False
            transaction.set(ref, {"until": now + ttl})
            return True

        return attempt(transaction)

    def release_lock(self, name: str) -> None:
        self._ref("locks", name).delete()
