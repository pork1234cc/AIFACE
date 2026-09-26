"""构建归档必须先验证所有源码与产物，禁止移动未知文件。"""

import runpy

import pytest
import yaml

from app.config import PROJECT_ROOT


def test_portable_includes_both_element_models():
    config = yaml.safe_load((PROJECT_ROOT / "project.yaml").read_text(encoding="utf-8"))
    resources = {source: target for source, target in config["build"]["extra_datas"]}
    for name in ["mobile_sam.encoder.onnx", "sam_vit_h_4b8939.decoder.onnx"]:
        source = f"storage/models/mobile-sam/{name}"
        assert resources.get(source) == "storage/models/mobile-sam"
        assert (PROJECT_ROOT / source).is_file()


@pytest.fixture
def build_case(tmp_path, monkeypatch):
    module = runpy.run_path(str(PROJECT_ROOT / "scripts/portable-build.py"))
    archive = module["archive_intermediates"]
    namespace = archive.__globals__
    root = tmp_path
    work = root / ".commenlib-build"
    work.mkdir()
    record_dir = root / "records"
    record_dir.mkdir()
    source = root / "module.py"
    source.write_text("value = 1\n", encoding="utf-8")
    artifact = root / "module.cp312-win_amd64.pyd"
    artifact.write_bytes(b"compiled")
    exe = root / "dist/AIFACE/AIFACE.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"executable")
    record = {
        "record_dir": str(record_dir),
        "dist_dir": str(root / "dist"),
        "sources": {source.name: module["digest"](source)},
        "artifacts": {artifact.name: module["digest"](artifact)},
        "exe_sha256": module["digest"](exe),
    }
    monkeypatch.setitem(namespace, "ROOT", root)
    monkeypatch.setitem(namespace, "WORK", work)
    monkeypatch.setitem(namespace, "load", lambda: record)
    return archive, root, source, artifact


def test_changed_source_prevents_archive(build_case):
    archive, root, source, artifact = build_case
    source.write_text("changed = True\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="源码发生变化"):
        archive()
    assert artifact.is_file()
    assert (root / ".commenlib-build").is_dir()


def test_changed_artifact_prevents_archive(build_case):
    archive, root, _, artifact = build_case
    artifact.write_bytes(b"unexpected")
    with pytest.raises(RuntimeError, match="哈希不匹配"):
        archive()
    assert artifact.is_file()
    assert (root / ".commenlib-build").is_dir()


def test_verified_artifacts_are_archived_and_unknown_files_preserved(build_case):
    archive, root, source, artifact = build_case
    unknown = root / "unrelated.pyd"
    unknown.write_bytes(b"not-this-build")
    archive()
    assert source.read_text(encoding="utf-8") == "value = 1\n"
    assert unknown.read_bytes() == b"not-this-build"
    assert not artifact.exists()
    assert (root / "records/compiled-modules" / artifact.name).is_file()
    assert (root / "records/intermediates").is_dir()


def test_namespace_module_keeps_full_import_path():
    module = runpy.run_path(str(PROJECT_ROOT / "scripts/portable-build.py"))
    assert module["module_name"]("backend/app/services/licensing.py") == "app.services.licensing"
    assert (
        module["module_name"]("commenlib/license_guard/license_client.py")
        == "commenlib.license_guard.license_client"
    )


def test_package_refuses_changed_compiled_module(build_case):
    archive, _, _, artifact = build_case
    namespace = archive.__globals__
    namespace["load"]()["status"] = "compiled"
    artifact.write_bytes(b"stale binary")
    with pytest.raises(RuntimeError, match="产物来源或哈希不匹配"):
        namespace["package"]()
