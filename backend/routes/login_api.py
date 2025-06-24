import base64
import bcrypt
import jwt
import random
import string
import time
from captcha.image import ImageCaptcha
from datetime import datetime, timedelta
from database import get_client
from flask import Blueprint, request, jsonify
from io import BytesIO

# 定义 Blueprint
login_bp = Blueprint('login', __name__)

# 配置项
CAPTCHA_EXPIRE_TIME = 300  # 验证码有效期5分钟
TOKEN_EXPIRE_HOURS = 2  # token有效期2小时
SECRET_KEY = "your_secure_secret_key_here"  # 生产环境应从环境变量获取

# 内存存储验证码（生产环境应使用Redis）
captcha_store = {}


# 生成随机验证码
def generate_captcha(length=4):
    """生成数字验证码"""
    return ''.join(random.choices(string.digits, k=length))


# 生成SVG验证码图片
def generate_captcha_image(captcha_text):
    """生成验证码图片并返回 base64 编码字符串"""
    image = ImageCaptcha(width=160, height=60, fonts=None, font_sizes=[42])  # 高度更大，字体更合适
    captcha_image = image.generate_image(captcha_text)

    # 转换为 base64 字符串
    buffered = BytesIO()
    captcha_image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    # 返回完整的 data URI
    return f"data:image/png;base64,{img_base64}"


# 获取验证码接口
@login_bp.route('/public/captcha', methods=['GET'])
def get_captcha():
    try:
        # 生成验证码
        captcha_text = generate_captcha()
        captcha_id = str(int(time.time()))  # 使用时间戳作为ID

        # 存储验证码
        captcha_store[captcha_id] = {
            'text': captcha_text,
            'expire': time.time() + CAPTCHA_EXPIRE_TIME
        }

        # 生成SVG图片
        svg_image = generate_captcha_image(captcha_text)

        print(f"[验证码] ID: {captcha_id}, 文本: {captcha_text}")

        response = jsonify({
            'status': 200,
            'message': 'success',
            'data': {
                'id': captcha_id,
                'svg': svg_image
            }
        })

        # 添加缓存控制头
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        print(f"[验证码生成错误] {str(e)}")
        return jsonify({
            'status': 500,
            'message': '验证码生成失败'
        }), 500


# 用户登录接口
@login_bp.route('/public/login', methods=['POST'])
def login():
    # 获取请求数据
    data = request.get_json()
    if not data:
        return jsonify({'status': 400, 'message': '请求数据必须为JSON格式'}), 400

    print("data")
    print(data)

    # 验证必填字段
    required_fields = ['name', 'password', 'captchaText', 'captchaId']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'status': 400, 'message': f'缺少必要参数: {field}'}), 400

    username = data['name'].strip()
    password = data['password'].strip()
    captcha_text = data['captchaText'].strip()
    captcha_id = data['captchaId']

    # 验证验证码
    if captcha_id not in captcha_store:
        return jsonify({'status': 400, 'message': '验证码已过期，请刷新重试'}), 400

    stored_captcha = captcha_store[captcha_id]

    if time.time() > stored_captcha['expire']:
        captcha_store.pop(captcha_id, None)
        return jsonify({'status': 400, 'message': '验证码已过期，请刷新重试'}), 400

    if captcha_text.lower() != stored_captcha['text'].lower():
        captcha_store.pop(captcha_id, None)
        return jsonify({'status': 400, 'message': '验证码错误'}), 400

    captcha_store.pop(captcha_id, None)  # 验证通过后删除验证码

    # 查询数据库验证用户
    client = get_client()
    try:
        with client.cursor() as cursor:
            sql = """
            SELECT id, user_name, password 
            FROM user_data 
            WHERE user_name = %s
            LIMIT 1
            """
            cursor.execute(sql, (username,))
            result = cursor.fetchone()

        if not result:
            return jsonify({'status': 404, 'message': '用户不存在或已被禁用'}), 404

        user_id = result['id']
        db_username = result['user_name']
        db_password = result['password']

        # 使用 bcrypt 验证密码
        if not verify_password(password, db_password):
            return jsonify({'status': 401, 'message': '用户名或密码错误'}), 401

        # 生成 JWT Token
        token_payload = {
            'user_id': user_id,
            'username': db_username,
            'exp': datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
        }
        token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256")

        return jsonify({
            'status': 200,
            'message': '登录成功',
            'data': {
                'token': token,
                'user': {
                    'id': user_id,
                    'username': db_username
                },
                'expires_in': TOKEN_EXPIRE_HOURS * 3600
            }
        })

    except Exception as e:
        print(f"[登录错误] {str(e)}")
        return jsonify({'status': 500, 'message': '服务器内部错误'}), 500


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(raw_password.encode('utf-8'), hashed_password.encode('utf-8'))