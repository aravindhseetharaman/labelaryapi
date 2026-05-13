from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from app.services import bin_parser, labelary, template_service, zpl_generator

router = APIRouter(prefix='/api/labels')


async def _resolve_bin_content(
    file: Optional[UploadFile],
    content: Optional[str],
) -> str:
    if file and file.filename:
        raw = await file.read()
        return raw.decode('utf-8')
    if content and content.strip():
        return content
    raise HTTPException(status_code=400, detail="No file received — provide a 'file' or 'content' field.")


# ── /convert ─────────────────────────────────────────────────────────────────

@router.post('/convert')
async def convert(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    content: Optional[str] = Form(default=None),
):
    content_type = request.headers.get('content-type', '')

    if 'text/plain' in content_type:
        body = await request.body()
        bin_content = body.decode('utf-8')
    else:
        bin_content = await _resolve_bin_content(file, content)

    labels = bin_parser.parse(bin_content)
    zpl_list = zpl_generator.generate_all(labels)
    detected = [template_service.detect_label_type(lbl) for lbl in labels]
    return JSONResponse({
        'labelCount': len(zpl_list),
        'zplLabels': zpl_list,
        'detectedTypes': detected,
        'message': f'{len(zpl_list)} label(s) converted successfully',
    })


# ── /preview ─────────────────────────────────────────────────────────────────

@router.post('/preview')
async def preview(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    content: Optional[str] = Form(default=None),
):
    return await _preview_at(request, file, content, index=0)


@router.post('/preview/{index}')
async def preview_by_index(
    index: int,
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    content: Optional[str] = Form(default=None),
):
    return await _preview_at(request, file, content, index=index)


# ── /templates ───────────────────────────────────────────────────────────────

@router.get('/templates')
async def list_templates():
    return JSONResponse({'templates': template_service.get_all_templates()})


# ── /validate ─────────────────────────────────────────────────────────────────

@router.post('/validate')
async def validate(
    request: Request,
    item_name: str = Form(...),
    item_price: str = Form(...),
    item_category: str = Form(...),
    item_description: str = Form(default=''),
    file: Optional[UploadFile] = File(default=None),
    content: Optional[str] = Form(default=None),
):
    content_type = request.headers.get('content-type', '')
    if 'text/plain' in content_type:
        body = await request.body()
        bin_content = body.decode('utf-8')
    else:
        bin_content = await _resolve_bin_content(file, content)

    labels = bin_parser.parse(bin_content)
    if not labels:
        raise HTTPException(status_code=400, detail='No labels found in input.')

    results = []
    for i, label in enumerate(labels):
        zpl = zpl_generator.generate(label)
        detected_type = template_service.detect_label_type(label)
        if detected_type == 'SYSTEM_LABEL':
            results.append({
                'label_index': i,
                'valid': True,
                'label_type': 'System Label',
                'template_used': 'SYSTEM_LABEL',
                'skipped': True,
                'reason': 'System label — not a product label, skipped from validation',
                'checks': {},
            })
            continue
        result = template_service.validate_label(
            zpl=zpl,
            item_name=item_name,
            item_price=item_price,
            item_description=item_description,
            item_category=item_category,
        )
        results.append({'label_index': i, **result})

    all_valid = all(r['valid'] for r in results)
    return JSONResponse({
        'overall_valid': all_valid,
        'label_count': len(results),
        'results': results,
    })


async def _preview_at(
    request: Request,
    file: Optional[UploadFile],
    content: Optional[str],
    index: int,
) -> Response:
    content_type = request.headers.get('content-type', '')

    if 'text/plain' in content_type:
        body = await request.body()
        bin_content = body.decode('utf-8')
    else:
        bin_content = await _resolve_bin_content(file, content)

    labels = bin_parser.parse(bin_content)

    if not labels:
        raise HTTPException(status_code=400, detail='No labels found in input.')
    if index >= len(labels):
        raise HTTPException(status_code=404, detail=f'Label index {index} out of range (0–{len(labels)-1}).')

    zpl = zpl_generator.generate(labels[index])
    png_bytes = labelary.render_to_png(zpl, 0)
    return Response(content=png_bytes, media_type='image/png')
