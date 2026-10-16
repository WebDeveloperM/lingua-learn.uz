import mimetypes
import os
import re

from django.http import FileResponse, HttpResponse, StreamingHttpResponse

RANGE_RE = re.compile(r'^bytes=(\d*)-(\d*)$')
CHUNK_SIZE = 64 * 1024


def _read_range(path, start, length):
    with open(path, 'rb') as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def file_response_with_range(request, path):
    """Serve a file honouring a single-range `Range` header, so browsers can seek inside audio."""
    size = os.path.getsize(path)
    content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    match = RANGE_RE.match(request.headers.get('Range', '').strip())

    if not match or match.groups() == ('', ''):
        response = FileResponse(open(path, 'rb'), content_type=content_type)
        response['Accept-Ranges'] = 'bytes'
        return response

    first, last = match.groups()
    if first == '':
        suffix_length = int(last)
        start, end = max(size - suffix_length, 0), size - 1
        if suffix_length == 0:
            start = size
    else:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1

    if start >= size or start > end:
        response = HttpResponse(status=416)
        response['Content-Range'] = f'bytes */{size}'
        return response

    length = end - start + 1
    response = StreamingHttpResponse(_read_range(path, start, length), status=206, content_type=content_type)
    response['Content-Length'] = str(length)
    response['Content-Range'] = f'bytes {start}-{end}/{size}'
    response['Accept-Ranges'] = 'bytes'
    return response
