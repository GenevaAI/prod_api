# downloads.py
import os
from io import BytesIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from dotenv import load_dotenv

router = APIRouter(tags=["Public Downloads"])

load_dotenv()

# R2 / S3 client
s3_client = boto3.client(
    "s3",
    endpoint_url=os.getenv("R2_ENDPOINT"),
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    config=Config(signature_version="s3v4"),
    region_name="auto",
)

BUCKET_NAME = os.getenv("R2_BUCKET")


def _stream_docx_from_r2(file_key: str, download_filename: str) -> StreamingResponse:
    """Download a .docx from R2 and return it as a StreamingResponse."""
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=file_key)
        file_content = response["Body"].read()

        return StreamingResponse(
            BytesIO(file_content),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{download_filename}"'
            },
        )
    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail="File not found in R2")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")


@router.get("/download/python-api-docx")
async def download_python_api_docx():
    return _stream_docx_from_r2(
        file_key="Python API.docx",
        download_filename="Python API.docx",
    )


@router.get("/download/python-api-weather-page-docx")
async def download_python_api_weather_page_docx():
    return _stream_docx_from_r2(
        file_key="Python API - Weather Page.docx",
        download_filename="Python API - Weather Page.docx",
    )


@router.get(
    "/download/kubernetes-a-detailed-guide-docx",
    response_class=HTMLResponse,
)


async def download_kubernetes_a_detailed_guide_docx():
    FILE_KEY = "Kubernetes - A Detailed Guide.docx"
    DOWNLOAD_FILENAME = "Kubernetes - A Detailed Guide.docx"

    try:
        presigned_url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": FILE_KEY,
                "ResponseContentDisposition": f'attachment; filename="{DOWNLOAD_FILENAME}"',
                "ResponseContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
            ExpiresIn=3600,
        )

        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Download – Kubernetes Guide</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f8fafc;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            color: #1e293b;
        }}
        .card {{
            background: white;
            padding: 2.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
            text-align: center;
            max-width: 420px;
            width: 90%;
        }}
        h1 {{
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
        }}
        p {{
            color: #64748b;
            margin-bottom: 2rem;
            line-height: 1.5;
        }}
        .download-btn {{
            display: inline-block;
            background: #2563eb;
            color: white;
            text-decoration: none;
            padding: 0.875rem 2rem;
            border-radius: 8px;
            font-weight: 600;
            font-size: 1.05rem;
            transition: background 0.2s;
        }}
        .download-btn:hover {{
            background: #1d4ed8;
        }}
        .note {{
            margin-top: 1.5rem;
            font-size: 0.875rem;
            color: #94a3b8;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Kubernetes – A Detailed Guide</h1>
        <p>Click the button below to download the document<br>(approximately 10 MB).</p>
        
        <a href="{presigned_url}" class="download-btn" download>
            Download Document
        </a>

        <p class="note">The download will start immediately after you click.</p>
    </div>
</body>
</html>
"""
        return HTMLResponse(content=html_content)

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="File not found in R2")
        raise HTTPException(status_code=500, detail=f"R2 error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating download page: {str(e)}")


@router.get(
    "/download/iam-technologies-and-tools-docx",
    response_class=HTMLResponse,
)


async def download_iam_technologies_and_tools_docx():
    FILE_KEY = "IAM Technologies and Tools.docx"
    DOWNLOAD_FILENAME = "IAM Technologies and Tools.docx"

    try:
        presigned_url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": FILE_KEY,
                "ResponseContentDisposition": f'attachment; filename="{DOWNLOAD_FILENAME}"',
                "ResponseContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
            ExpiresIn=3600,
        )

        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Download – Kubernetes Guide</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f8fafc;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            color: #1e293b;
        }}
        .card {{
            background: white;
            padding: 2.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
            text-align: center;
            max-width: 420px;
            width: 90%;
        }}
        h1 {{
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
        }}
        p {{
            color: #64748b;
            margin-bottom: 2rem;
            line-height: 1.5;
        }}
        .download-btn {{
            display: inline-block;
            background: #2563eb;
            color: white;
            text-decoration: none;
            padding: 0.875rem 2rem;
            border-radius: 8px;
            font-weight: 600;
            font-size: 1.05rem;
            transition: background 0.2s;
        }}
        .download-btn:hover {{
            background: #1d4ed8;
        }}
        .note {{
            margin-top: 1.5rem;
            font-size: 0.875rem;
            color: #94a3b8;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>IAM Technologies and Tools</h1>
        <p>Click the button below to download the document<br>(approximately 70 MB).</p>
        
        <a href="{presigned_url}" class="download-btn" download>
            Download Document
        </a>

        <p class="note">The download will start immediately after you click.</p>
    </div>
</body>
</html>
"""
        return HTMLResponse(content=html_content)

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="File not found in R2")
        raise HTTPException(status_code=500, detail=f"R2 error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating download page: {str(e)}")