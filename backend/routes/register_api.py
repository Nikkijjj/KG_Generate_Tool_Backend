from flask import Blueprint, request, jsonify
from extensions import mail, r
from flask_mail import Message
import random
from datetime import datetime
from database import get_client
import bcrypt

register_bp = Blueprint('register', __name__)


@register_bp.route('/public/send_code', methods=['POST'])
def send_code():
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({'status': 400, 'msg': '邮箱不能为空'})
    if isinstance(email, dict):
        email = list(email.values())[0]

    # 生成 6 位验证码
    code = ''.join(random.choices('0123456789', k=6))
    r.setex(f'verify:{email}', 300, code)

    try:
        msg = Message(
            subject='【图谱平台】邮箱验证码',
            recipients=[email],
            body=f'您的验证码是：{code}，5分钟内有效。'
        )
        mail.send(msg)
        return jsonify({'status': 200, 'msg': '验证码发送成功'})
    except Exception as e:
        print(f'邮件发送失败: {e}')
        return jsonify({'status': 500, 'msg': '发送失败，请稍后重试'})


@register_bp.route('/public/register', methods=['POST'])
def register():
    data = request.get_json()
    print(data)
    name = data.get('name')
    password = data.get('password')
    email = data.get('email')
    emailCode = data.get('emailCode')

    # 验证邮箱验证码
    saved_code = r.get(f'verify:{email}')
    if not saved_code or saved_code != emailCode:
        return jsonify({'status': 400, 'msg': '邮箱验证码错误或已过期'}), 400

    try:
        conn = get_client()
        cursor = conn.cursor()

        # 计算新 id
        cursor.execute("SELECT COUNT(*) AS cnt FROM user_data")
        count = cursor.fetchone()['cnt']
        new_id = count + 1

        # 加密密码
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # 时间格式
        create_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 插入用户数据
        insert_sql = """
        INSERT INTO user_data (id, user_name, password, email, create_time)
        VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(insert_sql, (new_id, name, hashed_password, email, create_time))
        conn.commit()

        cursor.close()
        conn.close()

        # 删除验证码
        r.delete(f'verify:{email}')

        return jsonify({'status': 200, 'msg': '注册成功'})

    except Exception as e:
        print(f"注册失败: {e}")
        if conn:
            conn.rollback()
            cursor.close()
            conn.close()
        return jsonify({'status': 500, 'msg': '注册失败，请稍后重试'}), 500
