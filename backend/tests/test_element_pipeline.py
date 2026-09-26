"""Codex 子进程边界、缓存及元素 API 的集成回归。"""

import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest
from test_assets import image_bytes
from test_elements import item
from test_orders_api import client as api_client
from test_orders_api import create, upload

from app.services import codex_elements, element_jobs
from app.services.elements import validate_analysis
from app.services.orders import BusinessError

client = api_client


@pytest.fixture
def fake_masks(monkeypatch):
    def segment(data, node, points=None):
        return {
            "mask_runs": [1, 3],
            "mask_area": 3,
            "mask_score": 0.9,
            "location_status": "located",
            "width": 8,
            "height": 6,
            "original_width": 8,
            "original_height": 6,
            "image_sha256": "unused",
        }

    monkeypatch.setattr(element_jobs.element_masks, "segment", segment)
    monkeypatch.setattr(element_jobs.element_masks, "sessions", lambda: ())


def test_instance_ids_change_on_reanalysis_but_cache_preserves_them(tmp_path, fake_masks):
    analysis = validate_analysis({"objects": [item("left"), item("right")]})
    first = element_jobs.build_result(b"picture", analysis)
    second = element_jobs.build_result(b"picture", analysis)
    assert first["regions"][0]["id"] != second["regions"][0]["id"]
    element_jobs.save_result(tmp_path, first)
    assert element_jobs.read_result(tmp_path, b"picture") == first
    assert element_jobs.read_result(tmp_path, b"other") is None
    assert "analysis" not in element_jobs.public_result({"result": first})["result"]


def test_children_are_grouped_under_their_parent(fake_masks):
    analysis = validate_analysis({"objects": [item("left"), item("right"), item("hair", "left")]})
    result = element_jobs.build_result(b"picture", analysis)
    assert [r["source_id"] for r in result["regions"]] == ["left", "hair", "right"]
    assert result["regions"][1]["depth"] == 1


def test_refinement_keeps_identity_and_rejects_stale_version(tmp_path, fake_masks):
    result = element_jobs.build_result(b"picture", validate_analysis({"objects": [item()]}))
    element_jobs.save_result(tmp_path, result)
    region_id, version = result["regions"][0]["id"], result["version"]
    revised = element_jobs.refine(tmp_path, b"picture", region_id, version, [[100, 100, 1]])
    assert revised["result"]["regions"][0]["id"] == region_id
    assert revised["result"]["version"] != version
    assert len(list(tmp_path.glob("result-*.json"))) == 2
    with pytest.raises(BusinessError) as exc:
        element_jobs.refine(tmp_path, b"picture", region_id, version, [[100, 100, 0]])
    assert exc.value.code == "element_version_changed"


def test_codex_uses_argument_array_and_validates_final_file(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_elements, "resolve_executable", lambda: "C:/手动 路径/codex.exe")
    monkeypatch.setenv("image_api", "secret-not-for-codex")

    def run(command, **kwargs):
        assert isinstance(command, list) and command[-1] == "-"
        assert command[0] == "C:/手动 路径/codex.exe"
        assert kwargs["encoding"] == "utf-8" and "shell" not in kwargs
        assert "image_api" not in kwargs["env"]
        assert command[command.index("--sandbox") + 1] == "read-only"
        (tmp_path / "analysis.json").write_text(json.dumps({"objects": [item()]}), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(codex_elements.subprocess, "run", run)
    assert len(codex_elements.analyze(image_bytes(), tmp_path).objects) == 1


@pytest.mark.parametrize(
    "failure,code",
    [("timeout", "codex_timeout"), ("exit", "codex_failed"), ("invalid", "codex_invalid_output")],
)
def test_codex_failures_do_not_return_raw_process_output(tmp_path, monkeypatch, failure, code):
    monkeypatch.setattr(codex_elements, "resolve_executable", lambda: "codex.exe")

    def run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("codex", 360)
        if failure == "invalid":
            (tmp_path / "analysis.json").write_text("not JSON", encoding="utf-8")
        return SimpleNamespace(returncode=1 if failure == "exit" else 0)

    monkeypatch.setattr(codex_elements.subprocess, "run", run)
    with pytest.raises(BusinessError) as exc:
        codex_elements.analyze(image_bytes(), tmp_path)
    assert exc.value.code == code


def test_element_api_ownership_import_digest_and_refresh(client, monkeypatch, fake_masks):
    order_id, other = create(client), create(client)
    main = upload(client, order_id, "main").json()["id"]
    foreign = upload(client, other, "main").json()["id"]
    client.patch(f"/api/orders/{order_id}/params", json={"base_asset_id": main})
    root = f"/api/orders/{order_id}/images"
    assert client.get(f"{root}/{foreign}/elements").status_code == 404
    assert client.post(f"{root}/{foreign}/elements").status_code == 404
    url = f"{root}/{main}/elements"
    assert client.get(url).json()["status"] == "idle"

    # 同步执行线程入口用于确定性 API 验证，不实际启动 CLI。
    class ImmediateThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(element_jobs, "Thread", ImmediateThread)
    payload = {"image_sha256": "0" * 64, "analysis": {"objects": [item()]}}
    assert client.post(url + "/import", json=payload).status_code == 409
    content = client.get(f"/api/images/{main}/content").content
    payload["image_sha256"] = hashlib.sha256(content).hexdigest()
    imported = client.post(url + "/import", json=payload)
    assert imported.status_code == 202, imported.text
    response = client.get(url).json()
    assert response["status"] == "ready" and len(response["result"]["regions"]) == 1
    assert "analysis" not in response["result"]
    assert client.get(f"/api/orders/{order_id}/batches").json()["items"] == []
    correction = {
        "version": response["result"]["version"],
        "points": [{"x": 2, "y": 3, "label": 1}],
    }
    region_id = response["result"]["regions"][0]["id"]
    assert client.post(f"{url}/{region_id}/refine", json=correction).status_code == 200
    assert client.post(f"{url}/{region_id}/refine", json=correction).status_code == 409
