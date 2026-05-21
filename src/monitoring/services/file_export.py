from pathlib import Path

import aiohttp.web


def build_export_app(export_dir: Path) -> aiohttp.web.Application:
    app = aiohttp.web.Application()
    app.router.add_static(
        "/files",
        str(export_dir),
        follow_symlinks=False,
        show_index=False,
    )
    return app
