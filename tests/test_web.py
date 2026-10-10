from datetime import timedelta

from fastapi.testclient import TestClient

from groundstation.web.app import create_app


def test_pages_scheduling_cancellation_and_restart(config):
    app = create_app(config)
    with TestClient(app) as client:
        for path in ["/", "/passes", "/hardware", "/gallery"]:
            response = client.get(path)
            assert response.status_code == 200
            assert "MOCK MODE" in response.text
        item = app.state.runtime.passes[-1]
        data = {"csrf": app.state.csrf}
        assert client.post(f"/passes/{item.id}/schedule", data=data).status_code == 200
        assert client.get("/api/status").json()["selected"] == [item.id]
        assert "conflicts" in client.post(f"/passes/{item.id}/schedule", data=data).text
        client.post(f"/passes/{item.id}/cancel", data=data)
        assert client.get("/api/status").json()["selected"] == []
        client.post(f"/passes/{item.id}/schedule", data=data)
        assert client.post("/hardware/park").status_code == 403
        for action in ["rotor", "position", "jog", "park", "sdr", "satdump", "tle"]:
            assert client.post(f"/hardware/{action}", data=data).status_code == 200
    with TestClient(create_app(config)) as restarted:
        assert restarted.get("/api/status").json()["selected"] == []


def test_web_mock_reception_and_filesystem_gallery(config, quick_pass):
    app = create_app(config)
    with TestClient(app) as client:
        app.state.runtime.scheduler.schedule(quick_pass)
        app.state.runtime.scheduler.tick(quick_pass.aos - timedelta(seconds=1))
        assert client.get("/api/status").json()["state"] == "COMPLETE"
        response = client.get("/gallery")
        assert "SIMULATED" in response.text
        assert not list(config.work_dir.glob("obs-*"))
    with TestClient(create_app(config)) as restarted:
        assert "SIMULATED" in restarted.get("/gallery").text


def test_hardware_unavailable_returns_useful_page(config):
    config.mock = False
    app = create_app(config)
    # Avoid internet; startup must still work without TLE or hardware.
    import httpx

    app.state.runtime.tle.fetch = lambda _: (_ for _ in ()).throw(httpx.ConnectError("offline"))
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        response = client.post("/hardware/rotor", data={"csrf": app.state.csrf})
        assert response.status_code == 200
        assert "rotor.host" in response.text


def test_lifespan_releases_singleton_across_threads(config):
    from concurrent.futures import ThreadPoolExecutor

    from groundstation.services.runtime import Runtime

    runtime = Runtime(config)
    # Separate pools force startup/shutdown onto distinct threads, as ASGI may do.
    with (
        ThreadPoolExecutor(max_workers=1) as startup,
        ThreadPoolExecutor(max_workers=1) as shutdown,
    ):
        startup.submit(runtime.start).result()
        shutdown.submit(runtime.close).result()
    with runtime.instance_lock:
        assert runtime.instance_lock.is_locked


def test_select_tracking_only_and_display_mode(config):
    app = create_app(config)
    with TestClient(app) as client:
        item = app.state.runtime.passes[-1]
        data = {"csrf": app.state.csrf}
        assert "Track only" in client.get("/passes").text
        response = client.post(f"/passes/{item.id}/schedule?mode=track", data=data)
        assert "Tracking only selected (no recording)" in response.text
        assert client.get("/api/status").json()["selected_modes"] == {item.id: "track"}
        assert "Track only" in client.get("/").text
        client.post(f"/passes/{item.id}/cancel", data=data)
        assert not client.get("/api/status").json()["selected_modes"]
        assert client.post(f"/passes/{item.id}/schedule?mode=typo", data=data).status_code == 422


def test_web_tracking_completes_without_receiver_or_gallery_files(config, quick_pass):
    from unittest.mock import Mock

    app = create_app(config)
    with TestClient(app) as client:
        runtime = app.state.runtime
        runtime.observation.receiver_factory = Mock(side_effect=AssertionError("No SDR"))
        runtime.observation.decoder = Mock()
        runtime.passes = [quick_pass]
        client.post(f"/passes/{quick_pass.id}/schedule?mode=track", data={"csrf": app.state.csrf})
        runtime.scheduler.tick(quick_pass.aos - timedelta(seconds=1))
        assert client.get("/api/status").json()["state"] == "COMPLETE"
        runtime.observation.receiver_factory.assert_not_called()
        runtime.observation.decoder.process.assert_not_called()
        assert not list(config.work_dir.iterdir())
        assert not list(config.gallery_dir.iterdir())
