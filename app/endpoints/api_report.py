from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from app.services.report_services import report_service

router = APIRouter()

@router.get("/api/v1/reports", tags=["Report"])
def get_report_list(user_uid: int = Query(...)):
    try:
        reports = report_service.get_report_list(user_uid)
        print(reports)
        return JSONResponse(content={"success": True, "data": reports})
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)

@router.get("/api/v1/reports/{master_uid}", tags=["Report"])
def get_report_details(master_uid: int):
    try:
        details = report_service.get_report_details(master_uid)
        return JSONResponse(content={"success": True, "data": details})
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)