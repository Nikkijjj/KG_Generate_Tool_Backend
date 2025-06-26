import json
import re
import traceback
from datetime import datetime
from flask import Blueprint, jsonify, request
from database import get_client  # 确保这是MySQL连接

extractSample_bp = Blueprint('extractSample', __name__)


def get_data_from_db(project_id=None):
    """从数据库获取项目数据"""
    try:
        client = get_client()
        cursor = client.cursor()

        query = """
        SELECT 
            title,
            text AS content,
            summary,
            publish_time,
            user AS operator,
            event_type,
            project_id,
            create_time AS insert_time
        FROM cyydws.project_data
        WHERE project_id = %s
        ORDER BY create_time DESC
        """
        cursor.execute(query, (project_id,))
        data_list = cursor.fetchall()

        return {
            "status": 200,
            "project_id": project_id,
            "data": data_list,
            "count": len(data_list)
        }

    except Exception as e:
        print(f'Database error: {str(e)}')
        traceback.print_exc()
        return {
            "status": 500,
            "error": str(e),
            "message": "获取数据失败"
        }
    finally:
        cursor.close()


@extractSample_bp.route('/extractSample/getAllTextData', methods=['POST'])
def fetch_data():
    try:
        params = request.get_json()
        project_id = params.get('project_id')
        page = params.get('page', 1)
        page_size = params.get('page_size', 10)

        if not project_id:
            return jsonify({"status": 400, "message": "project_id是必填字段"})

        client = get_client()
        cursor = client.cursor()
        offset = (page - 1) * page_size

        # 查询总条数
        count_query = "SELECT count(*) as total FROM cyydws.project_data WHERE project_id = %s"
        cursor.execute(count_query, (project_id,))
        total = cursor.fetchone()['total']

        # 查询分页数据
        data_query = """
        SELECT 
            title,
            text AS content,
            summary,
            publish_time,
            create_time
        FROM cyydws.project_data
        WHERE project_id = %s
        ORDER BY create_time DESC
        LIMIT %s OFFSET %s
        """
        cursor.execute(data_query, (project_id, page_size, offset))
        result = cursor.fetchall()

        formatted_data = []
        for idx, row in enumerate(result, start=1):
            formatted_data.append({
                "index": idx + offset,
                "title": row["title"] or "",
                "content": row["content"] or "",
                "publishTime": str(row["publish_time"]) if row["publish_time"] else "",
                "summary": row["summary"] or ""
            })

        return jsonify({
            "status": 200,
            "data": formatted_data,
            "count": total,
            "project_id": project_id,
            "page": page,
            "page_size": page_size
        })

    except Exception as e:
        print(f"Error: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "status": 500,
            "message": "服务器内部错误",
            "error": str(e)
        })
    finally:
        cursor.close()


@extractSample_bp.route('/extractSample/saveSelectData', methods=['POST'])
def save_selected_data():
    try:
        data = request.get_json()
        project_id = data.get('project_id')
        announcement_ids = data.get('announcement_ids', [])

        if not project_id:
            return jsonify({"msg": "project_id 不能为空", "status": 400})
        if not announcement_ids or not isinstance(announcement_ids, list):
            return jsonify({"msg": "announcement_ids 必须是非空数组", "status": 400})

        client = get_client()
        cursor = client.cursor()

        # 获取现有data_list
        project_query = "SELECT data_list FROM cyydws.graph_project WHERE id = %s"
        cursor.execute(project_query, (project_id,))
        project_result = cursor.fetchone()

        if not project_result:
            return jsonify({"msg": "项目不存在", "status": 404})

        current_id_list = []
        if project_result['data_list']:
            try:
                current_id_list = json.loads(project_result['data_list'])
                if not isinstance(current_id_list, list):
                    current_id_list = []
            except json.JSONDecodeError:
                current_id_list = []

        new_ids = [str(id) for id in announcement_ids if str(id) not in current_id_list]
        if not new_ids:
            return jsonify({
                "status": 200,
                "msg": "所有数据已存在，未添加新数据",
                "added_count": 0
            })

        updated_id_list = current_id_list + new_ids

        update_query = "UPDATE cyydws.graph_project SET data_list = %s WHERE id = %s"
        cursor.execute(update_query, (json.dumps(updated_id_list, ensure_ascii=False), project_id))
        client.commit()

        return jsonify({
            "status": 200,
            "msg": f"成功添加 {len(new_ids)} 条数据",
            "added_count": len(new_ids),
            "total_count": len(updated_id_list)
        })

    except Exception as e:
        client.rollback()
        print(f"保存数据异常: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "msg": f"保存失败: {str(e)}",
            "status": 500
        })
    finally:
        cursor.close()


@extractSample_bp.route('/extractSample/getProjectAnnouncements', methods=['POST'])
def get_project_announcements():
    try:
        data = request.get_json()
        project_id = data.get('project_id')

        if not project_id:
            return jsonify({"msg": "project_id 不能为空", "status": 400})

        client = get_client()
        cursor = client.cursor()

        # 获取项目中的公告ID列表
        project_query = "SELECT data_list FROM cyydws.graph_project WHERE id = %s"
        cursor.execute(project_query, (project_id,))
        project_result = cursor.fetchone()

        if not project_result:
            return jsonify({"msg": "项目不存在", "status": 404})

        id_list = []
        if project_result['data_list']:
            try:
                id_list = json.loads(project_result['data_list'])
                if not isinstance(id_list, list):
                    id_list = []
            except json.JSONDecodeError:
                id_list = []

        if not id_list:
            return jsonify({
                "status": 200,
                "data": [],
                "count": 0
            })

        # 构建IN查询参数
        placeholders = ','.join(['%s'] * len(id_list))
        announcement_query = f"""
        SELECT id, title, content, date, stock_num 
        FROM cyydws.announce_data
        WHERE id IN ({placeholders})
        ORDER BY date DESC
        """
        cursor.execute(announcement_query, tuple(id_list))
        result = cursor.fetchall()

        formatted_data = []
        for row in result:
            formatted_data.append({
                "id": str(row['id']),
                "title": row['title'],
                "content": row['content'],
                "date": str(row['date']) if row['date'] else '',
                "stock_num": row['stock_num']
            })

        return jsonify({
            "status": 200,
            "data": formatted_data,
            "count": len(formatted_data)
        })

    except Exception as e:
        print(f"获取项目公告异常: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "msg": f"获取数据失败: {str(e)}",
            "status": 500
        })
    finally:
        cursor.close()


@extractSample_bp.route('/extractSample/deleteSelectedData', methods=['POST'])
def delete_selected_data():
    try:
        data = request.get_json()
        project_id = data.get('project_id')
        ids = data.get('ids', [])  # 前端传来的要删除的公告ID列表

        if not project_id:
            return jsonify({"msg": "project_id 不能为空", "status": 400})
        if not ids or not isinstance(ids, list):
            return jsonify({"msg": "ids 必须是非空数组", "status": 400})

        client = get_client()
        cursor = client.cursor()

        # 1. 获取项目当前的data_list
        project_query = "SELECT data_list FROM cyydws.graph_project WHERE id = %s"
        cursor.execute(project_query, (project_id,))
        project_result = cursor.fetchone()

        if not project_result:
            return jsonify({"msg": "项目不存在", "status": 404})

        # 2. 解析现有的data_list
        current_id_list = []
        if project_result['data_list']:
            try:
                current_id_list = json.loads(project_result['data_list'])
                if not isinstance(current_id_list, list):
                    current_id_list = []
            except json.JSONDecodeError:
                current_id_list = []

        # 3. 从current_id_list中移除要删除的ID
        original_count = len(current_id_list)
        # 使用列表推导式过滤掉要删除的ID
        updated_id_list = [id for id in current_id_list if id not in ids]
        deleted_count = original_count - len(updated_id_list)

        # 4. 如果没有实际删除任何ID，直接返回
        if deleted_count == 0:
            return jsonify({
                "status": 200,
                "msg": "未找到匹配的公告ID",
                "deleted_count": 0
            })

        # 5. 更新data_list字段
        update_query = "UPDATE cyydws.graph_project SET data_list = %s WHERE id = %s"
        cursor.execute(update_query, (json.dumps(updated_id_list, ensure_ascii=False), project_id))
        client.commit()

        return jsonify({
            "status": 200,
            "msg": f"成功删除 {deleted_count} 条数据",
            "deleted_count": deleted_count,
            "remaining_count": len(updated_id_list)
        })

    except Exception as e:
        client.rollback()
        print(f"删除数据异常: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "msg": f"删除失败: {str(e)}",
            "status": 500
        })
    finally:
        cursor.close()