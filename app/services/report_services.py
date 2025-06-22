from app.dao.user_conversation_dao import UserConversationDAO

class ReportService:
    def __init__(self):
        self.dao = UserConversationDAO()

    def get_report_list(self, user_uid: int):
        # TODO: DAO에서 가져온 데이터를 리포트 형태로 가공하는 로직 추가 가능
        return self.dao.get_conversation_list_by_user_uid(user_uid)

    def get_report_details(self, master_uid: int):
        # TODO: 상세 대화 내용을 리포트 형태로 가공하는 로직 추가 가능
        return self.dao.get_conversation_details_by_master_uid(master_uid)

report_service = ReportService()
