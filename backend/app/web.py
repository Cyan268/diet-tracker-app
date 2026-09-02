from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.responses import FileResponse

WEB_ISOLATION_HEADERS = {
    "Cross-Origin-Embedder-Policy": "credentialless",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
}


def _file_response(path: Path, *, immutable: bool) -> FileResponse:
    cache_control = "public, max-age=31536000, immutable" if immutable else "no-store"
    return FileResponse(
        path,
        headers={
            **WEB_ISOLATION_HEADERS,
            "Cache-Control": cache_control,
        },
    )


def create_spa_router(web_dist_dir: Path, *, api_prefix: str) -> APIRouter:
    root = web_dist_dir.resolve(strict=True)
    index_path = (root / "index.html").resolve(strict=True)
    if not index_path.is_file():
        raise RuntimeError(f"web index is not a file: {index_path}")

    normalized_api_prefix = api_prefix.strip("/")
    router = APIRouter(include_in_schema=False)

    @router.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    async def serve_spa(full_path: str) -> FileResponse:
        if full_path == normalized_api_prefix or full_path.startswith(f"{normalized_api_prefix}/"):
            raise HTTPException(status_code=404, detail="not found")

        candidate = (root / full_path).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(status_code=404, detail="not found")
        if candidate.is_file():
            relative = candidate.relative_to(root)
            return _file_response(
                candidate,
                immutable=bool(relative.parts and relative.parts[0] == "assets"),
            )

        # Browser navigation such as /auth should load the SPA shell. A missing
        # file request must stay a 404 instead of receiving HTML as JS/WASM.
        if Path(full_path).suffix:
            raise HTTPException(status_code=404, detail="not found")
        return _file_response(index_path, immutable=False)

    return router
