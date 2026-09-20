from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI(title="LuckyDraw Web")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/create", response_class=HTMLResponse)
async def create_page(uid: int = 0):
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{UID}}", str(uid))
    return HTMLResponse(content=html)


@app.get("/verify", response_class=HTMLResponse)
async def verify_page(block: int = 0, hash: str = "", lottery: int = 0):
    html = (STATIC_DIR / "verify.html").read_text(encoding="utf-8")
    html = html.replace("{{BLOCK_HEIGHT}}", str(block))
    html = html.replace("{{BLOCK_HASH}}", hash)
    html = html.replace("{{LOTTERY_ID}}", str(lottery))
    return HTMLResponse(content=html)


@app.post("/api/lottery")
async def create_lottery_api(request: Request):
    data = await request.json()
    # TODO: 存入数据库 + 调用 Bot 发送消息
    return JSONResponse({"ok": True, "message": "抽奖创建成功"})
