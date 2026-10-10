import secrets
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlencode
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from groundstation.config import load_config
from groundstation.services.gallery import scan_gallery
from groundstation.services.runtime import Runtime


def create_app(config=None):
    config = config or load_config()
    runtime = Runtime(config)

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(runtime.start)
        try:
            yield
        finally:
            await run_in_threadpool(runtime.close)

    app = FastAPI(title="MetOp Ground Station", lifespan=lifespan)
    app.state.runtime = runtime
    app.state.csrf = secrets.token_urlsafe(32)
    directory = Path(__file__).parent
    templates = Jinja2Templates(directory=directory / "templates")

    def localtime(value):
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.astimezone(ZoneInfo(config.station.timezone)).strftime("%Y-%m-%d %H:%M:%S %Z")

    templates.env.filters["localtime"] = localtime
    app.mount("/static", StaticFiles(directory=directory / "static"), name="static")
    app.mount("/images", StaticFiles(directory=config.gallery_dir), name="images")

    @app.middleware("http")
    async def mutation_guard(request: Request, call_next):
        if request.method == "POST":
            # No accounts; a per-process form token prevents cross-site drive-by hardware actions.
            body = await request.body()
            if len(body) > 4096:
                return HTMLResponse("Form too large", status_code=413)
            fields = parse_qs(body.decode("utf-8", errors="replace"))
            supplied = fields.get("csrf", [""])[0]
            if not secrets.compare_digest(supplied, app.state.csrf):
                return HTMLResponse("Invalid form token; reload the page", status_code=403)
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    def render(request, page):
        status = runtime.scheduler.snapshot()
        images = scan_gallery(config.gallery_dir)
        selected_ids = {p.id for p in status["selected"]}
        if status["active"]:
            selected_ids.add(status["active"].id)
        # Keep selected snapshots visible when prediction refresh changes TLE/pass times.
        passes = {p.id: p for p in runtime.passes}
        passes.update({p.id: p for p in status["selected"]})
        if status["active"]:
            passes[status["active"].id] = status["active"]
        return templates.TemplateResponse(
            request=request,
            name=f"{page}.html",
            context=dict(
                page=page,
                config=config,
                status=status,
                images=images,
                csrf=app.state.csrf,
                passes=sorted(passes.values(), key=lambda p: p.aos),
                selected_ids=selected_ids,
                tle_age=runtime.tle.age_hours(),
                tle_warning=runtime.tle.warning,
                prediction_error=runtime.prediction_error,
                hardware=runtime.diagnostics.status,
                free_gb=shutil.disk_usage(config.work_dir).free / 1e9,
                message=request.query_params.get("message"),
                error=request.query_params.get("error"),
            ),
        )

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        return render(request, "dashboard")

    @app.get("/passes", response_class=HTMLResponse)
    def passes(request: Request):
        return render(request, "passes")

    @app.get("/gallery", response_class=HTMLResponse)
    def gallery(request: Request):
        return render(request, "gallery")

    @app.get("/hardware", response_class=HTMLResponse)
    def hardware(request: Request):
        return render(request, "hardware")

    def redirect(path, action):
        try:
            message = action() or "Done"
            return RedirectResponse(
                path + "?" + urlencode({"message": str(message)}), status_code=303
            )
        except Exception as exc:
            return RedirectResponse(path + "?" + urlencode({"error": str(exc)}), status_code=303)

    @app.post("/passes/{identifier}/schedule")
    def schedule(identifier: str, mode: Literal["record", "track"] = "record"):
        def action():
            selected = next((p for p in runtime.passes if p.id == identifier), None)
            if selected is None:
                raise ValueError("Pass has changed; refresh the list")
            if not config.mock and (not config.rotor.host or not config.rotor.limits_confirmed):
                raise ValueError(
                    "Configure verified rotor.host and confirm mechanical limits first"
                )
            runtime.scheduler.schedule(selected, mode=mode)
            return (
                "Tracking only selected (no recording)"
                if mode == "track"
                else "Pass selected in memory"
            )

        return redirect("/passes", action)

    @app.post("/passes/{identifier}/cancel")
    def cancel(identifier: str):
        return redirect("/passes", lambda: runtime.scheduler.cancel(identifier))

    @app.post("/hardware/{action}")
    def hardware_action(action: str):
        if action not in {
            "rotor",
            "position",
            "park",
            "stop",
            "jog",
            "sdr",
            "record",
            "satdump",
            "tle",
            "resume",
        }:
            raise HTTPException(404)

        def perform():
            if action == "tle":
                runtime.refresh(force=True)
                if runtime.tle.warning or runtime.prediction_error:
                    raise RuntimeError(runtime.tle.warning or runtime.prediction_error)
                return "TLE/pass refresh complete (requests are rate limited)"
            if action == "resume":
                with runtime.lock.hold("resume"):
                    runtime.scheduler.resume()
                    runtime.diagnostics.halted = False
                    runtime.diagnostics.cancel.clear()
                return "Scheduling resumed"
            if action == "stop":
                # Latch first so a new observation cannot win a race with STOP.
                runtime.scheduler.halt()
                if runtime.scheduler.snapshot()["active"]:
                    runtime.scheduler.stop()
                    return "STOP sent; active pass cancelled and selections cleared"
                if runtime.lock.owner and runtime.lock.owner.startswith("diagnostic"):
                    runtime.diagnostics.emergency_stop()
                    return "STOP sent; diagnostic cancelled and selections cleared"
                # Do not interrupt another process's G/T operation then allow it to resume motion.
                with runtime.lock.hold("STOP"):
                    runtime.scheduler.stop()
                    return "STOP sent; selections cleared"
            if runtime.scheduler.snapshot()["halted"] and action in {"park", "jog", "record"}:
                raise ValueError(
                    "Station stopped; resume before running movement or recording tests"
                )
            return runtime.diagnostics.run(action)

        return redirect("/hardware", perform)

    @app.get("/api/status")
    def status():
        snapshot = runtime.scheduler.snapshot()
        return dict(
            state=snapshot["state"],
            error=snapshot["error"],
            selected=[p.id for p in snapshot["selected"]],
            active=snapshot["active"].id if snapshot["active"] else None,
            active_mode=snapshot["active"].mode if snapshot["active"] else None,
            selected_modes={p.id: p.mode for p in snapshot["selected"]},
            simulated=config.mock,
        )

    return app
