import clickhouse_connect

def get_client():
    """ 获取 ClickHouse 客户端 """
    return clickhouse_connect.get_client(
        host='192.168.3.109',
        #host='172.26.159.215',
        port=8123,
        username='jjy',
        password='123456'
    )
