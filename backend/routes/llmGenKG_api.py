import hashlib
import json
import re
import time
import traceback
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file, Response
from database import get_client  # MySQL connection
import pandas as pd
from sqlalchemy import create_engine, text
from tqdm import tqdm
from pyvis.network import Network
import networkx as nx
import openai
from typing import Dict
import os
from neo4j import GraphDatabase

llmGenKG_bp = Blueprint('llmGenKG', __name__)

# 配置部分
MYSQL_CONFIG = {
    'host': '172.18.18.5',
    'port': 3306,
    'user': 'jhy',
    'password': '123456',
    'database': 'cyydws',
    'charset': 'utf8mb4'
}

# Neo4j 配置
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "20040725"


class Neo4jConnection:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def execute_query(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters)
            return list(result)


# DeepSeek API配置
DEEPSEEK_API_KEY = "sk-c886ee978dec45bfa1f184d64cddbc78"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


# 初始化SQLAlchemy引擎
def get_sqlalchemy_engine():
    connection_str = f"mysql+pymysql://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}?charset={MYSQL_CONFIG['charset']}"
    return create_engine(connection_str)


# 清理公告文本
def clean_text(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_nodes_with_llm(combined_text: str, project_id: str) -> Dict:
    """使用DeepSeek API从合并的公告文本中提取节点"""
    from openai import OpenAI

    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL
    )

    print("\n====== 开始处理公告 ======")
    print(f"合并公告内容前100字符: {combined_text[:100]}...")

    try:
        system_prompt = """你是一个专业的金融信息抽取系统，专门处理上市公司公告。请严格按以下要求操作：

        1. 从文本中提取两类节点：
           - 事件节点(type=1): 表示发生的事件或动作，通常是动词或动名词短语
           - 实体节点(type=0): 表示参与事件的实体，通常是名词或名词短语

        2.抽取出的节点不能是笼统的词语（比如“公司”、“公告”这种简单笼统的词是不行的，没有指导意义），需要具体一些，比如说公司要写完整公司名称。

        2. 节点类型判断规则：
           - 如果一个词或短语表示的是具体的动作或变化，标记为事件节点(type=1)
           - 如果一个词或短语表示的是参与事件的实体、人员、组织或对象，标记为实体节点(type=0)

        3. 每个节点必须包含以下属性：
           - id: 唯一标识符(使用"类型_名称"的拼音首字母组合，如 "1_sg" 表示事件"收购")
           - type: 节点类型(1表示事件，0表示实体)
           - value: 触发词/论元值
           - key: 事件类型/论元角色
             对于事件节点，key表示事件类型(如"收购")
             对于实体节点，key表示实体角色(如"收购方")

        4. 请以规范的JSON格式返回结果
        """

        user_prompt = f"""
        请从以下合并的公告内容中提取节点，并以JSON格式返回结果：

        [公告内容] {combined_text[:15000]}

        要求返回的JSON格式如下：
        {{
            "nodes": [
                {{
                    "id": "节点ID",
                    "type": "节点类型(0或1)",
                    "value": "触发词/论元值",
                    "key": "事件类型/论元角色",
                    "properties": {{
                        "source": "LLM抽取",
                        "project_id": "项目ID",
                        "context": "相关上下文（必须有）"
                    }}
                }},
                ...
            ]
        }}

        注意事项：
        1. 确保正确区分事件节点和实体节点
        2. 为每个节点提供有意义的key值
        3. 对于重要节点，可以在properties中添加context字段提供上下文
        """

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2000
        )

        result_str = response.choices[0].message.content
        json_str = (
            result_str.split('```json')[1].split('```')[0] if '```json' in result_str
            else result_str.split('```')[1].split('```')[0] if '```' in result_str
            else result_str
        )

        result = json.loads(json_str)

        if "nodes" not in result:
            raise ValueError("返回结果缺少nodes字段")

        # 添加ID生成函数
        def generate_node_id(node_type, value, context):
            # 使用时间戳+上下文哈希+值哈希生成更唯一的ID
            timestamp = str(int(time.time() * 1000))[-6:]  # 取时间戳后6位
            context_hash = hashlib.md5(context.encode('utf-8')).hexdigest()[:6]
            value_hash = hashlib.md5(value.encode('utf-8')).hexdigest()[:6]
            return f"{node_type}_{timestamp}_{context_hash}_{value_hash}"

        for node in result["nodes"]:
            # 获取节点周围的上下文（示例）
            context = combined_text[
                      max(0, combined_text.find(node["value"]) - 50):combined_text.find(node["value"]) + 50]
            node["id"] = generate_node_id(node["type"], node["value"], context)
            node["properties"] = node.get("properties", {})
            node["properties"]["project_id"] = project_id
            node["properties"]["source"] = "LLM抽取"

        return result

    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}\n原始响应: {result_str[:500]}...")
        return {"nodes": []}
    except Exception as e:
        print(f"API调用异常: {type(e).__name__}: {str(e)}")
        return {"nodes": []}


def save_nodes_to_database(nodes: list, project_id: str):
    """将节点保存到数据库"""
    engine = get_sqlalchemy_engine()
    try:
        with engine.connect() as connection:
            # 关键步骤1：先删除该项目之前的节点
            delete_stmt = text("DELETE FROM node_table WHERE project_id = :project_id")
            connection.execute(delete_stmt, {"project_id": project_id})
            connection.commit()

            # 关键步骤2：插入新节点
            for node in nodes:
                insert_stmt = text("""
                    INSERT INTO node_table 
                    (id, type, value, `key`, project_id, properties) 
                    VALUES 
                    (:id, :type, :value, :key, :project_id, :properties)
                """)
                connection.execute(insert_stmt, {
                    "id": node["id"],
                    "type": node["type"],
                    "value": node["value"],
                    "key": node["key"],
                    "project_id": project_id,
                    "properties": json.dumps(node.get("properties", {})),
                })
            connection.commit()
        return True
    except Exception as e:
        print(f"保存节点到数据库失败: {str(e)}")
        traceback.print_exc()
        return False


@llmGenKG_bp.route('/extract_nodes_with_llm', methods=['POST'])
def extract_nodes_with_llm_api():
    try:
        data = request.get_json()
        project_id = data.get('project_id')
        announcement_ids = data.get('announcement_ids', [])

        if not project_id:
            return jsonify({
                'success': False,
                'message': '项目ID不能为空',
                'status': 400
            }), 400

        print(f"\n=== 开始节点抽取流程 ===")
        print(f"项目ID: {project_id}")
        print(f"待处理公告数量: {len(announcement_ids)}")

        # 获取公告数据
        print("\n[步骤1/3] 从数据库获取公告数据...")
        announcements_df = fetch_announcements_by_ids(announcement_ids)
        if announcements_df is None or announcements_df.empty:
            print("未找到公告数据")
            return jsonify({
                'success': False,
                'message': f'未找到项目 {project_id} 的公告数据',
                'status': 404
            }), 404

        total_announcements = len(announcements_df)
        processed_count = 0
        all_nodes = []
        print(f"成功获取 {total_announcements} 条公告数据")

        def update_progress(progress, message):
            """生成进度更新消息"""
            print(f"进度更新: {progress}% - {message}")
            return json.dumps({
                'progress': progress,
                'message': message,
                'status': 'processing'
            })

        # 流式响应
        def generate():
            nonlocal processed_count, all_nodes

            print("\n[步骤2/3] 开始处理公告内容...")
            # 处理每条公告
            for idx, row in announcements_df.iterrows():
                content = clean_text(row['content'])
                print(f"\n处理公告 {processed_count + 1}/{total_announcements}:")
                print(f"公告ID: {row['id']}")
                print(f"标题: {row['title']}")
                print(f"内容摘要: {content[:100]}...")

                # 使用LLM抽取节点
                print("调用DeepSeek API抽取节点...")
                extraction_result = extract_nodes_with_llm(content, project_id)
                nodes = extraction_result.get("nodes", [])
                print(f"抽取到 {len(nodes)} 个节点")

                if nodes:
                    print("抽取到的节点示例:")
                    for i, node in enumerate(nodes[:3]):  # 打印前3个节点作为示例
                        print(f"  {i + 1}. ID:{node['id']} 类型:{node['type']} 值:{node['value']} 键:{node['key']}")

                all_nodes.extend(nodes)

                # 更新进度
                processed_count += 1
                progress = int((processed_count / total_announcements) * 100)
                yield update_progress(progress, f"正在处理公告 {processed_count}/{total_announcements}") + "\n"

            print("\n[步骤3/3] 保存节点到数据库...")
            # 处理完成后保存节点
            if all_nodes:
                print(f"准备保存 {len(all_nodes)} 个节点到数据库")
                save_success = save_nodes_to_database(all_nodes, project_id)
                if not save_success:
                    print("保存节点到数据库失败")
                    yield json.dumps({
                        'progress': progress,
                        'message': '保存节点到数据库失败',
                        'status': 'processing'
                    }) + "\n"
                    return
                print("节点保存成功")

            # 最终结果
            print("\n=== 节点抽取完成 ===")
            print(f"总计抽取节点数: {len(all_nodes)}")
            print(f"事件节点数: {sum(1 for node in all_nodes if node['type'] == 1)}")
            print(f"实体节点数: {sum(1 for node in all_nodes if node['type'] == 0)}")

            yield json.dumps({
                'status': 'complete',
                'progress': 100,
                'message': '节点抽取完成',
                'data': {
                    'nodes': all_nodes,
                    'count': len(all_nodes),
                    'project_id': project_id
                }
            }) + "\n"

        return Response(
            generate(),
            mimetype='application/x-ndjson',
            headers={
                'Content-Type': 'application/x-ndjson',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive'
            }
        )  # 使用NDJSON格式

    except Exception as e:
        print(f"\nLLM节点抽取异常: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'LLM节点抽取失败: {str(e)}',
            'status': 500
        }), 500


def fetch_announcements_by_ids(announcement_ids):
    if not announcement_ids:
        return None

    engine = get_sqlalchemy_engine()
    try:
        query = text("""
            SELECT id, title, content, date, stock_num 
            FROM cyydws.announce_data
            WHERE id IN :ids
            ORDER BY date DESC
        """)

        with engine.connect() as connection:
            result = connection.execute(query, {'ids': tuple(announcement_ids)})
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            return df if not df.empty else None

    except Exception as e:
        print(f"获取公告数据异常: {str(e)}")
        traceback.print_exc()
        return None
    finally:
        engine.dispose()


@llmGenKG_bp.route('/get_nodes_by_project', methods=['GET'])
def get_nodes_by_project():
    """根据项目ID从数据库获取所有节点"""
    try:
        project_id = request.args.get('project_id')
        if not project_id:
            return jsonify({
                'success': False,
                'message': '项目ID不能为空',
                'status': 400
            }), 400

        engine = get_sqlalchemy_engine()
        with engine.connect() as connection:
            query = text("""
                SELECT id, type, value, `key`, properties 
                FROM node_table 
                WHERE project_id = :project_id
                ORDER BY type DESC, value ASC
            """)
            result = connection.execute(query, {"project_id": project_id})
            nodes = []
            for row in result:
                nodes.append({
                    "id": row.id,
                    "type": row.type,
                    "value": row.value,
                    "key": row.key,
                    "properties": json.loads(row.properties) if isinstance(row.properties, str) else row.properties
                })

            return jsonify({
                'success': True,
                'message': '获取节点成功',
                'status': 200,
                'data': {
                    'nodes': nodes,
                    'count': len(nodes),
                    'project_id': project_id
                }
            })

    except Exception as e:
        print(f"获取节点异常: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'获取节点失败: {str(e)}',
            'status': 500
        }), 500
    finally:
        engine.dispose()


@llmGenKG_bp.route('/delete_nodes_by_project', methods=['POST'])
def delete_nodes_by_project():
    """根据项目ID删除所有节点"""
    engine = None
    try:
        # 获取项目ID（支持两种方式）
        project_id = None

        # 方式1：从JSON body获取
        if request.is_json:
            data = request.get_json()
            project_id = data.get('project_id')
        # 方式2：从URL参数获取
        else:
            project_id = request.args.get('project_id')

        if not project_id:
            return jsonify({
                'success': False,
                'message': '项目ID不能为空',
                'status': 400
            }), 400

        engine = get_sqlalchemy_engine()
        with engine.connect() as connection:
            # 删除该项目所有节点
            delete_stmt = text("DELETE FROM node_table WHERE project_id = :project_id")
            result = connection.execute(delete_stmt, {"project_id": project_id})
            connection.commit()

            deleted_count = result.rowcount
            print(f"已删除项目 {project_id} 的 {deleted_count} 个节点")

            return jsonify({
                'success': True,
                'message': f'成功删除 {deleted_count} 个节点',
                'status': 200,
                'data': {
                    'deleted_count': deleted_count,
                    'project_id': project_id
                }
            })

    except Exception as e:
        print(f"删除节点异常: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'删除节点失败: {str(e)}',
            'status': 500
        }), 500
    finally:
        if engine is not None:
            engine.dispose()


# 关系抽取类型映射
RELATION_TYPES = {
    'causal': '因果关系',
    'temporal': '时序关系',
    'general': '通用关系'
}

# 关系抽取提示词模板
RELATION_PROMPTS = {
    'causal': """你是一个专业的金融关系抽取系统，专门分析上市公司公告中的因果关系。请严格按以下要求操作并以json格式返回结果：

1. 只分析以下节点之间的因果关系：
   - 原因 → 结果 (如: 业绩下滑 → 股价下跌)
   - 条件 → 后果 (如: 利率上升 → 融资成本增加)

2. 每种关系必须包含：
   - from: 原因/条件的节点ID
   - to: 结果/后果的节点ID
   - type: "因果关系"
   - value: 具体关系描述(如"导致","引发")
   - context：描述该关系的上下文内容（相关文本片段），必须抽出来

3. 返回json格式示例：
{
    "edges": [
        {
            "from": "节点1ID",
            "to": "节点2ID",
            "type": "因果关系",
            "value": "导致",
            "context": "相关文本片段（必须有），要体现因果关系的内容，尽量详细"
        }
    ]
}""",

    'temporal': """你是一个专业的金融关系抽取系统，专门分析上市公司公告中的时序关系。请严格按以下要求操作并以json格式返回结果：

1. 只分析以下节点之间的时序关系：
   - 前序事件 → 后续事件 (如: 董事会决议 → 股东大会审议)
   - 准备动作 → 主要动作 (如: 签署意向书 → 正式收购)

2. 每种关系必须包含：
   - from: 前序节点ID
   - to: 后续节点ID
   - type: "时序关系" 
   - value: 具体关系描述(如"之后","之前")
   - context：描述该关系的上下文内容（相关文本片段），必须抽出来

3. 返回json格式示例：
{
    "edges": [
        {
            "from": "节点1ID",
            "to": "节点2ID",
            "type": "时序关系",
            "value": "之后",
            "context": "相关文本片段（必须有），要体现时序关系的内容，尽量详细"
        }
    ]
}""",

    'general': """你是一个专业的金融关系抽取系统，分析上市公司公告中的各类关系。请严格按以下要求操作并以json格式返回结果：

    1. 主要分析以下关系类型：
       - 因果关系 (如: 业绩下滑 → 股价下跌)
       - 时序关系 (如: 董事会决议 → 股东大会审议)
       - 其他语义关系（需根据上下文智能判断具体类型）

    2. 每种关系必须包含：
       - from: 起始节点ID
       - to: 目标节点ID
       - type: 关系类型（优先使用"因果关系"/"时序关系"，其他情况应准确概括关系本质）
       - value: 具体关系描述动词/短语
       - context: 对关系本质的简要说明（必须有），如果因果关系，要突出因果上下文；如果是时序关系，要突出时序上下文；其他关系自己分析总结

    3. 关系类型判断原则：
       - 当存在明确因果逻辑时用"因果关系"
       - 当存在时间先后顺序时用"时序关系"
       - 其他情况应创造性地概括关系本质，例如：
         * "股权关系"（当涉及持股/控股时）
         * "协议关系"（当涉及合同/协议时）
         * "供应链关系"（当涉及上下游时）
         * "人事关系"（当涉及高管关联时）



    4. 返回json格式示例：
    {
        "edges": [
            {
                "from": "节点1ID",
                "to": "节点2ID",
                "type": "因果关系",
                "value": "促使",
                "context": "市场需求下降促使公司调整生产计划",
            },
            {
                "from": "节点3ID",
                "to": "节点4ID",
                "type": "供应链关系", 
                "value": "长期供货",
                "context": "与XX公司签订三年期原材料供货协议",
            }

        5. context字段必须从原始文本中提取包含from和to节点的实际语句片段
           - 最少30字，最多100字
           - 必须直接体现from和to节点的关系
           - 示例: 
             "context": "公司公告显示，由于[from节点值](业绩下滑)，导致[to节点值](股价下跌)超过5%"

        6. 如果找不到直接体现关系的文本，则:
           - 从文本中提取最接近from和to节点的语句组合
           - 添加说明: "根据公告内容推断"
           - 示例:
             "context": "根据公告内容推断: [from节点值](董事会决议)后，公司将进行[to节点值](股东大会审议)"
            ]
    }"""
}


def extract_relations_with_llm(nodes: list, relation_type: str, project_id: str, announcements: list) -> Dict:
    """使用DeepSeek API从节点和公告文本中抽取关系"""
    from openai import OpenAI

    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL
    )

    print(f"\n====== 开始{RELATION_TYPES[relation_type]}抽取 ======")
    print(f"待分析节点数量: {len(nodes)}")
    print(f"关系类型: {relation_type} ({RELATION_TYPES[relation_type]})")
    print(f"相关公告数量: {len(announcements)}")

    try:
        # 准备节点信息和公告文本供模型分析
        nodes_info = "\n".join([
            f"ID: {node['id']} | 类型: {'事件' if node['type'] == 1 else '实体'} | 值: {node['value']} | 键: {node['key']}"
            for node in nodes[:50]  # 限制数量防止过长
        ])

        # 合并相关公告内容（限制长度）
        combined_content = "\n\n".join([ann['content'][:1000] for ann in announcements[:3]])[:5000]

        print("\n[关系抽取] 准备发送给LLM的节点摘要:")
        print(nodes_info[:500] + "..." if len(nodes_info) > 500 else nodes_info)
        print("\n[关系抽取] 相关公告内容摘要:")
        print(combined_content[:500] + "..." if len(combined_content) > 500 else combined_content)

        print("\n[关系抽取] 正在调用DeepSeek API...")
        start_time = time.time()

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": RELATION_PROMPTS[relation_type]},
                {"role": "user",
                 "content": f"请分析以下节点之间的关系，并结合公告内容:\n\n节点信息:\n{nodes_info}\n\n相关公告内容:\n{combined_content}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2000
        )

        elapsed_time = time.time() - start_time
        print(f"[关系抽取] API调用完成，耗时: {elapsed_time:.2f}秒")

        result_str = response.choices[0].message.content
        json_str = (
            result_str.split('```json')[1].split('```')[0] if '```json' in result_str
            else result_str.split('```')[1].split('```')[0] if '```' in result_str
            else result_str
        )

        result = json.loads(json_str)

        if "edges" not in result:
            print("[关系抽取] 警告: 返回结果缺少edges字段")
            raise ValueError("返回结果缺少edges字段")

        print(f"\n[关系抽取] 初步抽取到 {len(result['edges'])} 条关系")

        # 创建节点ID到节点对象的映射
        nodes_map = {node['id']: node for node in nodes}

        # 处理返回的关系数据
        processed_edges = []
        for edge in result["edges"]:
            # 检查节点是否存在
            if edge['from'] not in nodes_map or edge['to'] not in nodes_map:
                print(f"[关系抽取] 警告: 跳过无效关系，节点不存在: {edge['from']} -> {edge['to']}")
                continue

            # 生成唯一ID
            edge_id = hashlib.md5(
                f"{edge['from']}_{edge['to']}_{edge['type']}_{edge['value']}".encode()
            ).hexdigest()

            # 构建完整的关系对象
            processed_edge = {
                "id": edge_id,
                "type": edge["type"],
                "from": edge["from"],
                "to": edge["to"],
                "from_node": nodes_map[edge["from"]],  # 添加完整源节点信息
                "to_node": nodes_map[edge["to"]],  # 添加完整目标节点信息
                "value": edge["value"],
                "eventRel": edge.get("eventRel", edge["value"]),
                "project_id": project_id,
                "properties": edge.get("properties", {})
            }

            # 确保properties是字典
            if isinstance(processed_edge["properties"], str):
                try:
                    processed_edge["properties"] = json.loads(processed_edge["properties"])
                except json.JSONDecodeError:
                    processed_edge["properties"] = {"raw": processed_edge["properties"]}

            processed_edge["properties"]["source"] = "LLM抽取"
            processed_edge["properties"]["extraction_method"] = relation_type
            processed_edge["properties"]["context"] = edge.get("context", "")

            processed_edges.append(processed_edge)

        # 打印部分关系示例
        print("\n[关系抽取] 处理后的关系示例(前3条):")
        for i, edge in enumerate(processed_edges[:3]):
            print(
                f"  {i + 1}. {edge['from_node']['value']} -> {edge['to_node']['value']} | 类型: {edge['type']} | 关系: {edge['value']}")

        return {"edges": processed_edges}

    except json.JSONDecodeError as e:
        print(f"[关系抽取] JSON解析失败: {e}\n原始响应: {result_str[:500]}...")
        return {"edges": []}
    except Exception as e:
        print(f"[关系抽取] API调用异常: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        return {"edges": []}


def get_announcements_by_project(project_id: str) -> list:
    """根据项目ID获取相关公告数据"""
    client = None
    cursor = None
    try:
        client = get_client()
        cursor = client.cursor()

        # 获取项目中的公告ID列表
        project_query = "SELECT data_list FROM cyydws.graph_project WHERE id = %s"
        cursor.execute(project_query, (project_id,))
        project_result = cursor.fetchone()

        if not project_result:
            return []

        id_list = []
        if project_result['data_list']:
            try:
                id_list = json.loads(project_result['data_list'])
                if not isinstance(id_list, list):
                    id_list = []
            except json.JSONDecodeError:
                id_list = []

        if not id_list:
            return []

        # 构建IN查询参数
        placeholders = ','.join(['%s'] * len(id_list))
        announcement_query = f"""
            SELECT id, title, content, date, stock_num 
            FROM cyydws.announce_data
            WHERE id IN ({placeholders})
            ORDER BY date DESC
            LIMIT 10  # 保持与原函数相同的限制
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

        return formatted_data

    except Exception as e:
        print(f"获取公告数据异常: {str(e)}")
        traceback.print_exc()
        return []
    finally:
        if cursor:
            cursor.close()
        if client:
            client.close()


def save_edges_to_databases(edges: list, project_id: str, relation_type: str = None):
    """将边(关系)保存到 MySQL 和 Neo4j"""
    # 保存到 MySQL
    mysql_success = save_edges_to_mysql(edges, project_id, relation_type)

    # 保存到 Neo4j
    neo4j_success = save_edges_to_neo4j(edges, project_id)

    return mysql_success and neo4j_success


def save_edges_to_mysql(edges: list, project_id: str, relation_type: str = None):
    """将边(关系)保存到 MySQL"""
    engine = get_sqlalchemy_engine()
    try:
        with engine.connect() as connection:
            # 根据关系类型决定删除策略
            if relation_type == 'general':
                # 通用关系抽取时删除所有关系
                delete_stmt = text("DELETE FROM edge_table WHERE project_id = :project_id")
                connection.execute(delete_stmt, {"project_id": project_id})
            elif relation_type:
                # 特定类型关系抽取时只删除该类型的关系
                delete_stmt = text("""
                    DELETE FROM edge_table 
                    WHERE project_id = :project_id AND properties->>'$.extraction_method' = :relation_type
                """)
                connection.execute(delete_stmt, {
                    "project_id": project_id,
                    "relation_type": relation_type
                })
            else:
                # 没有指定类型时删除所有关系
                delete_stmt = text("DELETE FROM edge_table WHERE project_id = :project_id")
                connection.execute(delete_stmt, {"project_id": project_id})

            connection.commit()

            # 插入新关系
            for edge in edges:
                # 确保properties包含extraction_method
                properties = edge.get("properties", {})
                if relation_type and 'extraction_method' not in properties:
                    properties['extraction_method'] = relation_type

                insert_stmt = text("""
                    INSERT INTO edge_table 
                    (id, type, `from`, `to`, eventRel, value, properties, project_id) 
                    VALUES 
                    (:id, :type, :from, :to, :eventRel, :value, :properties, :project_id)
                """)
                connection.execute(insert_stmt, {
                    "id": edge["id"],
                    "type": edge["type"],
                    "from": edge["from"],
                    "to": edge["to"],
                    "eventRel": edge["eventRel"],
                    "value": edge["value"],
                    "properties": json.dumps(properties),
                    "project_id": project_id
                })
            connection.commit()
        return True
    except Exception as e:
        print(f"保存关系到 MySQL 失败: {str(e)}")
        traceback.print_exc()
        return False
    finally:
        engine.dispose()


def save_edges_to_neo4j(edges: list, project_id: str):
    """将边(关系)保存到 Neo4j"""
    neo4j = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    try:
        # 第一步：删除项目中已有的数据
        print(f"[Neo4j] 开始清理项目 {project_id} 的旧数据...")

        # 删除关系
        delete_rels_query = """
            MATCH ()-[r]-()
            WHERE r.project_id = $project_id
            DELETE r
        """
        rels_deleted = neo4j.execute_query(delete_rels_query, {"project_id": project_id})
        print(f"[Neo4j] 已删除 {len(rels_deleted)} 条关系")

        # 删除节点
        delete_nodes_query = """
            MATCH (n:KnowledgeNode)
            WHERE n.project_id = $project_id
            DELETE n
        """
        nodes_deleted = neo4j.execute_query(delete_nodes_query, {"project_id": project_id})
        print(f"[Neo4j] 已删除 {len(nodes_deleted)} 个节点")

        # 第二步：获取所有节点
        print(f"[Neo4j] 准备导入新数据...")
        nodes = get_nodes_from_database(project_id)
        nodes_map = {node['id']: node for node in nodes}

        # 第三步：创建节点
        print(f"[Neo4j] 正在创建 {len(nodes)} 个节点...")
        print("node数据", nodes)
        for node in nodes:
            node_type = "事件" if node['type'] == '事件' else "实体"

            query = """
                MERGE (n:KnowledgeNode {id: $id})
                SET n.type = $type,
                    n.value = $value,
                    n.key = $key,
                    n.name = $value,  
                    n.project_id = $project_id,
                    n += $properties
            """
            neo4j.execute_query(query, {
                "id": node['id'],
                "type": node_type,
                "value": node['value'],
                "key": node['key'],
                "project_id": project_id,
                "properties": node.get('properties', {})
            })

        # 第四步：创建关系
        print(f"[Neo4j] 正在创建 {len(edges)} 条关系...")
        print("边的数据：", edges)
        for edge in edges:
            from_node = nodes_map.get(edge['from'])
            to_node = nodes_map.get(edge['to'])

            if not from_node or not to_node:
                print(f"[Neo4j] 警告: 跳过无效关系，节点不存在: {edge['from']} -> {edge['to']}")
                continue

            # 定义关系类型
            rel_type = edge['type'].replace("关系", "").upper()

            query = """
                MATCH (a:KnowledgeNode {id: $from_id})
                MATCH (b:KnowledgeNode {id: $to_id})
                MERGE (a)-[r:%s]->(b)
                SET r.value = $value,
                    r.eventRel = $eventRel,
                    r.project_id = $project_id,
                    r += $properties
            """ % rel_type

            neo4j.execute_query(query, {
                "from_id": edge['from'],
                "to_id": edge['to'],
                "value": edge['value'],
                "eventRel": edge['eventRel'],
                "project_id": project_id,
                "properties": edge.get('properties', {})
            })

        print("[Neo4j] 数据导入完成")
        return True
    except Exception as e:
        print(f"[Neo4j] 保存关系到 Neo4j 失败: {str(e)}")
        traceback.print_exc()
        return False
    finally:
        neo4j.close()


# 保留原有的关系抽取API
@llmGenKG_bp.route('/extract_relations', methods=['POST'])
def extract_relations_api():
    """关系抽取API（返回表格数据）"""
    try:
        # 确保请求包含 JSON 数据
        if not request.is_json:
            return jsonify({
                'success': False,
                'message': '请求必须包含 JSON 数据',
                'status': 400
            }), 400
        data = request.get_json()
        project_id = data.get('project_id')
        relation_type = data.get('relation_type', 'general')
        model_base = data.get('model_base', 'llm')

        if not project_id:
            print("[关系抽取API] 错误: 缺少项目ID")
            return jsonify({
                'success': False,
                'message': '项目ID不能为空',
                'status': 400
            }), 400

        print(f"\n=== 开始关系抽取流程 ===")
        print(f"项目ID: {project_id}")
        print(f"关系类型: {relation_type}")
        print(f"模型基础: {model_base}")

        # 获取项目节点
        print("\n[关系抽取API] 从数据库获取节点数据...")
        nodes = get_nodes_from_database(project_id)
        if not nodes:
            print(f"[关系抽取API] 错误: 未找到项目 {project_id} 的节点数据")
            return jsonify({
                'success': False,
                'message': f'未找到项目 {project_id} 的节点数据',
                'status': 404
            }), 404

        print(f"获取到 {len(nodes)} 个节点")

        # 获取相关公告数据
        print("\n[关系抽取API] 获取相关公告数据...")
        announcements = get_announcements_by_project(project_id)
        if not announcements:
            print(f"[关系抽取API] 警告: 未找到项目 {project_id} 的公告数据")
            announcements = []

        print(f"获取到 {len(announcements)} 条相关公告")

        # 抽取关系
        if model_base == 'llm':
            print("\n[关系抽取API] 开始使用LLM抽取关系...")
            extraction_result = extract_relations_with_llm(nodes, relation_type, project_id, announcements)
        else:
            print("\n[关系抽取API] 使用非LLM方法抽取关系")
            extraction_result = {"edges": []}

        edges = extraction_result.get("edges", [])
        print(f"\n[关系抽取API] 抽取完成，共获得 {len(edges)} 条关系")

        # 准备返回给前端的数据（包含完整节点信息）
        frontend_edges = []
        for edge in edges:
            frontend_edge = {
                "id": edge["id"],
                "type": edge["type"],
                "from": edge["from"],
                "to": edge["to"],
                "from_node": {
                    "id": edge["from_node"]["id"],
                    "type": edge["from_node"]["type"],
                    "value": edge["from_node"]["value"],
                    "key": edge["from_node"]["key"]
                },
                "to_node": {
                    "id": edge["to_node"]["id"],
                    "type": edge["to_node"]["type"],
                    "value": edge["to_node"]["value"],
                    "key": edge["to_node"]["key"]
                },
                "value": edge["value"],
                "eventRel": edge["eventRel"],
                "properties": edge["properties"]
            }
            frontend_edges.append(frontend_edge)

        # 保存关系到数据库（MySQL 和 Neo4j）
        if edges:
            print("[关系抽取API] 正在保存关系到数据库...")
            save_success = save_edges_to_databases(edges, project_id, relation_type)
            if not save_success:
                print("[关系抽取API] 错误: 保存关系到数据库失败")
                return jsonify({
                    'success': False,
                    'message': '保存关系到数据库失败',
                    'status': 500
                }), 500
            print("[关系抽取API] 关系保存成功")

        return jsonify({
            'success': True,
            'message': '关系抽取完成',
            'status': 200,
            'data': {
                'edges': frontend_edges,  # 返回给前端的数据包含完整节点信息
                'count': len(frontend_edges),
                'project_id': project_id
            }
        })

    except Exception as e:
        print(f"\n[关系抽取API] 异常: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'关系抽取失败: {str(e)}',
            'status': 500
        }), 500


@llmGenKG_bp.route('/delete_edges_by_project', methods=['POST'])
def delete_edges_by_project():
    """根据项目ID删除所有关系（MySQL 和 Neo4j）"""
    engine = None
    try:
        # 获取项目ID（支持两种方式）
        project_id = None

        # 方式1：从JSON body获取
        if request.is_json:
            data = request.get_json()
            project_id = data.get('project_id')
        # 方式2：从URL参数获取
        else:
            project_id = request.args.get('project_id')

        if not project_id:
            return jsonify({
                'success': False,
                'message': '项目ID不能为空',
                'status': 400
            }), 400

        # 删除 MySQL 中的关系
        engine = get_sqlalchemy_engine()
        with engine.connect() as connection:
            # 删除该项目所有关系
            delete_stmt = text("DELETE FROM edge_table WHERE project_id = :project_id")
            result = connection.execute(delete_stmt, {"project_id": project_id})
            connection.commit()

            deleted_count = result.rowcount
            print(f"已删除项目 {project_id} 的 {deleted_count} 条 MySQL 关系")

        # 删除 Neo4j 中的关系
        neo4j_success = delete_neo4j_project_data(project_id)
        if not neo4j_success:
            raise Exception("删除 Neo4j 数据失败")

        return jsonify({
            'success': True,
            'message': f'成功删除 {deleted_count} 条关系',
            'status': 200,
            'data': {
                'deleted_count': deleted_count,
                'project_id': project_id
            }
        })

    except Exception as e:
        print(f"删除关系异常: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'删除关系失败: {str(e)}',
            'status': 500
        }), 500
    finally:
        if engine is not None:
            engine.dispose()


def delete_neo4j_project_data(project_id: str):
    """删除 Neo4j 中指定项目的所有数据"""
    neo4j = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    try:
        # 删除关系
        query = """
            MATCH ()-[r]-()
            WHERE r.project_id = $project_id
            DELETE r
        """
        neo4j.execute_query(query, {"project_id": project_id})

        # 删除节点
        query = """
            MATCH (n:KnowledgeNode)
            WHERE n.project_id = $project_id
            DELETE n
        """
        neo4j.execute_query(query, {"project_id": project_id})

        return True
    except Exception as e:
        print(f"删除 Neo4j 项目数据失败: {str(e)}")
        return False
    finally:
        neo4j.close()


@llmGenKG_bp.route('/get_neo4j_graph', methods=['GET'])
def get_neo4j_graph():
    """从 Neo4j 获取图谱数据"""
    try:
        project_id = request.args.get('project_id')
        if not project_id:
            return jsonify({
                'success': False,
                'message': '项目ID不能为空',
                'status': 400
            }), 400

        neo4j = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

        # 查询节点
        nodes_query = """
            MATCH (n:KnowledgeNode)
            WHERE n.project_id = $project_id
            RETURN n
        """
        nodes = neo4j.execute_query(nodes_query, {"project_id": project_id})

        # 查询关系
        edges_query = """
            MATCH (a)-[r]->(b)
            WHERE r.project_id = $project_id
            RETURN a, r, b
        """
        edges = neo4j.execute_query(edges_query, {"project_id": project_id})

        # 格式化结果
        formatted_nodes = []
        for record in nodes:
            node = record['n']
            formatted_nodes.append({
                "id": node["id"],
                "type": node["type"],
                "value": node["value"],
                "key": node["key"],
                "properties": dict(node)
            })

        formatted_edges = []
        for record in edges:
            a = record['a']
            r = record['r']
            b = record['b']
            formatted_edges.append({
                "from": a["id"],
                "to": b["id"],
                "type": type(r).__name__,
                "value": r["value"],
                "eventRel": r["eventRel"],
                "properties": dict(r)
            })

        return jsonify({
            'success': True,
            'message': '获取 Neo4j 图谱数据成功',
            'status': 200,
            'data': {
                'nodes': formatted_nodes,
                'edges': formatted_edges,
                'project_id': project_id
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取 Neo4j 图谱数据失败: {str(e)}',
            'status': 500
        }), 500
    finally:
        neo4j.close()


def get_nodes_from_database(project_id: str) -> list:
    """从数据库获取节点数据"""
    engine = get_sqlalchemy_engine()
    try:
        with engine.connect() as connection:
            query = text("""
                SELECT id, type, value, `key`, properties 
                FROM node_table 
                WHERE project_id = :project_id
            """)
            result = connection.execute(query, {"project_id": project_id})
            return [
                {
                    "id": row.id,
                    "type": row.type,
                    "value": row.value,
                    "key": row.key,
                    "properties": json.loads(row.properties) if isinstance(row.properties, str) else row.properties
                }
                for row in result
            ]
    except Exception as e:
        print(f"获取节点数据异常: {str(e)}")
        return []
    finally:
        engine.dispose()


@llmGenKG_bp.route('/get_edges_by_project', methods=['GET'])
def get_edges_by_project():
    """根据项目ID获取所有关系（包含完整节点信息）"""
    try:
        project_id = request.args.get('project_id')
        if not project_id:
            return jsonify({
                'success': False,
                'message': '项目ID不能为空',
                'status': 400
            }), 400

        # 获取节点数据
        nodes = get_nodes_from_database(project_id)
        nodes_map = {node['id']: node for node in nodes}

        # 获取边数据
        edges = []
        engine = get_sqlalchemy_engine()
        with engine.connect() as connection:
            query = text("""
                SELECT id, type, `from` as from_, `to`, eventRel, value, properties 
                FROM edge_table 
                WHERE project_id = :project_id
            """)
            result = connection.execute(query, {"project_id": project_id})

            for row in result:
                from_node = nodes_map.get(row.from_)
                to_node = nodes_map.get(row.to)

                if not from_node or not to_node:
                    continue  # 跳过无效关系

                edges.append({
                    "id": row.id,
                    "type": row.type,
                    "from": row.from_,
                    "to": row.to,
                    "from_node": {
                        "id": from_node["id"],
                        "type": from_node["type"],
                        "value": from_node["value"],
                        "key": from_node["key"]
                    },
                    "to_node": {
                        "id": to_node["id"],
                        "type": to_node["type"],
                        "value": to_node["value"],
                        "key": to_node["key"]
                    },
                    "value": row.value,
                    "eventRel": row.eventRel,
                    "properties": json.loads(row.properties) if isinstance(row.properties, str) else row.properties
                })

        return jsonify({
            'success': True,
            'message': '获取关系成功',
            'status': 200,
            'data': {
                'edges': edges,
                'count': len(edges),
                'project_id': project_id
            }
        })

    except Exception as e:
        print(f"获取关系异常: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'获取关系失败: {str(e)}',
            'status': 500
        }), 500
    finally:
        engine.dispose()


@llmGenKG_bp.route('/check_extraction_status', methods=['POST'])
def check_extraction_status():
    try:
        # 从请求体中获取project_id
        project_id = request.json.get('project_id')  # 修改点
        print("检查阶段的project_id：", project_id)
        if not project_id:
            return jsonify({'success': False, 'message': '项目ID不能为空'}), 400

        # 检查节点状态
        engine = get_sqlalchemy_engine()
        with engine.connect() as conn:
            # 检查节点
            node_query = text("SELECT COUNT(*) FROM node_table WHERE project_id = :project_id")
            node_count = conn.execute(node_query, {"project_id": project_id}).scalar()

            # 检查关系
            edge_query = text("SELECT COUNT(*) FROM edge_table WHERE project_id = :project_id")
            edge_count = conn.execute(edge_query, {"project_id": project_id}).scalar()

            print("node_count:", node_count)
            print("edge_count:", edge_count)

        return jsonify({
            'success': True,
            'has_nodes': node_count > 0,
            'has_edges': edge_count > 0,
            "status": 200,
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'检查状态失败: {str(e)}'
        }), 500