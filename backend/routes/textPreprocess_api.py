from flask import Blueprint, jsonify, request
from database import get_client
from datetime import datetime

textPreprocess_bp = Blueprint('textPreprocess', __name__)  # 创建 Blueprint


def get_data_from_db(page=1, page_size=12):
    """ 从数据库获取数据（服务端分页） """
    try:
        client = get_client()
        offset = (page - 1) * page_size

        # 1. 查询分页数据
        query_data = f'''
            SELECT id, title, content, date, stock_num 
            FROM cyydws.announce_data
            LIMIT {page_size} OFFSET {offset}
        '''
        result_data = client.query(query_data)

        # 2. 查询总数据量（用于前端分页器）
        query_total = 'SELECT COUNT(*) FROM cyydws.announce_data'
        result_total = client.query(query_total)
        total = result_total.result_rows[0][0] if result_total.result_rows else 0

        # 格式化数据
        data = [
            {
                "id": row[0],
                "title": row[1],
                "content": row[2],
                "date": row[3],
                "stock_num": row[4]
            }
            for row in result_data.result_rows
        ]

        return {
            "data": data,
            "total": total  # 返回总数据量
        }

    except Exception as e:
        print(f'Error fetching data from database: {e}')
        return {"data": [], "total": 0}

@textPreprocess_bp.route('/textPreprocess_api', methods=['POST'])
def fetch_data():
    try:
        # 获取请求参数
        params = request.get_json()
        page = int(params.get('page', 1))
        print("page", page)
        page_size = int(params.get('page_size', 12))

        # 直接获取分页后的项目数据
        result = get_data_from_db(page=page, page_size=page_size)
        print("result", result)

        # 构造响应
        response = {
            "data": result,  # 分页后的数据
            "total": len(result),  # 总记录数
            "page": page,
            "page_size": page_size,
            "status": 200
        }

        return response

    except Exception as e:
        print(f'Error processing request: {e}')
        return jsonify({
            'status': 500,
            "message": str(e)
        }), 500

@textPreprocess_bp.route('/textPreprocess_api/deleteAnnouncements', methods=['POST'])
def delete_selected_data():
    """
    根据公告ID数组删除指定数据
    请求参数格式：
    {
        "ids": ["id1", "id2"]
    }
    """
    try:
        # 1. 接收并验证请求数据
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "msg": "请求数据不能为空",
                "status": 400
            })

        ids = data.get('ids', [])

        if not ids or not isinstance(ids, list):
            return jsonify({
                "success": False,
                "msg": "ids 必须是非空数组",
                "status": 400
            })

        # 2. 获取数据库连接
        client = get_client()

        # 3. 执行批量删除（使用 ALTER TABLE ... DELETE 语法）
        deleted_count = 0
        for announcement_id in ids:
            try:
                # 使用 ClickHouse 推荐的 ALTER TABLE ... DELETE 语法
                delete_query = """
                ALTER TABLE cyydws.announce_data 
                DELETE WHERE id = %(id)s
                """
                # 使用 command() 执行删除操作
                result = client.command(delete_query, {
                    'id': announcement_id
                })
                deleted_count += 1
            except Exception as e:
                print(f"删除失败: id={announcement_id}, error={str(e)}")
                continue  # 继续尝试删除其他ID

        # 4. 返回响应
        if deleted_count > 0:
            return jsonify({
                "success": True,
                "status": 200,
                "msg": f"成功删除 {deleted_count} 条数据",
                "deleted_count": deleted_count
            })
        else:
            return jsonify({
                "success": False,
                "status": 404,
                "msg": "未找到匹配的数据或删除失败"
            })

    except Exception as e:
        print(f"删除数据异常: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "msg": f"删除失败: {str(e)}",
            "status": 500
        })

