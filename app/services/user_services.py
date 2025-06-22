from app.dao.user_dao import UserDAO

class UserService:
    def __init__(self):
        self.user_dao = UserDAO()

    def get_user_by_id(self, user_id: str):
        return self.user_dao.get_user_by_id(user_id)

    def get_user_uid_by_user_id(self, user_id: str) -> int | None:
        user = self.get_user_by_id(user_id)
        if user:
            return user.get('uid')
        return None
    
    def register_user(self, user_id: str, user_name: str):
        return self.user_dao.register_user(user_id, user_name)

user_service = UserService()
