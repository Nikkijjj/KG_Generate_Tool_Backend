from flask import Blueprint, jsonify, request
from database import get_client  # 复用数据库连接
from datetime import datetime
import random

projectManage_bp = Blueprint('projectManage', __name__)  # 创建 Blueprint

def get_data_from_db(creator, page, pagesize):
    """ 从数据库获取项目数据，并将 EE_schema 替换为 schema_name """
    try:
        client = get_client()
        offset = (page - 1) * pagesize

        # 构建查询条件和参数
        if creator == "admin":
            count_query = 'SELECT count(*) FROM cyydws.graph_project'
            project_query = '''
                SELECT 
                    id, project_name, project_desc, project_status, stock_num, create_time, creator
                FROM cyydws.graph_project
                ORDER BY create_time DESC
                LIMIT %(limit)s OFFSET %(offset)s
            '''
            query_params = {"limit": pagesize, "offset": offset}
        else:
            count_query = '''
                SELECT count(*) FROM cyydws.graph_project
                WHERE creator = %(creator)s
            '''
            project_query = '''
                SELECT 
                    id, project_name, project_desc, project_status, stock_num, create_time, creator
                FROM cyydws.graph_project
                WHERE creator = %(creator)s
                ORDER BY create_time DESC
                LIMIT %(limit)s OFFSET %(offset)s
            '''
            query_params = {"creator": creator, "limit": pagesize, "offset": offset}

        # 查询总数
        total_result = client.query(count_query, {"creator": creator} if creator != "admin" else {})
        total = total_result.result_rows[0][0]

        # 查询项目
        project_result = client.query(project_query, query_params)

        projects = [
            {
                "id": row[0],
                "project_name": row[1],
                "project_desc": row[2],
                "project_status": row[3],
                "stock_num": row[4],
                "create_time": row[5],
                "creator": row[6]
            }
            for row in project_result.result_rows
        ]

        return {"projects": projects, "total": total}

    except Exception as e:
        print(f'Error fetching data from database: {e}')
        return {"projects": [], "total": 0}


def delete_data_from_db(project_id):
    try:
        client = get_client()
        delete_query = """
            ALTER TABLE cyydws.graph_project DELETE WHERE id = %(id)s
        """
        print(project_id)
        client.command(delete_query, {'id': project_id})

        return {"status": 200, "msg": "删除成功"}

    except Exception as e:
        print(f'Error deleting project: {e}')
        return {"status": 500, "msg": "删除项目失败，请稍后重试"}

def generate_project_id():
    """生成8位数字字符串"""
    return ''.join(random.choices('0123456789', k=8))

def add_data_from_db(project_name, project_desc, creator):
    try:
        client = get_client()

        id = generate_project_id()  # 生成随机项目 ID
        project_status = 0
        stock_num = []
        data_list = []
        create_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # 当前时间

        insert_query = f"""
            INSERT INTO cyydws.graph_project (
                id, project_name, project_desc,
                project_status, stock_num, data_list, create_time, creator
            ) VALUES (
                '{id}', '{project_name}', '{project_desc}',
                '{project_status}', '{stock_num}', '{data_list}', '{create_time}', '{creator}'
            )
        """
        client.query(insert_query)

        return {"status": 200, "msg": "新增项目成功", "project_id": id}

    except Exception as e:
        print(f'Error adding project: {e}')
        return {"status": 500, "msg": "新增项目失败，请稍后重试", "project_id": "0"}

@projectManage_bp.route('/getProjectList', methods=['POST'])
def get_projects():
    """ 获取项目列表的 API """
    data = request.get_json()
    creator = data.get("creator")
    page = int(data.get("page", 1))
    pagesize = int(data.get("page_size", 10))
    result = get_data_from_db(creator, page, pagesize)
    return jsonify({
        "projectList": result["projects"],
        "total": result["total"],
        "status": 200
    })


@projectManage_bp.route('/deleteProject', methods=['POST'])
def delete_project():
    """ 获取项目列表的 API """
    data = request.get_json()
    project_id = data.get("project_id")
    result = delete_data_from_db(project_id)
    return jsonify({
        "status": result["status"],
        "msg": result["msg"]
    })

@projectManage_bp.route('/addProject', methods=['POST'])
def add_project():
    """ 获取项目列表的 API """
    data = request.get_json()
    project_name = data.get("project_name")
    project_desc = data.get("project_desc")
    creator = data.get("creator")
    result = add_data_from_db(project_name, project_desc, creator)
    return jsonify({
        "status": result["status"],
        "msg": result["msg"],
        "project_id": result["project_id"]
    })
