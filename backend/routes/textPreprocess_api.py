import time
from flask import Blueprint, jsonify, request
from database import get_client
from datetime import datetime

textPreprocess_bp = Blueprint('textPreprocess', __name__)  # 创建 Blueprint


def get_data_from_db(page=1, page_size=12):
    """ 从数据库获取数据（服务端分页） """
    try:
        client = get_client()
        offset = (page - 1) * page_size

        with client.cursor() as cursor:
            # 1. 查询分页数据 - 将参数直接拼接到SQL中
            query_data = f'''
                SELECT id, title, content, stock_num, date
                FROM announce_data
                LIMIT {page_size} OFFSET {offset}
            '''
            cursor.execute(query_data)
            result_data = cursor.fetchall()

            # 2. 查询总数据量
            query_total = 'SELECT COUNT(*) FROM announce_data'
            cursor.execute(query_total)
            total = cursor.fetchone()['COUNT(*)'] if cursor.rowcount else 0

            # 格式化数据
            data = [
                {
                    "id": row['id'],
                    "title": row['title'],
                    "content": row['content'],
                    "stock_num": row['stock_num'],
                    "date": str(row['date']) if row['date'] else None
                }
                for row in result_data
            ]

            return {
                "data": data,
                "total": total
            }

    except Exception as e:
        print(f'Error fetching data from database: {e}')
        return {"data": [], "total": 0}
    finally:
        client.close()



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
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "msg": "请求数据不能为空", "status": 400})

        ids = data.get('ids', [])
        if not ids or not isinstance(ids, list):
            return jsonify({"success": False, "msg": "ids 必须是非空数组", "status": 400})

        client = get_client()

    #     # 方法1：创建临时表并重新插入需要保留的数据
    #     temp_table = f"temp_{int(time.time())}"
    #
    #     # 1. 创建临时表
    #     client.command(f"""
    #         CREATE TABLE {temp_table} AS cyydws.announce_data
    #         ENGINE = MergeTree()
    #         ORDER BY id
    #     """)
    #
    #     # 2. 插入需要保留的数据
    #     id_list = ",".join([f"'{id}'" for id in ids])
    #     client.command(f"""
    #         INSERT INTO {temp_table}
    #         SELECT * FROM cyydws.announce_data
    #         WHERE id NOT IN ({id_list})
    #     """)
    #
    #     # 3. 删除原表并重命名临时表
    #     client.command("DROP TABLE cyydws.announce_data")
    #     client.command(f"RENAME TABLE {temp_table} TO cyydws.announce_data")
    #
    #     return jsonify({
    #         "success": True,
    #         "status": 200,
    #         "msg": f"成功删除 {len(ids)} 条数据",
    #         "deleted_count": len(ids)
    #     })
    #
    # except Exception as e:
    #     print(f"删除数据异常: {str(e)}", exc_info=True)
    #     return jsonify({
    #         "success": False,
    #         "msg": f"删除失败: {str(e)}",
    #         "status": 500
    #     })

        with client.cursor() as cursor:
            # MySQL 使用简单的 DELETE 语句
            placeholders = ','.join(['%s'] * len(ids))
            delete_query = f"DELETE FROM announce_data WHERE id IN ({placeholders})"
            cursor.execute(delete_query, ids)
            client.commit()

            deleted_count = cursor.rowcount

        return jsonify({
            "success": True,
            "status": 200,
            "msg": f"成功删除 {deleted_count} 条数据",
            "deleted_count": deleted_count
        })

    except Exception as e:
        print(f"删除数据异常: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "msg": f"删除失败: {str(e)}",
            "status": 500
        })


@textPreprocess_bp.route('/textPreprocess_api/search', methods=['POST'])
def search_data():
    try:
        # 获取请求参数
        params = request.get_json()
        keyword = params.get('keyword', '').strip()
        page = int(params.get('page', 1))
        page_size = int(params.get('page_size', 12))

        if not keyword:
            # 如果关键词为空，返回全部数据
            result = get_data_from_db(page=page, page_size=page_size)
            return jsonify({
                "data": result["data"],
                "total": result["total"],
                "status": 200
            })

        # 执行搜索
        client = get_client()
        offset = (page - 1) * page_size
        search_keyword = f'%{keyword}%'

        with client.cursor() as cursor:
            # 1. 查询分页数据
            query_data = '''
                        SELECT id, title, content, stock_num, date
                        FROM announce_data
                        WHERE stock_num LIKE %s OR title LIKE %s OR content LIKE %s
                        LIMIT %s OFFSET %s
                    '''
            cursor.execute(query_data, (search_keyword, search_keyword, search_keyword, page_size, offset))
            result_data = cursor.fetchall()

            # 2. 查询总数据量
            query_total = '''
                        SELECT COUNT(*) 
                        FROM announce_data
                        WHERE stock_num LIKE %s OR title LIKE %s OR content LIKE %s
                    '''
            cursor.execute(query_total, (search_keyword, search_keyword, search_keyword))
            total = cursor.fetchone()['COUNT(*)']

            # 格式化数据
            data = [
                {
                    "id": row['id'],
                    "title": row['title'],
                    "content": row['content'],
                    "stock_num": row['stock_num'],
                    "date": str(row['date']) if row['date'] else None,
                }
                for row in result_data
            ]

        return jsonify({
            "data": data,
            "total": total,
            "status": 200
        })

    except Exception as e:
        print(f'Error searching data: {e}')
        return jsonify({
            'status': 500,
            "message": str(e),
            "data": []
        }), 500


@textPreprocess_bp.route('/textPreprocess_api/addAnnouncement', methods=['POST'])
def add_announcement():
    try:
        # 1. 获取并验证请求数据
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "msg": "请求数据不能为空", "status": 400})

        title = data.get('title', '').strip()
        content = data.get('content', '').strip()

        if not title or not content:
            return jsonify({"success": False, "msg": "标题和内容不能为空", "status": 400})

        # 2. 准备插入数据
        announcement_id = data.get('id') or f"ann_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        date_str = data.get('date')
        stock_num = data.get('stock_num', '未知')

        # 3. 获取数据库连接
        client = get_client()

        # # 4. 修改插入语句，使用 parseDateTimeBestEffort 或 toDate 函数
        # insert_query = """
        # INSERT INTO cyydws.announce_data
        # (id, title, content, stock_num, date)
        # VALUES (%(id)s, %(title)s, %(content)s, %(stock_num)s, %(date)s)
        # """
        #
        # client.command(insert_query, {
        #     'id': announcement_id,
        #     'title': title,
        #     'content': content,
        #     'stock_num': stock_num,
        #     'date': date_str if date_str else datetime.now().strftime('%Y-%m-%d')
        # })

        with client.cursor() as cursor:
            insert_query = """
            INSERT INTO announce_data 
            (id, title, content, stock_num, date)
            VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (
                announcement_id,
                title,
                content,
                stock_num,
                date_str if date_str else datetime.now().strftime('%Y-%m-%d')
            ))
            client.commit()

        return jsonify({
            "success": True,
            "status": 200,
            "msg": "公告添加成功",
            "data": {
                "id": announcement_id,
                "title": title,
                "date": date_str
            }
        })

    except Exception as e:
        # 修复 print 错误
        print(f"添加公告失败: {str(e)}")
        import traceback
        traceback.print_exc()  # 打印完整的堆栈跟踪

        return jsonify({
            "success": False,
            "msg": f"添加公告失败: {str(e)}",
            "status": 500
        })



# @textPreprocess_bp.route('/textPreprocess_api/updateAnnouncement', methods=['POST'])
# def update_announcement():
#     try:
#         # 1. 获取并验证请求数据
#         data = request.get_json()
#         if not data:
#             return jsonify({"success": False, "msg": "请求数据不能为空", "status": 400})
#
#         announcement_id = data.get('id')
#         if not announcement_id:
#             return jsonify({"success": False, "msg": "公告ID不能为空", "status": 400})
#
#         title = data.get('title', '').strip()
#         content = data.get('content', '').strip()
#         if not title or not content:
#             return jsonify({"success": False, "msg": "标题和内容不能为空", "status": 400})
#
#         # 2. 准备更新数据
#         date_str = data.get('date')
#         stock_num = data.get('stock_num', '未知')
#
#         # 3. 获取数据库连接
#         client = get_client()
#
#         # 4. 检查公告是否存在
#         check_query = "SELECT id FROM cyydws.announce_data WHERE id = %(id)s"
#         check_result = client.query(check_query, {'id': announcement_id})
#         if not check_result.result_rows:
#             return jsonify({"success": False, "msg": "公告不存在", "status": 404})
#
#         # 5. 执行更新
#         update_query = """
#         ALTER TABLE cyydws.announce_data
#         UPDATE
#             title = %(title)s,
#             content = %(content)s,
#             stock_num = %(stock_num)s,
#             date = parseDateTimeBestEffort(%(date)s)
#         WHERE id = %(id)s
#         """
#
#         client.command(update_query, {
#             'id': announcement_id,
#             'title': title,
#             'content': content,
#             'stock_num': stock_num,
#             'date': date_str if date_str else datetime.now().strftime('%Y-%m-%d')
#         })
#
#         return jsonify({
#             "success": True,
#             "status": 200,
#             "msg": "公告更新成功",
#             "data": {
#                 "id": announcement_id,
#                 "title": title,
#                 "date": date_str
#             }
#         })
#
#     except Exception as e:
#         print(f"更新公告失败: {str(e)}")
#         import traceback
#         traceback.print_exc()
#
#         return jsonify({
#             "success": False,
#             "msg": f"更新公告失败: {str(e)}",
#             "status": 500
#         })

@textPreprocess_bp.route('/textPreprocess_api/updateAnnouncement', methods=['POST'])
def update_announcement():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "msg": "请求数据不能为空", "status": 400})

        announcement_id = data.get('id')
        if not announcement_id:
            return jsonify({"success": False, "msg": "公告ID不能为空", "status": 400})

        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        if not title or not content:
            return jsonify({"success": False, "msg": "标题和内容不能为空", "status": 400})

        date_str = data.get('date')
        stock_num = data.get('stock_num', '未知')

        client = get_client()
        with client.cursor() as cursor:
            # 检查公告是否存在
            check_query = "SELECT id FROM announce_data WHERE id = %s"
            cursor.execute(check_query, (announcement_id,))
            if not cursor.fetchone():
                return jsonify({"success": False, "msg": "公告不存在", "status": 404})

            # 执行更新
            update_query = """
            UPDATE announce_data 
            SET 
                title = %s,
                content = %s,
                stock_num = %s,
                date = %s
            WHERE id = %s
            """
            cursor.execute(update_query, (
                title,
                content,
                stock_num,
                date_str if date_str else datetime.now().strftime('%Y-%m-%d'),
                announcement_id
            ))
            client.commit()

        return jsonify({
            "success": True,
            "status": 200,
            "msg": "公告更新成功",
            "data": {
                "id": announcement_id,
                "title": title,
                "date": date_str
            }
        })

    except Exception as e:
        print(f"更新公告失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "msg": f"更新公告失败: {str(e)}",
            "status": 500
        })


@textPreprocess_bp.route('/textPreprocess_api/uploadAnnouncements', methods=['POST'])
def upload_announcements():
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "msg": "没有上传文件", "status": 400})

        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "msg": "没有选择文件", "status": 400})

        file_type = request.form.get('fileType', 'csv')
        delimiter = request.form.get('delimiter', ',')

        announcements = []
        if file_type == 'csv':
            import csv
            from io import StringIO

            content = file.read().decode('utf-8')
            reader = csv.reader(StringIO(content), delimiter=delimiter)
            headers = next(reader, [])

            required_fields = ['title', 'content']
            for field in required_fields:
                if field not in headers:
                    return jsonify({
                        "success": False,
                        "msg": f"CSV文件缺少必要字段: {field}",
                        "status": 400
                    })

            for row in reader:
                if len(row) != len(headers):
                    continue

                announcement = dict(zip(headers, row))

                # 处理日期字段
                if 'date' in announcement and announcement['date']:
                    import re
                    if not re.match(r'^\d{4}-\d{2}-\d{2}$', announcement['date']):
                        try:
                            dt = datetime.strptime(announcement['date'], '%Y/%m/%d')
                            announcement['date'] = dt.strftime('%Y-%m-%d')
                        except ValueError:
                            announcement['date'] = datetime.now().strftime('%Y-%m-%d')
                else:
                    announcement['date'] = datetime.now().strftime('%Y-%m-%d')

                announcement['id'] = announcement.get('id') or f"ann_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(announcements)}"
                announcement['stock_num'] = announcement.get('stock_num') or '未知'

                announcements.append(announcement)

        elif file_type == 'txt':
            content = file.read().decode('utf-8')
            entries = content.split('\n\n')

            for entry in entries:
                if not entry.strip():
                    continue

                announcement = {
                    'id': f"ann_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(announcements)}",
                    'title': '无标题公告',
                    'content': '',
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'stock_num': '未知'
                }

                lines = entry.split('\n')
                for line in lines:
                    if line.startswith('公告标题：'):
                        announcement['title'] = line.replace('公告标题：', '').strip()
                    elif line.startswith('公告内容：'):
                        announcement['content'] = line.replace('公告内容：', '').strip()
                    elif line.startswith('发布时间：'):
                        date_str = line.replace('发布时间：', '').strip()
                        import re
                        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                            announcement['date'] = date_str
                        else:
                            try:
                                dt = datetime.strptime(date_str, '%Y/%m/%d')
                                announcement['date'] = dt.strftime('%Y-%m-%d')
                            except ValueError:
                                announcement['date'] = datetime.now().strftime('%Y-%m-%d')
                    elif line.startswith('股票代码：'):
                        announcement['stock_num'] = line.replace('股票代码：', '').strip()

                announcements.append(announcement)

        if announcements:
            client = get_client()

            try:
                with client.cursor() as cursor:
                    values = []
                    for ann in announcements:
                        values.append((
                            ann['id'],
                            ann['title'],
                            ann['content'],
                            ann['stock_num'],
                            ann['date']
                        ))

                    insert_query = """
                    INSERT INTO announce_data 
                    (id, title, content, stock_num, date)
                    VALUES (%s, %s, %s, %s, %s)
                    """
                    cursor.executemany(insert_query, values)
                    client.commit()

                return jsonify({
                    "success": True,
                    "msg": f"成功导入 {len(announcements)} 条公告数据",
                    "count": len(announcements),
                    "status": 200
                })

            except Exception as e:
                client.rollback()
                raise e

            finally:
                client.close()

        else:
            return jsonify({
                "success": False,
                "msg": "文件中没有有效的公告数据",
                "status": 400
            })

    except Exception as e:
        print(f"上传公告文件失败: {str(e)}")
        import traceback
        traceback.print_exc()

        return jsonify({
            "success": False,
            "msg": f"上传失败: {str(e)}",
            "status": 500
        })
