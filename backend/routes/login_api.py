from flask import Blueprint, request, jsonify
import jwt
import datetime
from database import get_client

# 定义 Blueprint
login_bp = Blueprint('login', __name__)

# **获取验证码接口**
@login_bp.route('/api/captcha', methods=['GET'])
def get_captcha():
    # 直接返回一个固定的验证码
    captcha = "1184"

    return jsonify({
        'id': "captcha_id_123",  # 假设验证码 ID 为一个固定值
        'svg': f"<svg>验证码图片 {captcha}</svg>"  # 这里简单返回文本，实际中应返回验证码图片
    })

# **用户登录接口**
@login_bp.route('/api/login', methods=['POST'])
def login():
    data = request.json  # 获取前端发送的数据
    username = data.get('name')
    password = data.get('password')
    captcha = data.get('captchaText')  # 用户输入的验证码
    captcha_id = data.get('captchaId')  # 验证码 ID

    # 验证参数是否为空
    if not username or not password or not captcha or not captcha_id:
        return jsonify({'error': '缺少必填项'}), 400

    # 校验验证码（此处假设验证码始终为 "1184"）
    if captcha != "1184":
        return jsonify({'error': '验证码错误'}), 400

    # 校验数据库中是否存在该用户
    client = get_client()  # 连接数据库
    query = "SELECT id, user_name, password FROM cyydws.user_data WHERE user_name = %(username)s"
    params = {'username': username}

    result = client.query(query, params)  # 查询用户信息
    user = result.result_rows

    if not user:
        return jsonify({'error': '用户不存在'}), 404

    user_id, db_username, db_password = user[0]

    # 密码校验
    if password != db_password:
        return jsonify({'error': '密码错误'}), 401

    # 生成 JWT Token
    token_payload = {
        'user_id': user_id,
        'username': db_username,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)  # 过期时间 2 小时
    }
    token = jwt.encode(token_payload, "secret_key", algorithm="HS256")  # 使用你的 secret_key

    return jsonify({'message': '登录成功', 'token': token, 'user': {'id': user_id, 'username': db_username}}), 200
