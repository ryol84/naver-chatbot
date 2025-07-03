from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import openai
import os

app = FastAPI()

openai.api_key = os.getenv("OPENAI_API_KEY")

@app.post("/naver-callback")
async def naver_callback(request: Request):
    data = await request.json()
    message = data.get('content', '')

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": message}]
    )
    answer = response.choices[0].message.content.strip()

    return JSONResponse({
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": answer}}]
        }
    })
