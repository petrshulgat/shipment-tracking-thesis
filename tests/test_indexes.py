import pytest

from app.db.indexes import COLLECTIONS, INDEX_CONFIGS, apply_indexes


def index_names(db, collection):
    """Secondary index names of a collection (without the automatic _id index)."""
    return {i["name"] for i in db[collection].list_indexes()} - {"_id_"}


def expected_names(config, collection):
    return {m.document["name"] for m in INDEX_CONFIGS[config].get(collection, [])}


@pytest.mark.parametrize("config", list(INDEX_CONFIGS))
def test_apply_on_empty_database(db, config):
    apply_indexes(db, config)
    for collection in COLLECTIONS:
        assert index_names(db, collection) == expected_names(config, collection)


def test_switching_config_removes_old_indexes(db):
    apply_indexes(db, "full")
    apply_indexes(db, "minimal")
    for collection in COLLECTIONS:
        assert index_names(db, collection) == expected_names("minimal", collection)


def test_unknown_config(db):
    with pytest.raises(ValueError):
        apply_indexes(db, "huge")
