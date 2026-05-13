import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers.labels import router as labels_router

logging.basicConfig(level=logging.INFO, format='%(levelname)s  %(name)s  %(message)s')

app = FastAPI(
    title='Shelf Label Converter',
    description='Parses .bin shelf label files, converts to ZPL, and previews via Labelary.',
    version='1.0.0',
)

app.include_router(labels_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={'error': str(exc)})


if __name__ == '__main__':
    uvicorn.run('app.main:app', host=settings.host, port=settings.port, reload=False)
