from flask import Blueprint, request, jsonify
from database import get_client  # 复用数据库连接
from datetime import datetime
from auth.auth import token_required  # 导入 token_required 装饰器

dashboard_bp = Blueprint('dashboard', __name__)  # 创建 Blueprint


def get_dashboard_data(user_name):
    """ 从数据库获取仪表盘统计数据 """
    try:
        client = get_client()  # 获取数据库连接

        # 公告总量
        total_query = "SELECT COUNT(*) FROM cyydws.database"
        total_announcements = client.query(total_query).result_rows[0][0]

        # 今日新增公告数（根据当前日期）
        today = datetime.now().strftime("%Y-%m-%d")
        new_query = f"SELECT COUNT(*) FROM cyydws.database WHERE publish_time::text LIKE '{today}%'"
        new_announcements = client.query(new_query).result_rows[0][0]

        # 事件抽取模板数
        template_query = "SELECT COUNT(*) FROM cyydws.DuEEfin_schema WHERE author = '系统推荐'"
        template_count = client.query(template_query).result_rows[0][0]

        # 模型数量
        model_query = "SELECT COUNT(*) FROM cyydws.models_save WHERE user = 'admin'"
        model_count = client.query(model_query).result_rows[0][0]

        return {
            "user_name": user_name,
            "total_announcements": total_announcements,
            "new_announcements": new_announcements,
            "template_count": template_count,
            "model_count": model_count
        }

    except Exception as e:
        print(f"Error fetching dashboard data: {e}")
        return {
            "user_name": user_name,
            "total_announcements": 0,
            "new_announcements": 0,
            "template_count": 0,
            "model_count": 0
        }


@dashboard_bp.route('/dashboard_api', methods=['GET'])
@token_required  # 添加装饰器，验证 Token
def get_dashboard():
    """ 获取仪表盘数据的 API """
    # 使用当前用户的用户名
    user_name = request.username  # 从 JWT Token 中获取用户名
    data = get_dashboard_data(user_name)
    return jsonify(data)

