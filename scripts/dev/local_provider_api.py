"""Explicit development entrypoint; never use this module on an online test site."""
import os
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from learn_api.app import create_app
from scripts.dev.local_provider_gateway import attach_local_controls


def factory():
    app = create_app()
    attach_local_controls(app, proxy_url='http://127.0.0.1:18091',
                          token=os.environ['LEARN_LOCAL_PROXY_TOKEN'])

    @app.get('/local-test/start', include_in_schema=False)
    def start(request: Request):
        if request.url.hostname != '127.0.0.1' or request.client.host != '127.0.0.1':
            raise HTTPException(status_code=403)
        response = RedirectResponse('http://127.0.0.1:5173/', status_code=303)
        response.set_cookie('le_ticket', 'local-roadmap-test', httponly=True,
                            samesite='strict', max_age=43200, path='/')
        response.headers['Cache-Control'] = 'no-store'
        return response

    return app
