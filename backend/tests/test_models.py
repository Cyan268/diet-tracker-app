from app.models import Base, RefreshToken, User


def test_user_model_is_registered_in_metadata() -> None:
    table = Base.metadata.tables[User.__tablename__]

    assert table.name == "users"
    assert set(table.columns.keys()) == {
        "id",
        "email",
        "password_hash",
        "is_active",
        "is_demo",
        "created_at",
        "updated_at",
    }
    assert table.columns.email.index is True
    assert table.columns.email.unique is True


def test_unique_index_naming_is_deterministic() -> None:
    table = Base.metadata.tables[User.__tablename__]
    unique_indexes = [index for index in table.indexes if index.unique]

    assert [index.name for index in unique_indexes] == ["ix_users_email"]


def test_refresh_token_model_supports_rotation_and_family_revocation() -> None:
    table = Base.metadata.tables[RefreshToken.__tablename__]

    assert set(table.columns.keys()) == {
        "id",
        "user_id",
        "token_hash",
        "family_id",
        "expires_at",
        "revoked_at",
        "replaced_by_id",
        "created_at",
    }
    assert table.columns.token_hash.unique is True
    assert table.columns.replaced_by_id.foreign_keys
