from flask import Blueprint, jsonify
from database import get_client  # 复用数据库连接

projectManage_bp = Blueprint('projectManage', __name__)  # 创建 Blueprint

def get_data_from_db():
    """ 从数据库获取项目数据，并将 EE_schema 替换为 schema_name """
    try:
        client = get_client()  # 获取数据库连接

        # 第一步：获取所有项目信息，包括 EE_schema (ID)
        project_query = '''
        SELECT 
            project_id, project_name, event_type, EE_schema, model_selection, project_status, creator
        FROM cyydws.project_descriptions
        '''
        project_result = client.query(project_query)

        # 提取所有 EE_schema ID 列表（去重）
        schema_ids = {row[3] for row in project_result.result_rows if row[3]}

        # 第二步：用 EE_schema ID 去 DuEEfin_schema 里查找对应的 schema_name
        schema_mapping = {}
        if schema_ids:
            # 查询所有包含在 schema_ids 中的 schema_name，确保 ID 用单引号包围
            schema_query = f'''
            SELECT id, schema_name 
            FROM cyydws.DuEEfin_schema 
            WHERE id IN ({','.join(f"'{schema_id}'" for schema_id in schema_ids)})
            '''
            schema_result = client.query(schema_query)
            # 创建一个 ID 到 schema_name 的映射
            schema_mapping = {row[0]: row[1] for row in schema_result.result_rows}

        # 第三步：构造返回数据，把 EE_schema ID 替换成对应的 schema_name
        projects = [
            {
                "project_id": row[0],
                "project_name": row[1],
                "event_type": row[2],
                "ee_schema": schema_mapping.get(row[3], ""),  # 用 EE_schema ID 查找对应的 schema_name
                "ee_model": row[4],
                "ee_progress": row[5],
                "use": ""  # 目前没有对应的字段，默认空字符串
            }
            for row in project_result.result_rows
        ]
        return projects

    except Exception as e:
        print(f'Error fetching data from database: {e}')
        return []


@projectManage_bp.route('/projectManage_api', methods=['GET'])
def get_projects():
    """ 获取项目列表的 API """
    projects = get_data_from_db()
    return jsonify({"projectList": projects})
