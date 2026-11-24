from app.cuet_clat.source_registry import build_source_manifest


def test_source_manifest_lists_primary_urls_without_fake_hashes() -> None:
    manifest = build_source_manifest()
    assert len(manifest) >= 4
    for entry in manifest:
        assert entry["rights_status"] == "SOURCE_PENDING"
        assert entry["url"].startswith("https://")
        assert "sha256" not in entry