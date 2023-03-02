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


@router.get("/favicon.ico")
async def favicon_ico():
    return FileResponse("app/contents/favicon.ico")


@router.get("/test")
async def test(request: Request):
    """
    ELB status check
    """
    try:
        ...
    except Exception as exception:
        request.state.inspect = frame()
        raise exception
    else:
        return {"user_status": request.state.user}
