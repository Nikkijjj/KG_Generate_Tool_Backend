from flask import Blueprint, jsonify
from database import get_client
from datetime import datetime

textPreprocess_bp = Blueprint('textPreprocess', __name__)  # 创建 Blueprint

def get_data_from_db():
    """ 从数据库获取数据 """
    try:
        client = get_client()  # 复用数据库连接
        query = 'SELECT id, title, text, summary, publish_time FROM cyydws.data_operation_table'
        result = client.query(query)

        # 格式化数据
        data = [
            {
                "index": row[0],  # id → index
                "title": row[1],
                "content": row[2],
                "summary": row[3],
                "publishTime": row[4].strftime('%Y-%m-%d') if isinstance(row[4], datetime) else row[4]
            }
            for row in result.result_rows
        ]
        return data
    except Exception as e:
        print(f'Error fetching data from database: {e}')
        return []

@textPreprocess_bp.route('/textPreprocess_api', methods=['GET'])
def fetch_data():
    """ API 端点：获取数据 """
    data = get_data_from_db()
    return jsonify(data)  # 返回 JSON 数据
