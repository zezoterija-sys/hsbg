import json
import time
from pathlib import Path

import requests


BASE_URL = "https://hsbg.cards/api/v1"
OUTPUT_FILE = Path("data/raw/cards.json")

# Ask for a large page. The server may return fewer cards than requested, so
# pagination advances by the ACTUAL number returned rather than this number.
PAGE_LIMIT = 200

# The public batch endpoint supports up to 100 identifiers per request.
BATCH_SIZE = 100

MAX_RETRIES = 6
DEFAULT_RETRY_SECONDS = 2.0

RELATED_ID_FIELDS = (
    "childIds",
    "textMentionIds",
    "companionId",
    "parentId",
)


def _request_with_retry(session, method, url, **kwargs):
    """Make one HTTP request with basic 429/5xx retry handling."""
    for attempt in range(MAX_RETRIES + 1):
        response = session.request(
            method,
            url,
            **kwargs,
        )

        if response.status_code == 429:
            if attempt >= MAX_RETRIES:
                response.raise_for_status()

            retry_after = response.headers.get(
                "Retry-After"
            )

            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = (
                    DEFAULT_RETRY_SECONDS
                    * (2 ** attempt)
                )

            delay = max(
                DEFAULT_RETRY_SECONDS,
                delay,
            )

            print(
                f"Rate limited. Retrying in "
                f"{delay:g} seconds..."
            )
            time.sleep(delay)
            continue

        if 500 <= response.status_code < 600:
            if attempt >= MAX_RETRIES:
                response.raise_for_status()

            delay = (
                DEFAULT_RETRY_SECONDS
                * (2 ** attempt)
            )

            print(
                f"Server error {response.status_code}. "
                f"Retrying in {delay:g} seconds..."
            )
            time.sleep(delay)
            continue

        response.raise_for_status()
        return response

    raise RuntimeError(
        "Request retry loop exited unexpectedly."
    )


def _extract_referenced_ids(card):
    """Return numeric related-card IDs referenced by one card."""
    referenced = set()

    for field in RELATED_ID_FIELDS:
        value = card.get(field)

        if isinstance(value, int):
            referenced.add(value)

        elif isinstance(value, list):
            referenced.update(
                item
                for item in value
                if isinstance(item, int)
            )

    return referenced


def _chunks(values, size):
    """Yield lists of at most `size` items."""
    values = list(values)

    for start in range(
        0,
        len(values),
        size,
    ):
        yield values[
            start : start + size
        ]


def _download_referenced_batch(
    session,
    card_ids,
):
    """
    Resolve up to 100 card IDs in one API request.

    Missing/obsolete IDs are returned in `notFound` rather than raising 404.
    """
    response = _request_with_retry(
        session,
        "POST",
        f"{BASE_URL}/cards/batch",
        json={
            "identifiers": list(card_ids),
            "pool": "all",
        },
        timeout=30,
    )

    payload = response.json()

    data = payload.get(
        "data",
        [],
    )
    not_found = payload.get(
        "notFound",
        [],
    )

    if not isinstance(data, list):
        raise ValueError(
            "Batch API response 'data' field must be a list."
        )

    if not isinstance(not_found, list):
        not_found = []

    return data, not_found


def _add_cards(
    cards,
    cards_by_id,
    batch,
):
    """Add unique card definitions without modifying API card objects."""
    added = 0

    for card in batch:
        if not isinstance(card, dict):
            continue

        card_id = card.get("id")

        if not isinstance(card_id, int):
            continue

        if card_id in cards_by_id:
            continue

        cards.append(card)
        cards_by_id[card_id] = card
        added += 1

    return added


def download_cards():
    cards = []
    cards_by_id = {}

    with requests.Session() as session:

        # =========================================================
        # 1. BULK DOWNLOAD
        # =========================================================

        offset = 0

        while True:
            response = _request_with_retry(
                session,
                "GET",
                f"{BASE_URL}/cards",
                params={
                    "pool": "all",
                    "limit": PAGE_LIMIT,
                    "offset": offset,
                },
                timeout=30,
            )

            payload = response.json()
            batch = payload.get(
                "data",
                [],
            )

            if not isinstance(batch, list):
                raise ValueError(
                    "API response 'data' field must be a list."
                )

            if not batch:
                break

            _add_cards(
                cards,
                cards_by_id,
                batch,
            )

            print(
                f"Downloaded {len(cards)} bulk cards..."
            )

            has_more = payload.get(
                "hasMore"
            )

            if has_more is False:
                break

            # IMPORTANT:
            # Advance by what the server ACTUALLY returned. The API may clamp
            # the requested page limit; advancing by PAGE_LIMIT could skip data.
            offset += len(batch)

            total = payload.get(
                "total"
            )

            if (
                isinstance(total, int)
                and offset >= total
            ):
                break

        # =========================================================
        # 2. RESOLVE REFERENCED / GENERATED CARDS
        # =========================================================
        #
        # Bulk listings can contain cards whose childIds/textMentionIds point
        # to generated or legacy cards omitted from the listing. Resolve those
        # IDs in batches of 100. Newly added cards are scanned too, so nested
        # generated-card references are followed recursively.

        checked_ids = set()
        permanently_missing = set()

        while True:
            referenced_ids = set()

            for card in cards:
                referenced_ids.update(
                    _extract_referenced_ids(
                        card
                    )
                )

            missing_ids = sorted(
                referenced_ids
                - set(cards_by_id)
                - checked_ids
            )

            if not missing_ids:
                break

            print(
                f"Resolving {len(missing_ids)} "
                f"referenced cards in batches..."
            )

            added_this_pass = 0

            for id_batch in _chunks(
                missing_ids,
                BATCH_SIZE,
            ):
                checked_ids.update(
                    id_batch
                )

                resolved, not_found = (
                    _download_referenced_batch(
                        session,
                        id_batch,
                    )
                )

                added_this_pass += (
                    _add_cards(
                        cards,
                        cards_by_id,
                        resolved,
                    )
                )

                for identifier in not_found:
                    try:
                        permanently_missing.add(
                            int(identifier)
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        pass

            print(
                f"Added {added_this_pass} "
                f"referenced card definitions."
            )

            if added_this_pass == 0:
                break

    # =============================================================
    # 3. INTEGRITY CHECK
    # =============================================================

    all_referenced_ids = set()

    for card in cards:
        all_referenced_ids.update(
            _extract_referenced_ids(
                card
            )
        )

    unresolved = sorted(
        all_referenced_ids
        - set(cards_by_id)
    )

    # =============================================================
    # 4. SAVE
    # =============================================================

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = (
        OUTPUT_FILE.with_suffix(
            OUTPUT_FILE.suffix + ".tmp"
        )
    )

    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            cards,
            file,
            indent=2,
            ensure_ascii=False,
        )

    temporary_file.replace(
        OUTPUT_FILE
    )

    print(
        f"\nSaved {len(cards)} cards "
        f"to {OUTPUT_FILE}"
    )

    if unresolved:
        print(
            f"{len(unresolved)} referenced IDs "
            f"could not be resolved by the API."
        )

        # Keep console output manageable.
        preview = unresolved[:50]

        print(
            "First unresolved IDs:",
            ", ".join(
                str(card_id)
                for card_id in preview
            ),
        )

        if len(unresolved) > len(preview):
            print(
                f"... plus "
                f"{len(unresolved) - len(preview)} more."
            )
    else:
        print(
            "All referenced child/text-mention/"
            "companion/parent card IDs are present."
        )

    # Specific guard for the Chromadrake failure that exposed this issue.
    chromadrake_ids = {
        126711,
        126713,
        126715,
        126717,
        126718,
    }

    missing_chromadrakes = sorted(
        chromadrake_ids
        - set(cards_by_id)
    )

    if missing_chromadrakes:
        print(
            "WARNING: missing Chromadrake IDs:",
            ", ".join(
                str(card_id)
                for card_id
                in missing_chromadrakes
            ),
        )
    else:
        print(
            "Chromadrake generated-card definitions are present."
        )


if __name__ == "__main__":
    download_cards()
