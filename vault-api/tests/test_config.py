from config import ConfigStore, VaultConfig, mask


def test_round_trip_persists(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    store.update(
        jellyfin={"base_url": "http://jf.local", "api_key": "secret", "user_id": "u1"},
        tmdb={"api_key": "tmdb-key"},
    )
    # A fresh store reading the same file sees the saved values.
    reloaded = ConfigStore(path).get()
    assert reloaded.jellyfin.base_url == "http://jf.local"
    assert reloaded.jellyfin.api_key == "secret"
    assert reloaded.jellyfin.user_id == "u1"
    assert reloaded.tmdb.api_key == "tmdb-key"


def test_partial_update_merges(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.update(jellyfin={"base_url": "http://jf.local", "api_key": "k", "user_id": "u1"})
    # Updating one field must not wipe the others in the same section.
    store.update(jellyfin={"base_url": "http://new.local"})
    cfg = store.get()
    assert cfg.jellyfin.base_url == "http://new.local"
    assert cfg.jellyfin.api_key == "k"
    assert cfg.jellyfin.user_id == "u1"


def test_env_bootstrap_fills_only_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("JELLYFIN_URL", "http://env.local")
    monkeypatch.setenv("VAULT_BEARER_TOKEN", "env-token")
    monkeypatch.setenv("ROON_API_URL", "http://roon.local:3085")
    cfg = ConfigStore(tmp_path / "config.json").get()
    assert cfg.jellyfin.base_url == "http://env.local"
    assert cfg.bearer_token == "env-token"
    assert cfg.roon.base_url == "http://roon.local:3085"


def test_explicit_value_wins_over_env(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    ConfigStore(path).update(jellyfin={"base_url": "http://disk.local"})
    monkeypatch.setenv("JELLYFIN_URL", "http://env.local")
    cfg = ConfigStore(path).get()
    assert cfg.jellyfin.base_url == "http://disk.local"


def test_ensure_bearer_token_is_stable(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    first = store.ensure_bearer_token()
    assert first
    assert store.ensure_bearer_token() == first


def test_get_returns_a_copy(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.update(jellyfin={"base_url": "http://jf.local", "api_key": "k", "user_id": "u1"})
    snapshot = store.get()
    snapshot.jellyfin.base_url = "mutated"
    assert store.get().jellyfin.base_url == "http://jf.local"


def test_configured_properties():
    cfg = VaultConfig()
    assert cfg.jellyfin.configured is False
    assert cfg.roon.configured is False
    cfg.jellyfin.base_url = "x"; cfg.jellyfin.api_key = "y"
    assert cfg.jellyfin.configured is False  # still needs user_id
    cfg.jellyfin.user_id = "u"
    assert cfg.jellyfin.configured is True
    cfg.roon.base_url = "http://roon.local:3085"
    assert cfg.roon.configured is True


def test_mask():
    assert mask("") == ""
    assert mask("ab") == "••••"
    assert mask("abcdefgh").endswith("efgh")
    assert "abcd" not in mask("abcdefgh")
