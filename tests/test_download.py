"""Download contracts use small files; the full public source is checked separately."""
import copy
import hashlib
import io
import json

import pandas as pd
import pytest

from pv_hlca import download as dl
from pv_hlca import PVModel


def entry(body, key="z.txt"):
    return {"key": key, "size": len(body),
            "checksum": "md5:" + hashlib.md5(body).hexdigest(),
            "links": {"self": f"https://zenodo.org/api/records/{dl.RECORD}/files/{key}/content"}}


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


def no_network(*args, **kwargs):
    pytest.fail("Unexpected network request")


def test_resume_validates_range_and_full_checksum(tmp_path, monkeypatch):
    body = b"a complete source file"
    part = tmp_path / "z.txt.part"
    part.write_bytes(body[:5])

    def request(req, timeout):
        assert req.get_header("Range") == "bytes=5-"
        return Response(body[5:], 206, {"Content-Range": f"bytes 5-{len(body)-1}/{len(body)}"})

    monkeypatch.setattr(dl, "urlopen", request)
    path = dl._download_file(entry(body), tmp_path, progress=lambda _: None)
    assert path.read_bytes() == body
    assert not part.exists()
    monkeypatch.setattr(dl, "urlopen", no_network)
    assert dl._download_file(entry(body), tmp_path, progress=lambda _: None) == path


def test_ignored_range_restarts_instead_of_appending(tmp_path, monkeypatch):
    body = b"valid complete file"
    (tmp_path / "z.txt.part").write_bytes(b"partial")
    monkeypatch.setattr(dl, "urlopen", lambda *a, **k: Response(body))
    assert dl._download_file(entry(body), tmp_path, progress=lambda _: None).read_bytes() == body


def test_bad_range_never_commits_source(tmp_path, monkeypatch):
    (tmp_path / "z.txt.part").write_bytes(b"x")
    monkeypatch.setattr(dl, "urlopen", lambda *a, **k: Response(b"yz", 206, {"Content-Range": "bytes 0-1/2"}))
    with pytest.raises(ValueError, match="Invalid resume"):
        dl._download_file(entry(b"xyz"), tmp_path, progress=lambda _: None)
    assert not (tmp_path / "z.txt").exists()


def test_checksum_failure_never_commits_source(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "urlopen", lambda *a, **k: Response(b"wrong"))
    monkeypatch.setattr(dl.time, "sleep", lambda _: None)
    with pytest.raises(OSError, match="checksum mismatch"):
        dl._download_file(entry(b"right"), tmp_path, progress=lambda _: None)
    assert not (tmp_path / "z.txt").exists()


def test_truncated_transfer_resumes_on_retry(tmp_path, monkeypatch):
    body = b"resumable source"
    calls = []

    def request(req, **kwargs):
        calls.append(req)
        if len(calls) == 1:
            return Response(body[:4])
        assert req.get_header("Range") == "bytes=4-"
        return Response(body[4:], 206, {"Content-Range": f"bytes 4-{len(body)-1}/{len(body)}"})

    monkeypatch.setattr(dl, "urlopen", request)
    monkeypatch.setattr(dl.time, "sleep", lambda _: None)
    assert dl._download_file(entry(body), tmp_path, progress=lambda _: None).read_bytes() == body
    assert len(calls) == 2


def test_damaged_user_source_is_not_overwritten(tmp_path, monkeypatch):
    (tmp_path / "z.txt").write_bytes(b"damaged")
    monkeypatch.setattr(dl, "urlopen", no_network)
    with pytest.raises(ValueError, match="move the damaged file"):
        dl._download_file(entry(b"correct"), tmp_path)
    assert (tmp_path / "z.txt").read_bytes() == b"damaged"


@pytest.fixture
def tiny_source(tmp_path, monkeypatch):
    """Use real conversion, with enough rows to cross its chunk boundary."""
    monkeypatch.setattr(dl, "_CHUNK_ROWS", 128)
    index = pd.MultiIndex.from_tuples([("R", "Activity", f"a{i}") for i in range(130)])
    columns = pd.MultiIndex.from_tuples([("R", "Activity", "a0"), ("R", "Commodity", "c0")])
    frames = {}
    for stem in dl.REQUIRED:
        if stem == "units":
            frames[stem] = pd.DataFrame({"unit": ["None", "kg"]},
                                       index=pd.MultiIndex.from_tuples([("Activity", "a0"), ("Commodity", "c0")]))
        else:
            rows = index if stem in ("z", "Y") else pd.Index([f"row{i}" for i in range(130)])
            frames[stem] = pd.DataFrame([[0.12345678901234567, -0.00000000000023]] * 130,
                                       index=rows, columns=columns)
    bodies = {stem + ".txt": frame.to_csv().encode() for stem, frame in frames.items()}
    catalog = {"record_id": dl.RECORD, "doi": f"10.5281/zenodo.{dl.RECORD}",
               "files": [entry(body, key) for key, body in bodies.items()]}
    monkeypatch.setattr(dl, "_catalog", lambda: copy.deepcopy(catalog))

    def request(req, **kwargs):
        key = req.full_url.split("/files/")[1].split("/")[0]
        return Response(bodies[key])

    monkeypatch.setattr(dl, "urlopen", request)
    return frames


def test_complete_download_converts_and_reuses_verified_cache(tmp_path, monkeypatch, tiny_source):
    path = dl.download_database(tmp_path / "source", progress=lambda _: None)
    assert not (path / ".zenodo-download.json").exists()
    receipt = json.loads((path / "zenodo-source.json").read_text())
    assert receipt["record_id"] == dl.RECORD
    for stem, expected in tiny_source.items():
        actual = pd.read_parquet(path / f"{stem}.parquet")
        pd.testing.assert_frame_equal(actual, expected)
    monkeypatch.setattr(dl, "urlopen", no_network)
    assert dl.download_database(path, progress=lambda _: None) == path
    cfg = {"base_db": {"_path": tmp_path / "absent"}}
    resolved = dl.source_config(cfg, download=False, directory=path, progress=lambda _: None)
    assert resolved["base_db"]["_path"] == path
    assert cfg["base_db"]["_path"] == tmp_path / "absent"
    (path / "e.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        dl.download_database(path)


def test_unmanaged_parquets_are_never_overwritten(tmp_path, monkeypatch):
    (tmp_path / "z.parquet").write_bytes(b"my database")
    monkeypatch.setattr(dl, "urlopen", no_network)
    with pytest.raises(ValueError, match="unmanaged parquet"):
        dl.download_database(tmp_path)
    assert (tmp_path / "z.parquet").read_bytes() == b"my database"


def test_offline_missing_source_fails_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "urlopen", no_network)
    with pytest.raises(FileNotFoundError, match="pv-hlca download"):
        dl.source_config({"base_db": {"_path": tmp_path / "missing"}}, download=False)


def test_offline_incomplete_cache_never_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "urlopen", no_network)
    # An unexpected directory at the receipt path is not a complete cache.
    (tmp_path / "zenodo-source.json").mkdir()
    with pytest.raises(FileNotFoundError, match="offline mode"):
        dl.source_config({"base_db": {"_path": tmp_path / "missing"}},
                         download=False, directory=tmp_path)


def test_local_source_bypasses_download_but_lfs_pointer_does_not(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "urlopen", no_network)
    for stem in dl.REQUIRED:
        (tmp_path / f"{stem}.parquet").write_bytes(b"local data")
    cfg = {"base_db": {"_path": tmp_path}}
    assert dl.source_config(cfg, download=False) is cfg
    (tmp_path / "z.parquet").write_bytes(b"version https://git-lfs.github.com/spec/v1\n")
    with pytest.raises(FileNotFoundError):
        dl.source_config(cfg, download=False)


def test_build_downloads_only_when_preparation_is_needed(tmp_path, monkeypatch):
    class Model(PVModel):
        def __init__(self, db, cfg, parameters, provenance):
            self.cfg = cfg

    calls = []
    cfg = {"base_db": {"_path": tmp_path / "missing"}}

    def source(config, **kwargs):
        calls.append(kwargs)
        return {"downloaded": True}

    monkeypatch.setattr(dl, "source_config", source)
    monkeypatch.setattr("pv_hlca.model.prepared.prepare", lambda c, p: (None, {}))
    monkeypatch.setattr("pv_hlca.model.pipeline.apply_parameters", lambda *a: None)
    assert Model.build(cfg=cfg, prepared_path=tmp_path).cfg == {"downloaded": True}
    assert len(calls) == 1
    (tmp_path / "manifest.json").write_text("{}")
    assert Model.build(cfg=cfg, prepared_path=tmp_path, download=False).cfg == cfg
    assert len(calls) == 1


def test_cli_exposes_standalone_download(tmp_path, monkeypatch):
    from pv_hlca import cli
    calls = []
    monkeypatch.setattr(cli, "download_database", lambda output: calls.append(output))
    assert cli.main(["download", "--output", str(tmp_path)]) == 0
    assert calls == [tmp_path]


def test_cli_explicit_missing_base_db_does_not_download(tmp_path, monkeypatch, capsys):
    from pv_hlca import cli
    monkeypatch.setattr(dl, "urlopen", no_network)
    assert cli.main(["prepare", "--base-db", str(tmp_path / "missing"),
                     "--prepared", str(tmp_path / "prepared")]) == 2
    assert "offline mode" in capsys.readouterr().err
