# import clickhouse_connect
#
# def get_client():
#     """ 获取 ClickHouse 客户端 """
#     return clickhouse_connect.get_client(
#         host='192.168.3.111',
#         #host='172.26.159.215',
#         port=3306,
#         username='jhy',
#         password='123456'
#     )

import pymysql
from pymysql.cursors import DictCursor

def get_client():
    """
    获取 MySQL 数据库连接
    """
    connection = pymysql.connect(
        host='192.168.3.111',      # MySQL 服务器地址
        user='jhy',  # 用户名
        password='123456',  # 密码
        database='cyydws',     # 数据库名
        charset='utf8mb4',     # 字符集
        cursorclass=DictCursor # 返回字典格式结果
    )
    return connection
