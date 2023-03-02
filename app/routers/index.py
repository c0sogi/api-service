# from datetime import datetime
from inspect import currentframe as frame
from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.requests import Request

# from app.background_tasks import background_task_state
# from sqlalchemy.orm import Session
# from fastapi import Depends
# from app.database.connection import db
# from app.database.schema import Users

router = APIRouter(tags=["index"])


@router.get("/")
async def index():
    return FileResponse("./app/web/index.html")


@router.get("/{filename}.js")
async def js(filename: str):
    print("JS!!")
    return FileResponse(f"./app/web/{filename}.js")


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/contents/favicon.ico")


@router.get("/test")
async def test(req: Request):
    """
    ELB status check
    """
    try:
        ...
    except Exception as exception:
        req.state.inspect = frame()
        raise exception
    else:
        return {"user_status": req.state.user}
